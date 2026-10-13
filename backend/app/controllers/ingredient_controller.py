from sqlalchemy.orm import Session

from app.repositories import ingredient_repository
from app.schemas.ingredient import IngredientOut


def list_ingredients(db: Session) -> list[IngredientOut]:
    return [IngredientOut.model_validate(i) for i in ingredient_repository.list_all(db)]
