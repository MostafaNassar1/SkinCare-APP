"""Real products, whiteheads and pustules, quiz-based concerns, common allergens

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-28

Phase 3 Step 2 (decided 2026-10-24 → 2026-10-28):
- skin_concerns: two new photo concerns, whiteheads and pustules (the YOLO pimple detector of
  Step 3 tells them apart). Oiliness, dryness and redness now come from the skin quiz alone
  (detection_method "questionnaire", replacing "hybrid"): no reliable licensed photo data exists
  for them. The column is widened to 20 characters for the new value.
- ingredients.kind: "active" (recommended by the rules) or "allergen". Nine common causes of
  allergies or irritation in skincare products are added, so a user who declares them never gets
  a product that contains them (fragrance is the most common one).
- concern_recommendation_mapping.days_of_week: the weekdays a rule's step is done; the retinoid
  rules (adapalene, retinol) start on Mon, Wed, Fri (21) instead of every night.
- Three rules for the new concerns (same safety filters as every rule).
- products + product_ingredients: the hand-curated catalogue of real over-the-counter products
  (filled by a later migration, after each product is checked on its official page).
- rule_products: the products chosen by hand for each rule, best first (safe substitution walks
  down this list).
- routine_steps.product_id / needs_product / product_ready_on + routine_step_products: the
  products offered on a saved routine step, the one the user uses, and whether they have it yet
  (a step waiting for its product is left out of reminders and streaks).

Written by hand (checked with `alembic check`): autogenerate does not see CHECK constraints or
the updated_at trigger.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STEP_CATEGORIES = "'cleanse', 'treat', 'moisturize', 'protect'"
QUIZ_CONCERNS = "'oiliness', 'dryness', 'redness'"
MON_WED_FRI = 1 + 4 + 16  # see app/services/weekdays.py

NEW_CONCERNS = [
    ("whiteheads", "Whiteheads",
     "Small closed bumps with a white or skin-coloured top, caused by clogged pores."),
    ("pustules", "Pustules",
     "Inflamed spots with a visible white or yellow centre."),
]  # fmt: skip

# (name, description), all kind = 'allergen', none to avoid during pregnancy
ALLERGENS = [
    ("Fragrance (Parfum)",
     "Added scent; the most common cause of allergic reactions to skincare products."),
    ("Essential Oils",
     "Plant oils used for scent (e.g. lavender, tea tree, citrus); can irritate or cause "
     "allergies."),
    ("Denatured Alcohol",
     "Alcohol denat.; makes products feel light but can dry and irritate sensitive skin."),
    ("Methylisothiazolinone",
     "Preservative (MI, often with MCI) known to cause allergic skin reactions."),
    ("Formaldehyde Releasers",
     "Preservatives that slowly release formaldehyde, e.g. DMDM hydantoin or imidazolidinyl "
     "urea."),
    ("Parabens",
     "Preservatives such as methylparaben or propylparaben; allergies are rare but some people "
     "avoid them."),
    ("Lanolin",
     "Wool wax used in rich creams and lip balms; a known allergen for some people."),
    ("Propylene Glycol",
     "Common moisturizing ingredient and solvent; can irritate or cause allergies in some "
     "people."),
    ("Cocamidopropyl Betaine",
     "Mild cleansing agent made from coconut oil, found in many cleansers; an occasional "
     "allergen."),
]  # fmt: skip

# (concern, category, title, product type, ingredient, concentration, time, min severity,
#  priority, days of week, notes) — the same layout as the rules in seed_v2.sql
NEW_RULES = [
    ("whiteheads", "cleanse", "Cleanse", "Salicylic acid foaming cleanser", "Salicylic Acid",
     "0.5-2%", "both", "mild", 10, 127, "Helps unclog the pores that form whiteheads."),
    ("whiteheads", "treat", "Clogged Pore Treatment", "Adapalene gel", "Adapalene", "0.1%",
     "evening", "moderate", 20, MON_WED_FRI,
     "Start 2-3 nights a week; expect some dryness at first."),
    ("pustules", "treat", "Spot Treatment", "Benzoyl peroxide spot treatment gel",
     "Benzoyl Peroxide", "2.5-5%", "evening", "mild", 10, 127,
     "Apply thinly on inflamed spots only; never squeeze them."),
]  # fmt: skip


def upgrade() -> None:
    # --- concerns ---
    op.drop_constraint(op.f("skin_concerns_detection_method_check"), "skin_concerns", "check")
    op.alter_column(
        "skin_concerns", "detection_method", type_=sa.String(20), existing_type=sa.String(10)
    )
    op.execute(
        "UPDATE skin_concerns SET detection_method = 'questionnaire' "
        f"WHERE name IN ({QUIZ_CONCERNS})"
    )
    op.create_check_constraint(
        op.f("skin_concerns_detection_method_check"),
        "skin_concerns",
        "detection_method IN ('photo', 'questionnaire')",
    )
    insert_concern = sa.text(
        "INSERT INTO skin_concerns (name, display_name, description, detection_method) "
        "VALUES (:name, :display_name, :description, 'photo')"
    )
    for name, display_name, description in NEW_CONCERNS:
        op.get_bind().execute(
            insert_concern, {"name": name, "display_name": display_name, "description": description}
        )

    # --- ingredients: kind + common allergens ---
    op.add_column(
        "ingredients",
        sa.Column("kind", sa.String(10), server_default="active", nullable=False),
    )
    op.create_check_constraint(
        op.f("ingredients_kind_check"), "ingredients", "kind IN ('active', 'allergen')"
    )
    insert_allergen = sa.text(
        "INSERT INTO ingredients (name, description, kind) VALUES (:name, :description, 'allergen')"
    )
    for name, description in ALLERGENS:
        op.get_bind().execute(insert_allergen, {"name": name, "description": description})

    # --- rules: scheduled weekdays + rules for the new concerns ---
    op.add_column(
        "concern_recommendation_mapping",
        sa.Column("days_of_week", sa.SmallInteger(), server_default=sa.text("127"), nullable=False),
    )
    op.create_check_constraint(
        op.f("concern_recommendation_mapping_days_of_week_check"),
        "concern_recommendation_mapping",
        "days_of_week BETWEEN 1 AND 127",
    )
    op.execute(
        f"UPDATE concern_recommendation_mapping SET days_of_week = {MON_WED_FRI} "
        "WHERE ingredient_id IN (SELECT id FROM ingredients WHERE name IN ('Adapalene', 'Retinol'))"
    )
    insert_rule = sa.text(
        "INSERT INTO concern_recommendation_mapping (skin_concern_id, step_category, step_title, "
        "product_type, ingredient_id, recommended_concentration, time_of_day, min_severity, "
        "priority, days_of_week, notes) VALUES ("
        "(SELECT id FROM skin_concerns WHERE name = :concern), :category, :title, :product_type, "
        "(SELECT id FROM ingredients WHERE name = :ingredient), :concentration, :time, "
        ":severity, :priority, :days, :notes)"
    )
    for rule in NEW_RULES:
        keys = (
            "concern", "category", "title", "product_type", "ingredient", "concentration",
            "time", "severity", "priority", "days", "notes",
        )  # fmt: skip
        op.get_bind().execute(insert_rule, dict(zip(keys, rule, strict=True)))

    # --- product catalogue ---
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("brand", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("step_category", sa.String(20), nullable=False),
        sa.Column("directions", sa.Text(), nullable=False),
        sa.Column("inci_list", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("checked_on", sa.Date(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"step_category IN ({STEP_CATEGORIES})", name=op.f("products_step_category_check")
        ),
        sa.UniqueConstraint("brand", "name", name=op.f("products_brand_name_key")),
    )
    op.execute(
        "CREATE TRIGGER trg_products_updated_at BEFORE UPDATE ON products "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_table(
        "product_ingredients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ingredient_id", sa.Integer(), sa.ForeignKey("ingredients.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("concentration", sa.String(50), nullable=True),
        sa.UniqueConstraint(
            "product_id", "ingredient_id",
            name=op.f("product_ingredients_product_id_ingredient_id_key"),
        ),
    )  # fmt: skip
    op.create_index("idx_product_ingredients_ingredient", "product_ingredients", ["ingredient_id"])
    op.create_table(
        "rule_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "mapping_id", sa.Integer(),
            sa.ForeignKey("concern_recommendation_mapping.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rank", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint("rank >= 1", name=op.f("rule_products_rank_check")),
        sa.UniqueConstraint(
            "mapping_id", "product_id", name=op.f("rule_products_mapping_id_product_id_key")
        ),
    )  # fmt: skip
    op.create_index("idx_rule_products_product", "rule_products", ["product_id"])

    # --- products on saved routines ---
    op.add_column(
        "routine_steps",
        sa.Column(
            "product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )  # fmt: skip
    op.add_column(
        "routine_steps",
        sa.Column("needs_product", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("routine_steps", sa.Column("product_ready_on", sa.Date(), nullable=True))
    op.create_check_constraint(
        op.f("routine_steps_product_ready_check"),
        "routine_steps",
        "NOT (needs_product AND product_ready_on IS NOT NULL)",
    )
    op.create_table(
        "routine_step_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "routine_step_id", sa.Integer(),
            sa.ForeignKey("routine_steps.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("rank", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint("rank >= 1", name=op.f("routine_step_products_rank_check")),
        sa.UniqueConstraint(
            "routine_step_id", "product_id",
            name=op.f("routine_step_products_routine_step_id_product_id_key"),
        ),
    )  # fmt: skip
    op.create_index(
        "idx_routine_step_products_product", "routine_step_products", ["product_id"]
    )


def downgrade() -> None:
    op.drop_table("routine_step_products")
    op.drop_constraint(op.f("routine_steps_product_ready_check"), "routine_steps", "check")
    op.drop_column("routine_steps", "product_ready_on")
    op.drop_column("routine_steps", "needs_product")
    op.drop_column("routine_steps", "product_id")
    op.drop_table("rule_products")
    op.drop_table("product_ingredients")
    op.drop_table("products")  # also drops its trigger

    op.execute(
        "DELETE FROM concern_recommendation_mapping WHERE skin_concern_id IN "
        "(SELECT id FROM skin_concerns WHERE name IN ('whiteheads', 'pustules'))"
    )
    op.drop_constraint(
        op.f("concern_recommendation_mapping_days_of_week_check"),
        "concern_recommendation_mapping",
        "check",
    )
    op.drop_column("concern_recommendation_mapping", "days_of_week")

    op.execute("DELETE FROM ingredients WHERE kind = 'allergen'")
    op.drop_constraint(op.f("ingredients_kind_check"), "ingredients", "check")
    op.drop_column("ingredients", "kind")

    op.execute("DELETE FROM skin_concerns WHERE name IN ('whiteheads', 'pustules')")
    op.drop_constraint(op.f("skin_concerns_detection_method_check"), "skin_concerns", "check")
    op.execute(
        "UPDATE skin_concerns SET detection_method = CASE name "
        "WHEN 'redness' THEN 'photo' ELSE 'hybrid' END WHERE name IN (" + QUIZ_CONCERNS + ")"
    )
    op.alter_column(
        "skin_concerns", "detection_method", type_=sa.String(10), existing_type=sa.String(20)
    )
    op.create_check_constraint(
        op.f("skin_concerns_detection_method_check"),
        "skin_concerns",
        "detection_method IN ('photo', 'hybrid')",
    )
