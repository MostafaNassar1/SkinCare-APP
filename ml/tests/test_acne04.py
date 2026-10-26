import json

import pytest

from skincare_ml.acne04 import grade_from_file_name, hayashi_grade, load_v2_annotations


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
