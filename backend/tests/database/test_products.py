"""Migration 0010: product catalogue, products on routine steps, new concerns and rules."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    ConcernRecommendationMapping,
    Ingredient,
    Product,
    ProductIngredient,
    Routine,
    RoutineStep,
    RoutineStepProduct,
    RuleProduct,
    SkinConcern,
)


def make_product(**overrides) -> Product:
    fields = {
        "brand": "Test Brand",
        "name": "Gentle Cleanser",
        "step_category": "cleanse",
        "directions": "Massage onto wet skin, then rinse.",
        "inci_list": "Aqua, Glycerin",
        "source_url": "https://example.com/gentle-cleanser",
        "checked_on": date(2026, 10, 28),
    }
    return Product(**(fields | overrides))


def ingredient_id(db: Session, name: str) -> int:
    return db.scalar(select(Ingredient.id).where(Ingredient.name == name))


def rules_of(db: Session, concern: str) -> list[ConcernRecommendationMapping]:
    return list(
        db.scalars(
            select(ConcernRecommendationMapping)
            .join(SkinConcern, SkinConcern.id == ConcernRecommendationMapping.skin_concern_id)
            .where(SkinConcern.name == concern)
            .order_by(ConcernRecommendationMapping.id)
        )
    )


def make_step(db: Session, app_user, **overrides) -> RoutineStep:
    routine = Routine(user_id=app_user.id)
    db.add(routine)
    db.flush()
    fields = {
        "routine_id": routine.id,
        "time_of_day": "morning",
        "step_order": 1,
        "step_category": "cleanse",
        "title": "Cleanse",
        "product_type": "Gentle cleanser",
    }
    step = RoutineStep(**(fields | overrides))
    db.add(step)
    db.flush()
    return step


# ---------- reference data ----------


def test_retinoid_rules_start_three_nights_a_week(db: Session):
    retinoids = {ingredient_id(db, "Adapalene"), ingredient_id(db, "Retinol")}
    rules = db.scalars(
        select(ConcernRecommendationMapping).where(
            ConcernRecommendationMapping.ingredient_id.in_(retinoids)
        )
    ).all()

    # adapalene for acne (deactivated in 0011, cosmetics only) and retinol for wrinkles
    assert len(rules) == 2
    assert {rule.days_of_week for rule in rules} == {1 + 4 + 16}  # Mon, Wed, Fri
    others = db.scalars(
        select(ConcernRecommendationMapping.days_of_week).where(
            ConcernRecommendationMapping.ingredient_id.not_in(retinoids)
            | ConcernRecommendationMapping.ingredient_id.is_(None)
        )
    ).all()
    assert set(others) == {127}  # every day


def test_new_concerns_have_their_rules(db: Session):
    whiteheads = rules_of(db, "whiteheads")
    pustules = rules_of(db, "pustules")

    assert [(r.step_category, r.min_severity) for r in whiteheads] == [
        ("cleanse", "mild"),
        ("treat", "moderate"),
    ]
    assert whiteheads[1].time_of_day == "evening"
    assert [(r.step_category, r.time_of_day) for r in pustules] == [("treat", "evening")]
    # cosmetics only (0011): the products are chosen per rule, not one medicine ingredient
    assert whiteheads[1].ingredient_id is None and whiteheads[1].product_type == (
        "Non-prescription unclogging treatment"
    )
    assert pustules[0].product_type == "Hydrocolloid pimple patch"


def test_allergens_are_never_pregnancy_flags(db: Session):
    allergens = db.scalars(select(Ingredient).where(Ingredient.kind == "allergen")).all()

    assert len(allergens) == 9
    assert all(not a.avoid_during_pregnancy and a.description for a in allergens)


# ---------- products ----------


def test_product_defaults_and_updated_at_trigger(db: Session):
    old = datetime(2000, 1, 1, tzinfo=UTC)
    product = make_product(updated_at=old)  # an INSERT does not fire the update trigger
    db.add(product)
    db.flush()
    assert product.is_active is True

    product.directions = "New directions."
    db.flush()

    assert product.updated_at > old


def test_a_product_is_listed_once_per_brand(db: Session):
    db.add(make_product())
    db.flush()

    db.add(make_product(source_url="https://example.com/other"))
    with pytest.raises(IntegrityError, match="products_brand_name_key"):
        db.flush()


def test_product_step_category_is_checked(db: Session):
    db.add(make_product(step_category="exfoliate"))
    with pytest.raises(IntegrityError, match="products_step_category_check"):
        db.flush()


def test_an_ingredient_in_a_product_cannot_be_deleted(db: Session):
    product = make_product()
    db.add(product)
    db.flush()
    fragrance = db.get(Ingredient, ingredient_id(db, "Fragrance (Parfum)"))
    db.add(ProductIngredient(product_id=product.id, ingredient_id=fragrance.id))
    db.flush()

    with pytest.raises(IntegrityError, match="product_ingredients_ingredient_id_fkey"):
        db.execute(text("DELETE FROM ingredients WHERE id = :id"), {"id": fragrance.id})


def test_rule_products_are_ranked_from_one(db: Session):
    product = make_product()
    db.add(product)
    db.flush()
    rule = rules_of(db, "pustules")[0]

    db.add(RuleProduct(mapping_id=rule.id, product_id=product.id, rank=0))
    with pytest.raises(IntegrityError, match="rule_products_rank_check"):
        db.flush()


def test_a_product_is_linked_to_a_rule_once(db: Session):
    product = make_product()
    db.add(product)
    db.flush()
    rule = rules_of(db, "pustules")[0]
    db.add(RuleProduct(mapping_id=rule.id, product_id=product.id, rank=1))
    db.flush()

    db.add(RuleProduct(mapping_id=rule.id, product_id=product.id, rank=2))
    with pytest.raises(IntegrityError, match="rule_products_mapping_id_product_id_key"):
        db.flush()


# ---------- products on routine steps ----------


def test_existing_steps_count_from_the_start(db: Session, app_user):
    step = make_step(db, app_user)

    assert step.product_id is None
    assert step.needs_product is False
    assert step.product_ready_on is None


def test_a_step_waiting_for_its_product_has_no_ready_date(db: Session, app_user):
    with pytest.raises(IntegrityError, match="routine_steps_product_ready_check"):
        make_step(db, app_user, needs_product=True, product_ready_on=date(2026, 10, 28))


def test_a_product_used_in_a_saved_routine_cannot_be_deleted(db: Session, app_user):
    product = make_product()
    db.add(product)
    db.flush()
    step = make_step(db, app_user, product_id=product.id)
    db.add(RoutineStepProduct(routine_step_id=step.id, product_id=product.id, rank=1))
    db.flush()

    # products are deactivated, never deleted: the routine snapshot stays complete
    with pytest.raises(IntegrityError, match="_product_id_fkey"):
        db.execute(text("DELETE FROM products WHERE id = :id"), {"id": product.id})
