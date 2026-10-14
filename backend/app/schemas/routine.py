from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.models.choices import STEP_CATEGORIES, STEP_TIMES_OF_DAY


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
    scheduled: bool  # part of THIS day (e.g. retinol only on its nights)
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
