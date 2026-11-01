import json
import sys
from collections import Counter
from pathlib import Path

import pytest
from PIL import Image

from skincare_ml import lesion_types
from skincare_ml.lesion_types import (
    MAX_PER_PHOTO,
    MIN_BOX_PX,
    REPEAT_GAP,
    crop_square,
    load_answers,
    make_queue,
    save_answer,
    self_agreement,
)

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def image(name: str, split: str, boxes: int, size: int = 40, grade: str = "mild") -> dict:
    return {
        "file": f"acne04/{name}.jpg",
        "split": split,
        "expert_grade": grade,
        "boxes": [{"type": "lesion", "box": [10 * i, 10, 10 * i + size, 10 + size]}
                  for i in range(boxes)],
    }  # fmt: skip


@pytest.fixture
def images() -> list[dict]:
    photos = [image(f"train{i}", "train", 6) for i in range(70)]
    photos += [image(f"val{i}", "val", 6) for i in range(15)]
    photos += [image(f"test{i}", "test", 6) for i in range(15)]
    return photos


# ---------- the queue of a round ----------


def test_queue_size_shares_and_test_first(images):
    queue = make_queue(images, 200, seed=1)

    new = [item for item in queue if not item.is_repeat]
    assert len(new) == 200
    splits = Counter(item.split for item in new)
    assert splits == {"train": 140, "val": 30, "test": 30}  # follows the photos: 70 / 15 / 15
    order = [item.split for item in new]
    assert order == sorted(order, key=("test", "val", "train").index)  # test labelled first


def test_queue_takes_a_few_circles_per_photo_and_skips_tiny_ones():
    photos = [image("big", "train", 8), image("tiny", "train", 8, size=MIN_BOX_PX - 1)]

    queue = make_queue(photos, 50, seed=1)

    files = Counter(item.file for item in queue if not item.is_repeat)
    assert files == {"acne04/big.jpg": MAX_PER_PHOTO}


def test_hidden_repeats_come_much_later(images):
    queue = make_queue(images, 200, seed=1)

    repeats = [n for n, item in enumerate(queue) if item.is_repeat]
    assert len(repeats) == 20  # 10%
    ids = [item.id for item in queue]
    for position in repeats:
        assert position - ids.index(queue[position].circle_id) >= REPEAT_GAP


def test_queue_is_reproducible_and_skips_answered_circles(images):
    first = make_queue(images, 100, seed=7)
    again = make_queue(images, 100, seed=7)
    done = {item.id for item in first if not item.is_repeat}

    later = make_queue(images, 100, seed=8, skip=done)

    assert first == again
    assert not done & {item.circle_id for item in later}


# ---------- close-ups ----------


@pytest.mark.parametrize(
    ("box", "expected"),
    [((100, 100, 150, 150), (50, 50, 200, 200)),  # 3 x 50 = 150 px around the centre
     ((100, 100, 120, 120), (78, 78, 142, 142)),  # 3 x 20 = 60, raised to the 64 px minimum
     ((0, 0, 10, 10), (0, 0, 64, 64)),  # at least 64 px, shifted inside at the corner
     ((990, 490, 1000, 500), (936, 436, 1000, 500))],  # bottom-right edge
)  # fmt: skip
def test_crop_square_stays_inside_the_photo(box, expected):
    assert crop_square(box, 1000, 500, scale=3, minimum=64) == expected


# ---------- answers and self-agreement ----------


def test_last_answer_wins_and_backspace_takes_it_back(tmp_path):
    path = tmp_path / "answers.jsonl"
    save_answer(path, "a#0", "papule")
    save_answer(path, "a#0", "pustule")
    save_answer(path, "a#1", "whitehead")
    save_answer(path, "a#1", None)

    assert load_answers(path) == {"a#0": "pustule"}
    assert len(path.read_text().splitlines()) == 4  # nothing is ever rewritten


