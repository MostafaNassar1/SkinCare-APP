"""Migration 0012: the product catalogue gives the same answers as the approved PDF matrix.

The situations are filtered here the way the PDF ("Phase 3 Product Recommendation Matrix") did;
the rules engine of Part 2.3 applies the same filters to the user's profile.
"""

import re

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ConcernRecommendationMapping,
    Ingredient,
    Product,
    ProductIngredient,
    RuleProduct,
    SkinConcern,
)

FRAGRANCE = {"Fragrance (Parfum)", "Essential Oils"}
# situation -> (avoid in pregnancy, ingredients to avoid, sensitive skin)
SITUATIONS = {
    "standard": (False, set(), False),
    "pregnant": (True, set(), False),
    "fragrance allergy": (False, FRAGRANCE, False),
    "alcohol allergy": (False, {"Denatured Alcohol"}, False),
    "propylene glycol allergy": (False, {"Propylene Glycol"}, False),
    "paraben allergy": (False, {"Parabens"}, False),
    "sensitive skin": (False, set(), True),
}


def ingredients_of(db: Session, product_id: int) -> list[Ingredient]:
    return list(
        db.scalars(
            select(Ingredient)
            .join(ProductIngredient, ProductIngredient.ingredient_id == Ingredient.id)
            .where(ProductIngredient.product_id == product_id)
        )
    )


def all_rules(db: Session) -> list[tuple[str | None, str, int]]:
    rows = db.execute(
        select(SkinConcern.name, ConcernRecommendationMapping.step_title,
               ConcernRecommendationMapping.id)
        .outerjoin(SkinConcern, SkinConcern.id == ConcernRecommendationMapping.skin_concern_id)
        .where(ConcernRecommendationMapping.is_active)
        .order_by(ConcernRecommendationMapping.id)
    ).all()  # fmt: skip
    return [tuple(row) for row in rows]


def safe_products(db: Session, mapping_id: int, situation: str) -> list[str]:
    """The names of a rule's products that suit the situation, best first."""
    pregnant, avoid, sensitive = SITUATIONS[situation]
    products = db.scalars(
        select(Product)
        .join(RuleProduct, RuleProduct.product_id == Product.id)
        .where(RuleProduct.mapping_id == mapping_id, Product.is_active)
        .order_by(RuleProduct.rank)
    ).all()
    names = []
    for product in products:
        found = ingredients_of(db, product.id)
        if pregnant and any(i.avoid_during_pregnancy for i in found):
            continue
        if avoid & {i.name for i in found} or (sensitive and not product.suitable_for_sensitive):
            continue
        names.append(product.name)
    return names


def rule_id(db: Session, concern: str | None, title: str) -> int:
    return next(i for c, t, i in all_rules(db) if (c, t) == (concern, title))


# ---------- the data itself ----------


def test_32_products_from_official_pages(db: Session):
    products = db.scalars(select(Product)).all()

    assert len(products) == 32
    assert len({p.brand for p in products}) == 10
    assert all(p.source_url.startswith("https://") and p.directions for p in products)
    # where the product was found is never stored: no shop names or shop links
    shops = re.compile(r"mazen|drugstore|skinsociety|everyoung", re.IGNORECASE)
    assert not any(shops.search(f"{p.source_url} {p.directions} {p.name}") for p in products)
    assert all(p.image_url is None and p.image_source_url is None for p in products)


def test_ingredient_lists_have_no_spaced_out_letters(db: Session):
    lists = db.scalars(select(Product.inci_list)).all()

    assert not any(re.search(r"\b(?:\w ){3,}\w\b", inci) for inci in lists)


@pytest.mark.parametrize(
    ("allergen", "pattern"),
    [("Fragrance (Parfum)", r"\bparfum\b"), ("Denatured Alcohol", r"alcohol denat"),
     ("Parabens", r"paraben"), ("Propylene Glycol", r"(?<!di)propylene glycol")],
)  # fmt: skip
def test_allergen_links_match_the_ingredient_lists(db: Session, allergen, pattern):
    for product in db.scalars(select(Product)):
        linked = allergen in {i.name for i in ingredients_of(db, product.id)}
        assert linked == bool(re.search(pattern, product.inci_list, re.IGNORECASE)), product.name


def test_only_the_retinol_products_are_unsafe_in_pregnancy(db: Session):
    unsafe = {
        p.name
        for p in db.scalars(select(Product))
        if any(i.avoid_during_pregnancy for i in ingredients_of(db, p.id))
    }

    assert unsafe == {
        "The Retinol 0.1 Cream",
        "Retinol B3 Serum",
        "Revitalift Laser 0.2% Pure Retinol Night Serum",
    }


