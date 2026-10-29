"""Routine reminders: at the user's own times, only for the steps still to do, sent once."""

import logging
from datetime import time

import pytest
from sqlalchemy.orm import Session

from app.models import RoutineLog, User, UserDevice
from app.services.scheduler_service import run_due
from tests.scheduler.conftest import beirut, saved

MONDAY, TUESDAY = 19, 20  # October 2026


def tick(db: Session, user: User, steps, day: int) -> None:
    on = beirut(day, 12).date()
    db.add_all(RoutineLog(routine_step_id=s.id, user_id=user.id, log_date=on) for s in steps)
    db.flush()


def evening(routine, title: str | None = None):
    return [
        s for s in routine.steps if s.time_of_day == "evening" and title in (None, s.title)
    ]


def test_evening_reminder_lists_the_steps_of_the_day(db: Session, app_user, routine):
    summary = run_due(db, beirut(MONDAY, 21, 2))

    assert summary.routine_reminders == 1
    [reminder] = saved(db, app_user)
    assert reminder.type == "reminder"
    assert reminder.title == "🌙 It's 9:02 PM"
    assert reminder.message == (
        "Time for your evening routine: Cleanse → Anti-Aging Treatment → Moisturize."
    )
    assert reminder.dedupe_key == "routine-evening:2026-10-19"


def test_rest_days_leave_out_the_retinoid(db: Session, app_user, routine):
    run_due(db, beirut(TUESDAY, 21, 2))

    assert saved(db, app_user)[0].message == "Time for your evening routine: Cleanse → Moisturize."


def test_morning_reminder(db: Session, app_user, routine):
    run_due(db, beirut(MONDAY, 8, 0))

    [reminder] = saved(db, app_user)
    assert reminder.title == "☀️ It's 8:00 AM"
    assert reminder.message.startswith("Time for your morning routine: Cleanse → Oil Control")
    assert reminder.dedupe_key == "routine-morning:2026-10-19"


def test_only_the_steps_not_done_yet(db: Session, app_user, routine):
    tick(db, app_user, evening(routine, "Cleanse"), MONDAY)

    run_due(db, beirut(MONDAY, 21, 2))

    assert saved(db, app_user)[0].message == (
        "Time for your evening routine: Anti-Aging Treatment → Moisturize."
    )


def test_nothing_left_to_do_no_reminder(db: Session, app_user, routine):
    tick(db, app_user, evening(routine), MONDAY)

    assert run_due(db, beirut(MONDAY, 21, 2)).routine_reminders == 0
    assert saved(db, app_user) == []


def test_ticks_of_another_day_do_not_count(db: Session, app_user, routine):
    tick(db, app_user, evening(routine), MONDAY)

    run_due(db, beirut(TUESDAY, 21, 0))

    assert saved(db, app_user)[0].message == "Time for your evening routine: Cleanse → Moisturize."


@pytest.mark.parametrize(
    ("hour", "minute", "sent"),
    [
        (20, 59, 0),  # too early
        (21, 0, 1),
        (21, 59, 1),  # the server was down at 21:00: still useful
        (22, 0, 0),  # an hour late: stale, skipped
    ],
)
def test_late_window(db: Session, app_user, routine, hour, minute, sent):
    assert run_due(db, beirut(MONDAY, hour, minute)).routine_reminders == sent


def test_running_twice_sends_once(db: Session, app_user, routine):
    first = run_due(db, beirut(MONDAY, 21, 0))
    second = run_due(db, beirut(MONDAY, 21, 5))

    assert (first.routine_reminders, second.routine_reminders) == (1, 0)
    assert len(saved(db, app_user)) == 1


def test_each_day_gets_its_own_reminder(db: Session, app_user, routine):
    run_due(db, beirut(MONDAY, 21, 0))
    run_due(db, beirut(TUESDAY, 21, 0))

    assert [n.dedupe_key for n in saved(db, app_user)] == [
        "routine-evening:2026-10-19",
        "routine-evening:2026-10-20",
    ]


def test_the_users_own_time_and_time_zone(db: Session, app_user: User, routine):
    app_user.timezone = "Europe/Paris"  # one hour behind Beirut in October
    app_user.profile.morning_reminder_time = time(7, 30)
    db.flush()

    assert run_due(db, beirut(MONDAY, 8, 0)).routine_reminders == 0  # 07:00 in Paris
    assert run_due(db, beirut(MONDAY, 8, 35)).routine_reminders == 1  # 07:35 in Paris
    assert saved(db, app_user)[0].title == "☀️ It's 7:35 AM"


def test_a_late_evening_reminder_crosses_midnight(db: Session, app_user: User, routine):
    app_user.profile.evening_reminder_time = time(23, 40)
    db.flush()

    run_due(db, beirut(TUESDAY, 0, 10))  # 30 minutes after Monday's 23:40

    [reminder] = saved(db, app_user)
    assert reminder.dedupe_key == "routine-evening:2026-10-19"
    assert "Anti-Aging Treatment" in reminder.message  # Monday's steps, not Tuesday's


def test_reminders_switched_off(db: Session, app_user: User, routine):
    app_user.profile.routine_reminders_enabled = False
    db.flush()

    assert run_due(db, beirut(MONDAY, 21, 0)).routine_reminders == 0


@pytest.mark.parametrize("field", ["email_verified", "is_active"])
def test_unverified_or_disabled_accounts_get_nothing(db: Session, app_user: User, routine, field):
    setattr(app_user, field, False)
    db.flush()

    assert run_due(db, beirut(MONDAY, 21, 0)).routine_reminders == 0


def test_no_routine_no_reminder(db: Session, app_user):
    assert run_due(db, beirut(MONDAY, 21, 0)).routine_reminders == 0


def test_the_reminder_is_pushed_to_the_phone(db: Session, app_user, routine, caplog):
    db.add(UserDevice(user_id=app_user.id, fcm_token="phone-" + "x" * 30, platform="android"))
    db.flush()

    with caplog.at_level(logging.INFO, logger="app.push"):
        summary = run_due(db, beirut(MONDAY, 21, 0))

    assert summary.pushes_sent == 1
    assert "🌙 It's 9:00 PM" in caplog.text
