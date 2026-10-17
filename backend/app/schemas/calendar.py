from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.models.choices import APPOINTMENT_STATUSES, PLACE_CATEGORIES
from app.schemas.appointment import Notes


def _title(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("The title cannot be empty")
    return value


Title = Annotated[str, Field(max_length=150), AfterValidator(_title)]

# How a day looks in the calendar:
# complete = every scheduled step done (a streak day) · partial = some done · missed = none done
# today = not finished yet · planned = a future day with steps · rest = no step scheduled
# (e.g. a retinoid-only evening on a rest day) · None = no routine on that day
RoutineDay = Literal["complete", "partial", "missed", "today", "planned", "rest"]


class CalendarEventCreate(BaseModel):
    """A personal event, e.g. "Start the new sunscreen" or "Dermatologist follow-up call"."""

    model_config = ConfigDict(extra="forbid")

    title: Title
    starts_at: AwareDatetime  # with its time zone, e.g. 2026-10-25T09:00:00+03:00
    notes: Notes = None


class CalendarEventUpdate(BaseModel):
    """Only the sent fields change; null clears the notes."""

    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    starts_at: AwareDatetime | None = None
    notes: Notes = None

    @model_validator(mode="after")
    def required_not_cleared(self) -> "CalendarEventUpdate":
        for field in ("title", "starts_at"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be empty")
        return self


class CalendarPlaceOut(BaseModel):
    id: int
    name: str
    category: Literal[PLACE_CATEGORIES]


class CalendarEventOut(BaseModel):
    kind: Literal["appointment", "custom"]  # appointments come from the appointment tracker
    id: int  # the appointment id or the custom event id (use it with that kind's endpoints)
    title: str
    starts_at: datetime  # in the user's time zone
    notes: str | None
    status: Literal[APPOINTMENT_STATUSES] | None = None  # appointments only
    place: CalendarPlaceOut | None = None  # appointments only


class CalendarDayOut(BaseModel):
    date: date
    routine: RoutineDay | None
    scheduled_count: int  # routine steps scheduled that day
    done_count: int


class CalendarMonthOut(BaseModel):
    month: str  # "2026-10"
    today: date  # the user's today, to highlight it
    days: list[CalendarDayOut]  # every day of the month
    events: list[CalendarEventOut]  # appointments + personal events, in time order
