from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers import achievement_controller
from app.core.dependencies import CurrentUser, get_db, reference_cache
from app.schemas.reference import AchievementOut, MyAchievementOut

router = APIRouter(tags=["Achievements"])

DB = Annotated[Session, Depends(get_db)]


@router.get(
    "/achievements",
    response_model=list[AchievementOut],
    dependencies=[Depends(reference_cache)],
)
def list_achievements(db: DB):
    """All badges the app offers (public reference list)."""
    return achievement_controller.list_achievements(db)


@router.get("/me/achievements", response_model=list[MyAchievementOut])
def list_my_achievements(user: CurrentUser, db: DB):
    """The same badges, each marked earned or locked for the logged-in user."""
    return achievement_controller.list_my_achievements(db, user)
