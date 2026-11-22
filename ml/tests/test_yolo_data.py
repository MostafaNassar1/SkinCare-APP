import json

import pytest
from PIL import Image

from skincare_ml.yolo_data import MAX_SIDE, added_boxes, export, label_lines, yolo_line


def test_yolo_line_is_relative_and_clipped():
    assert yolo_line([100, 50, 200, 150], 1000, 500) == "0 0.150000 0.200000 0.100000 0.200000"
    # a box crossing the right edge is clipped to the photo
    assert yolo_line([950, 0, 1050, 100], 1000, 500) == "0 0.975000 0.100000 0.050000 0.200000"


def test_student_additions_are_added_to_test_photos_only():
    frozen = {"added": {"a.jpg": [{"x": 100, "y": 100, "r": 10}]}}
    extra = added_boxes(frozen)
    test = {"file": "a.jpg", "split": "test", "width": 1000, "height": 1000,
            "boxes": [{"box": [0, 0, 20, 20]}]}  # fmt: skip
    train = {**test, "split": "train"}

    assert extra == {"a.jpg": [[90, 90, 110, 110]]}
    assert len(label_lines(test, extra)) == 2
    assert len(label_lines(train, extra)) == 1


@pytest.fixture
def dataset(tmp_path):
    sources = tmp_path / "sources"
    images = []
    for n, split in enumerate(["train", "train", "val", "test", "test"]):
        file = f"acne04/p{n}.jpg"
        (sources / "acne04").mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (3200, 2400), (200, 150, 130)).save(sources / file)
        images.append({"file": file, "split": split, "width": 3200, "height": 2400,
                       "boxes": [{"box": [100, 100, 140, 140]}]})  # fmt: skip
    frozen = {"added": {"acne04/p3.jpg": [{"x": 500, "y": 500, "r": 20}], "acne04/p4.jpg": []}}
    return {"images": images}, sources, tmp_path / "yolo", frozen


def test_export_writes_shrunk_images_labels_and_yaml(dataset):
    manifest, sources, out, frozen = dataset

    counts = export(manifest, sources, out, frozen)

    assert counts["train"] == {"images": 2, "boxes": 2}
    assert counts["test"] == {"images": 2, "boxes": 3}  # + the student's addition
    with Image.open(out / "images" / "train" / "p0.jpg") as image:
        assert max(image.size) == MAX_SIDE and image.size == (1600, 1200)
    label = (out / "labels" / "test" / "p3.txt").read_text().splitlines()
    assert len(label) == 2 and all(line.startswith("0 ") for line in label)
    assert (out / "test_checked.txt").read_text().split() == [
        "./images/test/p3.jpg", "./images/test/p4.jpg"]  # fmt: skip
    assert "names:\n  0: pimple" in (out / "data.yaml").read_text()
    assert json.loads((out / "export.json").read_text())["test_checked"] == 2


def test_export_never_overwrites(dataset):
    manifest, sources, out, frozen = dataset
    export(manifest, sources, out, frozen)

    with pytest.raises(FileExistsError):
        export(manifest, sources, out, frozen)
