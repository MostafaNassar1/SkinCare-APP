"""Cosmetics only, the user's own products, sensitive-skin flag, product pictures

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-29

Decided on 2026-10-28 → 2026-10-29 after the product research (Phase 3 Step 2.2):
- Cosmetics only, no medicines: Differin (adapalene) and benzoyl peroxide are registered medicines
  in Lebanon (Ministry of Public Health) and prescription-only in the UK. The acne adapalene rule
  is deactivated (kept for history); the whiteheads adapalene rule and the two benzoyl peroxide
  rules now recommend non-prescription products (anti-blemish treatment, hydrocolloid patch),
  chosen per product in rule_products (migration 0012), so they have no single ingredient.
- New ingredients found in the approved products: Lactic Acid, LHA (capryloyl salicylic acid),
  Retinal and Retinyl Palmitate (both retinoids: avoid during pregnancy), with their conflicts
  (retinoid + exfoliating acid, two retinoids together).
- products.suitable_for_sensitive: strong or irritating products are never offered to a
  sensitive skin type, even without a declared allergy.
- products.image_url (the picture the app shows, our own copy) and image_source_url (internal
  copyright record, never sent to the app).
- routine_steps.custom_product_name + routine_step_ingredients: "I'll use my own product"; the
  ingredients the user ticks get the same pregnancy / allergy / conflict checks.
- product_suggestions: the admin review list of products users use but the catalogue lacks.

Written by hand (checked with `alembic check`).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STEP_CATEGORIES = "'cleanse', 'treat', 'moisturize', 'protect'"

# (name, description, avoid during pregnancy)
NEW_ACTIVES = [
    ("Lactic Acid", "Gentle AHA that exfoliates the surface and helps hold moisture.", False),
    ("LHA (Capryloyl Salicylic Acid)",
     "Salicylic acid derivative that exfoliates gradually inside the pore.", False),
    ("Retinal",
     "Retinaldehyde, a retinoid one step from retinoic acid; boosts cell turnover.", True),
    ("Retinyl Palmitate",
     "Mild retinoid ester (vitamin A) used in anti-ageing and spot care.", True),
]  # fmt: skip

RETINOIDS = ["Retinol", "Adapalene", "Retinal", "Retinyl Palmitate"]
ACIDS = ["Glycolic Acid", "Salicylic Acid", "Lactic Acid", "LHA (Capryloyl Salicylic Acid)"]
RETINOID_ACID = "Retinoid plus exfoliating acid causes over-exfoliation and irritation."
TWO_RETINOIDS = "Two retinoids together greatly increase irritation."
TWO_ACIDS = "Two exfoliating acids at once over-exfoliate the skin."
BPO_RETINOID = "Benzoyl peroxide can degrade retinoids and adds dryness."
NEW_NAMES = {name for name, _, _ in NEW_ACTIVES}


def _new_conflicts() -> list[tuple[str, str, str]]:
    """Every pair involving a new ingredient (the old pairs are already in seed_v2.sql)."""
    pairs = []
    for retinoid in RETINOIDS:
        for acid in ACIDS:
            pairs.append((retinoid, acid, RETINOID_ACID))
        pairs.append((retinoid, "Benzoyl Peroxide", BPO_RETINOID))
    for i, a in enumerate(RETINOIDS):
        pairs += [(a, b, TWO_RETINOIDS) for b in RETINOIDS[i + 1:]]
    for i, a in enumerate(ACIDS):
        pairs += [(a, b, TWO_ACIDS) for b in ACIDS[i + 1:]]
    return [p for p in pairs if NEW_NAMES & {p[0], p[1]}]


# rule changes: (concern, old ingredient) -> new values; None = deactivate
RULE_CHANGES = {
    ("acne", "Benzoyl Peroxide"): dict(
        step_title="Acne Treatment", product_type="Non-prescription anti-blemish treatment",
        notes="Thin layer in the evening. For a stronger treatment (e.g. adapalene), ask a "
              "pharmacist or dermatologist."),
    ("acne", "Adapalene"): None,
    ("whiteheads", "Adapalene"): dict(
        step_title="Clogged Pore Treatment", product_type="Non-prescription unclogging treatment",
        notes="Thin layer in the evening on clean, dry skin. For a stronger treatment (e.g. "
              "adapalene), ask a pharmacist or dermatologist."),
    ("pustules", "Benzoyl Peroxide"): dict(
        step_title="Spot Treatment", product_type="Hydrocolloid pimple patch",
        notes="On a single inflamed spot, overnight; never squeeze."),
}  # fmt: skip
# the original values, restored by downgrade
RULE_ORIGINALS = {
    ("acne", "Benzoyl Peroxide"): ("Spot Treatment", "Benzoyl peroxide spot treatment gel",
                                   "2.5-5%", 127, "Apply thinly on active spots only."),
    ("acne", "Adapalene"): ("Acne Treatment", "Adapalene gel", "0.1%", 21,
                            "Start 2-3 nights a week; expect some dryness at first."),
    ("whiteheads", "Adapalene"): ("Clogged Pore Treatment", "Adapalene gel", "0.1%", 21,
                                  "Start 2-3 nights a week; expect some dryness at first."),
    ("pustules", "Benzoyl Peroxide"): ("Spot Treatment", "Benzoyl peroxide spot treatment gel",
                                       "2.5-5%", 127,
                                       "Apply thinly on inflamed spots only; never squeeze them."),
}  # fmt: skip
RULE_BY_CONCERN_AND_INGREDIENT = (
    "skin_concern_id = (SELECT id FROM skin_concerns WHERE name = :concern) "
    "AND ingredient_id = (SELECT id FROM ingredients WHERE name = :ingredient)"
)
RULE_BY_CONCERN_AND_TITLE = (
    "skin_concern_id = (SELECT id FROM skin_concerns WHERE name = :concern) "
    "AND ingredient_id IS NULL AND step_title = :title AND product_type = :product_type"
)


def upgrade() -> None:
    bind = op.get_bind()

    # --- ingredients + conflicts ---
    insert_ingredient = sa.text(
        "INSERT INTO ingredients (name, description, avoid_during_pregnancy, kind) "
        "VALUES (:name, :description, :pregnancy, 'active')"
    )
    for name, description, pregnancy in NEW_ACTIVES:
        bind.execute(
            insert_ingredient, {"name": name, "description": description, "pregnancy": pregnancy}
        )
    insert_conflict = sa.text(
        "INSERT INTO ingredient_conflicts (ingredient_a_id, ingredient_b_id, reason) "
        "SELECT LEAST(a.id, b.id), GREATEST(a.id, b.id), :reason "
        "FROM ingredients a, ingredients b WHERE a.name = :a AND b.name = :b"
    )
    for a, b, reason in _new_conflicts():
        bind.execute(insert_conflict, {"a": a, "b": b, "reason": reason})

    # --- cosmetics only ---
    for (concern, ingredient), change in RULE_CHANGES.items():
        params = {"concern": concern, "ingredient": ingredient}
        if change is None:
            bind.execute(sa.text(
                f"UPDATE concern_recommendation_mapping SET is_active = false "
                f"WHERE {RULE_BY_CONCERN_AND_INGREDIENT}"), params)
            continue
        bind.execute(sa.text(
            "UPDATE concern_recommendation_mapping SET step_title = :step_title, "
            "product_type = :product_type, notes = :notes, ingredient_id = NULL, "
            "recommended_concentration = NULL, days_of_week = 127 "
            f"WHERE {RULE_BY_CONCERN_AND_INGREDIENT}"), params | change)

    # --- products: sensitive flag + pictures ---
    op.add_column(
        "products",
        sa.Column("suitable_for_sensitive", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column("products", sa.Column("image_url", sa.String(500), nullable=True))
    op.add_column("products", sa.Column("image_source_url", sa.String(500), nullable=True))

    # --- the user's own product ---
    op.add_column("routine_steps", sa.Column("custom_product_name", sa.String(200), nullable=True))
    op.create_check_constraint(
        op.f("routine_steps_one_product_check"),
        "routine_steps",
        "product_id IS NULL OR custom_product_name IS NULL",
    )
    op.create_table(
        "routine_step_ingredients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "routine_step_id", sa.Integer(),
            sa.ForeignKey("routine_steps.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "ingredient_id", sa.Integer(), sa.ForeignKey("ingredients.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "routine_step_id", "ingredient_id",
            name=op.f("routine_step_ingredients_routine_step_id_ingredient_id_key"),
        ),
    )  # fmt: skip

    # --- admin review list ---
    op.create_table(
        "product_suggestions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("step_category", sa.String(20), nullable=False),
        sa.Column("status", sa.String(10), server_default="pending", nullable=False),
        sa.Column(
            "product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"step_category IN ({STEP_CATEGORIES})",
            name=op.f("product_suggestions_step_category_check"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'added', 'rejected')",
            name=op.f("product_suggestions_status_check"),
        ),
    )  # fmt: skip
    op.create_index("idx_product_suggestions_status", "product_suggestions", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_table("product_suggestions")
    op.drop_table("routine_step_ingredients")
    op.drop_constraint(op.f("routine_steps_one_product_check"), "routine_steps", "check")
    op.drop_column("routine_steps", "custom_product_name")
    op.drop_column("products", "image_source_url")
    op.drop_column("products", "image_url")
    op.drop_column("products", "suitable_for_sensitive")

    for (concern, ingredient), change in RULE_CHANGES.items():
        title, product_type, concentration, days, notes = RULE_ORIGINALS[(concern, ingredient)]
        params = {
            "concern": concern, "ingredient": ingredient, "title": title,
            "product_type": product_type, "concentration": concentration, "days": days,
            "notes": notes,
        }  # fmt: skip
        if change is None:
            bind.execute(sa.text(
                f"UPDATE concern_recommendation_mapping SET is_active = true "
                f"WHERE {RULE_BY_CONCERN_AND_INGREDIENT}"), params)
            continue
        # find the rule by its NEW title and type (its ingredient is now NULL)
        bind.execute(sa.text(
            "UPDATE concern_recommendation_mapping SET step_title = :title, "
            "product_type = :old_type, notes = :notes, "
            "ingredient_id = (SELECT id FROM ingredients WHERE name = :ingredient), "
            "recommended_concentration = :concentration, days_of_week = :days "
            f"WHERE {RULE_BY_CONCERN_AND_TITLE.replace(':title', ':new_title')}"),
            params | {"new_title": change["step_title"], "product_type": change["product_type"],
                      "old_type": product_type})  # fmt: skip

    names = tuple(name for name, _, _ in NEW_ACTIVES)
    bind.execute(sa.text(
        "DELETE FROM ingredient_conflicts WHERE ingredient_a_id IN "
        "(SELECT id FROM ingredients WHERE name IN :names) OR ingredient_b_id IN "
        "(SELECT id FROM ingredients WHERE name IN :names)"
    ).bindparams(sa.bindparam("names", expanding=True)), {"names": list(names)})
    bind.execute(sa.text("DELETE FROM ingredients WHERE name IN :names").bindparams(
        sa.bindparam("names", expanding=True)), {"names": list(names)})
