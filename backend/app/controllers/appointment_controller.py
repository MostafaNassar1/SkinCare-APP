"""The appointment tracker: real appointments booked by phone, recorded by the user.

Reminders (the day before and 2 hours before) and the calendar come in Step 11.
"""

from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models import Appointment, User
from app.repositories import appointment_repository, place_repository
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentOut,
    AppointmentPlaceOut,
    AppointmentUpdate,
)
from app.schemas.places import CATEGORIES_BY_TYPE

MAX_DAYS_AHEAD = 365


def _not_found() -> AppError:
    return AppError(404, "appointment_not_found", "This appointment does not exist.")


def _out(appointment: Appointment) -> AppointmentOut:
    place = appointment.clinic
    return AppointmentOut(
        id=appointment.id,
        status=appointment.status,
        appointment_at=appointment.requested_datetime,
        doctor_name=appointment.doctor_name,
        notes=appointment.notes,
        created_at=appointment.created_at,
        place=AppointmentPlaceOut(
            id=place.id,
            name=place.name,
            category=place.category,
            address=place.address,
            phone_number=place.phone_number,
            latitude=float(place.latitude),
            longitude=float(place.longitude),
            is_active=place.is_active,
        ),
    )


def _check_time(at: datetime) -> None:
    now = datetime.now(UTC)
    if not now < at <= now + timedelta(days=MAX_DAYS_AHEAD):
        raise AppError(
            422,
            "invalid_appointment_time",
            f"The appointment must be in the future, within {MAX_DAYS_AHEAD} days.",
        )


def _own_scheduled(db: Session, user: User, appointment_id: int) -> Appointment:
    appointment = appointment_repository.get_for_user(db, user.id, appointment_id)
    if appointment is None:
        raise _not_found()
    if appointment.status != "scheduled":
        raise AppError(
            409, "appointment_closed", "This appointment is already completed or cancelled."
        )
    return appointment


def create(db: Session, user: User, data: AppointmentCreate) -> AppointmentOut:
    place = place_repository.get_active(db, data.place_id)
    if place is None:
        raise AppError(404, "place_not_found", "This place does not exist or has closed.")
    if place.category not in CATEGORIES_BY_TYPE["clinics"]:
        raise AppError(422, "not_a_clinic", "Appointments are for clinics, doctors and hospitals.")
    _check_time(data.appointment_at)

    appointment = appointment_repository.create(
        db,
        user_id=user.id,
        place_id=place.id,
        at=data.appointment_at,
        doctor_name=data.doctor_name,
        notes=data.notes,
    )
    db.commit()
    return get(db, user, appointment.id)


def list_mine(db: Session, user: User, when: Literal["upcoming", "past"]) -> list[AppointmentOut]:
    now = datetime.now(UTC)
    if when == "upcoming":
        appointments = appointment_repository.list_upcoming(db, user.id, now)
    else:
        appointments = appointment_repository.list_past(db, user.id, now)
    return [_out(a) for a in appointments]


def get(db: Session, user: User, appointment_id: int) -> AppointmentOut:
    appointment = appointment_repository.get_for_user(db, user.id, appointment_id)
    if appointment is None:
        raise _not_found()
    return _out(appointment)


def update(db: Session, user: User, appointment_id: int, data: AppointmentUpdate) -> AppointmentOut:
    appointment = _own_scheduled(db, user, appointment_id)
    changes = data.model_dump(exclude_unset=True)
    if "appointment_at" in changes:
        _check_time(changes["appointment_at"])
        appointment.requested_datetime = changes.pop("appointment_at")
    for field, value in changes.items():
        setattr(appointment, field, value)
    db.commit()
    return get(db, user, appointment.id)


def complete(db: Session, user: User, appointment_id: int) -> AppointmentOut:
    appointment = _own_scheduled(db, user, appointment_id)
    if appointment.requested_datetime > datetime.now(UTC):
        raise AppError(
            409, "appointment_not_yet", "An appointment can be marked done once its time passed."
        )
    appointment.status = "completed"
    db.commit()
    return get(db, user, appointment.id)


def cancel(db: Session, user: User, appointment_id: int) -> AppointmentOut:
    appointment = _own_scheduled(db, user, appointment_id)
    appointment.status = "cancelled"
    db.commit()
    return get(db, user, appointment.id)


def remove(db: Session, user: User, appointment_id: int) -> None:
    """Delete a wrong entry (the user's own record); 404 if it is not theirs."""
    if appointment_repository.get_for_user(db, user.id, appointment_id) is None:
        raise _not_found()
    appointment_repository.delete_for_user(db, user.id, appointment_id)
    db.commit()
