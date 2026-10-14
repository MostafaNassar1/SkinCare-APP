"""Fixtures and helpers for routine tests."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import Routine, RoutineLog, User
from app.scripts.create_sample_routine import create_sample_routine
from app.services.local_time import user_today


def days_ago(user: User, days: int) -> date:
    return user_today(user) - timedelta(days=days)


def last_weekday(user: User, weekday: int) -> date:
    """The most recent past day (yesterday or before) with this weekday (0 = Monday)."""
    day = days_ago(user, 1)
    while day.weekday() != weekday:
        day -= timedelta(days=1)
    return day


def start_routine_on(db: Session, routine: Routine, days_back: int) -> None:
    """Pretend the routine was created `days_back` days ago."""
    routine.created_at = datetime.now(UTC) - timedelta(days=days_back)
    db.flush()


def log(db: Session, user: User, step_ids, on: date) -> None:
    db.add_all(RoutineLog(routine_step_id=i, user_id=user.id, log_date=on) for i in step_ids)
    db.flush()


@pytest.fixture
def routine(db: Session, app_user: User) -> Routine:
    """The sample routine (adapalene on Mon/Wed/Fri), created 30 days ago."""
    routine = create_sample_routine(db, app_user)
    start_routine_on(db, routine, days_back=30)
    return routine
