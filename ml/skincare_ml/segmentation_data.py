"""Photos and masks for the U-Net (Phase 3 Step 4): loading and the measurements of Part 4.1.

Two sources, each knowing ONE channel (segmentation.json, Step 1):
- FFHQ-Wrinkle: a binary wrinkle mask (0 / 255) inside manual_wrinkle_masks.zip, 1024 x 1024.
- MEMI-DS: a colour mask (memi.REGION_COLOURS) where every coloured pixel is a dark spot and the
  colour names its face region; only the regions of the photo's view were annotated.
"""

import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from skincare_ml.memi import REGION_COLOURS

REGIONS = tuple(REGION_COLOURS.values())  # region id = position + 1 (0 = no dark spot)

# The U-Net's face crop (decided 2026-11-22, Part 4.1): YuNet's box starts near the eyebrows and
# melasma on MEMI foreheads reaches up to half a face-height above it; 20% kept only part of it on
# 43 of 59 front views, 50% at the top keeps 100% (forehead wrinkles in selfies too).
CROP_MARGINS = {"left": 0.2, "right": 0.2, "top": 0.5, "bottom": 0.2}

# Cheek zones in face-box units, measured on the 126 MEMI photos with a face (Part 4.1).
# Side views (the zone is what we LEARN from): marked cheeks start >= 0.13 face widths beside the
# nose tip and lie between eye level and 0.13 below the mouth, so the zone is a little larger.
# Front views (the zones are IGNORED): the marked nose reaches 0.25 face widths beside the nose
# tip and the marked "chin" starts at mouth level (it includes the skin beside the mouth), so the
# cheek zones start beside the nose wings and stop just above the mouth (first version with the
# side-view numbers hid marked nose wings and chin patches: seen on the check pictures).
CHEEK_ZONE = {  # (start beside the nose tip in face widths, end below the mouth in face heights)
    "side": (0.10, 0.15),
    "front": (0.22, -0.03),
}
FACE_AREA = {"left": 0.4, "right": 0.4, "top": 0.6, "bottom": 0.3}  # beyond = background


@dataclass
class Sample:
    image: np.ndarray  # BGR, as read by OpenCV
    wrinkles: np.ndarray | None  # 0 / 1, None = unknown for this source
    dark_spots: np.ndarray | None  # 0 / 1
    regions: np.ndarray | None  # 0 = none, else REGIONS index + 1 (MEMI only)


def decode_memi_mask(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """A MEMI colour mask (BGR) -> (dark spots 0 / 1, region ids)."""
    regions = np.zeros(mask.shape[:2], np.uint8)
    for number, colour in enumerate(REGION_COLOURS, 1):
        regions[np.all(mask == colour, axis=2)] = number
    return (regions > 0).astype(np.uint8), regions


@lru_cache(maxsize=2)
def _zip(path: str) -> zipfile.ZipFile:
    return zipfile.ZipFile(path)


def load_sample(entry: dict, data_dir: Path) -> Sample:
    """One segmentation.json entry -> its photo and masks."""
    image = cv2.imread(str(data_dir / entry["file"]))
    if image is None:
        raise FileNotFoundError(entry["file"])
    if entry["source"] == "ffhq_wrinkle":
        archive, stem = entry["mask"].split(":")
        z = _zip(str(data_dir / "starter_kit" / "data" / "raw" / archive))
        raw = z.read(f"manual_wrinkle_masks/{stem}.png")
        mask = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_GRAYSCALE)
        return Sample(image, (mask > 127).astype(np.uint8), None, None)
    colour = cv2.imread(str(data_dir / entry["mask"]))
    if colour is None:
        raise FileNotFoundError(entry["mask"])
    dark, regions = decode_memi_mask(colour)
    return Sample(image, None, dark, regions)


def unet_crop_box(face, width: int, height: int) -> tuple[int, int, int, int]:
    """(left, top, right, bottom) of the U-Net's face crop (CROP_MARGINS), kept inside the photo."""
    m = CROP_MARGINS
    return (max(0, int(face.x - m["left"] * face.width)),
            max(0, int(face.y - m["top"] * face.height)),
            min(width, int(round(face.x + (1 + m["right"]) * face.width))),
            min(height, int(round(face.y + (1 + m["bottom"]) * face.height))))  # fmt: skip


def _box(face, shape, x0: float, x1: float, y0: float, y1: float) -> np.ndarray:
    """A 0 / 1 picture with a rectangle given in face-box units (0 = box left / top edge)."""
    out = np.zeros(shape[:2], np.uint8)
    height, width = shape[:2]
    left = int(np.clip(face.x + x0 * face.width, 0, width))
    right = int(np.clip(face.x + x1 * face.width, 0, width))
    top = int(np.clip(face.y + y0 * face.height, 0, height))
    bottom = int(np.clip(face.y + y1 * face.height, 0, height))
    out[top:bottom, left:right] = 1
    return out


