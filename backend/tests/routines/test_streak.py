from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.controllers import routine_controller
from app.models import Routine, User
from app.services.weekdays import is_scheduled
from tests.routines.conftest import days_ago, log

TODAY_OFFSET = 1  # "today" is frozen to yesterday's real date: always after the routine started


@pytest.fixture
def today(monkeypatch, app_user: User) -> date:
    day = days_ago(app_user, TODAY_OFFSET)
    monkeypatch.setattr(routine_controller, "user_today", lambda user: day)
    return day


def complete(db: Session, user: User, routine: Routine, *days: date) -> None:
    """Tick every step scheduled on each of these days."""
    for day in days:
        log(db, user, [s.id for s in routine.steps if is_scheduled(s.days_of_week, day)], day)


def before(day: date, n: int) -> date:
    return day - timedelta(days=n)


def streak(client: TestClient, headers: dict) -> dict:
    return client.get("/me/streak", headers=headers).json()


# ---------- Streak ----------


def test_no_routine_no_streak(client, user_headers, today):
    assert streak(client, user_headers) == {
        "current_days": 0, "longest_days": 0, "today_complete": False,
    }  # fmt: skip


def test_streak_is_kept_until_today_is_over(client, db, user_headers, app_user, routine, today):
    complete(db, app_user, routine, before(today, 3), before(today, 2), before(today, 1))

    # today not done yet: the 3-day streak still shows
    assert streak(client, user_headers) == {
        "current_days": 3, "longest_days": 3, "today_complete": False,
    }  # fmt: skip

    complete(db, app_user, routine, today)
    assert streak(client, user_headers)["current_days"] == 4
    assert streak(client, user_headers)["today_complete"] is True


def test_missing_yesterday_breaks_the_streak(client, db, user_headers, app_user, routine, today):
    complete(db, app_user, routine, before(today, 3), before(today, 2))  # yesterday skipped

    body = streak(client, user_headers)

    assert body["current_days"] == 0
    assert body["longest_days"] == 2


def test_longest_streak_is_remembered(client, db, user_headers, app_user, routine, today):
    complete(db, app_user, routine, *[before(today, n) for n in range(10, 5, -1)])  # 5 days
    complete(db, app_user, routine, before(today, 2), before(today, 1))  # then 2 days

    body = streak(client, user_headers)

    assert (body["current_days"], body["longest_days"]) == (2, 5)


def test_a_partly_done_day_breaks_the_streak(client, db, user_headers, app_user, routine, today):
    yesterday = before(today, 1)
    complete(db, app_user, routine, before(today, 2))
    scheduled = [s.id for s in routine.steps if is_scheduled(s.days_of_week, yesterday)]
    log(db, app_user, scheduled[:-1], yesterday)  # one step missing

    assert streak(client, user_headers)["current_days"] == 0


def test_rest_days_of_the_retinoid_are_not_needed(
    client, db, user_headers, app_user, routine, today
):
    # completing only the scheduled steps (no retinoid on its rest days) is a full streak
    complete(db, app_user, routine, *[before(today, n) for n in range(1, 8)])

    assert streak(client, user_headers)["current_days"] == 7


# ---------- History ----------


def test_history_defaults_to_the_last_30_days(client, db, user_headers, app_user, routine, today):
    complete(db, app_user, routine, before(today, 1))

    body = client.get("/me/routine/history", headers=user_headers).json()

    assert body["end"] == today.isoformat()
    assert body["start"] == before(today, 29).isoformat()
    assert len(body["days"]) == 30
    yesterday = next(d for d in body["days"] if d["date"] == before(today, 1).isoformat())
    assert yesterday["complete"] is True
    assert yesterday["done_count"] == yesterday["scheduled_count"] > 0


def test_history_skips_days_before_the_first_routine(client, user_headers, routine, today):
    params = {"from": before(today, 40).isoformat(), "to": today.isoformat()}
    body = client.get("/me/routine/history", headers=user_headers, params=params).json()

    # the routine started 30 real days ago = 29 days before the frozen today
    assert len(body["days"]) == 30


@pytest.mark.parametrize(
    "params",
    [
        {"to": "2999-01-01"},  # future
        {"from": "2026-01-10", "to": "2026-01-01"},  # backwards
        {"from": "2025-01-01", "to": "2025-12-31"},  # more than 92 days
    ],
)
def test_invalid_history_ranges(client, user_headers, routine, today, params):
    response = client.get("/me/routine/history", headers=user_headers, params=params)
    assert response.status_code == 422


def test_streak_and_history_require_login(client):
    assert client.get("/me/streak").status_code == 401
    assert client.get("/me/routine/history").status_code == 401
