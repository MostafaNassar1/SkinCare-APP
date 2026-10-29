"""GET /me/calendar (a month), personal events, and the .ics export."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import Appointment, Clinic, Routine, RoutineLog, User, UserProfile
from tests.sample_routine import create_sample_routine
from app.services.local_time import user_today
from app.services.routine_service import scheduled_steps

BEIRUT = ZoneInfo("Asia/Beirut")


def in_days(days: float, hour: int = 10) -> datetime:
    moment = datetime.now(BEIRUT) + timedelta(days=days)
    return moment.replace(hour=hour, minute=0, second=0, microsecond=0)


def month_of(day: date) -> str:
    return day.strftime("%Y-%m")


def calendar(client: TestClient, headers: dict, month: str | None = None) -> dict:
    params = {"month": month} if month else None
    response = client.get("/me/calendar", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def day_in(body: dict, day: date) -> dict:
    return next(d for d in body["days"] if d["date"] == day.isoformat())


@pytest.fixture
def routine(db: Session, app_user: User) -> Routine:
    """The sample routine (4 morning steps every day), created 40 days ago."""
    routine = create_sample_routine(db, app_user)
    routine.created_at = datetime.now(UTC) - timedelta(days=40)
    db.flush()
    return routine


def tick(db: Session, user: User, routine: Routine, day: date, how_many: int | None = None):
    steps = scheduled_steps(routine, day)[:how_many]
    db.add_all(RoutineLog(routine_step_id=s.id, user_id=user.id, log_date=day) for s in steps)
    db.flush()


@pytest.fixture
def hospital(db: Session) -> Clinic:
    clinic = Clinic(
        name="Test Hospital",
        category="hospital",
        latitude=Decimal("33.89"),
        longitude=Decimal("35.50"),
        address="Gemmayzeh, Beirut",
        phone_number="+961 1 440800",
        osm_id="way/calendar-test",
    )
    db.add(clinic)
    db.flush()
    return clinic


def add_appointment(db: Session, user: User, place: Clinic, at: datetime, **fields) -> Appointment:
    appointment = Appointment(user_id=user.id, clinic_id=place.id, requested_datetime=at, **fields)
    db.add(appointment)
    db.flush()
    db.refresh(appointment)
    return appointment


# ---------- The month ----------


def test_current_month_by_default(client: TestClient, user_headers, app_user):
    today = user_today(app_user)

    body = calendar(client, user_headers)

    assert body["month"] == month_of(today)
    assert body["today"] == today.isoformat()
    assert body["days"][0]["date"] == today.replace(day=1).isoformat()
    assert len(body["days"]) in (28, 29, 30, 31)
    assert body["events"] == []


def test_february_of_a_leap_year(client: TestClient, user_headers):
    assert len(calendar(client, user_headers, "2028-02")["days"]) == 29


@pytest.mark.parametrize("month", ["2026-13", "2026-1", "26-10", "1999-10", "2026-10-01"])
def test_invalid_month(client: TestClient, user_headers, month):
    response = client.get("/me/calendar", headers=user_headers, params={"month": month})
    assert response.status_code == 422


def test_routine_days(client: TestClient, db, user_headers, app_user, routine):
    today = user_today(app_user)
    complete, partial, missed = (today - timedelta(days=n) for n in (3, 2, 1))
    tick(db, app_user, routine, complete)
    tick(db, app_user, routine, partial, how_many=1)

    def status(day: date) -> dict:
        return day_in(calendar(client, user_headers, month_of(day)), day)

    assert status(complete)["routine"] == "complete"
    assert status(partial) | {"date": None} == {
        "date": None,
        "routine": "partial",
        "scheduled_count": len(scheduled_steps(routine, partial)),
        "done_count": 1,
    }
    assert status(missed)["routine"] == "missed"
    assert status(today)["routine"] == "today"  # not finished yet, still time
    tomorrow = status(today + timedelta(days=1))
    assert tomorrow["routine"] == "planned" and tomorrow["done_count"] == 0
    assert status(today - timedelta(days=41))["routine"] is None  # before the routine existed


def test_today_once_complete(client: TestClient, db, user_headers, app_user, routine):
    today = user_today(app_user)
    tick(db, app_user, routine, today)

    assert day_in(calendar(client, user_headers), today)["routine"] == "complete"


def test_a_rest_day(client: TestClient, db, user_headers, app_user, routine):
    # keep only the Mon/Wed/Fri evening retinoid: the other days have nothing scheduled
    for step in list(routine.steps):
        if step.days_of_week == 127:
            routine.steps.remove(step)
    db.flush()
    today = user_today(app_user)
    tuesday = (1 - today.weekday()) % 7 or 7  # the next Tuesday: no retinoid that evening
    day = today + timedelta(days=tuesday)

    assert day_in(calendar(client, user_headers, month_of(day)), day)["routine"] == "rest"


def test_no_routine_at_all(client: TestClient, user_headers):
    assert {d["routine"] for d in calendar(client, user_headers)["days"]} == {None}


def test_appointments_and_events_in_time_order(client, db, user_headers, app_user, hospital):
    at = in_days(0, hour=23)  # late tonight: same month in any case
    add_appointment(db, app_user, hospital, at, doctor_name="Dr. Haddad", notes="Bring products")
    add_appointment(db, app_user, hospital, at - timedelta(hours=2), status="cancelled")
    created = client.post(
        "/me/calendar/events",
        headers=user_headers,
        json={
            "title": "Start the new sunscreen",
            "starts_at": (at - timedelta(hours=1)).isoformat(),
        },
    ).json()

    events = calendar(client, user_headers, month_of(at.date()))["events"]

    assert [(e["kind"], e["title"]) for e in events] == [
        ("appointment", "Appointment at Test Hospital"),
        ("custom", "Start the new sunscreen"),
        ("appointment", "Appointment with Dr. Haddad"),
    ]
    assert events[0]["status"] == "cancelled"
    assert events[1]["id"] == created["id"] and events[1]["place"] is None
    assert events[2]["place"] == {
        "id": hospital.id,
        "name": "Test Hospital",
        "category": "hospital",
    }
    assert events[2]["starts_at"] == at.isoformat()  # in the user's time zone, +03:00


def test_events_of_other_months_are_not_included(client, db, user_headers, app_user, hospital):
    add_appointment(db, app_user, hospital, in_days(45))

    assert calendar(client, user_headers)["events"] == []


def test_month_edges_use_the_users_time_zone(client, db, user_headers, app_user, hospital):
    # 00:30 on 1 November in Beirut is still 31 October in UTC: it belongs to November
    add_appointment(db, app_user, hospital, datetime(2026, 11, 1, 0, 30, tzinfo=BEIRUT))

    assert calendar(client, user_headers, "2026-10")["events"] == []
    assert len(calendar(client, user_headers, "2026-11")["events"]) == 1


# ---------- Personal events ----------


def create(client: TestClient, headers: dict, **fields):
    body = {"title": "Dermatologist follow-up call", "starts_at": in_days(3).isoformat()} | fields
    return client.post("/me/calendar/events", headers=headers, json=body)


def test_create_edit_delete_an_event(client: TestClient, user_headers):
    response = create(client, user_headers, title="  Patch test  ", notes="Inner arm")
    assert response.status_code == 201
    event = response.json()
    assert event["kind"] == "custom" and event["title"] == "Patch test"
    assert event["notes"] == "Inner arm" and event["status"] is None

    edited = client.patch(
        f"/me/calendar/events/{event['id']}",
        headers=user_headers,
        json={"title": "Patch test (day 2)", "notes": None},
    ).json()
    assert (edited["title"], edited["notes"], edited["starts_at"]) == (
        "Patch test (day 2)",
        None,
        event["starts_at"],
    )

    url = f"/me/calendar/events/{event['id']}"
    assert client.delete(url, headers=user_headers).status_code == 204
    assert client.delete(url, headers=user_headers).status_code == 404


def test_past_events_are_allowed(client: TestClient, user_headers):
    assert create(client, user_headers, starts_at=in_days(-10).isoformat()).status_code == 201


@pytest.mark.parametrize(
    "fields",
    [
        {"title": "   "},
        {"title": "x" * 151},
        {"starts_at": "2026-10-25T09:00:00"},  # no time zone
        {"notes": "x" * 1001},
        {"event_type": "appointment"},  # appointments come from the tracker only
    ],
)
def test_invalid_events(client: TestClient, user_headers, fields):
    assert create(client, user_headers, **fields).status_code == 422


def test_too_far_away(client: TestClient, user_headers):
    response = create(client, user_headers, starts_at=in_days(6 * 365).isoformat())

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_event_time"


@pytest.mark.parametrize("fields", [{"title": None}, {"starts_at": None}, {"colour": "red"}])
def test_invalid_edits(client: TestClient, user_headers, fields):
    event_id = create(client, user_headers).json()["id"]

    response = client.patch(f"/me/calendar/events/{event_id}", headers=user_headers, json=fields)
    assert response.status_code == 422


def test_other_users_events_stay_private(client: TestClient, db: Session, user_headers):
    other = User(
        full_name="Other",
        email="other@example.com",
        password_hash="x",
        email_verified=True,
        profile=UserProfile(),
    )
    db.add(other)
    db.flush()
    other_headers = {"Authorization": f"Bearer {create_access_token(other.id, 'user')}"}
    theirs = create(client, other_headers).json()

    assert calendar(client, user_headers)["events"] == []
    url = f"/me/calendar/events/{theirs['id']}"
    assert client.patch(url, headers=user_headers, json={"title": "x"}).status_code == 404
    response = client.delete(url, headers=user_headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "calendar_event_not_found"


def test_calendar_requires_login(client: TestClient):
    assert client.get("/me/calendar").status_code == 401
    assert client.get("/me/calendar.ics").status_code == 401
    assert client.post("/me/calendar/events", json={}).status_code == 401


# ---------- .ics export ----------


def test_ics_export(client: TestClient, db, user_headers, app_user, hospital):
    add_appointment(db, app_user, hospital, in_days(2, hour=16), doctor_name="Dr. Haddad")
    add_appointment(db, app_user, hospital, in_days(5), status="cancelled")
    add_appointment(db, app_user, hospital, in_days(400))  # more than a year away: not exported
    create(client, user_headers, title="Patch test")

    response = client.get("/me/calendar.ics", headers=user_headers)

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/calendar; charset=utf-8"
    assert response.headers["content-disposition"] == 'attachment; filename="skincare-calendar.ics"'
    assert response.headers["cache-control"] == "no-store"
    lines = response.text.replace("\r\n ", "").split("\r\n")
    assert lines.count("BEGIN:VEVENT") == 3
    assert "SUMMARY:Appointment with Dr. Haddad" in lines
    assert "LOCATION:Test Hospital\\, Gemmayzeh\\, Beirut" in lines
    assert "DESCRIPTION:Doctor: Dr. Haddad\\nPhone: +961 1 440800" in lines
    assert "STATUS:CANCELLED" in lines
    assert lines.count("BEGIN:VALARM") == 1  # only the scheduled appointment
    assert "SUMMARY:Patch test" in lines
