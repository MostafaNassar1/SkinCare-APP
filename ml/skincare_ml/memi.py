"""MEMI-DS melasma masks: every coloured pixel is a dark spot; the colour names a face region.

The source does not document the colours; Part 1.3 found (DATASETS.md) that front views (`_F`)
annotate the forehead, nose and chin, and side views annotate only the cheek they show. A region
that a view does not annotate is UNKNOWN (cheeks in front views are not "free of dark spots"), so
training must ignore it.
"""

# OpenCV reads colours as (blue, green, red)
REGION_COLOURS = {
    (0, 0, 128): "forehead",
    (0, 128, 0): "nose",
    (128, 0, 128): "chin",
    (0, 128, 128): "left_cheek",
    (128, 128, 0): "right_cheek",
}
VIEW_REGIONS = {
    "F": ("forehead", "nose", "chin"),
    "L": ("left_cheek",),
    "R": ("right_cheek",),
}


def parse_name(stem: str) -> tuple[str, str]:
    """'27_F' -> (person '27', view 'F')."""
    person, view = stem.split("_")
    if not person.isdigit() or view not in VIEW_REGIONS:
        raise ValueError(f"Not a MEMI-DS photo name: {stem}")
    return person, view
