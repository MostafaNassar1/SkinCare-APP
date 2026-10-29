"""Which routine applied on a given day, and which of its steps were scheduled then.

Shared by the routine screen, logging and the streak calculation.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.models import Routine, RoutineStep, User
from app.repositories import routine_repository
from app.services.local_time import local_date
from app.services.weekdays import is_scheduled


def routine_on(routines: list[Routine], day: date, user: User) -> Routine | None:
    """The routine that applied on `day`: the newest one created on or before that (local) day.

    `routines` must be sorted oldest first. A routine replaced later still applies to its own
    past days, so history keeps showing the steps the user really had.
    """
    current = None
    for routine in routines:
        if local_date(routine.created_at, user) <= day:
            current = routine
        else:
            break
    return current


def find_routine_on(db: Session, user: User, day: date) -> Routine | None:
    return routine_on(routine_repository.list_for_user(db, user.id), day, user)


def step_counts_on(step: RoutineStep, day: date) -> bool:
    """Whether the step is due on `day`: one of its weekdays, and the user has its product.

    A step waiting for its product (needs_product) is left out of reminders and streaks; once
    the user taps "I have it now" it counts from that day (product_ready_on), never before.
    """
    if step.needs_product:
        return False
    if step.product_ready_on is not None and day < step.product_ready_on:
        return False
    return is_scheduled(step.days_of_week, day)


def scheduled_steps(routine: Routine, day: date) -> list[RoutineStep]:
    return [step for step in routine.steps if step_counts_on(step, day)]
