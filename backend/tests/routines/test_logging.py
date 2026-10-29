from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.controllers import routine_controller
from app.core.security import create_access_token
from app.models import Routine, RoutineLog, User, UserProfile
from tests.sample_routine import create_sample_routine
from tests.routines.conftest import last_weekday, start_routine_on

MONDAY, TUESDAY = 0, 1


@pytest.fixture
def today_is(monkeypatch, app_user: User):
    """Freeze the user's "today" on a given weekday (a recent past date, after the routine)."""

    def freeze(weekday: int) -> date:
        day = last_weekday(app_user, weekday)
        monkeypatch.setattr(routine_controller, "user_today", lambda user: day)
        return day

    return freeze


def step_id(routine: Routine, title: str, time_of_day: str = "evening") -> int:
    return next(s.id for s in routine.steps if s.title == title and s.time_of_day == time_of_day)


def tick(client: TestClient, headers: dict, sid: int, **params):
    return client.post(f"/me/routine/steps/{sid}/log", headers=headers, params=params or None)


def untick(client: TestClient, headers: dict, sid: int):
    return client.delete(f"/me/routine/steps/{sid}/log", headers=headers)


def log_rows(db: Session, user: User) -> list[tuple[int, date]]:
    db.expire_all()
    rows = db.query(RoutineLog).filter_by(user_id=user.id)
    return [(row.routine_step_id, row.log_date) for row in rows]


# ---------- Ticking ----------


def test_tick_a_step_for_today(client, db, user_headers, app_user, routine, today_is):
    today = today_is(TUESDAY)
    cleanse = step_id(routine, "Cleanse", "morning")

    response = tick(client, user_headers, cleanse)

    assert response.status_code == 200
    body = response.json()["day"]  # the updated day, ready for the screen
    assert body["date"] == today.isoformat()
    assert body["done_count"] == 1
    assert body["morning"][0]["done"] is True
    assert log_rows(db, app_user) == [(cleanse, today)]


def test_ticking_twice_keeps_one_row(client, db, user_headers, app_user, routine, today_is):
    today_is(TUESDAY)
    cleanse = step_id(routine, "Cleanse", "morning")

    tick(client, user_headers, cleanse)
    assert tick(client, user_headers, cleanse).status_code == 200

    assert len(log_rows(db, app_user)) == 1


def test_a_date_cannot_be_sent(client, db, user_headers, app_user, routine, today_is):
    today = today_is(TUESDAY)

    tick(client, user_headers, step_id(routine, "Cleanse", "morning"), date="2020-01-01")

    assert [day for _, day in log_rows(db, app_user)] == [today]  # always today


def test_untick(client, db, user_headers, app_user, routine, today_is):
    today_is(TUESDAY)
    cleanse = step_id(routine, "Cleanse", "morning")
    tick(client, user_headers, cleanse)

    body = untick(client, user_headers, cleanse).json()["day"]

    assert body["done_count"] == 0
    assert log_rows(db, app_user) == []
    assert untick(client, user_headers, cleanse).status_code == 200  # nothing to undo: fine


# ---------- Scheduled days (the retinoid safety rule) ----------


def test_retinoid_cannot_be_ticked_on_its_rest_day(client, user_headers, routine, today_is):
    today_is(TUESDAY)

    response = tick(client, user_headers, step_id(routine, "Anti-Aging Treatment"))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "step_not_scheduled_today"


def test_retinoid_can_be_ticked_on_its_night(client, user_headers, routine, today_is):
    today_is(MONDAY)
    assert tick(client, user_headers, step_id(routine, "Anti-Aging Treatment")).status_code == 200


@pytest.mark.parametrize(("weekday", "steps"), [(MONDAY, 7), (TUESDAY, 6)])
def test_ticking_every_scheduled_step_completes_the_day(
    client, user_headers, routine, today_is, weekday, steps
):
    day = today_is(weekday)
    body = None
    for step in routine.steps:
        if step.days_of_week & (1 << day.weekday()):
            body = tick(client, user_headers, step.id).json()["day"]

    assert (body["done_count"], body["scheduled_count"], body["complete"]) == (steps, steps, True)


# ---------- Only your own, current steps ----------


def test_another_users_step_is_not_found(client, db, user_headers, routine, today_is):
    today_is(TUESDAY)
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

    response = tick(client, other_headers, step_id(routine, "Cleanse", "morning"))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "step_not_found"


def test_steps_of_a_replaced_routine_cannot_be_ticked(
    client, db, user_headers, app_user, routine, today_is
):
    today_is(TUESDAY)
    old_step = step_id(routine, "Cleanse", "morning")
    new = create_sample_routine(db, app_user)
    start_routine_on(db, new, days_back=20)

    assert tick(client, user_headers, old_step).status_code == 404
    assert untick(client, user_headers, old_step).status_code == 404


def test_unknown_step_is_not_found(client, user_headers, routine):
    assert tick(client, user_headers, 999_999).status_code == 404


def test_logging_requires_login(client, routine):
    assert client.post(f"/me/routine/steps/{routine.steps[0].id}/log").status_code == 401
