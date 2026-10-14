from datetime import date

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models import RoutineStep, User
from app.repositories import ingredient_repository, routine_repository
from app.schemas.routine import RoutineDayOut, RoutineStepOut, StepIngredientOut
from app.services import routine_service
from app.services.local_time import user_today
from app.services.weekdays import from_mask, is_scheduled


def _no_routine() -> AppError:
    return AppError(404, "no_routine", "No routine yet. Take a skin scan to get your routine.")


def _step_not_found() -> AppError:
    # same answer for a step of another user, of an old routine, or that does not exist
    return AppError(404, "step_not_found", "This step is not part of your current routine.")


def log_step(db: Session, user: User, step_id: int) -> RoutineDayOut:
    """Tick a step as done TODAY (there is no date parameter: past days cannot be changed)."""
    step = routine_repository.get_step_in_active_routine(db, user.id, step_id)
    if step is None:
        raise _step_not_found()
    today = user_today(user)
    if not is_scheduled(step.days_of_week, today):
        # e.g. a retinoid advised 2-3 nights a week, on one of its rest days
        raise AppError(
            409, "step_not_scheduled_today", "This step is not part of today's routine."
        )

    routine_repository.add_log(db, user_id=user.id, step_id=step.id, log_date=today)
    db.commit()
    return get_day(db, user, today)


def unlog_step(db: Session, user: User, step_id: int) -> RoutineDayOut:
    """Un-tick a step for today (e.g. tapped by mistake)."""
    step = routine_repository.get_step_in_active_routine(db, user.id, step_id)
    if step is None:
        raise _step_not_found()
    today = user_today(user)
    routine_repository.remove_log(db, user_id=user.id, step_id=step.id, log_date=today)
    db.commit()
    return get_day(db, user, today)


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
            scheduled=is_scheduled(step.days_of_week, day),
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
