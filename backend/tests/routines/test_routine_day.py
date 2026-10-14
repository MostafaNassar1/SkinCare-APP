from contextlib import nullcontext
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Routine, User
from app.scripts import create_sample_routine as script
from app.scripts.create_sample_routine import create_sample_routine
from app.services.local_time import user_today
from tests.routines.conftest import days_ago, last_weekday, log, start_routine_on

MONDAY, TUESDAY = 0, 1


def get_day(client: TestClient, headers: dict, day=None):
    params = {"date": day.isoformat()} if day else None
    return client.get("/me/routine", headers=headers, params=params)


def step(body: dict, title: str) -> dict:
    return next(s for s in body["morning"] + body["evening"] if s["title"] == title)


# ---------- Today ----------


def test_no_routine_yet(client: TestClient, user_headers):
    response = get_day(client, user_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "no_routine"


def test_today_shows_the_steps_in_order(client: TestClient, user_headers, app_user, routine):
    body = get_day(client, user_headers).json()

    assert body["date"] == user_today(app_user).isoformat()
    assert body["is_today"] is True and body["can_log"] is True
    assert [s["title"] for s in body["morning"]] == [
        "Cleanse", "Oil Control Serum", "Moisturize", "Sunscreen",
    ]  # fmt: skip
    assert [s["title"] for s in body["evening"]] == ["Cleanse", "Acne Treatment", "Moisturize"]
    assert body["done_count"] == 0 and body["complete"] is False


def test_steps_show_ingredient_concentration_and_days(client: TestClient, user_headers, routine):
    adapalene = step(get_day(client, user_headers).json(), "Acne Treatment")

    assert adapalene["ingredient"]["name"] == "Adapalene"
    assert adapalene["recommended_concentration"] == "0.1%"
    assert adapalene["days"] == ["mon", "wed", "fri"]
    assert adapalene["product_type"] == "Adapalene gel"


# ---------- Scheduled days ----------


def test_retinoid_night_has_7_scheduled_steps(client: TestClient, user_headers, app_user, routine):
    body = get_day(client, user_headers, last_weekday(app_user, MONDAY)).json()

    assert step(body, "Acne Treatment")["scheduled"] is True
    assert body["scheduled_count"] == 7


def test_other_nights_have_6(client: TestClient, user_headers, app_user, routine):
    body = get_day(client, user_headers, last_weekday(app_user, TUESDAY)).json()

    assert step(body, "Acne Treatment")["scheduled"] is False
    assert body["scheduled_count"] == 6


# ---------- Past days: view only ----------


def test_past_day_is_view_only_and_shows_what_was_done(
    client: TestClient, db: Session, user_headers, app_user, routine
):
    tuesday = last_weekday(app_user, TUESDAY)
    morning_ids = [s.id for s in routine.steps if s.time_of_day == "morning"]
    log(db, app_user, morning_ids[:2], tuesday)

    body = get_day(client, user_headers, tuesday).json()

    assert body["is_today"] is False and body["can_log"] is False
    assert body["done_count"] == 2
    assert [s["done"] for s in body["morning"]] == [True, True, False, False]
    assert body["complete"] is False


def test_day_is_complete_when_every_scheduled_step_is_done(
    client: TestClient, db: Session, user_headers, app_user, routine
):
    tuesday = last_weekday(app_user, TUESDAY)
    # all steps except the Mon/Wed/Fri retinoid, which is not scheduled on Tuesday
    log(db, app_user, [s.id for s in routine.steps if s.title != "Acne Treatment"], tuesday)

    body = get_day(client, user_headers, tuesday).json()

    assert (body["done_count"], body["scheduled_count"], body["complete"]) == (6, 6, True)


def test_future_dates_cannot_be_viewed(client: TestClient, user_headers, app_user, routine):
    tomorrow = user_today(app_user) + timedelta(days=1)

    response = get_day(client, user_headers, tomorrow)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "date_in_future"


def test_day_before_the_first_routine_has_none(client, user_headers, app_user, routine):
    response = get_day(client, user_headers, days_ago(app_user, 40))
    assert response.json()["error"]["code"] == "no_routine"


def test_old_days_keep_the_routine_they_really_had(
    client: TestClient, db: Session, user_headers, app_user: User, routine: Routine
):
    old_id = routine.id
    new = create_sample_routine(db, app_user)  # replaces the old routine
    start_routine_on(db, new, days_back=2)

    assert get_day(client, user_headers, days_ago(app_user, 10)).json()["routine_id"] == old_id
    assert get_day(client, user_headers).json()["routine_id"] == new.id


def test_routine_requires_login(client: TestClient):
    assert client.get("/me/routine").status_code == 401


# ---------- Time zones ----------


def test_today_depends_on_the_users_time_zone(app_user: User):
    moment = datetime(2026, 10, 14, 22, 30, tzinfo=UTC)  # 22:30 UTC

    app_user.timezone = "Asia/Beirut"  # UTC+3: already the 15th
    assert user_today(app_user, moment).isoformat() == "2026-10-15"
    app_user.timezone = "America/New_York"  # UTC-4: still the 14th
    assert user_today(app_user, moment).isoformat() == "2026-10-14"


# ---------- Sample routine command ----------


def test_sample_routine_command(db: Session, app_user: User, monkeypatch, capsys):
    monkeypatch.setattr(script, "SessionLocal", lambda: nullcontext(db))
    first = create_sample_routine(db, app_user)

    assert script.main(["--email", app_user.email]) == 0
    assert "with 7 steps" in capsys.readouterr().out
    db.refresh(first)
    assert first.is_active is False  # the previous routine was replaced
    assert db.query(Routine).filter_by(user_id=app_user.id, is_active=True).count() == 1


def test_sample_routine_command_unknown_email(db: Session, monkeypatch, capsys):
    monkeypatch.setattr(script, "SessionLocal", lambda: nullcontext(db))

    assert script.main(["--email", "nobody@example.com"]) == 1
