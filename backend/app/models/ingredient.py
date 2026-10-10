from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, IntPK


class Ingredient(Base):
    __tablename__ = "ingredients"

    id: Mapped[IntPK]
    name: Mapped[str] = mapped_column(String(100), unique=True)  # e.g. "Salicylic Acid"
    description: Mapped[str | None] = mapped_column(Text)
    avoid_during_pregnancy: Mapped[bool] = mapped_column(server_default=false())
    created_at: Mapped[CreatedAt]


class UserAllergy(Base):
    __tablename__ = "user_allergies"
    __table_args__ = (
        UniqueConstraint("user_id", "ingredient_id"),
        Index("idx_user_allergies_user", "user_id"),
    )

    id: Mapped[IntPK]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id", ondelete="CASCADE"))
    created_at: Mapped[CreatedAt]


class IngredientConflict(Base):
    """Pairs that should not be used in the same time slot (e.g. retinol + AHA)."""

    __tablename__ = "ingredient_conflicts"
    __table_args__ = (
        # store each pair once, in one direction
        CheckConstraint("ingredient_a_id < ingredient_b_id", name="check"),
        UniqueConstraint("ingredient_a_id", "ingredient_b_id"),
    )

    id: Mapped[IntPK]
    ingredient_a_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id", ondelete="CASCADE"))
    ingredient_b_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id", ondelete="CASCADE"))
    reason: Mapped[str] = mapped_column(Text)
