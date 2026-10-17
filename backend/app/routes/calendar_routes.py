from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.controllers import calendar_controller
from app.core.dependencies import CurrentUser, get_db
from app.schemas.calendar import (
    CalendarEventCreate,
    CalendarEventOut,
    CalendarEventUpdate,
    CalendarMonthOut,
)

router = APIRouter(prefix="/me", tags=["Calendar"])

DB = Annotated[Session, Depends(get_db)]


@router.get("/calendar", response_model=CalendarMonthOut)
def get_month(
    user: CurrentUser,
    db: DB,
    month: Annotated[
        str | None, Query(pattern=r"^20\d\d-(0[1-9]|1[0-2])$", examples=["2026-10"])
    ] = None,
):
    """One month (default: the current one): each day's routine status, appointments and
    personal events, in the user's time zone."""
    return calendar_controller.get_month(db, user, month)


@router.get("/calendar.ics", response_class=Response)
def export_ics(user: CurrentUser, db: DB):
    """"Add to my phone's calendar": a standard .ics file (Google Calendar, Apple Calendar...)."""
    return Response(
        content=calendar_controller.export_ics(db, user),
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="skincare-calendar.ics"',
            "Cache-Control": "no-store",  # personal data
        },
    )


@router.post(
    "/calendar/events", response_model=CalendarEventOut, status_code=status.HTTP_201_CREATED
)
def create_event(data: CalendarEventCreate, user: CurrentUser, db: DB):
    return calendar_controller.create_event(db, user, data)


@router.patch("/calendar/events/{event_id}", response_model=CalendarEventOut)
def update_event(event_id: int, data: CalendarEventUpdate, user: CurrentUser, db: DB):
    return calendar_controller.update_event(db, user, event_id, data)


@router.delete("/calendar/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: int, user: CurrentUser, db: DB):
    calendar_controller.delete_event(db, user, event_id)
