import pytest

from skincare_ml.faces import Face, crop_box, detection_scale


@pytest.mark.parametrize(
    ("width", "height", "scale"),
    [
        (5184, 3456, 640 / 5184),
        (3112, 3456, 640 / 3456),
        (640, 480, 1.0),
        (300, 200, 1.0),  # small photos are never enlarged
    ],
)
def test_detection_scale_fits_the_longest_side(width, height, scale):
    assert detection_scale(width, height) == pytest.approx(scale)


def test_crop_box_adds_a_margin_around_the_face():
    face = Face(x=100, y=200, width=50, height=100, score=0.9)

    assert crop_box(face, width=1000, height=1000) == (90, 180, 160, 320)


def test_crop_box_stays_inside_the_photo():
    face = Face(x=5, y=10, width=200, height=300, score=0.9)

    assert crop_box(face, width=210, height=320) == (0, 0, 210, 320)
