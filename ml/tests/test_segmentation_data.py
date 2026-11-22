import io
import zipfile

import cv2
import numpy as np
import pytest

from skincare_ml.faces import Face
from skincare_ml.segmentation_data import (
    REGIONS,
    decode_memi_mask,
    kept_at_size,
    known_dark_spots,
    line_width,
    load_sample,
    patches,
    relative_spread,
    share_inside,
    unet_crop_box,
)


def test_memi_colours_become_dark_spots_and_region_ids():
    mask = np.zeros((4, 4, 3), np.uint8)
    mask[0, 0] = (0, 0, 128)  # forehead (BGR)
    mask[3, 3] = (128, 128, 0)  # right cheek
    mask[1, 1] = (10, 10, 10)  # not a region colour: ignored

    dark, regions = decode_memi_mask(mask)

    assert dark.sum() == 2
    assert REGIONS[regions[0, 0] - 1] == "forehead"
    assert REGIONS[regions[3, 3] - 1] == "right_cheek"
    assert regions[1, 1] == 0


def test_a_thin_line_vanishes_when_shrunk_and_a_thick_one_survives():
    thin = np.zeros((1024, 1024), np.uint8)
    thin[500, 100:900] = 1  # 1 px line
    thick = np.zeros((1024, 1024), np.uint8)
    thick[500:516, 100:900] = 1  # 16 px line

    assert kept_at_size(thin, 1024) == 1.0
    assert kept_at_size(thin, 256) == 0.0  # 1 px becomes a quarter of a pixel: gone
    assert kept_at_size(thick, 256) > 0.9
    assert kept_at_size(np.zeros((8, 8), np.uint8), 4) is None


def test_line_width_of_a_drawn_line():
    mask = np.zeros((200, 200), np.uint8)
    mask[97:104, 20:180] = 1  # 7 px wide
    mask[150:153, 20:180] = 1  # 3 px wide

    assert line_width(mask[90:110]) == pytest.approx(7, abs=0.5)
    assert line_width(mask[145:160]) == pytest.approx(3, abs=0.5)
    assert line_width(np.zeros((5, 5), np.uint8)) is None


def test_share_inside_and_spread_relative_to_the_face():
    mask = np.zeros((100, 100), np.uint8)
    mask[10:20, 10:20] = 1
    mask[80:90, 80:90] = 1
    face = Face(x=0, y=0, width=100, height=100, score=1.0)

    assert share_inside(mask, (0, 0, 50, 50)) == 0.5
    spread = relative_spread(mask, face)
    assert spread["x"][0] < 0.2 and spread["x"][1] > 0.8
    assert relative_spread(np.zeros((5, 5), np.uint8), face) is None


def test_patches_count_and_size():
    mask = np.zeros((100, 100), np.uint8)
    mask[0:10, 0:10] = 1
    mask[50:60, 50:60] = 1

    assert patches(mask, face_area=10_000) == {"count": 2, "median_percent_of_face": 1.0}
    assert patches(np.zeros((5, 5), np.uint8), 100)["median_percent_of_face"] is None


def _face(nose_x):
    # face box 100 x 100 at (100, 100); eyes at y 120, mouth at y 165
    return Face(x=100, y=100, width=100, height=100, score=1.0,
                landmarks=((125, 120), (175, 120), (nose_x, 145), (130, 165), (170, 165)))  # fmt: skip


def test_unet_crop_has_room_for_the_forehead():
    assert unet_crop_box(_face(150), 1000, 1000) == (80, 50, 220, 220)
    assert unet_crop_box(_face(150), 210, 210) == (80, 50, 210, 210)  # kept inside the photo


def test_front_view_ignores_both_cheeks_but_never_a_marked_pixel():
    dark = np.zeros((400, 400), np.uint8)
    dark[90, 150] = 1  # forehead spot
    dark[150, 115] = 1  # a marked spot inside a cheek zone

    known = known_dark_spots(_face(150), "F", dark)

    assert known[150, 115] == 1  # marked = always learned
    assert known[150, 120] == 0 and known[150, 180] == 0  # both cheeks ignored
    assert known[150, 135] == 1 and known[150, 165] == 1  # the nose and its wings are learned
    assert known[90, 150] == 1 and known[195, 150] == 1  # forehead, chin
    assert known[110, 120] == 1  # above eye level: not a cheek
    assert known[166, 120] == 1  # beside the mouth: part of MEMI's "chin", learned


def test_side_views_learn_only_their_cheek_and_the_background():
    dark = np.zeros((400, 400), np.uint8)

    left_view = known_dark_spots(_face(112), "L", dark)  # nose on the left of the picture
    right_view = known_dark_spots(_face(188), "R", dark)

    assert left_view[150, 170] == 1 and left_view[150, 105] == 0  # its cheek vs the nose side
    assert left_view[80, 150] == 0  # forehead unknown
    assert right_view[150, 130] == 1 and right_view[150, 195] == 0
    assert left_view[10, 10] == 1 and right_view[390, 390] == 1  # background is known


def test_load_sample_reads_both_sources(tmp_path):
    raw = tmp_path / "starter_kit" / "data" / "raw"
    (raw / "FFHQ").mkdir(parents=True)
    (raw / "MEMI").mkdir(parents=True)
    cv2.imwrite(str(raw / "FFHQ" / "00001.png"), np.zeros((8, 8, 3), np.uint8))
    wrinkle = np.zeros((8, 8), np.uint8)
    wrinkle[2, 1:7] = 255
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("manual_wrinkle_masks/00001.png", cv2.imencode(".png", wrinkle)[1].tobytes())
    (raw / "FFHQ_Wrinkle").mkdir()
    (raw / "FFHQ_Wrinkle" / "masks.zip").write_bytes(buffer.getvalue())
    colour = np.zeros((8, 8, 3), np.uint8)
    colour[4:6, 4:6] = (0, 128, 0)  # nose
    cv2.imwrite(str(raw / "MEMI" / "1_F.jpg"), np.zeros((8, 8, 3), np.uint8))
    cv2.imwrite(str(raw / "MEMI" / "1_F.png"), colour)

    ffhq = load_sample({"source": "ffhq_wrinkle", "file": "starter_kit/data/raw/FFHQ/00001.png",
                        "mask": "FFHQ_Wrinkle/masks.zip:00001"}, tmp_path)  # fmt: skip
    memi = load_sample({"source": "memi_ds", "file": "starter_kit/data/raw/MEMI/1_F.jpg",
                        "mask": "starter_kit/data/raw/MEMI/1_F.png"}, tmp_path)  # fmt: skip

    assert ffhq.wrinkles.sum() == 6 and ffhq.dark_spots is None
    assert memi.dark_spots.sum() == 4 and memi.wrinkles is None
    assert REGIONS[memi.regions[4, 4] - 1] == "nose"
    with pytest.raises(FileNotFoundError):
        load_sample({"source": "memi_ds", "file": "missing.jpg", "mask": "x.png"}, tmp_path)
