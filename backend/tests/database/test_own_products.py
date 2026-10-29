"""Migration 0011: cosmetics only, retinoid conflicts, the user's own products, admin review list."""

from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    ConcernRecommendationMapping,
    Ingredient,
    IngredientConflict,
    Product,
    ProductSuggestion,
    Routine,
    RoutineStep,
    RoutineStepIngredient,
    SkinConcern,
)


def ingredient(db: Session, name: str) -> Ingredient:
    return db.scalar(select(Ingredient).where(Ingredient.name == name))


def make_step(db: Session, app_user, **overrides) -> RoutineStep:
    routine = Routine(user_id=app_user.id)
    db.add(routine)
    db.flush()
    fields = {
        "routine_id": routine.id,
        "time_of_day": "evening",
        "step_order": 2,
        "step_category": "treat",
        "title": "Acne Treatment",
        "product_type": "Non-prescription anti-blemish treatment",
    }
    step = RoutineStep(**(fields | overrides))
    db.add(step)
    db.flush()
    return step


def make_product(db: Session) -> Product:
    product = Product(
        brand="Test Brand", name="Blemish Gel", step_category="treat", directions="Thin layer.",
        inci_list="Aqua, Glycerin", source_url="https://example.com/gel",
        checked_on=date(2026, 10, 29),
    )  # fmt: skip
    db.add(product)
    db.flush()
    return product


# ---------- cosmetics only ----------


def test_no_active_rule_recommends_a_medicine(db: Session):
    medicines = {ingredient(db, "Adapalene").id, ingredient(db, "Benzoyl Peroxide").id}

    active = db.scalars(
        select(ConcernRecommendationMapping).where(
            ConcernRecommendationMapping.is_active,
            ConcernRecommendationMapping.ingredient_id.in_(medicines),
        )
    ).all()

    assert active == []


def test_medicine_rules_became_cosmetic_steps(db: Session):
    rows = db.execute(
        select(SkinConcern.name, ConcernRecommendationMapping.step_title,
               ConcernRecommendationMapping.product_type, ConcernRecommendationMapping.is_active)
        .join(SkinConcern, SkinConcern.id == ConcernRecommendationMapping.skin_concern_id)
        .where(ConcernRecommendationMapping.step_category == "treat",
               SkinConcern.name.in_(["acne", "whiteheads", "pustules"]))
    ).all()  # fmt: skip

    active = {(name, title, kind) for name, title, kind, is_active in rows if is_active}
    assert active == {
        ("acne", "Acne Treatment", "Non-prescription anti-blemish treatment"),
        ("whiteheads", "Clogged Pore Treatment", "Non-prescription unclogging treatment"),
        ("pustules", "Spot Treatment", "Hydrocolloid pimple patch"),
    }
    # the acne adapalene rule is kept for history, switched off
    assert [(name, kind) for name, _, kind, is_active in rows if not is_active] == [
        ("acne", "Adapalene gel")
    ]


# ---------- new ingredients and conflicts ----------


@pytest.mark.parametrize(
    ("name", "avoid_in_pregnancy"),
    [("Retinal", True), ("Retinyl Palmitate", True), ("Lactic Acid", False),
     ("LHA (Capryloyl Salicylic Acid)", False)],
)  # fmt: skip
def test_new_actives_and_their_pregnancy_flag(db: Session, name, avoid_in_pregnancy):
    found = ingredient(db, name)

    assert found.kind == "active"
    assert found.avoid_during_pregnancy is avoid_in_pregnancy


@pytest.mark.parametrize(
    ("a", "b"),
    [("Retinal", "Glycolic Acid"), ("Retinol", "Lactic Acid"),
     ("Retinyl Palmitate", "LHA (Capryloyl Salicylic Acid)"), ("Retinol", "Retinal"),
     ("Lactic Acid", "Salicylic Acid")],
)  # fmt: skip
def test_retinoids_conflict_with_acids_and_each_other(db: Session, a, b):
    ids = sorted([ingredient(db, a).id, ingredient(db, b).id])

    conflict = db.scalar(
        select(IngredientConflict).where(
            IngredientConflict.ingredient_a_id == ids[0],
            IngredientConflict.ingredient_b_id == ids[1],
        )
    )

    assert conflict is not None and conflict.reason


def test_products_are_suitable_for_sensitive_skin_by_default(db: Session):
    product = make_product(db)

    assert product.suitable_for_sensitive is True
    assert product.image_url is None and product.image_source_url is None


# ---------- the user's own product ----------


def test_own_product_with_ticked_ingredients(db: Session, app_user):
    step = make_step(db, app_user, custom_product_name="My cousin's acne cream")
    db.add(RoutineStepIngredient(routine_step_id=step.id, ingredient_id=ingredient(db, "Retinol").id))
    db.flush()

    assert step.product_id is None
    assert step.custom_product_name == "My cousin's acne cream"


def test_a_step_has_a_catalogue_product_or_an_own_product_not_both(db: Session, app_user):
    product = make_product(db)

    with pytest.raises(IntegrityError, match="routine_steps_one_product_check"):
        make_step(db, app_user, product_id=product.id, custom_product_name="Something else")


def test_a_ticked_ingredient_is_listed_once(db: Session, app_user):
    step = make_step(db, app_user, custom_product_name="Own cream")
    retinol = ingredient(db, "Retinol").id
    db.add(RoutineStepIngredient(routine_step_id=step.id, ingredient_id=retinol))
    db.flush()

    db.add(RoutineStepIngredient(routine_step_id=step.id, ingredient_id=retinol))
    with pytest.raises(IntegrityError, match="routine_step_ingredients_routine_step_id_ingredient"):
        db.flush()


# ---------- admin review list ----------


def test_a_suggestion_starts_pending(db: Session, app_user):
    suggestion = ProductSuggestion(user_id=app_user.id, name="Some Serum", step_category="treat")
    db.add(suggestion)
    db.flush()

    assert suggestion.status == "pending"
    assert suggestion.product_id is None and suggestion.created_at is not None


def test_suggestion_status_is_checked(db: Session, app_user):
    db.add(ProductSuggestion(user_id=app_user.id, name="X", step_category="treat", status="maybe"))
    with pytest.raises(IntegrityError, match="product_suggestions_status_check"):
        db.flush()


def test_a_suggestion_outlives_the_deleted_account(db: Session, app_user):
    suggestion = ProductSuggestion(user_id=app_user.id, name="Some Serum", step_category="treat")
    db.add(suggestion)
    db.flush()

    db.execute(text("DELETE FROM users WHERE id = :id"), {"id": app_user.id})
    db.expire_all()

    # the product name stays useful for the admin; nothing links it to the person any more
    assert db.get(ProductSuggestion, suggestion.id).user_id is None
