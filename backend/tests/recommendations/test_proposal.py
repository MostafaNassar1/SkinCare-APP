"""The rules engine's proposal: which steps a user needs and which real products suit them."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Ingredient, Product, ProductIngredient, RuleProduct, User, UserAllergy
from app.services.recommendation_service import ProposedStep, propose

CETAPHIL = "Gentle Skin Cleanser"
CERAVE_FOAMING = "Foaming Cleanser"
SENSIBIO_GEL = "Sensibio Gel Moussant"
CERAVE_SA = "SA Smoothing Cleanser"
SEBIUM = "Sébium Gel Moussant Actif"
TOLERIANE = "Toleriane Dermallergo Fluide"
CERAVE_CREAM = "Moisturising Cream"
ANTHELIOS = "Anthelios UVMune 400 Invisible Fluid SPF50+ (non-perfumed)"
ANTHELIOS_OIL = "Anthelios UVMune 400 Oil Control Fluid SPF50+"
AVENE_MINERAL = "SPF 50+ Mineral Fluid"
CERAVE_SPF = "Invisible Hydrating Fluid Sunscreen SPF50+"
ACNE_TREATMENTS = [
    "Effaclar Duo+M",
    "Blemish Control Gel",
    "Cleanance Comedomed",
    "Biology AC Perfect Anti-Blemish Fluid",
]


def allergic_to(db: Session, user: User, *names: str) -> None:
    for name in names:
        ingredient = db.scalar(select(Ingredient).where(Ingredient.name == name))
        db.add(UserAllergy(user_id=user.id, ingredient_id=ingredient.id))
    db.flush()


def layout(steps: list[ProposedStep]) -> list[tuple[str, str, str]]:
    return [(s.time_of_day, s.step_category, s.title) for s in steps]


def step(steps: list[ProposedStep], time_of_day: str, title: str) -> ProposedStep:
    return next(s for s in steps if (s.time_of_day, s.title) == (time_of_day, title))


def names(s: ProposedStep) -> list[str]:
    return [p.name for p in s.products]


# ---------- the base routine ----------


def test_no_concern_gives_the_base_routine(db: Session, app_user):
    proposal = propose(db, app_user, {})

    assert layout(proposal.steps) == [
        ("morning", "cleanse", "Cleanse"),
        ("morning", "moisturize", "Moisturize"),
        ("morning", "protect", "Sunscreen"),
        ("evening", "cleanse", "Cleanse"),
        ("evening", "moisturize", "Moisturize"),
    ]
    assert names(proposal.steps[0]) == [CETAPHIL, CERAVE_FOAMING, SENSIBIO_GEL]
    assert names(proposal.steps[2]) == [ANTHELIOS, AVENE_MINERAL, ANTHELIOS_OIL]
    assert all(s.concerns == [] for s in proposal.steps)
    assert proposal.skipped == [] and proposal.see_dermatologist == []


def test_concern_products_come_first_then_the_base_ones(db: Session, app_user):
    proposal = propose(db, app_user, {"acne": "mild"})

    cleanse = step(proposal.steps, "evening", "Cleanse")
    assert cleanse.concerns == ["acne"]
    assert cleanse.product_type == "Salicylic acid foaming cleanser"
    assert names(cleanse) == [CERAVE_SA, SEBIUM, CETAPHIL, CERAVE_FOAMING, SENSIBIO_GEL]
    assert names(step(proposal.steps, "evening", "Acne Treatment")) == ACNE_TREATMENTS


def test_severity_below_the_rule_minimum_adds_nothing(db: Session, app_user):
    mild = propose(db, app_user, {"whiteheads": "mild"})
    moderate = propose(db, app_user, {"whiteheads": "moderate"})

    assert "Clogged Pore Treatment" not in [s.title for s in mild.steps]
    assert ("evening", "treat", "Clogged Pore Treatment") in layout(moderate.steps)


# ---------- several concerns at once ----------


def test_acne_and_whiteheads_share_one_treatment(db: Session, app_user):
    proposal = propose(db, app_user, {"acne": "mild", "whiteheads": "moderate"})

    treatments = [s for s in proposal.steps if s.step_category == "treat"]
    assert [(s.title, s.concerns) for s in treatments] == [
        ("Acne Treatment", ["acne", "whiteheads"])
    ]
    assert names(treatments[0]) == ACNE_TREATMENTS
    assert step(proposal.steps, "morning", "Cleanse").concerns == ["acne", "whiteheads"]


def test_a_spot_patch_is_not_merged_with_the_acne_treatment(db: Session, app_user):
    proposal = propose(db, app_user, {"acne": "mild", "pustules": "mild"})

    evening = [s.title for s in proposal.steps if s.time_of_day == "evening"]
    assert evening == ["Cleanse", "Acne Treatment", "Spot Treatment", "Moisturize"]


def test_redness_and_dark_spots_share_the_azelaic_acid_step(db: Session, app_user):
    proposal = propose(db, app_user, {"redness": "moderate", "dark_spots": "moderate"})

    evening_treatments = [
        s for s in proposal.steps if (s.time_of_day, s.step_category) == ("evening", "treat")
    ]
    assert [(s.title, s.concerns) for s in evening_treatments] == [
        ("Redness Treatment", ["redness", "dark_spots"])
    ]
    sunscreen = step(proposal.steps, "morning", "Sunscreen")
    assert sunscreen.concerns == ["dark_spots", "redness"]  # SPF 50 rule has the higher priority
    assert names(sunscreen) == [ANTHELIOS, CERAVE_SPF, AVENE_MINERAL, ANTHELIOS_OIL]


def test_every_concern_gets_its_steps_in_one_routine(db: Session, app_user):
    proposal = propose(db, app_user, {"acne": "mild", "wrinkles": "mild", "dryness": "mild"})

    assert layout(proposal.steps) == [
        ("morning", "cleanse", "Cleanse"),
        ("morning", "treat", "Hydrating Serum"),
        ("morning", "moisturize", "Deep Moisturize"),
        ("morning", "protect", "Sunscreen"),
        ("evening", "cleanse", "Cleanse"),
        ("evening", "treat", "Anti-Aging Treatment"),
        ("evening", "treat", "Acne Treatment"),
        ("evening", "treat", "Firming Serum"),
        ("evening", "moisturize", "Deep Moisturize"),
    ]
    retinol = step(proposal.steps, "evening", "Anti-Aging Treatment")
    assert retinol.days_of_week == 21  # Mon, Wed, Fri (the alternate nights come in Part 2.3b)


def test_a_severe_concern_keeps_the_base_routine_and_refers(db: Session, app_user):
    proposal = propose(db, app_user, {"acne": "severe", "wrinkles": "mild"})

    assert proposal.see_dermatologist == ["acne"]
    assert all("acne" not in s.concerns for s in proposal.steps)
    assert names(step(proposal.steps, "morning", "Cleanse"))[0] == CETAPHIL
    assert "Anti-Aging Treatment" in [s.title for s in proposal.steps]


# ---------- the user's situation ----------


def test_pregnancy_skips_retinol_and_keeps_the_peptide_serum(db: Session, app_user):
    app_user.profile.is_pregnant_or_breastfeeding = True

    proposal = propose(db, app_user, {"wrinkles": "mild"})

    assert [(s.title, s.reason) for s in proposal.skipped] == [
        ("Anti-Aging Treatment", "pregnancy")
    ]
    assert names(step(proposal.steps, "evening", "Firming Serum")) == [
        "The 6 Peptide Skin Booster Serum"
    ]


def test_a_fragrance_allergy_removes_fragranced_products(db: Session, app_user):
    allergic_to(db, app_user, "Fragrance (Parfum)")

    proposal = propose(db, app_user, {"acne": "mild", "oiliness": "mild"})

    assert names(step(proposal.steps, "evening", "Acne Treatment")) == [
        "Blemish Control Gel",
        "Cleanance Comedomed",
    ]
    # Effaclar MAT (fragrance) and Hydra Genius (fragrance + essential oils) are gone
    assert names(step(proposal.steps, "morning", "Moisturize")) == [TOLERIANE, CERAVE_CREAM]


def test_an_allergy_can_leave_a_treatment_without_products(db: Session, app_user):
    allergic_to(db, app_user, "Propylene Glycol")

    proposal = propose(db, app_user, {"redness": "moderate"})

    assert [(s.title, s.reason) for s in proposal.skipped] == [("Redness Treatment", "allergy")]


def test_sensitive_skin_gets_only_gentle_products(db: Session, app_user):
    app_user.profile.skin_type = "sensitive"

    proposal = propose(db, app_user, {"dark_spots": "mild", "acne": "mild"})

    assert [(s.title, s.reason) for s in proposal.skipped] == [
        ("Brightening Serum", "sensitive_skin")
    ]
    assert names(step(proposal.steps, "evening", "Acne Treatment")) == ["Cleanance Comedomed"]
    assert names(step(proposal.steps, "morning", "Sunscreen")) == [CERAVE_SPF, AVENE_MINERAL]


def test_mixed_reasons_are_reported_as_no_safe_product(db: Session, app_user):
    # a second vitamin C serum with fragrance next to COSRX 23% (not for sensitive skin)
    rule_id = step(propose(db, app_user, {"dark_spots": "mild"}).steps, "morning",
                   "Brightening Serum").mapping_id
    serum = Product(brand="Test", name="Scented C Serum", step_category="treat", directions="-",
                    inci_list="Aqua, Ascorbic Acid, Parfum", source_url="https://example.com",
                    checked_on=date(2026, 10, 29))
    db.add(serum)
    db.flush()
    fragrance = db.scalar(select(Ingredient.id).where(Ingredient.name == "Fragrance (Parfum)"))
    db.add_all([ProductIngredient(product_id=serum.id, ingredient_id=fragrance),
                RuleProduct(mapping_id=rule_id, product_id=serum.id, rank=2)])
    allergic_to(db, app_user, "Fragrance (Parfum)")
    app_user.profile.skin_type = "sensitive"

    proposal = propose(db, app_user, {"dark_spots": "mild"})

    assert [(s.title, s.reason) for s in proposal.skipped] == [
        ("Brightening Serum", "no_safe_product")
    ]  # fmt: skip


def test_the_base_steps_always_stay(db: Session, app_user):
    allergic_to(db, app_user, "Denatured Alcohol")
    app_user.profile.skin_type = "sensitive"

    proposal = propose(db, app_user, {})

    assert names(step(proposal.steps, "morning", "Sunscreen")) == [AVENE_MINERAL]
    assert len(proposal.steps) == 5
