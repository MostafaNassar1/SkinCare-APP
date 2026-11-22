"""The pimple finder's numbers at FROZEN settings (decided 2026-11-21): the same summary for the
validation photos (when the settings are frozen) and for the one-time final test.

- display cutoff: the dots the app draws (chosen so ~80% of them are on real pimples);
- count cutoff: the pimples counted for the acne grade (best-F1 on validation, a complete count);
- both matching rules: "box" (IoU >= 0.5, the standard benchmark) and "centre" (the dot is on the
  pimple, what the user sees);
- grade agreement with ACNE04's dermatologists (limits from skincare_ml/grading.py);
- bootstrap 95% ranges over the photos.
"""

import numpy as np

from skincare_ml.detection_metrics import bootstrap, score
from skincare_ml.grading import agreement, app_level, grade_from_count

KEPT = ("cutoff", "precision", "recall", "recall_by_size", "count_mean_abs_error",
        "count_mean_bias")  # fmt: skip


def summarise(rows: list[dict], count_cutoff: float, display_cutoff: float,
              limits: tuple[int, int], grades_by_file: dict[str, str],
              rounds: int = 1000, seed: int = 2026) -> dict:  # fmt: skip
    result = {"photos": len(rows), "expert_boxes": int(sum(len(r["truth"]) for r in rows)),
              "AP50_box": score(rows, rule="box")["AP50"],
              "AP50_centre": score(rows, rule="centre")["AP50"]}  # fmt: skip
    for label, cutoff in (("display", display_cutoff), ("count", count_cutoff)):
        for rule in ("box", "centre"):
            scored = score(rows, cutoff, rule)
            result[f"{label}_{rule}"] = {key: scored[key] for key in KEPT}
            if rounds:
                ranges = bootstrap({"m": rows}, {"m": cutoff}, rounds, seed, rule)["models"]["m"]
                result[f"{label}_{rule}"]["ranges_95"] = ranges
    counts = [int((r["scores"] >= count_cutoff).sum()) for r in rows]
    grades = [grades_by_file[r["file"]] for r in rows]
    result["grade"] = agreement(counts, grades, limits)
    if rounds and rows:
        right = np.array([grade_from_count(c, limits) == app_level(g)
                          for c, g in zip(counts, grades, strict=True)])  # fmt: skip
        rng = np.random.default_rng(seed)
        shares = [right[rng.integers(0, len(right), len(right))].mean() for _ in range(rounds)]
        result["grade"]["ranges_95"] = [round(float(v), 4) for v in np.percentile(shares, [2.5, 97.5])]
    return result


def describe(name: str, summary: dict) -> str:
    """A few readable lines for the console."""
    lines = [f"{name}: {summary['photos']} faces, {summary['expert_boxes']} expert pimples, "
             f"AP50 {summary['AP50_box']:.3f} (box) / {summary['AP50_centre']:.3f} (dot on pimple)"]  # fmt: skip
    for key in ("display_centre", "count_centre", "display_box", "count_box"):
        part = summary[key]
        ranges = part.get("ranges_95", {})
        lines.append(f"  {key:15} cutoff {part['cutoff']:.2f}: dots right {part['precision']:.0%} "
                     f"{ranges.get('precision', '')}  pimples found {part['recall']:.0%} "
                     f"{ranges.get('recall', '')}")  # fmt: skip
    grade = summary["grade"]
    lines.append(f"  grade agreement {grade['agreement']:.0%} {grade.get('ranges_95', '')}  "
                 f"expert -> ours {grade['expert_to_ours']}")
    return "\n".join(lines)
