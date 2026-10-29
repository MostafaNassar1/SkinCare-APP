from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models import RoutineStep, User
from app.repositories import ingredient_repository, routine_repository
from app.schemas.routine import (
    HistoryDayOut,
    HistoryOut,
    RoutineDayOut,
    RoutineStepOut,
    StepIngredientOut,
    StepLogOut,
    StreakOut,
)
from app.schemas.reference import AchievementOut
from app.services import (
    achievement_service,
    notification_service,
    routine_service,
    streak_service,
)
from app.services.local_time import user_today
from app.services.weekdays import from_mask


def _no_routine() -> AppError:
    return AppError(404, "no_routine", "No routine yet. Take a skin scan to get your routine.")


HISTORY_DEFAULT_DAYS = 30
HISTORY_MAX_DAYS = 92  # about 3 months per request


def get_streak(db: Session, user: User) -> StreakOut:
    streak = streak_service.compute_streak(db, user, user_today(user))
    return StreakOut(
        current_days=streak.current_days,
        longest_days=streak.longest_days,
        today_complete=streak.today_complete,
    )


def get_history(db: Session, user: User, start: date | None, end: date | None) -> HistoryOut:
    """The calendar: each day with done/scheduled counts and whether it was complete."""
    today = user_today(user)
    end = end or today
    start = start or end - timedelta(days=HISTORY_DEFAULT_DAYS - 1)
    if end > today:
        raise AppError(422, "date_in_future", "The history cannot include future days.")
    if start > end:
        raise AppError(422, "invalid_date_range", "The start date must be before the end date.")
    if (end - start).days + 1 > HISTORY_MAX_DAYS:
        raise AppError(
            422, "invalid_date_range", f"At most {HISTORY_MAX_DAYS} days can be requested."
        )

    return HistoryOut(
        start=start,
        end=end,
        days=[
            HistoryDayOut(
                date=status.day,
                scheduled_count=status.scheduled_count,
                done_count=status.done_count,
                complete=status.complete,
            )
            for status in streak_service.day_statuses(db, user, start, end)
        ],
    )


def _step_not_found() -> AppError:
    # same answer for a step of another user, of an old routine, or that does not exist
    return AppError(404, "step_not_found", "This step is not part of your current routine.")


def log_step(db: Session, user: User, step_id: int) -> StepLogOut:
    """Tick a step as done TODAY (there is no date parameter: past days cannot be changed)."""
    step = routine_repository.get_step_in_active_routine(db, user.id, step_id)
    if step is None:
        raise _step_not_found()
    today = user_today(user)
    if step.needs_product:
        raise AppError(
            409, "product_not_ready", "Tap \"I have it now\" once you have this step's product."
        )
    if not routine_service.step_counts_on(step, today):
        # e.g. a retinoid advised 2-3 nights a week, on one of its rest days
        raise AppError(
            409, "step_not_scheduled_today", "This step is not part of today's routine."
        )

    routine_repository.add_log(db, user_id=user.id, step_id=step.id, log_date=today)
    awarded = achievement_service.award_new(db, user, today)
    db.commit()
    notification_service.push_all(db, awarded.notifications)  # only after the commit
    return StepLogOut(
        day=get_day(db, user, today),
        new_achievements=[AchievementOut.model_validate(a) for a in awarded.achievements],
    )


def unlog_step(db: Session, user: User, step_id: int) -> StepLogOut:
    """Un-tick a step for today (e.g. tapped by mistake)."""
    step = routine_repository.get_step_in_active_routine(db, user.id, step_id)
    if step is None:
        raise _step_not_found()
    today = user_today(user)
    routine_repository.remove_log(db, user_id=user.id, step_id=step.id, log_date=today)
    db.commit()
    # badges already earned are kept: unticking never takes one away
    return StepLogOut(day=get_day(db, user, today), new_achievements=[])


def get_day(db: Session, user: User, day: date | None) -> RoutineDayOut:
    """The routine as it applied on `day` (default: the user's today), with what was done."""
    today = user_today(user)
    day = day or today
    if day > today:
        raise AppError(422, "date_in_future", "Only today and past days can be viewed.")

    routine = routine_service.find_routine_on(db, user, day)
    if routine is None:
        raise _no_routine()

    done_ids = routine_repository.logged_step_ids(db, user.id, day)
    ingredient_ids = {s.ingredient_id for s in routine.steps if s.ingredient_id is not None}
    names = {i.id: i.name for i in ingredient_repository.get_by_ids(db, ingredient_ids)}

    def step_out(step: RoutineStep) -> RoutineStepOut:
        return RoutineStepOut(
            id=step.id,
            time_of_day=step.time_of_day,
            step_order=step.step_order,
            step_category=step.step_category,
            title=step.title,
            description=step.description,
            product_type=step.product_type,
            ingredient=(
                StepIngredientOut(id=step.ingredient_id, name=names[step.ingredient_id])
                if step.ingredient_id in names
                else None
            ),
            recommended_concentration=step.recommended_concentration,
            days=from_mask(step.days_of_week),
            scheduled=routine_service.step_counts_on(step, day),
            needs_product=step.needs_product,
            done=step.id in done_ids,
        )

    steps = sorted(routine.steps, key=lambda s: s.step_order)
    scheduled = routine_service.scheduled_steps(routine, day)
    done_count = sum(1 for step in scheduled if step.id in done_ids)
    return RoutineDayOut(
        date=day,
        is_today=day == today,
        can_log=day == today and routine.is_active,
        routine_id=routine.id,
        morning=[step_out(s) for s in steps if s.time_of_day == "morning"],
        evening=[step_out(s) for s in steps if s.time_of_day == "evening"],
        scheduled_count=len(scheduled),
        done_count=done_count,
        complete=bool(scheduled) and done_count == len(scheduled),
    )
