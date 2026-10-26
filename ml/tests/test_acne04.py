import json

import pytest

from skincare_ml.acne04 import (
    AcneImage,
    Lesion,
    circle_to_box,
    grade_from_file_name,
    hayashi_grade,
    load_split_file_grades,
    load_v2_annotations,
    pick_unique,
)


@pytest.mark.parametrize(
    ("file_name", "grade"),
    [
        ("levle0_196.jpg", "mild"),
        ("levle1_360.jpg", "moderate"),
        ("levle2_130.jpg", "severe"),
        ("levle3_116.jpg", "very_severe"),
    ],
)
def test_grade_comes_from_the_file_name(file_name, grade):
    assert grade_from_file_name(file_name) == grade


@pytest.mark.parametrize("file_name", ["levle4_1.jpg", "level0_1.jpg", "levle0_1.png", "x.jpg"])
def test_unknown_file_names_are_refused(file_name):
    with pytest.raises(ValueError):
        grade_from_file_name(file_name)


@pytest.mark.parametrize(
    ("count", "grade"),
    [
        (0, None),
        (1, "mild"),
        (5, "mild"),
        (6, "moderate"),
        (20, "moderate"),
        (21, "severe"),
        (50, "severe"),
        (51, "very_severe"),
    ],
)
def test_hayashi_grade_boundaries(count, grade):
    assert hayashi_grade(count) == grade


def test_negative_count_is_refused():
    with pytest.raises(ValueError):
        hayashi_grade(-1)


def test_load_v2_annotations_separates_circles_outside_the_photo(tmp_path):
    path = tmp_path / "annotations.json"
    path.write_text(
        json.dumps(
            {
                "images": [
                    {"id": 0, "file_name": "levle1_7.jpg", "width": 100, "height": 50},
                    {"id": 1, "file_name": "levle0_3.jpg", "width": 100, "height": 50},
                ],
                "annotations": [
                    {"id": 0, "image_id": 0, "radius": 4, "coordinates": [10, 20]},
                    {"id": 1, "image_id": 0, "radius": 3, "coordinates": [99, 49]},
                    {"id": 2, "image_id": 0, "radius": 3, "coordinates": [100, 20]},
                    {"id": 3, "image_id": 0, "radius": 3, "coordinates": [10, -1]},
                ],
            }
        ),
        encoding="utf-8",
    )

    first, second = load_v2_annotations(path)

    assert (first.file_name, first.grade) == ("levle1_7.jpg", "moderate")
    assert [(lesion.x, lesion.y) for lesion in first.lesions] == [(10, 20), (99, 49)]
    assert len(first.invalid_lesions) == 2
    assert second.lesions == [] and second.invalid_lesions == []


def test_split_file_grade_wins_over_the_file_name(tmp_path):
    (tmp_path / "NNEW_trainval_0.txt").write_text("levle1_181.jpg  0  1\nlevle2_5.jpg  2  30\n")
    (tmp_path / "NNEW_test_0.txt").write_text("levle3_9.jpg  3  60\n")

    assert load_split_file_grades(tmp_path) == {
        "levle1_181.jpg": ("mild", 1),
        "levle2_5.jpg": ("severe", 30),
        "levle3_9.jpg": ("very_severe", 60),
    }


def test_circle_to_box_is_clipped_to_the_photo():
    assert circle_to_box(Lesion(10, 20, 5), width=100, height=50) == (5, 15, 15, 25)
    assert circle_to_box(Lesion(2, 48, 5), width=100, height=50) == (0, 43, 7, 50)


def test_pick_unique_keeps_the_copy_with_the_most_circles():
    def image(name, circles):
        return AcneImage(name, 10, 10, "mild", [Lesion(1, 1, 1)] * circles)

    images = [image("b.jpg", 3), image("a.jpg", 3), image("c.jpg", 5), image("d.jpg", 1)]
    digests = {"a.jpg": "x", "b.jpg": "x", "c.jpg": "y", "d.jpg": "y"}

    kept = pick_unique(images, digests)

    assert [i.file_name for i in kept] == ["a.jpg", "c.jpg"]  # tie on circles -> name order
