"""The product catalogue: 32 real over-the-counter products and the products of each rule

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-29

Phase 3 Step 2.2 (product research of 2026-10-27 → 2026-10-28, approved by the student):
- products: 32 real products sold in Lebanese pharmacies (10 brands), each checked on its brand's
  official page (source_url, checked_on). inci_list = the full list as published, with obvious
  web-page errors fixed by hand (letters spaced out, missing commas). image_url / image_source_url
  stay empty: a later script stores our own copy of each picture taken from the brand's page.
  No shop names or shop links are stored (the app shows "Available in pharmacies" + the map of
  the nearest pharmacies).
- product_ingredients: our active and allergen ingredients found in each list (used by the
  pregnancy, allergy and conflict filters). Traces at the end of a list (a pH adjuster, an
  antioxidant) are not counted as the product's active.
- rule_products: the products of each rule, best first (rank 1 = "Top pick"); the engine shows
  every product that is safe for the user and lets them choose.

The data lives in data/0012_catalogue.json next to this file (one place to review it).
"""

import json
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATA = json.loads(
    (Path(__file__).parent / "data" / "0012_catalogue.json").read_text(encoding="utf-8")
)


def upgrade() -> None:
    bind = op.get_bind()
    ids = {}
    for product in DATA["products"]:
        ids[product["key"]] = bind.scalar(
            sa.text(
                "INSERT INTO products (brand, name, step_category, directions, inci_list, "
                "source_url, suitable_for_sensitive, checked_on) VALUES (:brand, :name, "
                ":step_category, :directions, :inci_list, :source_url, :suitable_for_sensitive, "
                "CAST(:checked_on AS date)) RETURNING id"
            ),
            {key: value for key, value in product.items() if key not in ("key", "ingredients")},
        )
        for ingredient in product["ingredients"]:
            bind.execute(
                sa.text(
                    "INSERT INTO product_ingredients (product_id, ingredient_id, concentration) "
                    "VALUES (:product_id, (SELECT id FROM ingredients WHERE name = :name), "
                    ":concentration)"
                ),
                {"product_id": ids[product["key"]], **ingredient},
            )

    for rule in DATA["rules"]:
        mapping_id = bind.scalar(
            sa.text(
                "SELECT m.id FROM concern_recommendation_mapping m "
                "LEFT JOIN skin_concerns c ON c.id = m.skin_concern_id "
                "WHERE m.is_active AND m.step_title = :title "
                "AND c.name IS NOT DISTINCT FROM :concern"
            ),
            {"title": rule["step_title"], "concern": rule["concern"]},
        )
        if mapping_id is None:
            raise RuntimeError(f"no active rule {rule['concern']} / {rule['step_title']}")
        for rank, key in enumerate(rule["products"], start=1):
            bind.execute(
                sa.text(
                    "INSERT INTO rule_products (mapping_id, product_id, rank) "
                    "VALUES (:mapping_id, :product_id, :rank)"
                ),
                {"mapping_id": mapping_id, "product_id": ids[key], "rank": rank},
            )


def downgrade() -> None:
    # product_ingredients and rule_products go with their product (ON DELETE CASCADE); a product
    # used in a saved routine blocks this (RESTRICT), as it should
    for product in DATA["products"]:
        op.get_bind().execute(
            sa.text("DELETE FROM products WHERE brand = :brand AND name = :name"),
            {"brand": product["brand"], "name": product["name"]},
        )