def test_unknown_type_is_refused(tmp_path):
    with pytest.raises(ValueError):
        save_answer(tmp_path / "answers.jsonl", "a#0", "blackhead")


def test_self_agreement_and_kappa():
    answers = {
        "a#0": "papule", "repeat:a#0": "papule",
        "a#1": "pustule", "repeat:a#1": "pustule",
        "a#2": "whitehead", "repeat:a#2": "papule",
        "a#3": "whitehead", "repeat:a#3": "whitehead",
        "b#0": "other",  # no repeat
    }  # fmt: skip

    result = self_agreement(answers)

    assert result["pairs"] == 4 and result["agreement"] == 0.75
    # first answers: papule 1, pustule 1, whitehead 2; repeats: papule 2, pustule 1, whitehead 1
    # chance = (1*2 + 1*1 + 2*1) / 16 = 5/16 -> kappa = (0.75 - 0.3125) / 0.6875
    assert result["kappa"] == pytest.approx(0.636, abs=0.001)
    assert self_agreement({})["agreement"] is None


# ---------- the labelling page's round ----------


@pytest.fixture
def labelling(monkeypatch, tmp_path):
    monkeypatch.setenv("SKINCARE_DATA_DIR", str(tmp_path))
    photo = tmp_path / "sources" / "acne04" / "face.jpg"
    photo.parent.mkdir(parents=True)
    Image.new("RGB", (800, 600), (200, 150, 130)).save(photo, "PNG")  # lossless: exact colours
    queue = {"round": 1, "items": [
        {"id": f"acne04/face.jpg#{n}", "file": "acne04/face.jpg", "box": [100 + 50 * n, 100,
         130 + 50 * n, 130], "split": "test", "grade": "mild"} for n in range(3)]}  # fmt: skip
    folder = tmp_path / "prepared" / "lesion_types"
    folder.mkdir(parents=True)
    (folder / "round1_queue.json").write_text(json.dumps(queue))
    manifests = tmp_path / "prepared" / "manifests"
    manifests.mkdir()
    boxes = [item["box"] for item in queue["items"]] + [[500, 100, 530, 130]]  # + one not queued
    (manifests / "pimples.json").write_text(json.dumps({"images": [
        {"file": "acne04/face.jpg", "boxes": [{"type": "lesion", "box": b} for b in boxes]}]}))
    monkeypatch.syspath_prepend(str(SCRIPTS))
    sys.modules.pop("label_types", None)
    import label_types

    return label_types.Round(1)


def test_round_moves_forward_and_back(labelling):
    assert labelling.state()["position"] == 0

    save_answer(labelling.answers_file, "acne04/face.jpg#0", "papule")
    save_answer(labelling.answers_file, "acne04/face.jpg#1", "pustule")
    state = labelling.state()
    assert state["position"] == 2 and state["inflamed"] == 2

    labelling.take_back()

    assert labelling.state()["item"]["id"] == "acne04/face.jpg#1"
    assert load_answers(labelling.answers_file) == {"acne04/face.jpg#0": "papule"}


def test_round_pictures_are_jpegs(labelling):
    for kind in ("close", "context"):
        data = labelling.picture("acne04/face.jpg#0", kind)
        assert data[:2] == b"\xff\xd8"  # JPEG

    with Image.open(__import__("io").BytesIO(data)) as picture:
        assert picture.size == (420, 420)


@pytest.mark.parametrize("kind", ["context", "face"])
def test_context_and_face_circle_this_spot_bright_and_the_others_dim(labelling, kind):
    import label_types

    colours = {colour for _, colour in labelling.render("acne04/face.jpg#0", kind).getcolors()}

    assert label_types.CURRENT_RING[0] in colours  # this spot: bright cyan
    assert label_types.OTHER_RING[0] in colours  # the photo's other circles: light grey


