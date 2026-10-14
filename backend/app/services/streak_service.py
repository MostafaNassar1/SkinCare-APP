"""Day completion and streaks (decided with the user, 2026-10-14):

- A day is COMPLETE when every step scheduled for that day (by its weekdays) was ticked. A
  retinoid on its rest day is not scheduled, so it is never needed.
- Each day is judged with the routine that applied on that day.
- The current streak counts complete days up to today; if today is not complete YET, it counts
  up to yesterday (a streak is not broken until the day is over).
- Days before the user's first routine are not counted.

Shared by GET /me/streak, GET /me/routine/history and achievement awarding, so a "7-Day Streak"
badge always matches the streak the user sees.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import User
from app.repositories import routine_repository
from app.services.local_time import local_date
from app.services.routine_service import routine_on, scheduled_steps


@dataclass(frozen=True)
class DayStatus:
    day: date
    scheduled_count: int
    done_count: int

    @property
    def complete(self) -> bool:
        return self.scheduled_count > 0 and self.done_count == self.scheduled_count


@dataclass(frozen=True)
class Streak:
    current_days: int
    longest_days: int
    today_complete: bool


def _days(first: date, last: date):
    day = first
    while day <= last:
        yield day
        day += timedelta(days=1)


def day_statuses(db: Session, user: User, first: date, last: date) -> list[DayStatus]:
    """One status per day in [first, last] on which the user had a routine."""
    routines = routine_repository.list_for_user(db, user.id)
    logs = routine_repository.logs_between(db, user.id, first, last)
    statuses = []
    for day in _days(first, last):
        routine = routine_on(routines, day, user)
        if routine is None:
            continue
        scheduled = {step.id for step in scheduled_steps(routine, day)}
        done = scheduled & logs.get(day, set())
        statuses.append(DayStatus(day, len(scheduled), len(done)))
    return statuses


def first_routine_day(db: Session, user: User) -> date | None:
    routines = routine_repository.list_for_user(db, user.id)
    return local_date(routines[0].created_at, user) if routines else None


def compute_streak(db: Session, user: User, today: date) -> Streak:
    first = first_routine_day(db, user)
    if first is None or first > today:
        return Streak(current_days=0, longest_days=0, today_complete=False)

    complete = {status.day for status in day_statuses(db, user, first, today) if status.complete}

    longest = run = 0
    for day in _days(first, today):
        run = run + 1 if day in complete else 0
        longest = max(longest, run)

    today_complete = today in complete
    current = 0
    day = today if today_complete else today - timedelta(days=1)
    while day in complete:
        current += 1
        day -= timedelta(days=1)

    return Streak(current_days=current, longest_days=longest, today_complete=today_complete)
