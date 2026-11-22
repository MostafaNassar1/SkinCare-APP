"""Run the pimple finder on a whole photo, either at once or tile by tile (decided 2026-11-06).

- "whole": the photo shrunk to `imgsz` (how v1 and run A were trained).
- "tiled": overlapping TILE x TILE pieces at FULL resolution (how runs B and C were trained), the
  boxes moved back to photo coordinates, and duplicates in the overlaps merged by non-maximum
  suppression (the more confident of two boxes that overlap by MERGE_IOU or more wins).
Both return boxes in the photo's own pixels, so every model is scored the same way.
"""

from dataclasses import dataclass

import numpy as np
import torch
from PIL import Image
from torchvision.ops import nms

from skincare_ml.yolo_tiles import OVERLAP, TILE, tile_origins

MERGE_IOU = 0.5
MAX_DETECTIONS = 434  # the most pimples labelled on one training photo (Ultralytics' own setting)


@dataclass(frozen=True)
class Detections:
    boxes: np.ndarray  # N x 4, x1 y1 x2 y2 in photo pixels
    scores: np.ndarray  # N, model confidence


def _run(model, images: list[Image.Image], imgsz: int, conf: float, device) -> list[Detections]:
    results = model.predict(images, imgsz=imgsz, conf=conf, iou=0.7, max_det=MAX_DETECTIONS,
                            device=device, verbose=False)  # fmt: skip
    return [Detections(r.boxes.xyxy.cpu().numpy().reshape(-1, 4),
                       r.boxes.conf.cpu().numpy().reshape(-1)) for r in results]  # fmt: skip


def predict_whole(model, photo: Image.Image, conf: float, imgsz: int = 1280,
                  device=None) -> Detections:  # fmt: skip
    return _run(model, [photo], imgsz, conf, device)[0]


def predict_tiled(
    model, photo: Image.Image, conf: float, imgsz: int = TILE, tile: int = TILE,
    overlap: int = OVERLAP, batch: int = 8, device=None,
) -> Detections:  # fmt: skip
    width, height = photo.size
    origins = [(x, y) for y in tile_origins(height, tile, overlap)
               for x in tile_origins(width, tile, overlap)]  # fmt: skip
    all_boxes, all_scores = [], []
    for start in range(0, len(origins), batch):
        group = origins[start : start + batch]
        crops = [photo.crop((x, y, min(x + tile, width), min(y + tile, height))) for x, y in group]
        for (x, y), found in zip(group, _run(model, crops, imgsz, conf, device), strict=True):
            all_boxes.append(found.boxes + np.array([x, y, x, y], dtype=np.float32))
            all_scores.append(found.scores)
    return merge(np.concatenate(all_boxes) if all_boxes else np.zeros((0, 4)),
                 np.concatenate(all_scores) if all_scores else np.zeros(0))  # fmt: skip


def merge(boxes: np.ndarray, scores: np.ndarray, iou: float = MERGE_IOU) -> Detections:
    """Keep the more confident of overlapping boxes (the same pimple seen in two tiles)."""
    if len(boxes) == 0:
        return Detections(np.zeros((0, 4), dtype=np.float32), np.zeros(0, dtype=np.float32))
    keep = nms(torch.as_tensor(boxes, dtype=torch.float32),
               torch.as_tensor(scores, dtype=torch.float32), iou).numpy()  # fmt: skip
    keep = keep[np.argsort(-scores[keep], kind="stable")][:MAX_DETECTIONS]
    return Detections(boxes[keep].astype(np.float32), scores[keep].astype(np.float32))
