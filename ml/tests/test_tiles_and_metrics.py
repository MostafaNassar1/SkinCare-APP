import json
import random
import sys
from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image

from skincare_ml import detection_metrics as metrics
from skincare_ml import tiled_predict, yolo_tiles
from skincare_ml.yolo_tiles import boxes_in_tile, export_tiles, phone_like, tile_origins

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


# ---------- tiles ----------


@pytest.mark.parametrize(
    ("length", "expected"),
    [(1024, [0]), (900, [0]), (1500, [0, 476]), (2560, [0, 768, 1536])],
)
def test_tiles_cover_the_photo_without_going_outside(length, expected):
    starts = tile_origins(length, tile=1024, overlap=256)

    assert starts == expected
    assert starts[-1] + min(1024, length) == length  # the last tile ends at the edge


def test_boxes_cut_at_the_tile_edge_are_kept_only_if_mostly_inside():
    boxes = [[100, 100, 140, 140],  # fully inside
             [1000, 100, 1040, 140],  # 60% inside on the right edge -> clipped, kept
             [1014, 100, 1054, 140],  # 25% inside -> left out
             [2000, 2000, 2040, 2040]]  # fmt: skip

    kept = boxes_in_tile(boxes, left=0, top=0, size_x=1024, size_y=1024)

    assert kept == [[100, 100, 140, 140], [1000, 100, 1024, 140]]


def test_phone_like_copy_keeps_the_size_and_changes_the_pixels():
    tile = Image.new("RGB", (256, 256), (200, 120, 110))
    tile.paste((240, 230, 220), (100, 100, 120, 120))  # a small white top

    copy = phone_like(tile, random.Random(1))

    assert copy.size == tile.size
    assert np.abs(np.asarray(copy, float) - np.asarray(tile, float)).mean() > 1


def test_export_tiles_train_val_and_phone_copies(tmp_path):
    sources = tmp_path / "sources"
    (sources / "acne04").mkdir(parents=True)
    images = []
    for n, split in enumerate(["train", "val", "test"]):
        file = f"acne04/p{n}.jpg"
        Image.new("RGB", (2000, 1500), (200, 150, 130)).save(sources / file)
        boxes = [{"box": [100, 100, 140, 140]}, {"box": [1500, 1200, 1540, 1240]}]
        images.append({"file": file, "split": split, "width": 2000, "height": 1500,
                       "boxes": boxes})  # fmt: skip

    counts = export_tiles({"images": images}, sources, tmp_path / "tiles")

    # a pimple in the overlap of two tiles is in both (each tile shows every pimple it contains)
    assert counts["train"]["boxes"] >= 2 and counts["val"]["boxes"] >= 2
    assert counts["train_phone"]["tiles"] == counts["train"]["tiles"]  # one copy per training tile
    assert not list((tmp_path / "tiles" / "images").glob("test*"))  # test photos never tiled
    tile = next((tmp_path / "tiles" / "images" / "train").glob("p0_0_0.jpg"))
    with Image.open(tile) as picture:
        assert picture.size == (1024, 1024)  # full resolution, not shrunk
    assert json.loads((tmp_path / "tiles" / "export.json").read_text())["val"]["tiles"] >= 1
    with pytest.raises(FileExistsError):
        export_tiles({"images": images}, sources, tmp_path / "tiles")


# ---------- tiled prediction ----------


class FakeBoxes:
    def __init__(self, boxes, scores):
        self.xyxy = torch.tensor(boxes, dtype=torch.float32).reshape(-1, 4)
        self.conf = torch.tensor(scores, dtype=torch.float32).reshape(-1)


class FakeResult:
    def __init__(self, boxes, scores):
        self.boxes = FakeBoxes(boxes, scores)


class FakeModel:
    """Finds one 'pimple' wherever an image has a pure white 20 x 20 square."""

    def predict(self, images, **settings):
        results = []
        for image in images:
            pixels = np.asarray(image)
            ys, xs = np.where((pixels == 255).all(axis=2))
            if len(xs):
                box = [xs.min(), ys.min(), xs.max() + 1, ys.max() + 1]
                results.append(FakeResult([box], [0.9]))
            else:
                results.append(FakeResult([], []))
        return results


def test_tiled_prediction_returns_photo_coordinates_and_merges_overlaps():
    photo = Image.new("RGB", (2000, 1500), (180, 140, 120))
    photo.paste((255, 255, 255), (900, 700, 920, 720))  # inside the overlap of several tiles

    found = tiled_predict.predict_tiled(FakeModel(), photo, conf=0.1)

    assert len(found.boxes) == 1  # seen by several tiles, merged into one
    assert found.boxes[0].tolist() == [900, 700, 920, 720]


def test_merge_keeps_the_more_confident_box():
    boxes = np.array([[0, 0, 10, 10], [1, 1, 11, 11], [50, 50, 60, 60]], dtype=np.float32)

    merged = tiled_predict.merge(boxes, np.array([0.4, 0.8, 0.5], dtype=np.float32))

    assert merged.scores.tolist() == pytest.approx([0.8, 0.5])


# ---------- scoring ----------


def test_match_finds_each_expert_box_once_most_confident_first():
    truth = np.array([[0, 0, 10, 10]], dtype=float)
    pred = np.array([[0, 0, 10, 10], [1, 0, 11, 10]], dtype=float)

    hits, found = metrics.match(pred, np.array([0.3, 0.9]), truth)

    assert hits.tolist() == [False, True] and found.tolist() == [-1, 0]


