from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    ConcernRecommendationMapping,
    Ingredient,
    IngredientConflict,
    Product,
    ProductIngredient,
    ProductSuggestion,
    RuleProduct,
    SkinConcern,
)


def list_active_rules(db: Session) -> list[tuple[ConcernRecommendationMapping, str | None]]:
    """Every active rule with its concern name (None = a base step for everyone)."""
    return [
        (rule, concern)
        for rule, concern in db.execute(
            select(ConcernRecommendationMapping, SkinConcern.name)
            .outerjoin(SkinConcern, SkinConcern.id == ConcernRecommendationMapping.skin_concern_id)
            .where(ConcernRecommendationMapping.is_active)
            .order_by(ConcernRecommendationMapping.id)
        )
    ]


def products_of_rules(db: Session, mapping_ids: Iterable[int]) -> dict[int, list[Product]]:
    """rule id -> its active products, best first (rank 1 = "Top pick")."""
    by_rule: dict[int, list[Product]] = {}
    for mapping_id, product in db.execute(
        select(RuleProduct.mapping_id, Product)
        .join(Product, Product.id == RuleProduct.product_id)
        .where(RuleProduct.mapping_id.in_(list(mapping_ids)), Product.is_active)
        .order_by(RuleProduct.mapping_id, RuleProduct.rank)
    ):
        by_rule.setdefault(mapping_id, []).append(product)
    return by_rule


def ingredient_ids_of_products(db: Session, product_ids: Iterable[int]) -> dict[int, set[int]]:
    """product id -> the ids of our ingredients (actives and allergens) it contains."""
    by_product: dict[int, set[int]] = {}
    for product_id, ingredient_id in db.execute(
        select(ProductIngredient.product_id, ProductIngredient.ingredient_id).where(
            ProductIngredient.product_id.in_(list(product_ids))
        )
    ):
        by_product.setdefault(product_id, set()).add(ingredient_id)
    return by_product


def ingredient_ids_by_name(db: Session) -> dict[str, int]:
    return {name: ingredient_id for name, ingredient_id in db.execute(
        select(Ingredient.name, Ingredient.id)
    )}


def pregnancy_unsafe_ingredient_ids(db: Session) -> set[int]:
    return set(db.scalars(select(Ingredient.id).where(Ingredient.avoid_during_pregnancy)))


def conflict_pairs(db: Session) -> dict[frozenset[int], str]:
    """{ingredient a, ingredient b} -> why they should not be used together."""
    return {
        frozenset((a, b)): reason
        for a, b, reason in db.execute(
            select(
                IngredientConflict.ingredient_a_id,
                IngredientConflict.ingredient_b_id,
                IngredientConflict.reason,
            )
        )
    }


def add_suggestion(db: Session, *, user_id: int, name: str, step_category: str) -> None:
    """Put a user's own product on the admin review list (once per user and name)."""
    already = db.scalar(
        select(ProductSuggestion.id).where(
            ProductSuggestion.user_id == user_id,
            func.lower(ProductSuggestion.name) == name.lower(),
            ProductSuggestion.status == "pending",
        )
    )
    if already is None:
        db.add(ProductSuggestion(user_id=user_id, name=name, step_category=step_category))
