"""Scoring the pimple finder the same way for every model (decided 2026-11-06).

Ultralytics scores a model on the images it was trained on (whole photos for v1 / A, tiles for B /
C), so its numbers cannot compare the runs. Here every model is scored on the same WHOLE photos,
in photo pixels:
- a predicted box finds an expert box when they overlap by at least IOU (0.5, as mAP50); each
  expert box can be found once, the most confident prediction first;
- AP50 = area under the precision-recall curve (all-point, as in PASCAL VOC / COCO);
- the best-F1 confidence cutoff, and precision / recall at it or at a given cutoff;
- recall by pimple size (the expert box side in photo pixels), to see whether small ones improve;
- count error per photo against the expert circles (the acne grade comes from a count);
- bootstrap 95% ranges, to tell real differences between models from luck of the photos.
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


def match_centre(pred: np.ndarray, scores: np.ndarray,
                 truth: np.ndarray) -> tuple[np.ndarray, np.ndarray]:  # fmt: skip
    """As match, but a prediction finds an expert box when its CENTRE lies inside it: the dot the
    app draws is on the pimple (added 2026-11-21). The box rule punishes a box shifted by a few
    pixels on a 15-pixel pimple; this rule measures what the user sees. Both are reported."""
    hits = np.zeros(len(pred), dtype=bool)
    found = np.full(len(pred), -1)
    if len(pred) == 0 or len(truth) == 0:
        return hits, found
    cx = (pred[:, 0] + pred[:, 2]) / 2
    cy = (pred[:, 1] + pred[:, 3]) / 2
    taken = np.zeros(len(truth), dtype=bool)
    truth_cx = (truth[:, 0] + truth[:, 2]) / 2
    truth_cy = (truth[:, 1] + truth[:, 3]) / 2
    for p in np.argsort(-scores, kind="stable"):
        inside = (~taken & (truth[:, 0] <= cx[p]) & (cx[p] <= truth[:, 2])
                  & (truth[:, 1] <= cy[p]) & (cy[p] <= truth[:, 3]))  # fmt: skip
        candidates = np.where(inside)[0]
        if len(candidates):  # the expert box whose centre is closest
            distance = (truth_cx[candidates] - cx[p]) ** 2 + (truth_cy[candidates] - cy[p]) ** 2
            best = candidates[np.argmin(distance)]
            taken[best] = True
            hits[p], found[p] = True, best
    return hits, found


MATCHERS = {"box": match, "centre": match_centre}


def score(photos: list[dict], cutoff: float | None = None, rule: str = "box") -> dict:
    """photos: [{"pred", "scores", "truth"}] (numpy, photo pixels). Precision / recall are given
    at `cutoff`, or at the best-F1 cutoff when it is None. rule: "box" (IoU >= 0.5, as mAP50) or
    "centre" (the dot is on the pimple)."""
    matcher = MATCHERS[rule]
    all_scores, all_hits = [], []
    sizes, found_at = [], []  # per expert box: its size, and the score it was found with (or -1)
    total_truth = 0
    for photo in photos:
        hits, found = matcher(photo["pred"], photo["scores"], photo["truth"])
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


def _ap_precision_recall(scores: np.ndarray, hits: np.ndarray, total_truth: int,
                         cutoff: float) -> tuple[float, float, float]:  # fmt: skip
    order = np.argsort(-scores, kind="stable")
    tp = np.cumsum(hits[order])
    fp = np.cumsum(~hits[order])
    ap = average_precision(tp / max(total_truth, 1), tp / np.maximum(tp + fp, 1))
    kept = scores >= cutoff
    tp_at = int(hits[kept].sum())
    return ap, tp_at / max(int(kept.sum()), 1), tp_at / max(total_truth, 1)


def bootstrap(runs: dict[str, list[dict]], cutoffs: dict[str, float], rounds: int = 1000,
              seed: int = 2026, rule: str = "box") -> dict:  # fmt: skip
    """How sure the scores are (added 2026-11-21): the PHOTOS are drawn again with replacement
    `rounds` times and every model is re-scored on each draw. 95% range = the middle 95% of those
    scores. The same draws are used for every model (paired), so "A beats C in x% of the draws"
    compares the models on identical photo sets. runs: model -> rows of the SAME photos, in the
    same order (see score); cutoffs: each model's confidence cutoff for precision / recall."""
    names = list(runs)
    sizes = {len(rows) for rows in runs.values()}
    if len(sizes) != 1:
        raise ValueError("every model must be scored on the same photos")
    count = sizes.pop()
    per_photo = {}
    for name, rows in runs.items():
        per_photo[name] = [(np.asarray(r["scores"], dtype=float),
                            MATCHERS[rule](r["pred"], r["scores"], r["truth"])[0], len(r["truth"]))
                           for r in rows]  # fmt: skip
    rng = np.random.default_rng(seed)
    drawn = {name: np.zeros((rounds, 3)) for name in names}  # AP50, precision, recall
    for k in range(rounds):
        pick = rng.integers(0, count, count)
        for name in names:
            rows = per_photo[name]
            drawn[name][k] = _ap_precision_recall(
                np.concatenate([rows[i][0] for i in pick]),
                np.concatenate([rows[i][1] for i in pick]),
                sum(rows[i][2] for i in pick), cutoffs[name])  # fmt: skip

    def middle(values: np.ndarray) -> list[float]:
        return [round(float(v), 4) for v in np.percentile(values, [2.5, 97.5])]

    result = {"rounds": rounds, "photos": count, "models": {}, "pairs": {}}
    for name in names:
        result["models"][name] = {metric: middle(drawn[name][:, i])
                                  for i, metric in enumerate(("AP50", "precision", "recall"))}  # fmt: skip
    for i, first in enumerate(names):
        for second in names[i + 1 :]:
            difference = drawn[first][:, 0] - drawn[second][:, 0]
            result["pairs"][f"{first} - {second}"] = {
                "AP50_difference_95": middle(difference),
                "first_better_share": round(float((difference > 0).mean()), 3),
            }
    return result


def average_precision(recall: np.ndarray, precision: np.ndarray) -> float:
    """Area under the precision-recall curve, precision made non-increasing (all-point)."""
    if len(recall) == 0:
        return 0.0
    r = np.concatenate([[0.0], recall, [recall[-1]]])
    p = np.concatenate([[1.0], precision, [0.0]])
    p = np.maximum.accumulate(p[::-1])[::-1]
    return float(np.sum((r[1:] - r[:-1]) * p[1:]))
