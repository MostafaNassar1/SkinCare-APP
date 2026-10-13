from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers import allergy_controller, ingredient_controller
from app.core.dependencies import CurrentUser, get_db, reference_cache
from app.schemas.ingredient import AllergiesOut, AllergiesUpdate, IngredientOut

router = APIRouter(tags=["Ingredients and allergies"])

DB = Annotated[Session, Depends(get_db)]


@router.get(
    "/ingredients",
    response_model=list[IngredientOut],
    dependencies=[Depends(reference_cache)],
)
def list_ingredients(db: DB):
    """Reference list (no login needed): the choices on the allergy screen."""
    return ingredient_controller.list_ingredients(db)


@router.get("/me/allergies", response_model=AllergiesOut)
def get_allergies(user: CurrentUser, db: DB):
    return allergy_controller.get_allergies(db, user)


@router.put("/me/allergies", response_model=AllergiesOut)
def replace_allergies(data: AllergiesUpdate, user: CurrentUser, db: DB):
    return allergy_controller.replace_allergies(db, user, data)
