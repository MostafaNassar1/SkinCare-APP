"""The calendar: a month of routine days, appointments and personal events, plus a .ics export.

Appointments are read from the appointment tracker (never copied into calendar_events), so a
moved or cancelled appointment is always shown as it really is.
"""

import calendar
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models import Appointment, CalendarEvent, User
from app.repositories import appointment_repository, calendar_repository, routine_repository
from app.schemas.calendar import (
    CalendarDayOut,
    CalendarEventCreate,
    CalendarEventOut,
    CalendarEventUpdate,
    CalendarMonthOut,
    CalendarPlaceOut,
)
from app.services import ics_service, streak_service
from app.services.ics_service import IcsEvent
from app.services.local_time import user_today, user_zone
from app.services.routine_service import scheduled_steps

MAX_YEARS_AWAY = 5  # personal events: a sanity limit, not a rule of the app
EXPORT_PAST_DAYS = 30
EXPORT_FUTURE_DAYS = 365
APPOINTMENT_LENGTH = timedelta(hours=1)  # the tracker stores only the start time
EVENT_LENGTH = timedelta(minutes=30)
APPOINTMENT_ALARM = timedelta(hours=2)  # same as the app's own "2 hours before" reminder


def _not_found() -> AppError:
    return AppError(404, "calendar_event_not_found", "This calendar event does not exist.")


def _local_midnight(day: date, user: User) -> datetime:
    return datetime.combine(day, time(0), tzinfo=user_zone(user)).astimezone(UTC)


def _appointment_title(appointment: Appointment) -> str:
    if appointment.doctor_name:
        return f"Appointment with {appointment.doctor_name}"
    return f"Appointment at {appointment.clinic.name}"


def _appointment_out(appointment: Appointment, user: User) -> CalendarEventOut:
    place = appointment.clinic
    return CalendarEventOut(
        kind="appointment",
        id=appointment.id,
        title=_appointment_title(appointment),
        starts_at=appointment.requested_datetime.astimezone(user_zone(user)),
        notes=appointment.notes,
        status=appointment.status,
        place=CalendarPlaceOut(id=place.id, name=place.name, category=place.category),
    )


def _custom_out(event: CalendarEvent, user: User) -> CalendarEventOut:
    return CalendarEventOut(
        kind="custom",
        id=event.id,
        title=event.title,
        starts_at=event.event_datetime.astimezone(user_zone(user)),
        notes=event.notes,
    )


# ---------- The month ----------


def _routine_days(db: Session, user: User, first: date, last: date) -> list[CalendarDayOut]:
    today = user_today(user)
    # past days and today: exactly what the streak counts (same service)
    past = (
        {s.day: s for s in streak_service.day_statuses(db, user, first, min(last, today))}
        if first <= today
        else {}
    )
    # future days: the active routine's schedule
    active = routine_repository.get_active(db, user.id) if last > today else None

    days = []
    day = first
    while day <= last:
        if day <= today:
            status = past.get(day)
            scheduled, done = (status.scheduled_count, status.done_count) if status else (0, 0)
            if status is None:
                kind = None  # no routine yet on that day
            elif scheduled == 0:
                kind = "rest"
            elif status.complete:
                kind = "complete"
            elif day == today:
                kind = "today"  # still time to finish it
            else:
                kind = "partial" if done else "missed"
        else:
            scheduled = len(scheduled_steps(active, day)) if active else 0
            done = 0
            kind = None if active is None else ("planned" if scheduled else "rest")
        days.append(
            CalendarDayOut(date=day, routine=kind, scheduled_count=scheduled, done_count=done)
        )
        day += timedelta(days=1)
    return days


