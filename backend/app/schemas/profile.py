from datetime import date, datetime
from functools import cache
from typing import Literal
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.choices import GENDERS, SKIN_TYPES
from app.schemas.auth import FullName

# Google Play and common privacy law (e.g. COPPA) require parental consent below 13
MIN_AGE_YEARS = 13
SKIN_NOTES_MAX_LENGTH = 1000


@cache
def _time_zones() -> frozenset[str]:
    return frozenset(available_timezones())


def age_on(birth: date, today: date) -> int:
    had_birthday = (today.month, today.day) >= (birth.month, birth.day)
    return today.year - birth.year - (0 if had_birthday else 1)


class SkinProfileOut(BaseModel):
    skin_type: Literal[SKIN_TYPES] | None  # set by the skin quiz
    fitzpatrick_scale: int | None  # skin tone type 1-6, from the skin quiz
    skin_quiz_completed_at: datetime | None
    is_pregnant_or_breastfeeding: bool
    skin_notes: str | None


class ProfileOut(BaseModel):
    id: int
    full_name: str
    email: str
    email_verified: bool
    auth_provider: str  # how the account was created
    has_password: bool  # False for Google-only accounts: the app offers "Add a password"
    phone_number: str | None
    date_of_birth: date | None
    gender: Literal[GENDERS] | None
    timezone: str
    profile_picture_url: str | None
    created_at: datetime
    skin: SkinProfileOut


class ProfileUpdate(BaseModel):
    """Only the fields that are sent are changed; null clears an optional field."""

    # a typo such as "fulname" is an error instead of being silently ignored; the email cannot be
    # changed here either
    model_config = ConfigDict(extra="forbid")

    full_name: FullName | None = None
    phone_number: str | None = Field(default=None, pattern=r"^\+?[0-9][0-9 \-]{5,28}$")
    date_of_birth: date | None = None
    gender: Literal[GENDERS] | None = None
    timezone: str | None = None
    is_pregnant_or_breastfeeding: bool | None = None
    skin_notes: str | None = Field(default=None, max_length=SKIN_NOTES_MAX_LENGTH)

    @field_validator("phone_number", mode="before")
    @classmethod
    def strip_phone(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("timezone")
    @classmethod
    def known_time_zone(cls, value: str | None) -> str | None:
        # the daily forecast is sent at 11:00 in this zone, so it must be a real IANA name
        if value is not None and value not in _time_zones():
            raise ValueError("Unknown time zone; use an IANA name such as Asia/Beirut")
        return value

    @field_validator("date_of_birth")
    @classmethod
    def plausible_birth_date(cls, value: date | None) -> date | None:
        if value is None:
            return value
        today = date.today()
        if value > today:
            raise ValueError("Date of birth cannot be in the future")
        if value.year < 1900:
            raise ValueError("Date of birth is too far in the past")
        if age_on(value, today) < MIN_AGE_YEARS:
            raise ValueError(f"You must be at least {MIN_AGE_YEARS} years old")
        return value

    @field_validator("skin_notes")
    @classmethod
    def clean_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None  # only spaces = no notes

    @model_validator(mode="after")
    def required_fields_not_cleared(self) -> "ProfileUpdate":
        for field in ("full_name", "timezone", "is_pregnant_or_breastfeeding"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be empty")
        return self
