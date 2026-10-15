from datetime import datetime

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Appointment


def create(
    db: Session,
    *,
    user_id: int,
    place_id: int,
    at: datetime,
    doctor_name: str | None,
    notes: str | None,
) -> Appointment:
    appointment = Appointment(
        user_id=user_id,
        clinic_id=place_id,
        requested_datetime=at,
        status="scheduled",
        doctor_name=doctor_name,
        notes=notes,
    )
    db.add(appointment)
    db.flush()
    return appointment


def get_for_user(db: Session, user_id: int, appointment_id: int) -> Appointment | None:
    """Only this user's own appointment (another user's id is simply not found)."""
    return db.scalar(
        select(Appointment)
        .where(Appointment.id == appointment_id, Appointment.user_id == user_id)
        .options(selectinload(Appointment.clinic))
    )


def list_upcoming(db: Session, user_id: int, now: datetime) -> list[Appointment]:
    """Still scheduled and not yet passed, soonest first."""
    return list(
        db.scalars(
            select(Appointment)
            .where(
                Appointment.user_id == user_id,
                Appointment.status == "scheduled",
                Appointment.requested_datetime >= now,
            )
            .options(selectinload(Appointment.clinic))
            .order_by(Appointment.requested_datetime)
        )
    )


def list_past(db: Session, user_id: int, now: datetime) -> list[Appointment]:
    """Passed, completed or cancelled, most recent first."""
    return list(
        db.scalars(
            select(Appointment)
            .where(
                Appointment.user_id == user_id,
                or_(Appointment.status != "scheduled", Appointment.requested_datetime < now),
            )
            .options(selectinload(Appointment.clinic))
            .order_by(Appointment.requested_datetime.desc())
        )
    )


def delete_for_user(db: Session, user_id: int, appointment_id: int) -> None:
    db.execute(
        delete(Appointment).where(
            Appointment.id == appointment_id, Appointment.user_id == user_id
        )
    )