def get_month(db: Session, user: User, month: str | None) -> CalendarMonthOut:
    today = user_today(user)
    year, number = (int(p) for p in month.split("-")) if month else (today.year, today.month)
    first = date(year, number, 1)
    last = date(year, number, calendar.monthrange(year, number)[1])
    start, end = _local_midnight(first, user), _local_midnight(last + timedelta(days=1), user)

    events = [
        *(_appointment_out(a, user) for a in appointment_repository.list_between_for_user(
            db, user.id, start, end
        )),
        *(_custom_out(e, user) for e in calendar_repository.list_custom_between(
            db, user.id, start, end
        )),
    ]
    events.sort(key=lambda e: (e.starts_at, e.kind, e.id))
    return CalendarMonthOut(
        month=f"{year:04d}-{number:02d}",
        today=today,
        days=_routine_days(db, user, first, last),
        events=events,
    )


# ---------- Personal events ----------


def _check_time(at: datetime) -> None:
    if abs(at - datetime.now(UTC)) > timedelta(days=365 * MAX_YEARS_AWAY):
        raise AppError(
            422,
            "invalid_event_time",
            f"The event must be within {MAX_YEARS_AWAY} years from today.",
        )


def create_event(db: Session, user: User, data: CalendarEventCreate) -> CalendarEventOut:
    _check_time(data.starts_at)
    event = calendar_repository.create_custom(
        db, user_id=user.id, title=data.title, at=data.starts_at, notes=data.notes
    )
    db.commit()
    return _custom_out(event, user)


def update_event(
    db: Session, user: User, event_id: int, data: CalendarEventUpdate
) -> CalendarEventOut:
    event = calendar_repository.get_custom_for_user(db, user.id, event_id)
    if event is None:
        raise _not_found()
    changes = data.model_dump(exclude_unset=True)
    if "starts_at" in changes:
        _check_time(changes["starts_at"])
        event.event_datetime = changes.pop("starts_at")
    for field, value in changes.items():
        setattr(event, field, value)
    db.commit()
    return _custom_out(event, user)


def delete_event(db: Session, user: User, event_id: int) -> None:
    if calendar_repository.get_custom_for_user(db, user.id, event_id) is None:
        raise _not_found()
    calendar_repository.delete_custom(db, user.id, event_id)
    db.commit()


# ---------- .ics export ----------


def _appointment_ics(appointment: Appointment) -> IcsEvent:
    place = appointment.clinic
    details = [
        f"Doctor: {appointment.doctor_name}" if appointment.doctor_name else None,
        f"Phone: {place.phone_number}" if place.phone_number else None,
        appointment.notes,
    ]
    return IcsEvent(
        uid=f"appointment-{appointment.id}",
        title=_appointment_title(appointment),
        starts_at=appointment.requested_datetime,
        duration=APPOINTMENT_LENGTH,
        description="\n".join(d for d in details if d) or None,
        location=", ".join(p for p in (place.name, place.address) if p),
        cancelled=appointment.status == "cancelled",
        alarm_before=APPOINTMENT_ALARM if appointment.status == "scheduled" else None,
    )


def _custom_ics(event: CalendarEvent) -> IcsEvent:
    return IcsEvent(
        uid=f"event-{event.id}",
        title=event.title,
        starts_at=event.event_datetime,
        duration=EVENT_LENGTH,
        description=event.notes,
    )


def export_ics(db: Session, user: User, now: datetime | None = None) -> str:
    """The last 30 days and the next year: appointments (cancelled ones marked as cancelled, so a
    re-import removes them from the phone's calendar) and personal events."""
    now = now or datetime.now(UTC)
    start, end = now - timedelta(days=EXPORT_PAST_DAYS), now + timedelta(days=EXPORT_FUTURE_DAYS)
    events = [
        *(_appointment_ics(a) for a in appointment_repository.list_between_for_user(
            db, user.id, start, end
        )),
        *(_custom_ics(e) for e in calendar_repository.list_custom_between(db, user.id, start, end)),
    ]
    events.sort(key=lambda e: (e.starts_at, e.uid))
    return ics_service.build_calendar(events, name="SkinCare App", now=now)
