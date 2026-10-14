from datetime import date

from sqlalchemy import select, update
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
