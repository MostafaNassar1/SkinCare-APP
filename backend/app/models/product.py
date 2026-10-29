from datetime import date

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, IntPK, UpdatedAt, check_in
from app.models.choices import PRODUCT_SUGGESTION_STATUSES, STEP_CATEGORIES


class Product(Base):
    """A real over-the-counter product from the hand-curated catalogue (migration 0010).

    Every product is checked on its brand's official page (source_url, checked_on). Products
    are never deleted, only deactivated, so saved routines keep pointing at them.
    """

    __tablename__ = "products"
    __table_args__ = (
        check_in("step_category", STEP_CATEGORIES),
        UniqueConstraint("brand", "name"),
    )

    id: Mapped[IntPK]
    brand: Mapped[str] = mapped_column(String(100))  # "La Roche-Posay"
    name: Mapped[str] = mapped_column(String(200))  # "Effaclar Purifying Foaming Gel"
    step_category: Mapped[str] = mapped_column(String(20))
    # how to use it, from the official directions (in our own words)
    directions: Mapped[str] = mapped_column(Text)
    # the full ingredient list as printed on the pack (INCI), for reference; the filters use
    # product_ingredients
    inci_list: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(String(500))  # the brand's official product page
    # false for strong or irritating products (e.g. 23% vitamin C): never offered to a sensitive
    # skin type, even without a declared allergy (migration 0011)
    suitable_for_sensitive: Mapped[bool] = mapped_column(server_default=true())
    # the picture the app shows (our own Cloudinary copy, filled by a script) and, internally
    # only, where it was taken from (copyright record; never sent to the app) (migration 0011)
    image_url: Mapped[str | None] = mapped_column(String(500))
    image_source_url: Mapped[str | None] = mapped_column(String(500))
    checked_on: Mapped[date]  # when the page was last checked
    is_active: Mapped[bool] = mapped_column(server_default=true())
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class ProductIngredient(Base):
    """Which of our ingredients (actives and common allergens) a product contains.

    Used by the pregnancy, allergy and conflict filters of the rules engine.
    """

    __tablename__ = "product_ingredients"
    __table_args__ = (
        UniqueConstraint("product_id", "ingredient_id"),
        Index("idx_product_ingredients_ingredient", "ingredient_id"),
    )

    id: Mapped[IntPK]
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id", ondelete="RESTRICT"))
    concentration: Mapped[str | None] = mapped_column(String(50))  # "2%", when the brand states it


class RuleProduct(Base):
    """The real products chosen by hand for a recommendation rule, best first (rank 1).

    The engine walks down the list and skips any product that is unsafe for the user (safe
    substitution), then shows the first one or two that are left.
    """

    __tablename__ = "rule_products"
    __table_args__ = (
        CheckConstraint("rank >= 1", name="rank_check"),
        UniqueConstraint("mapping_id", "product_id"),
        Index("idx_rule_products_product", "product_id"),
    )

    id: Mapped[IntPK]
    mapping_id: Mapped[int] = mapped_column(
        ForeignKey("concern_recommendation_mapping.id", ondelete="CASCADE")
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    rank: Mapped[int] = mapped_column(SmallInteger)


class RoutineStepProduct(Base):
    """The products offered for a step of a saved routine (part of the routine snapshot)."""

    __tablename__ = "routine_step_products"
    __table_args__ = (
        CheckConstraint("rank >= 1", name="rank_check"),
        UniqueConstraint("routine_step_id", "product_id"),
        Index("idx_routine_step_products_product", "product_id"),
    )

    id: Mapped[IntPK]
    routine_step_id: Mapped[int] = mapped_column(
        ForeignKey("routine_steps.id", ondelete="CASCADE")
    )
    # RESTRICT: products are deactivated, never deleted, so the snapshot stays complete
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    rank: Mapped[int] = mapped_column(SmallInteger)


class RoutineStepIngredient(Base):
    """Ingredients the user says their OWN product contains ("Does it contain...?" checklist).

    Only used when the step has a custom product: the engine applies the same pregnancy, allergy
    and conflict rules to them (migration 0011).
    """

    __tablename__ = "routine_step_ingredients"
    __table_args__ = (UniqueConstraint("routine_step_id", "ingredient_id"),)

    id: Mapped[IntPK]
    routine_step_id: Mapped[int] = mapped_column(
        ForeignKey("routine_steps.id", ondelete="CASCADE")
    )
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id", ondelete="RESTRICT"))


class ProductSuggestion(Base):
    """A product a user uses but the catalogue does not have: the admin review list (migration
    0011). An admin checks it on its official page and may add it to the catalogue (Phase 7)."""

    __tablename__ = "product_suggestions"
    __table_args__ = (
        check_in("step_category", STEP_CATEGORIES),
        check_in("status", PRODUCT_SUGGESTION_STATUSES),
        Index("idx_product_suggestions_status", "status"),
    )

    id: Mapped[IntPK]
    # SET NULL: the suggestion stays useful for the admin after the account is deleted
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(200))  # as typed by the user
    step_category: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(10), server_default="pending")
    # the catalogue product it became, once an admin added it
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"))
    created_at: Mapped[CreatedAt]
