from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers import skin_quiz_controller
from app.core.dependencies import CurrentUser, get_db
from app.schemas.skin_quiz import SkinQuizAnswers, SkinQuizOut, SkinQuizResultOut

router = APIRouter(tags=["Skin quiz"])

DB = Annotated[Session, Depends(get_db)]


@router.get("/skin-quiz", response_model=SkinQuizOut)
def get_quiz():
    """The onboarding quiz questions (no login needed: nothing personal)."""
    return skin_quiz_controller.get_quiz()


@router.post("/me/skin-quiz", response_model=SkinQuizResultOut)
def submit_answers(data: SkinQuizAnswers, user: CurrentUser, db: DB):
    return skin_quiz_controller.submit_answers(db, user, data)
