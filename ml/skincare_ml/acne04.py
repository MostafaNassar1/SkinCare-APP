"""ACNE04 / ACNE04-v2: expert severity grades and lesion circles.

ACNE04 stores the expert grade in the file name (`levle0_12.jpg`, the authors' spelling): 0 mild,
1 moderate, 2 severe, 3 very severe on the Hayashi scale. ACNE04-v2 adds one circle per lesion
(centre + radius, in pixels of the original photo), all labelled "acne".
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

GRADES = ("mild", "moderate", "severe", "very_severe")  # index = the number in the file name
_FILE_NAME = re.compile(r"levle([0-3])_\d+\.jpg")


def grade_from_file_name(file_name: str) -> str:
    match = _FILE_NAME.fullmatch(file_name)
    if not match:
        raise ValueError(f"Not an ACNE04 file name: {file_name}")
    return GRADES[int(match.group(1))]


def hayashi_grade(lesion_count: int) -> str | None:
    """Hayashi scale (Hayashi et al., J Dermatol 2008), counted on half of the face.

    None for 0 lesions: the scale (and ACNE04) has no "clear" level.
    """
    if lesion_count < 0:
        raise ValueError("A lesion count cannot be negative.")
    if lesion_count == 0:
        return None
    if lesion_count <= 5:
        return "mild"
    if lesion_count <= 20:
        return "moderate"
    if lesion_count <= 50:
        return "severe"
    return "very_severe"


@dataclass(frozen=True)
class Lesion:
    x: float
    y: float
    radius: float


@dataclass
class AcneImage:
    file_name: str
    width: int
    height: int
    grade: str
    lesions: list[Lesion] = field(default_factory=list)
    # circles whose centre lies outside the photo (a source error): kept apart, never trained on
    invalid_lesions: list[Lesion] = field(default_factory=list)


def load_v2_annotations(path: Path) -> list[AcneImage]:
    """Reads Acne04-v2_annotations.json (COCO-like: images + one annotation per lesion)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    images = {
        record["id"]: AcneImage(
            file_name=record["file_name"],
            width=record["width"],
            height=record["height"],
            grade=grade_from_file_name(record["file_name"]),
        )
        for record in data["images"]
    }
    for record in data["annotations"]:
        image = images[record["image_id"]]
        x, y = record["coordinates"]
        lesion = Lesion(float(x), float(y), float(record["radius"]))
        inside = 0 <= lesion.x < image.width and 0 <= lesion.y < image.height
        (image.lesions if inside else image.invalid_lesions).append(lesion)
    return list(images.values())
