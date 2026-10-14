from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.controllers import routine_controller
from app.core.dependencies import CurrentUser, get_db
from app.schemas.routine import RoutineDayOut

router = APIRouter(prefix="/me/routine", tags=["Routine"])

DB = Annotated[Session, Depends(get_db)]


@router.get("", response_model=RoutineDayOut)
def get_routine_day(
    user: CurrentUser,
    db: DB,
    day: Annotated[date | None, Query(alias="date")] = None,
):
    """Today's routine by default; `?date=YYYY-MM-DD` shows a past day (view only)."""
    return routine_controller.get_day(db, user, day)
