"""Face detection with YuNet (OpenCV Zoo, MIT licence), used as it is (not trained by us).

YuNet only finds faces of the sizes it was trained on: on full-size 3,000-5,000 px photos it finds
none. So it runs on a copy whose longest side is ~640 px, and the boxes are scaled back to the
original photo, from which the crop is taken (small lesions need the full detail).
"""

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

DETECTION_MAX_SIDE = 640
MIN_SCORE = 0.8


@dataclass(frozen=True)
class Face:
    x: float  # box in pixels of the ORIGINAL photo
    y: float
    width: float
    height: float
    score: float
    # eyes, nose tip, mouth corners (x, y) in pixels of the original photo
    landmarks: tuple[tuple[float, float], ...] = ()

    def as_yunet_row(self) -> np.ndarray:
        """The face in YuNet's output layout, which SFace's alignment expects."""
        points = [value for point in self.landmarks for value in point]
        return np.array([self.x, self.y, self.width, self.height, *points, self.score], np.float32)


def detection_scale(width: int, height: int, max_side: int = DETECTION_MAX_SIDE) -> float:
    """Factor that shrinks the photo so its longest side is max_side (never enlarges it)."""
    return min(1.0, max_side / max(width, height))


def crop_box(face: Face, width: int, height: int, margin: float = 0.2) -> tuple[int, int, int, int]:
    """(left, top, right, bottom) around the face plus a margin, kept inside the photo."""
    extra_x, extra_y = face.width * margin, face.height * margin
    left = max(0, int(face.x - extra_x))
    top = max(0, int(face.y - extra_y))
    right = min(width, int(round(face.x + face.width + extra_x)))
    bottom = min(height, int(round(face.y + face.height + extra_y)))
    return left, top, right, bottom


class FaceDetector:
    def __init__(self, model_path: Path, min_score: float = MIN_SCORE):
        self._model_path = str(model_path)
        self._min_score = min_score

    def detect(self, image: np.ndarray) -> list[Face]:
        """Every face found in a BGR image (as read by cv2.imread), best score first."""
        height, width = image.shape[:2]
        scale = detection_scale(width, height)
        small = image
        if scale < 1.0:
            small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        small_height, small_width = small.shape[:2]
        detector = cv2.FaceDetectorYN.create(
            self._model_path, "", (small_width, small_height), self._min_score
        )
        _, found = detector.detect(small)
        if found is None:
            return []
        faces = [
            Face(
                x=float(row[0]) / scale,
                y=float(row[1]) / scale,
                width=float(row[2]) / scale,
                height=float(row[3]) / scale,
                score=float(row[-1]),
                landmarks=tuple(
                    (float(row[i]) / scale, float(row[i + 1]) / scale) for i in range(4, 14, 2)
                ),
            )
            for row in found
        ]
        return sorted(faces, key=lambda face: face.score, reverse=True)


class FaceRecognizer:
    """SFace (OpenCV Zoo, Apache 2.0): a face -> a fingerprint vector; close vectors = same person.

    Used only to keep photos of the same person in the same split, never in the app.
    """

    # Cosine similarity at or above = same person. OpenCV recommends 0.363 for frontal faces, but
    # on ACNE04's angled clinical photos 7% of all pairs passed it and chaining merged 1,008 photos
    # into one group. At 0.65 the largest group (15 photos) is one patient over several visits and
    # borderline pairs were checked by eye (2026-10-26, DATASETS.md).
    SAME_PERSON = 0.65

    def __init__(self, model_path: Path):
        self._model = cv2.FaceRecognizerSF.create(str(model_path), "")

    def fingerprint(self, image: np.ndarray, face: Face) -> np.ndarray:
        aligned = self._model.alignCrop(image, face.as_yunet_row())
        return self._model.feature(aligned).copy()

    def similarity(self, first: np.ndarray, second: np.ndarray) -> float:
        return float(self._model.match(first, second, cv2.FaceRecognizerSF_FR_COSINE))
