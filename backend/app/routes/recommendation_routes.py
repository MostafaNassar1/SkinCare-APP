from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers import recommendation_controller
from app.core.dependencies import CurrentUser, get_db
from app.schemas.recommendation import RecommendationsOut

router = APIRouter(prefix="/me", tags=["Recommendations"])

DB = Annotated[Session, Depends(get_db)]


@router.get("/recommendations", response_model=RecommendationsOut)
def get_recommendations(user: CurrentUser, db: DB):
    """The steps the user needs (latest scan + skin quiz) with every safe real product for each,
    best first; steps left out for safety reasons, with why; the dermatologist referral."""
    return recommendation_controller.get_recommendations(db, user)
