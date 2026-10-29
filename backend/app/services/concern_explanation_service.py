"""What the app tells the user about each concern, by severity (Phase 3 Step 2.4b, 2026-10-29).

Each step already explains itself (the rule's notes); this explains the concern as a whole:
what the routine does for it, when to expect results, and when to ask for more help:
- mild: the routine is enough to start with;
- moderate: if it does not improve after 8-12 weeks, ask a pharmacist or a dermatologist (a
  stronger, non-cosmetic treatment may be needed: the app itself recommends cosmetics only);
- severe: no treatment step is added, the routine stays gentle, and the user is referred to a
  dermatologist (the map shows clinics near them).
Wording rules (the student's decision): "visible concern", never disease, diagnosis or cure,
and never "healthy skin". The texts are original and written once here, like the quiz.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Explanation:
    routine_focus: str  # what the routine does for the concern
    expect: str | None  # when results usually show (None when nothing is added for it)
    advice: str | None  # when to ask for more help (None = nothing to add)


FOCUS_AND_EXPECT = {
    "acne": (
        "A salicylic acid cleanser keeps pores clear and an evening anti-blemish treatment calms "
        "breakouts.",
        "Breakouts usually start to improve after 4-6 weeks; give each product at least 8 weeks.",
    ),
    "whiteheads": (
        "Salicylic acid keeps pores clear so fewer whiteheads form. Never squeeze them: it can "
        "leave marks.",
        "Whiteheads usually become fewer after 6-8 weeks.",
    ),
    "pustules": (
        "A hydrocolloid patch protects an inflamed spot overnight and absorbs its fluid. Never "
        "squeeze it: it can leave a mark.",
        "A single inflamed spot usually calms down within a few days.",
    ),
    "oiliness": (
        "An oil-free moisturizer and niacinamide help control shine without drying the skin. "
        "Skipping moisturizer can make the skin produce more oil.",
        "Shine usually decreases after about 4 weeks.",
    ),
    "dryness": (
        "A gentle cream cleanser, hyaluronic acid and a rich ceramide cream bring back moisture "
        "and support the skin barrier.",
        "The skin usually feels more comfortable within 1-2 weeks.",
    ),
    "redness": (
        "Soothing ingredients and a mineral sunscreen calm the skin. Avoid very hot water, scrubs "
        "and fragranced products.",
        "Redness usually looks calmer after 4-8 weeks.",
    ),
    "dark_spots": (
        "Vitamin C or azelaic acid fade spots gradually. Sunscreen every morning is essential: "
        "without it, spots come back darker.",
        "Spots fade slowly: expect 8-12 weeks.",
    ),
    "wrinkles": (
        "Retinol (or a peptide serum during pregnancy) supports smoother-looking skin, and daily "
        "sunscreen prevents new lines.",
        "Fine lines usually look softer after about 12 weeks.",
    ),
}

MODERATE_ADVICE = (
    "If there is no improvement after 8-12 weeks, a pharmacist or dermatologist can suggest a "
    "stronger treatment."
)
SEVERE_FOCUS = (
    "No treatment product is added for this concern: your routine stays gentle so it does not "
    "irritate the skin."
)
SEVERE_ADVICE = (
    "This looks like more than a skincare routine should handle on its own. Please see a "
    "dermatologist; the map shows clinics near you."
)


def explain(concern: str, severity: str) -> Explanation:
    focus, expect = FOCUS_AND_EXPECT[concern]
    if severity == "severe":
        return Explanation(routine_focus=SEVERE_FOCUS, expect=None, advice=SEVERE_ADVICE)
    advice = MODERATE_ADVICE if severity == "moderate" else None
    return Explanation(routine_focus=focus, expect=expect, advice=advice)
