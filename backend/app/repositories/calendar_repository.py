from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import CalendarEvent


def list_custom_between(
    db: Session, user_id: int, start: datetime, end: datetime
) -> list[CalendarEvent]:
    """The user's own events in [start, end), in time order."""
    return list(
        db.scalars(
            select(CalendarEvent)
            .where(
                CalendarEvent.user_id == user_id,
                CalendarEvent.event_type == "custom",
                CalendarEvent.event_datetime >= start,
                CalendarEvent.event_datetime < end,
            )
            .order_by(CalendarEvent.event_datetime, CalendarEvent.id)
        )
    )


def get_custom_for_user(db: Session, user_id: int, event_id: int) -> CalendarEvent | None:
    """Only this user's own custom event (another user's id is simply not found)."""
    return db.scalar(
        select(CalendarEvent).where(
            CalendarEvent.id == event_id,
            CalendarEvent.user_id == user_id,
            CalendarEvent.event_type == "custom",
        )
    )


def create_custom(
    db: Session, *, user_id: int, title: str, at: datetime, notes: str | None
) -> CalendarEvent:
    event = CalendarEvent(
        user_id=user_id, title=title, event_type="custom", event_datetime=at, notes=notes
    )
    db.add(event)
    db.flush()
    return event


def delete_custom(db: Session, user_id: int, event_id: int) -> None:
    db.execute(
        delete(CalendarEvent).where(
            CalendarEvent.id == event_id,
            CalendarEvent.user_id == user_id,
            CalendarEvent.event_type == "custom",
        )
    )
