"""Acne grade from the detector's pimple count, calibrated on VALIDATION (decided 2026-11-21).

The Hayashi table applied to our raw count agreed with ACNE04's dermatologists on only ~25% of the
validation faces: the ACNE04-v2 circles (what the model learned) mark far more lesions than the
dermatologists counted for their grade. So the count limits are learned instead: the two limits
that agree best with the expert grades on the validation photos. The app shows three levels
(severe -> dermatologist referral), so ACNE04's "very severe" is counted as severe.
"""

import itertools

LEVELS = ("mild", "moderate", "severe")


def app_level(expert_grade: str) -> str:
    return "severe" if expert_grade == "very_severe" else expert_grade


def grade_from_count(count: int, limits: tuple[int, int]) -> str:
    """mild up to limits[0] pimples, moderate up to limits[1], severe above."""
    return LEVELS[sum(count > limit for limit in limits)]


def fit_limits(counts: list[int], grades: list[str]) -> tuple[int, int]:
    """The (low, high) limits with the most agreement; ties -> the lowest limits (a stricter grade
    errs towards a dermatologist referral)."""
    if not counts:
        raise ValueError("no photos to fit the limits on")
    expected = [app_level(g) for g in grades]
    candidates = sorted(set(counts))
    best, best_limits = -1, None
    for limits in itertools.combinations_with_replacement(candidates, 2):
        right = sum(grade_from_count(c, limits) == g for c, g in zip(counts, expected, strict=True))
        if right > best:
            best, best_limits = right, limits
    return tuple(int(v) for v in best_limits)


def agreement(counts: list[int], grades: list[str], limits: tuple[int, int]) -> dict:
    """Share of photos with the expert's level, and the confusion table expert -> ours."""
    expected = [app_level(g) for g in grades]
    ours = [grade_from_count(c, limits) for c in counts]
    table = {e: {o: 0 for o in LEVELS} for e in LEVELS}
    for e, o in zip(expected, ours, strict=True):
        table[e][o] += 1
    right = sum(e == o for e, o in zip(expected, ours, strict=True))
    return {"photos": len(counts), "agreement": round(right / max(len(counts), 1), 4),
            "expert_to_ours": table}  # fmt: skip
