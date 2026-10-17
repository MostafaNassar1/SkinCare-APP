from datetime import time

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator


class RemindersOut(BaseModel):
    enabled: bool  # routine reminders
    daily_forecast: bool  # the 11:00 skin forecast push
    morning_time: time  # in the user's time zone
    evening_time: time

    @field_serializer("morning_time", "evening_time")
    def hours_minutes(self, value: time) -> str:
        return value.strftime("%H:%M")  # "21:00"


class RemindersUpdate(BaseModel):
    """Only the sent fields change; times as "HH:MM" in the user's own time zone."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    daily_forecast: bool | None = None
    morning_time: time | None = None
    evening_time: time | None = None

    @field_validator("morning_time", "evening_time")
    @classmethod
    def whole_minutes(cls, value: time | None) -> time | None:
        if value is None:
            raise ValueError("A reminder time cannot be empty")
        if value.tzinfo is not None:
            raise ValueError("Send the local time without a time zone, e.g. 21:00")
        return value.replace(second=0, microsecond=0)

    @field_validator("enabled", "daily_forecast")
    @classmethod
    def switch_not_empty(cls, value: bool | None) -> bool:
        if value is None:
            raise ValueError("Must be true or false")
        return value

    @field_validator("morning_time")
    @classmethod
    def morning_before_noon(cls, value: time) -> time:
        if value.hour >= 12:
            raise ValueError("The morning reminder must be before 12:00")
        return value

    @field_validator("evening_time")
    @classmethod
    def evening_after_noon(cls, value: time) -> time:
        if value.hour < 12:
            raise ValueError("The evening reminder must be at 12:00 or later")
        return value
