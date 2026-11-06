"""Scoring the pimple finder the same way for every model (decided 2026-11-06).

Ultralytics scores a model on the images it was trained on (whole photos for v1 / A, tiles for B /
C), so its numbers cannot compare the runs. Here every model is scored on the same WHOLE photos,
in photo pixels:
- a predicted box finds an expert box when they overlap by at least IOU (0.5, as mAP50); each
  expert box can be found once, the most confident prediction first;
- AP50 = area under the precision-recall curve (all-point, as in PASCAL VOC / COCO);
- the best-F1 confidence cutoff, and precision / recall at it or at a given cutoff;
- recall by pimple size (the expert box side in photo pixels), to see whether small ones improve;
- count error per photo against the expert circles (the acne grade comes from a count).
"""

import numpy as np

IOU = 0.5
SIZE_BUCKETS = ((0, 20), (20, 40), (40, 80), (80, 10_000))  # px, side of the expert box


def iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Overlap (intersection over union) of every box of a with every box of b."""
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)))
    x1 = np.maximum(a[:, None, 0], b[None, :, 0])
    y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2])
    y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return inter / (area_a[:, None] + area_b[None, :] - inter)


def match(pred: np.ndarray, scores: np.ndarray, truth: np.ndarray,
          iou: float = IOU) -> tuple[np.ndarray, np.ndarray]:  # fmt: skip
    """(hit per prediction, index of the expert box each prediction found or -1), most confident
    prediction first; each expert box can be found only once."""
    hits = np.zeros(len(pred), dtype=bool)
    found = np.full(len(pred), -1)
    if len(pred) == 0 or len(truth) == 0:
        return hits, found
    overlaps = iou_matrix(pred, truth)
    taken = np.zeros(len(truth), dtype=bool)
    for p in np.argsort(-scores, kind="stable"):
        candidates = np.where(~taken & (overlaps[p] >= iou))[0]
        if len(candidates):
            best = candidates[np.argmax(overlaps[p, candidates])]
            taken[best] = True
            hits[p], found[p] = True, best
    return hits, found


def score(photos: list[dict], cutoff: float | None = None) -> dict:
    """photos: [{"pred", "scores", "truth"}] (numpy, photo pixels). Precision / recall are given
    at `cutoff`, or at the best-F1 cutoff when it is None."""
    all_scores, all_hits = [], []
    sizes, found_at = [], []  # per expert box: its size, and the score it was found with (or -1)
    total_truth = 0
    for photo in photos:
        hits, found = match(photo["pred"], photo["scores"], photo["truth"])
        all_scores.append(photo["scores"])
        all_hits.append(hits)
        truth = photo["truth"]
        total_truth += len(truth)
        best = np.full(len(truth), -1.0)
        for p, t in enumerate(found):
            if t >= 0:
                best[t] = max(best[t], photo["scores"][p])
        found_at.append(best)
        sizes.append(np.minimum(truth[:, 2] - truth[:, 0], truth[:, 3] - truth[:, 1])
                     if len(truth) else np.zeros(0))  # fmt: skip
    scores_all = np.concatenate(all_scores) if all_scores else np.zeros(0)
    hits_all = np.concatenate(all_hits) if all_hits else np.zeros(0, dtype=bool)
    order = np.argsort(-scores_all, kind="stable")
    tp = np.cumsum(hits_all[order])
    fp = np.cumsum(~hits_all[order])
    recall = tp / max(total_truth, 1)
    precision = tp / np.maximum(tp + fp, 1)
    ap = average_precision(recall, precision)
    f1 = 2 * precision * recall / np.maximum(precision + recall, 1e-9)
    if cutoff is None:
        cutoff = float(scores_all[order][np.argmax(f1)]) if len(f1) else 0.0
    kept = scores_all >= cutoff
    tp_at = int(hits_all[kept].sum())
    sizes_all = np.concatenate(sizes) if sizes else np.zeros(0)
    found_all = np.concatenate(found_at) if found_at else np.zeros(0)
    by_size = {}
    for low, high in SIZE_BUCKETS:
        inside = (sizes_all >= low) & (sizes_all < high)
        found_share = float((found_all[inside] >= cutoff).mean()) if inside.any() else None
        by_size[f"{low}-{high if high < 10_000 else 'up'} px"] = {
            "boxes": int(inside.sum()),
            "recall": round(found_share, 3) if found_share is not None else None,
        }
    counts = [(int((p["scores"] >= cutoff).sum()), len(p["truth"])) for p in photos]
    return {
        "photos": len(photos),
        "expert_boxes": total_truth,
        "AP50": round(ap, 4),
        "cutoff": round(cutoff, 3),
        "precision": round(tp_at / max(int(kept.sum()), 1), 4),
        "recall": round(tp_at / max(total_truth, 1), 4),
        "recall_by_size": by_size,
        "count_mean_abs_error": round(float(np.mean([abs(a - b) for a, b in counts])), 2)
        if counts else None,
        "count_mean_bias": round(float(np.mean([a - b for a, b in counts])), 2) if counts else None,
    }


def average_precision(recall: np.ndarray, precision: np.ndarray) -> float:
    """Area under the precision-recall curve, precision made non-increasing (all-point)."""
    if len(recall) == 0:
        return 0.0
    r = np.concatenate([[0.0], recall, [recall[-1]]])
    p = np.concatenate([[1.0], precision, [0.0]])
    p = np.maximum.accumulate(p[::-1])[::-1]
    return float(np.sum((r[1:] - r[:-1]) * p[1:]))
