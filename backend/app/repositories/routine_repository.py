from datetime import date

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, selectinload

from app.models import Routine, RoutineLog, RoutineStep


def list_for_user(db: Session, user_id: int) -> list[Routine]:
    """All the user's routines, oldest first, with their steps loaded."""
    return list(
        db.scalars(
            select(Routine)
            .where(Routine.user_id == user_id)
            .options(selectinload(Routine.steps))
            .order_by(Routine.created_at, Routine.id)
        )
    )


def get_active(db: Session, user_id: int) -> Routine | None:
    return db.scalar(
        select(Routine)
        .where(Routine.user_id == user_id, Routine.is_active)
        .options(selectinload(Routine.steps))
    )


def deactivate_all(db: Session, user_id: int) -> None:
    """Before a new routine becomes active (at most one active routine per user)."""
    db.execute(
        update(Routine).where(Routine.user_id == user_id, Routine.is_active).values(is_active=False)
    )


def create(db: Session, *, user_id: int, steps: list[RoutineStep]) -> Routine:
    routine = Routine(user_id=user_id, is_active=True, steps=steps)
    db.add(routine)
    db.flush()
    return routine


def logged_step_ids(db: Session, user_id: int, log_date: date) -> set[int]:
    """Steps this user ticked on that (local) date."""
    return set(
        db.scalars(
            select(RoutineLog.routine_step_id).where(
                RoutineLog.user_id == user_id, RoutineLog.log_date == log_date
            )
        )
    )


def get_step_in_active_routine(db: Session, user_id: int, step_id: int) -> RoutineStep | None:
    """The step, only if it belongs to this user's ACTIVE routine (never someone else's)."""
    return db.scalar(
        select(RoutineStep)
        .join(Routine, Routine.id == RoutineStep.routine_id)
        .where(RoutineStep.id == step_id, Routine.user_id == user_id, Routine.is_active)
    )


def add_log(db: Session, *, user_id: int, step_id: int, log_date: date) -> None:
    """Tick a step for a day. ON CONFLICT DO NOTHING: ticking twice (or two taps at the same
    moment) leaves exactly one row, thanks to the unique (step, user, date) rule."""
    db.execute(
        pg_insert(RoutineLog)
        .values(routine_step_id=step_id, user_id=user_id, log_date=log_date)
        .on_conflict_do_nothing(
            index_elements=["routine_step_id", "user_id", "log_date"]
        )
    )


def remove_log(db: Session, *, user_id: int, step_id: int, log_date: date) -> None:
    db.execute(
        delete(RoutineLog).where(
            RoutineLog.routine_step_id == step_id,
            RoutineLog.user_id == user_id,
            RoutineLog.log_date == log_date,
        )
    )


def logs_between(db: Session, user_id: int, first: date, last: date) -> dict[date, set[int]]:
    """date -> ids of the steps ticked that day, for every day in [first, last]."""
    rows = db.execute(
        select(RoutineLog.log_date, RoutineLog.routine_step_id).where(
            RoutineLog.user_id == user_id, RoutineLog.log_date.between(first, last)
        )
    )
    by_day: dict[date, set[int]] = {}
    for log_date, step_id in rows:
        by_day.setdefault(log_date, set()).add(step_id)
    return by_day