def test_score_precision_recall_ap_sizes_and_counts():
    truth = np.array([[0, 0, 10, 10], [100, 100, 150, 150]], dtype=float)
    pred = np.array([[0, 0, 10, 10], [300, 300, 310, 310]], dtype=float)  # one hit, one false
    photos = [{"pred": pred, "scores": np.array([0.9, 0.6]), "truth": truth}]

    result = metrics.score(photos, cutoff=0.5)

    assert (result["precision"], result["recall"]) == (0.5, 0.5)
    assert result["AP50"] == pytest.approx(0.5)  # recall 0.5 reached at precision 1
    assert result["recall_by_size"]["0-20 px"] == {"boxes": 1, "recall": 1.0}
    assert result["recall_by_size"]["40-80 px"] == {"boxes": 1, "recall": 0.0}
    assert (result["count_mean_abs_error"], result["count_mean_bias"]) == (0.0, 0.0)


def test_best_f1_cutoff_is_chosen_when_none_is_given():
    truth = np.array([[0, 0, 10, 10]], dtype=float)
    pred = np.array([[0, 0, 10, 10], [50, 50, 60, 60]], dtype=float)
    photos = [{"pred": pred, "scores": np.array([0.8, 0.2]), "truth": truth}]

    result = metrics.score(photos)

    assert result["cutoff"] == 0.8 and result["precision"] == 1.0 and result["recall"] == 1.0


# ---------- training runs ----------


@pytest.fixture
def train_yolo(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    sys.modules.pop("train_yolo", None)
    import train_yolo

    return train_yolo


def test_fine_tuning_runs_start_from_v1_with_a_fixed_batch(train_yolo):
    for run in ("A", "B", "C"):
        dataset, weights, _, settings = train_yolo.RUNS[run]
        assert weights == "yolo_pimples_v1.pt"
        assert train_yolo.run_settings(run)["batch"] == 4
    assert train_yolo.RUNS["A"][0] == "yolo_pimples"
    assert train_yolo.RUNS["B"][0] == "yolo_pimples_tiles"
    assert train_yolo.RUNS["C"][2] is True and train_yolo.RUNS["B"][2] is False
    settings = train_yolo.run_settings("B", batch=2, lr=0.0005)
    assert (settings["batch"], settings["lr0"], settings["optimizer"]) == (2, 0.0005, "AdamW")
    assert settings["hsv_h"] == 0.0 and settings["flipud"] == 0.0


def test_data_yaml_lists_the_phone_copies_for_run_c(train_yolo, monkeypatch, tmp_path):
    monkeypatch.setenv("SKINCARE_DATA_DIR", str(tmp_path))
    for folder in ("train", "train_phone", "val"):
        (tmp_path / "prepared" / "yolo_pimples_tiles" / "images" / folder).mkdir(parents=True)

    text = Path(train_yolo.data_yaml("yolo_pimples_tiles", phone_copies=True)).read_text()

    assert "  - images/train\n  - images/train_phone" in text and "val: images/val" in text
    assert "\ntest:" not in text  # the frozen test set is never used while training


# ---------- comparing models ----------


@pytest.fixture
def compare(monkeypatch, tmp_path):
    monkeypatch.setenv("SKINCARE_DATA_DIR", str(tmp_path))
    monkeypatch.syspath_prepend(str(SCRIPTS))
    sys.modules.pop("compare_models", None)
    import compare_models

    return compare_models


def test_model_argument_names_file_and_mode(compare, tmp_path):
    name, path, mode = compare.parse_model("v1=yolo_pimples_v1.pt:whole")

    assert (name, mode) == ("v1", "whole")
    assert path == tmp_path.resolve() / "models" / "yolo_pimples_v1.pt"
    with pytest.raises(Exception):
        compare.parse_model("v1=model.pt:sideways")


def test_spearman_rank_correlation(compare):
    assert compare.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert compare.spearman([1, 2, 3, 4], [40, 30, 20, 10]) == -1.0
    assert compare.spearman([1, 2], [1, 2]) is None


def test_phone_photo_is_smaller_and_degraded():
    photo = Image.new("RGB", (1000, 800), (200, 150, 130))

    small = yolo_tiles.phone_photo(photo, random.Random(1), factor=0.4)

    assert small.size == (400, 320)


def test_evaluate_scores_whole_and_phone_like_photos(compare, tmp_path):
    sources = tmp_path / "sources"
    (sources / "acne04").mkdir(parents=True)
    photo = Image.new("RGB", (1000, 800), (180, 140, 120))
    photo.paste((255, 255, 255), (400, 300, 440, 340))
    photo.save(sources / "acne04" / "p.png")
    photos = [{"file": "acne04/p.png", "boxes": [{"box": [400, 300, 440, 340]}],
               "original_lesion_count": 1}]  # fmt: skip

    original = compare.evaluate(FakeModel(), "whole", photos, sources, phone=False, device=None)
    tiled = compare.evaluate(FakeModel(), "tiled", photos, sources, phone=False, device=None)

    assert original["recall"] == 1.0 and original["precision"] == 1.0
    assert tiled["recall"] == 1.0
