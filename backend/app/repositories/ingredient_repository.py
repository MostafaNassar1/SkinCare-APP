from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Ingredient, UserAllergy


def list_all(db: Session) -> list[Ingredient]:
    return list(db.scalars(select(Ingredient).order_by(Ingredient.name)))


def get_by_ids(db: Session, ingredient_ids: Iterable[int]) -> list[Ingredient]:
    return list(db.scalars(select(Ingredient).where(Ingredient.id.in_(list(ingredient_ids)))))


def list_allergies(db: Session, user_id: int) -> list[Ingredient]:
    """The ingredients this user is allergic to, by name."""
    return list(
        db.scalars(
            select(Ingredient)
            .join(UserAllergy, UserAllergy.ingredient_id == Ingredient.id)
            .where(UserAllergy.user_id == user_id)
            .order_by(Ingredient.name)
        )
    )


def replace_allergies(db: Session, user_id: int, ingredient_ids: set[int]) -> None:
    """Make the user's allergy list exactly `ingredient_ids`. The caller commits."""
    db.execute(delete(UserAllergy).where(UserAllergy.user_id == user_id))
    db.add_all(UserAllergy(user_id=user_id, ingredient_id=i) for i in sorted(ingredient_ids))
    db.flush()