def test_close_up_has_no_marks_and_face_keeps_the_photo_shape(labelling):
    close = labelling.render("acne04/face.jpg#0", "close")
    face = labelling.render("acne04/face.jpg#0", "face")

    assert {colour for _, colour in close.getcolors()} == {(200, 150, 130)}
    assert face.size == (640, 480)  # 800 x 600 shrunk to 640 on its longest side


def test_module_documents_every_type():
    for name in lesion_types.TYPES:
        assert f"- {name}:" in lesion_types.__doc__


# ---------- round 2: training photos, more severe faces ----------


def test_round_can_take_training_photos_only_and_favour_severe_faces():
    photos = [image(f"mild{i}", "train", 3, grade="mild") for i in range(50)]
    photos += [image(f"severe{i}", "train", 3, grade="severe") for i in range(50)]
    photos += [image(f"test{i}", "test", 3) for i in range(20)]

    plain = make_queue(photos, 60, seed=3, splits=["train"])
    weighted = make_queue(photos, 60, seed=3, splits=["train"],
                          grade_weights={"mild": 1.0, "severe": 4.0})  # fmt: skip

    assert {item.split for item in weighted} == {"train"}
    severe = [sum(i.grade == "severe" for i in q if not i.is_repeat) for q in (plain, weighted)]
    assert severe[1] > severe[0] and severe[1] >= 45  # mostly severe faces once weighted


# ---------- frozen test labels ----------


def test_frozen_record_keeps_only_test_answers_with_a_fingerprint():
    items = [{"id": "a#0", "split": "test"}, {"id": "repeat:a#0", "split": "test"},
             {"id": "b#0", "split": "train"}, {"id": "c#0", "split": "test"}]  # fmt: skip
    answers = {"a#0": "papule", "repeat:a#0": "whitehead", "b#0": "pustule"}

    record = lesion_types.frozen_test_record(items, answers)

    assert record["labels"] == {"a#0": "papule"}  # first answer, test only, answered only
    assert record["sha256"] == lesion_types.fingerprint({"a#0": "papule"})
    assert lesion_types.fingerprint({"a#0": "pustule"}) != record["sha256"]


@pytest.fixture
def scripts(monkeypatch, tmp_path):
    monkeypatch.setenv("SKINCARE_DATA_DIR", str(tmp_path))
    monkeypatch.syspath_prepend(str(SCRIPTS))
    for name in ("freeze_test_labels", "make_label_queue"):
        sys.modules.pop(name, None)
    import freeze_test_labels
    import make_label_queue

    folder = tmp_path / "prepared" / "lesion_types"
    folder.mkdir(parents=True)
    (folder / "round1_queue.json").write_text(json.dumps({"round": 1, "items": [
        {"id": "a#0", "split": "test"}, {"id": "b#0", "split": "train"}]}))
    save_answer(folder / "round1_answers.jsonl", "a#0", "papule")
    save_answer(folder / "round1_answers.jsonl", "b#0", "pustule")
    return freeze_test_labels, make_label_queue, folder


def test_freeze_once_then_check(scripts, capsys):
    freeze, _, folder = scripts

    assert freeze.main(["--round", "1"]) == 0
    assert freeze.main(["--round", "1"]) == 1  # frozen once
    assert freeze.main(["--check"]) == 0

    target = folder / "test_labels_frozen.json"
    record = json.loads(target.read_text())
    record["labels"]["a#0"] = "pustule"  # edited after freezing
    target.write_text(json.dumps(record))
    assert freeze.main(["--check"]) == 1
    assert "CHANGED" in capsys.readouterr().err


def test_no_new_test_close_ups_once_frozen(scripts):
    freeze, make, _ = scripts
    freeze.main(["--round", "1"])

    assert make.main(["--round", "2"]) == 1  # default splits include test
    assert make.main(["--round", "2", "--splits", "val", "train", "--favour-severe"]) == 1


def test_page_state_tells_the_minimum_viewing_time(monkeypatch, tmp_path, labelling):
    assert labelling.state()["min_seconds"] == 2.0
