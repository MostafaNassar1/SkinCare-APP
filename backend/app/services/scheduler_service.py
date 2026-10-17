"""What the background scheduler sends every few minutes: routine and appointment reminders.

Written once and called from three places: the in-process scheduler (app/core/scheduler.py),
the manual command (app/scripts/run_scheduler_once.py) and the protected endpoint
POST /internal/scheduler/run (for an external trigger later). It works from a given "now", so
tests can choose the moment.

Running it twice, or from two places at once, never sends anything twice: every reminder has a
dedupe key, and the database stores a key only once per user (notifications_user_id_dedupe_key_key).
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.models import Appointment, Notification, Routine, User
from app.repositories import appointment_repository, routine_repository
from app.services import notification_service
from app.services.local_time import user_zone
from app.services.routine_reminder_service import build_reminder, clock
from app.services.routine_service import scheduled_steps

# A reminder is still sent if the server was down at the exact time and comes back within this
# window (e.g. 21:00 reminder sent at 21:30); later than that it would be stale, so it is skipped.
REMINDER_LATE_WINDOW = timedelta(minutes=60)

# Appointment reminders: the day before, then shortly before.
DAY_BEFORE = timedelta(hours=24)
SHORTLY_BEFORE = timedelta(hours=2)


@dataclass(frozen=True)
class RunSummary:
    routine_reminders: int
    appointment_reminders: int
    pushes_sent: int


# ---------- Routine reminders ----------


def reminder_day(now: datetime, at: time, user: User) -> date | None:
    """The user's local day whose reminder at `at` is due now, or None.

    Due = between the reminder time and the end of the late window. Yesterday is checked too, so
    a 23:30 reminder can still go out at 00:10 (for yesterday's routine). Compared in UTC, so
    daylight-saving changes cannot confuse it.
    """
    zone = user_zone(user)
    today = now.astimezone(zone).date()
    for day in (today, today - timedelta(days=1)):
        start = datetime.combine(day, at, tzinfo=zone).astimezone(UTC)
        if start <= now < start + REMINDER_LATE_WINDOW:
            return day
    return None


def _routine_reminders_for(
    db: Session, user: User, routine: Routine, now: datetime
) -> list[Notification]:
    profile = user.profile
    created = []
    for slot, at in (
        ("morning", profile.morning_reminder_time),
        ("evening", profile.evening_reminder_time),
    ):
        day = reminder_day(now, at, user)
        if day is None:
            continue
        done = routine_repository.logged_step_ids(db, user.id, day)
        # only what is still to do: steps of this part of the day, scheduled that weekday, not
        # ticked yet. Nothing left -> no reminder (build_reminder returns None).
        left = [
            step.title
            for step in scheduled_steps(routine, day)
            if step.time_of_day == slot and step.id not in done
        ]
        local_now = now.astimezone(user_zone(user)).time().replace(second=0, microsecond=0)
        reminder = build_reminder(slot, left, local_now)
        if reminder is None:
            continue
        notification = notification_service.notify(
            db,
            user_id=user.id,
            type="reminder",
            title=reminder.title,
            message=reminder.body,
            dedupe_key=f"routine-{slot}:{day.isoformat()}",
        )
        if notification is not None:
            created.append(notification)
    return created


def due_routine_reminders(db: Session, now: datetime) -> list[Notification]:
    created = []
    for user, routine in routine_repository.list_reminder_candidates(db):
        created += _routine_reminders_for(db, user, routine, now)
    return created


# ---------- Appointment reminders ----------


def _day_word(day: date, today: date) -> str:
    if day == today:
        return "today"
    if day == today + timedelta(days=1):
        return "tomorrow"
    return day.strftime("%A")  # cannot happen within 24 h, kept as a safe fallback


def appointment_message(appointment: Appointment, user: User, now: datetime) -> tuple[str, str]:
    """(title, body), e.g. ("📅 Appointment tomorrow",
    "With Dr. Haddad at Rosary Sisters Hospital, tomorrow at 4:00 PM.")."""
    zone = user_zone(user)
    local_at = appointment.requested_datetime.astimezone(zone)
    word = _day_word(local_at.date(), now.astimezone(zone).date())
    who = f"With {appointment.doctor_name} at " if appointment.doctor_name else "At "
    return (
        f"📅 Appointment {word}",
        f"{who}{appointment.clinic.name}, {word} at {clock(local_at.time())}.",
    )


def due_appointment_reminders(db: Session, now: datetime) -> list[Notification]:
    created = []
    for appointment, user in appointment_repository.list_scheduled_between(
        db, now, now + DAY_BEFORE
    ):
        left = appointment.requested_datetime - now
        kind, lead = ("2h", SHORTLY_BEFORE) if left <= SHORTLY_BEFORE else ("24h", DAY_BEFORE)
        # recorded after the reminder moment (e.g. booked this morning for tonight): the user
        # just entered it, a "tomorrow" reminder would be pointless
        if appointment.created_at > appointment.requested_datetime - lead:
            continue
        title, body = appointment_message(appointment, user, now)
        notification = notification_service.notify(
            db,
            user_id=user.id,
            type="appointment_update",
            title=title,
            message=body,
            # the time is part of the key: a moved appointment gets reminded again
            dedupe_key=(
                f"appointment-{kind}:{appointment.id}:"
                f"{appointment.requested_datetime.astimezone(UTC):%Y%m%dT%H%M}"
            ),
        )
        if notification is not None:
            created.append(notification)
    return created


# ---------- One run ----------


def run_due(db: Session, now: datetime | None = None) -> RunSummary:
    """Save every reminder that is due, commit, then push them (push only after the commit)."""
    now = now or datetime.now(UTC)
    routine = due_routine_reminders(db, now)
    appointments = due_appointment_reminders(db, now)
    db.commit()
    pushed = notification_service.push_all(db, routine + appointments)
    return RunSummary(
        routine_reminders=len(routine),
        appointment_reminders=len(appointments),
        pushes_sent=pushed,
    )
