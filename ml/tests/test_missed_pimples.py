import json
import sys
from collections import Counter
from pathlib import Path

import pytest
from PIL import Image

from skincare_ml import missed_pimples
from skincare_ml.missed_pimples import (
    add_circle,
    choose_photos,
    default_radius,
    load_state,
    mark_done,
    remove_circle,
    summary,
)

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def photo(name: str, split: str = "test", grade: str = "mild", sizes=(20, 40, 60)) -> dict:
    return {"file": f"acne04/{name}.jpg", "split": split, "expert_grade": grade,
            "width": 800, "height": 600,
            "boxes": [{"type": "lesion", "box": [10, 10, 10 + s, 10 + s]}
                      for s in sizes]}  # fmt: skip


def test_photos_are_test_photos_spread_over_the_grades():
    images = [photo(f"m{i}", grade="mild") for i in range(60)]
    images += [photo(f"s{i}", grade="severe") for i in range(20)]
    images += [photo(f"t{i}", split="train") for i in range(50)]

    chosen = choose_photos(images, 20, seed=1)

    assert len(chosen) == 20 and {p["split"] for p in chosen} == {"test"}
    assert Counter(p["expert_grade"] for p in chosen) == {"mild": 15, "severe": 5}
    assert choose_photos(images, 20, seed=1) == chosen  # reproducible


def test_new_circles_use_the_photos_median_expert_size():
    assert default_radius(photo("a", sizes=(20, 40, 100))) == 20  # median diameter 40 -> r 20


def test_log_replay_add_remove_done_reopen(tmp_path):
    log = tmp_path / "missed.jsonl"
    first = add_circle(log, "a.jpg", 100, 120, 15)
    second = add_circle(log, "a.jpg", 300, 220, 15)
    remove_circle(log, "a.jpg", first)
    mark_done(log, "a.jpg")
    mark_done(log, "b.jpg")
    mark_done(log, "b.jpg", done=False)

    state = load_state(log)

    assert list(state.added["a.jpg"]) == [second]
    assert state.added["a.jpg"][second] == {"x": 100 + 200, "y": 220, "r": 15}
    assert state.done == {"a.jpg"}
    assert len(log.read_text().splitlines()) == 6  # append-only: nothing rewritten


def test_summary_counts_misses_on_checked_photos_only(tmp_path):
    log = tmp_path / "missed.jsonl"
    photos = [photo("a"), photo("b"), photo("c")]
    add_circle(log, photos[0]["file"], 1, 1, 5)
    add_circle(log, photos[0]["file"], 2, 2, 5)
    add_circle(log, photos[2]["file"], 3, 3, 5)  # photo c is not finished: not counted
    mark_done(log, photos[0]["file"])
    mark_done(log, photos[1]["file"])

    result = summary(photos, load_state(log))

    assert result == {"photos_checked": 2, "missed_added": 2, "photos_with_a_miss": 1,
                      "missed_per_photo": 1.0, "expert_circles_on_them": 6,
                      "missed_share": 0.25}  # fmt: skip


@pytest.fixture
def check(monkeypatch, tmp_path):
    monkeypatch.setenv("SKINCARE_DATA_DIR", str(tmp_path))
    images = [photo(f"face{i}") for i in range(3)]
    for image in images:
        path = tmp_path / "sources" / image["file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (800, 600), (200, 150, 130)).save(path)
    manifests = tmp_path / "prepared" / "manifests"
    manifests.mkdir(parents=True)
    (manifests / "pimples.json").write_text(json.dumps({"images": images}))
    monkeypatch.syspath_prepend(str(SCRIPTS))
    sys.modules.pop("check_missed", None)
    import check_missed

    return check_missed.Check()


def test_check_walks_through_the_chosen_photos(check):
    state = check.state()
    assert state["total"] == 3 and state["index"] == 0
    assert len(state["photo"]["experts"]) == 3

    add_circle(check.log, state["photo"]["file"], 400, 300, state["photo"]["radius"])
    mark_done(check.log, state["photo"]["file"])

    after = check.state()
    assert after["index"] == 1 and after["summary"]["missed_added"] == 1
    check.back()
    assert check.state()["index"] == 0  # reopened, its circle kept
    assert len(check.state()["photo"]["added"]) == 1


def test_the_chosen_photos_stay_the_same_between_sessions(check):
    import check_missed

    assert [p["file"] for p in check_missed.Check().photos] == [p["file"] for p in check.photos]


def test_photo_is_sent_as_a_jpeg(check):
    assert check.picture(0)[:2] == b"\xff\xd8"


def test_module_states_the_correction_rules():
    assert "only clear misses" in missed_pimples.__doc__
