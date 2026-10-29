from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.models.choices import STEP_CATEGORIES, STEP_TIMES_OF_DAY
from app.schemas.reference import AchievementOut


class StepIngredientOut(BaseModel):
    id: int
    name: str


class RoutineStepOut(BaseModel):
    id: int
    time_of_day: Literal[STEP_TIMES_OF_DAY]
    step_order: int
    step_category: Literal[STEP_CATEGORIES]
    title: str
    description: str | None
    product_type: str  # e.g. "Salicylic acid foaming cleanser" (product types, no brands)
    ingredient: StepIngredientOut | None
    recommended_concentration: str | None  # e.g. "0.5-2%"
    days: list[str]  # scheduled weekdays, e.g. ["mon", "wed", "fri"]
    scheduled: bool  # part of THIS day (e.g. retinol only on its nights; not while waiting)
    needs_product: bool  # the user does not have the product yet: not counted until they do
    done: bool


class RoutineDayOut(BaseModel):
    date: date
    is_today: bool
    can_log: bool  # only today can be ticked; past days are view-only
    routine_id: int
    morning: list[RoutineStepOut]
    evening: list[RoutineStepOut]
    scheduled_count: int  # steps scheduled for this day
    done_count: int  # of those, how many were done
    complete: bool  # all scheduled steps done: the day counts for the streak


class StreakOut(BaseModel):
    current_days: int  # complete days in a row up to today (or yesterday if today is not done yet)
    longest_days: int
    today_complete: bool


class HistoryDayOut(BaseModel):
    date: date
    scheduled_count: int
    done_count: int
    complete: bool


class HistoryOut(BaseModel):
    start: date
    end: date
    days: list[HistoryDayOut]  # only days on which the user had a routine


class StepLogOut(BaseModel):
    """The answer to ticking / unticking a step."""

    day: RoutineDayOut  # the updated day, ready for the screen
    new_achievements: list[AchievementOut]  # badges earned by this tick: show a celebration