def known_dark_spots(face, view: str, dark_spots: np.ndarray) -> np.ndarray:
    """Where a MEMI mask can be trusted (1) and where training must ignore it (0).

    Front views (forehead, nose, chin annotated): both cheeks are unknown. Side views (only the
    cheek they show): the rest of the face is unknown; the cheek and the background are known. A
    marked pixel is always known (a dark spot whatever the zone). Zones come from YuNet's nose tip,
    eyes and mouth corners (CHEEK_ZONE, FACE_AREA).
    """
    (_, eye_r), (_, eye_l), (nose_x, _), (_, mouth_r), (_, mouth_l) = face.landmarks
    beside_nose, below_mouth = CHEEK_ZONE["front" if view == "F" else "side"]
    nose = (nose_x - face.x) / face.width
    top = ((eye_r + eye_l) / 2 - face.y) / face.height
    bottom = ((mouth_r + mouth_l) / 2 - face.y) / face.height + below_mouth
    far_left, far_right = -FACE_AREA["left"], 1 + FACE_AREA["right"]
    image_left_cheek = _box(face, dark_spots.shape, far_left, nose - beside_nose, top, bottom)
    image_right_cheek = _box(face, dark_spots.shape, nose + beside_nose, far_right, top, bottom)
    if view == "F":
        known = 1 - (image_left_cheek | image_right_cheek)
    else:
        face_area = _box(face, dark_spots.shape, far_left, far_right,
                         -FACE_AREA["top"], 1 + FACE_AREA["bottom"])  # fmt: skip
        # the person's left cheek is on the right of the picture (and the nose on the left)
        cheek = image_right_cheek if view == "L" else image_left_cheek
        known = (1 - face_area) | cheek
    return (known | (dark_spots > 0)).astype(np.uint8)


def kept_at_size(mask: np.ndarray, size: int) -> float | None:
    """Share of the mask's pixels still marked if the model sees the picture with its longest side
    at `size` pixels.

    The mask is shrunk like a photo (each small pixel = the average of the big ones it covers), a
    small pixel counts as marked when at least half of it is marked, and the result is enlarged back
    and compared with the original. Thin lines vanish when the size is too small. None = empty mask.
    """
    total = int(mask.sum())
    if total == 0:
        return None
    height, width = mask.shape
    scale = min(1.0, size / max(height, width))
    if scale == 1.0:
        return 1.0
    small_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    small = cv2.resize(mask.astype(np.float32), small_size, interpolation=cv2.INTER_AREA)
    back = cv2.resize((small >= 0.5).astype(np.uint8), (width, height),
                      interpolation=cv2.INTER_NEAREST)  # fmt: skip
    return float((back & mask).sum()) / total


def line_width(mask: np.ndarray) -> float | None:
    """Typical width in pixels of the marked lines, from the distance between the middle of a line
    and the first unmarked pixel, taken on the line's middle (local maxima of the distance map):
    a line w pixels wide has 2 x distance - 1 = w (exact for odd widths, 1 px more for even)."""
    if not mask.any():
        return None
    distance = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    ridge = (distance >= cv2.dilate(distance, np.ones((3, 3), np.uint8))) & (mask > 0)
    return float(2 * np.median(distance[ridge]) - 1)


def share_inside(mask: np.ndarray, box: tuple[int, int, int, int]) -> float | None:
    """Share of the mask's pixels inside (left, top, right, bottom)."""
    total = int(mask.sum())
    if total == 0:
        return None
    left, top, right, bottom = box
    return float(mask[top:bottom, left:right].sum()) / total


def relative_spread(mask: np.ndarray, face) -> dict | None:
    """Where the marked pixels lie relative to the face box: 5th and 95th percentiles of x and y
    as fractions of the face width / height (0 = left / top edge of the box, 1 = right / bottom)."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    rx = (xs - face.x) / face.width
    ry = (ys - face.y) / face.height
    return {"x": [round(float(v), 2) for v in np.percentile(rx, [5, 95])],
            "y": [round(float(v), 2) for v in np.percentile(ry, [5, 95])]}  # fmt: skip


def patches(mask: np.ndarray, face_area: float) -> dict:
    """Separate marked patches: how many and their median size as % of the face box."""
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    areas = stats[1:, cv2.CC_STAT_AREA]
    return {"count": int(count - 1),
            "median_percent_of_face": round(float(np.median(areas)) / face_area * 100, 3)
            if len(areas) else None}  # fmt: skip
