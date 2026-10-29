from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.controllers import routine_controller
from app.core.dependencies import CurrentUser, get_db
from app.schemas.recommendation import RoutineIn
from app.schemas.routine import HistoryOut, RoutineDayOut, RoutineSavedOut, StepLogOut, StreakOut

router = APIRouter(prefix="/me/routine", tags=["Routine"])
streak_router = APIRouter(prefix="/me", tags=["Routine"])

DB = Annotated[Session, Depends(get_db)]


@router.get("", response_model=RoutineDayOut)
def get_routine_day(
    user: CurrentUser,
    db: DB,
    day: Annotated[date | None, Query(alias="date")] = None,
):
    """Today's routine by default; `?date=YYYY-MM-DD` shows a past day (view only)."""
    return routine_controller.get_day(db, user, day)


@router.put("", response_model=RoutineSavedOut)
def save_routine(body: RoutineIn, user: CurrentUser, db: DB):
    """Save the routine as the user wants it, first time and every edit (a new version: past
    days keep the old one). Each step = one of GET /me/recommendations, with a product of its
    list or the user's own; steps left out are removed. 409 steps_conflict when clashing
    treatments cannot be put on different days."""
    return routine_controller.save_routine(db, user, body)


@router.post("/steps/{step_id}/product-ready", response_model=RoutineDayOut)
def mark_product_ready(step_id: int, user: CurrentUser, db: DB):
    """ "I have it now": a step waiting for its product counts from today on."""
    return routine_controller.mark_product_ready(db, user, step_id)


@router.post("/steps/{step_id}/log", response_model=StepLogOut)
def log_step(step_id: int, user: CurrentUser, db: DB):
    """Mark a step as done today; returns the updated day and any badge earned by it."""
    return routine_controller.log_step(db, user, step_id)


@router.delete("/steps/{step_id}/log", response_model=StepLogOut)
def unlog_step(step_id: int, user: CurrentUser, db: DB):
    """Undo today's tick for a step; returns the updated day."""
    return routine_controller.unlog_step(db, user, step_id)


@router.get("/history", response_model=HistoryOut)
def get_history(
    user: CurrentUser,
    db: DB,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
):
    """Calendar of past days (default: the last 30 days, at most 92)."""
    return routine_controller.get_history(db, user, start, end)


@streak_router.get("/streak", response_model=StreakOut)
def get_streak(user: CurrentUser, db: DB):
    """Days in a row with every scheduled step done."""
    return routine_controller.get_streak(db, user)
