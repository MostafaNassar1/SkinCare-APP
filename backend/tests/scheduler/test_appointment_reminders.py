"""Appointment reminders: the day before (24 h) and shortly before (2 h), once each."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import Appointment, Clinic, User
from app.services.scheduler_service import run_due
from tests.scheduler.conftest import beirut, saved

AT = beirut(20, 16, 0)  # Tuesday 20 October, 4:00 PM in Beirut


@pytest.fixture
def hospital(db: Session) -> Clinic:
    clinic = Clinic(
        name="Test Hospital",
        category="hospital",
        latitude=Decimal("33.89"),
        longitude=Decimal("35.50"),
        osm_id="way/scheduler-test",
    )
    db.add(clinic)
    db.flush()
    return clinic


def add_appointment(
    db: Session,
    user: User,
    place: Clinic,
    *,
    doctor_name: str | None = "Dr. Haddad",
    created_at: datetime = AT - timedelta(days=7),
    status: str = "scheduled",
) -> Appointment:
    appointment = Appointment(
        user_id=user.id,
        clinic_id=place.id,
        requested_datetime=AT,
        doctor_name=doctor_name,
        created_at=created_at,
        status=status,
    )
    db.add(appointment)
    db.flush()
    return appointment


def test_the_day_before(db: Session, app_user, hospital):
    add_appointment(db, app_user, hospital)

    summary = run_due(db, AT - timedelta(hours=23, minutes=55))

    assert summary.appointment_reminders == 1
    [reminder] = saved(db, app_user)
    assert reminder.type == "appointment_update"
    assert reminder.title == "📅 Appointment tomorrow"
    assert reminder.message == "With Dr. Haddad at Test Hospital, tomorrow at 4:00 PM."
    assert reminder.dedupe_key.startswith("appointment-24h:")


def test_two_hours_before(db: Session, app_user, hospital):
    add_appointment(db, app_user, hospital, doctor_name=None)

    run_due(db, AT - timedelta(hours=23))
    run_due(db, AT - timedelta(hours=1, minutes=58))

    day_before, shortly_before = saved(db, app_user)
    assert shortly_before.title == "📅 Appointment today"
    assert shortly_before.message == "At Test Hospital, today at 4:00 PM."
    assert shortly_before.dedupe_key.startswith("appointment-2h:")


def test_each_reminder_is_sent_once(db: Session, app_user, hospital):
    add_appointment(db, app_user, hospital)

    counts = [
        run_due(db, AT - timedelta(hours=h)).appointment_reminders for h in (23, 20, 10, 1.9, 1)
    ]

    assert counts == [1, 0, 0, 1, 0]


@pytest.mark.parametrize(
    "now",
    [
        AT - timedelta(hours=24, minutes=5),  # more than a day before
        AT,  # it has started
        AT + timedelta(hours=1),  # passed
    ],
)
def test_outside_the_reminder_times(db: Session, app_user, hospital, now):
    add_appointment(db, app_user, hospital)

    assert run_due(db, now).appointment_reminders == 0


@pytest.mark.parametrize("status", ["completed", "cancelled"])
def test_closed_appointments_are_not_reminded(db: Session, app_user, hospital, status):
    add_appointment(db, app_user, hospital, status=status)

    assert run_due(db, AT - timedelta(hours=1)).appointment_reminders == 0


def test_no_day_before_reminder_for_one_recorded_today(db: Session, app_user, hospital):
    add_appointment(db, app_user, hospital, created_at=AT - timedelta(hours=5))

    assert run_due(db, AT - timedelta(hours=4)).appointment_reminders == 0  # just entered it
    assert run_due(db, AT - timedelta(hours=1)).appointment_reminders == 1  # 2 h one still sent


def test_a_moved_appointment_is_reminded_again(db: Session, app_user, hospital):
    appointment = add_appointment(db, app_user, hospital)
    run_due(db, AT - timedelta(hours=23))

    appointment.requested_datetime = AT + timedelta(days=1)  # postponed by a day
    db.flush()

    assert run_due(db, AT + timedelta(hours=1)).appointment_reminders == 1
    assert len(saved(db, app_user)) == 2


def test_disabled_accounts_get_nothing(db: Session, app_user: User, hospital):
    app_user.is_active = False
    db.flush()
    add_appointment(db, app_user, hospital)

    assert run_due(db, AT - timedelta(hours=1)).appointment_reminders == 0


def test_the_time_is_shown_in_the_users_time_zone(db: Session, app_user: User, hospital):
    app_user.timezone = "Europe/Paris"  # one hour behind Beirut in October
    db.flush()
    add_appointment(db, app_user, hospital)

    run_due(db, AT - timedelta(hours=1))

    assert saved(db, app_user)[0].message == "With Dr. Haddad at Test Hospital, today at 3:00 PM."
