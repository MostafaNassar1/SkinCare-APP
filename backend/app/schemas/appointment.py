from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.models.choices import APPOINTMENT_STATUSES, PLACE_CATEGORIES

NOTES_MAX_LENGTH = 1000


def _clean(value: str | None) -> str | None:
    return (value.strip() or None) if value is not None else None


# trimmed; only spaces = no text
DoctorName = Annotated[str | None, Field(max_length=150), AfterValidator(_clean)]
Notes = Annotated[str | None, Field(max_length=NOTES_MAX_LENGTH), AfterValidator(_clean)]


class AppointmentCreate(BaseModel):
    """A real appointment the user booked by phone, recorded so the app can remind them."""

    model_config = ConfigDict(extra="forbid")

    place_id: int  # a clinic, doctor or hospital from the map
    # with its time zone (e.g. 2026-10-20T16:00:00+03:00), so it can never be misread
    appointment_at: AwareDatetime
    doctor_name: DoctorName = None
    notes: Notes = None


class AppointmentUpdate(BaseModel):
    """Only the sent fields change (e.g. the clinic moved the appointment); null clears the doctor
    or the notes."""

    model_config = ConfigDict(extra="forbid")

    appointment_at: AwareDatetime | None = None
    doctor_name: DoctorName = None
    notes: Notes = None

    @model_validator(mode="after")
    def time_not_cleared(self) -> "AppointmentUpdate":
        if "appointment_at" in self.model_fields_set and self.appointment_at is None:
            raise ValueError("appointment_at cannot be empty")
        return self


class AppointmentPlaceOut(BaseModel):
    id: int
    name: str
    category: Literal[PLACE_CATEGORIES]
    address: str | None
    phone_number: str | None  # "Call to reschedule"
    latitude: float
    longitude: float
    is_active: bool  # False if the place has since disappeared from the map data


class AppointmentOut(BaseModel):
    id: int
    status: Literal[APPOINTMENT_STATUSES]
    appointment_at: datetime
    doctor_name: str | None
    notes: str | None
    created_at: datetime
    place: AppointmentPlaceOut
