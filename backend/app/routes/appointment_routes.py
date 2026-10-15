from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.controllers import appointment_controller
from app.core.dependencies import CurrentUser, get_db
from app.schemas.appointment import AppointmentCreate, AppointmentOut, AppointmentUpdate

router = APIRouter(prefix="/me/appointments", tags=["Appointments"])

DB = Annotated[Session, Depends(get_db)]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=AppointmentOut)
def create_appointment(data: AppointmentCreate, user: CurrentUser, db: DB):
    """Record a real appointment booked by phone at a clinic/hospital from the map."""
    return appointment_controller.create(db, user, data)


@router.get("", response_model=list[AppointmentOut])
def list_appointments(
    user: CurrentUser, db: DB, when: Annotated[Literal["upcoming", "past"], Query()] = "upcoming"
):
    return appointment_controller.list_mine(db, user, when)


@router.get("/{appointment_id}", response_model=AppointmentOut)
def get_appointment(appointment_id: int, user: CurrentUser, db: DB):
    return appointment_controller.get(db, user, appointment_id)


@router.patch("/{appointment_id}", response_model=AppointmentOut)
def update_appointment(appointment_id: int, data: AppointmentUpdate, user: CurrentUser, db: DB):
    """Change the time, doctor or notes (e.g. the clinic moved it)."""
    return appointment_controller.update(db, user, appointment_id, data)


@router.post("/{appointment_id}/complete", response_model=AppointmentOut)
def complete_appointment(appointment_id: int, user: CurrentUser, db: DB):
    return appointment_controller.complete(db, user, appointment_id)


@router.post("/{appointment_id}/cancel", response_model=AppointmentOut)
def cancel_appointment(appointment_id: int, user: CurrentUser, db: DB):
    return appointment_controller.cancel(db, user, appointment_id)


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_appointment(appointment_id: int, user: CurrentUser, db: DB):
    """Remove a wrongly recorded appointment."""
    appointment_controller.remove(db, user, appointment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
