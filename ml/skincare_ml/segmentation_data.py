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