def test_fragranced_products_are_not_for_sensitive_skin(db: Session):
    for product in db.scalars(select(Product)):
        names = {i.name for i in ingredients_of(db, product.id)}
        if names & (FRAGRANCE | {"Denatured Alcohol"}):
            assert product.suitable_for_sensitive is False, product.name


def test_every_active_rule_has_products_ranked_from_one(db: Session):
    for concern, title, mapping_id in all_rules(db):
        ranks = db.scalars(
            select(RuleProduct.rank)
            .where(RuleProduct.mapping_id == mapping_id)
            .order_by(RuleProduct.rank)
        ).all()
        assert ranks == list(range(1, len(ranks) + 1)) and ranks, (concern, title)


def test_products_match_the_step_of_their_rule(db: Session):
    rows = db.execute(
        select(Product.name, Product.step_category, ConcernRecommendationMapping.step_category)
        .join(RuleProduct, RuleProduct.product_id == Product.id)
        .join(ConcernRecommendationMapping,
              ConcernRecommendationMapping.id == RuleProduct.mapping_id)
    ).all()  # fmt: skip

    assert len(rows) == 44
    assert all(product == rule for _, product, rule in rows)


# ---------- the same answers as the PDF matrix ----------


def test_only_the_known_gaps_have_no_safe_product(db: Session):
    gaps = {
        (concern, title, situation)
        for concern, title, mapping_id in all_rules(db)
        for situation in SITUATIONS
        if not safe_products(db, mapping_id, situation)
    }

    assert gaps == {
        ("redness", "Redness Treatment", "propylene glycol allergy"),
        ("dark_spots", "Spot Fading Treatment", "propylene glycol allergy"),
        ("dark_spots", "Brightening Serum", "sensitive skin"),
        # by design: the peptide serum (Firming Serum) covers wrinkles in pregnancy
        ("wrinkles", "Anti-Aging Treatment", "pregnant"),
    }


@pytest.mark.parametrize(
    ("situation", "expected"),
    [
        ("standard", ["Effaclar Duo+M", "Blemish Control Gel", "Cleanance Comedomed",
                      "Biology AC Perfect Anti-Blemish Fluid"]),
        ("pregnant", ["Effaclar Duo+M", "Blemish Control Gel", "Cleanance Comedomed",
                      "Biology AC Perfect Anti-Blemish Fluid"]),
        ("fragrance allergy", ["Blemish Control Gel", "Cleanance Comedomed"]),
        ("sensitive skin", ["Cleanance Comedomed"]),
    ],
)  # fmt: skip
def test_acne_treatment_per_situation(db: Session, situation, expected):
    assert safe_products(db, rule_id(db, "acne", "Acne Treatment"), situation) == expected


@pytest.mark.parametrize(
    ("situation", "expected"),
    [
        ("standard", ["The Retinol 0.1 Cream", "Retinol B3 Serum",
                      "Revitalift Laser 0.2% Pure Retinol Night Serum"]),
        ("pregnant", []),
        ("fragrance allergy", ["The Retinol 0.1 Cream"]),
        ("propylene glycol allergy", ["The Retinol 0.1 Cream", "Retinol B3 Serum"]),
        ("sensitive skin", ["The Retinol 0.1 Cream"]),
    ],
)  # fmt: skip
def test_retinol_per_situation(db: Session, situation, expected):
    assert safe_products(db, rule_id(db, "wrinkles", "Anti-Aging Treatment"), situation) == expected


@pytest.mark.parametrize(
    ("situation", "expected"),
    [
        ("standard", ["Anthelios UVMune 400 Invisible Fluid SPF50+ (non-perfumed)",
                      "SPF 50+ Mineral Fluid", "Anthelios UVMune 400 Oil Control Fluid SPF50+"]),
        ("fragrance allergy", ["Anthelios UVMune 400 Invisible Fluid SPF50+ (non-perfumed)",
                               "SPF 50+ Mineral Fluid"]),
        ("alcohol allergy", ["SPF 50+ Mineral Fluid"]),
        ("sensitive skin", ["SPF 50+ Mineral Fluid"]),
    ],
)  # fmt: skip
def test_base_sunscreen_per_situation(db: Session, situation, expected):
    assert safe_products(db, rule_id(db, None, "Sunscreen"), situation) == expected
