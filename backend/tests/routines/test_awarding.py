"""Achievement progress and automatic awarding when steps are ticked."""

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.controllers import achievement_controller, routine_controller
from app.models import Achievement, Notification, Routine, ScanResult, User, UserAchievement
from app.services.weekdays import is_scheduled
from tests.routines.conftest import days_ago, log


@pytest.fixture(params=range(1, 8), ids=lambda n: f"{n}-days-ago")
def today(request, monkeypatch, app_user: User) -> date:
    """Freeze "today" on each of the last 7 days in turn, so every test runs on every weekday.

    The number of steps per day depends on the weekday (the retinoid is Mon/Wed/Fri only), so a
    test that passes on one day can fail on another; running all 7 catches that (2026-10-15).
    """
    day = days_ago(app_user, request.param)
    monkeypatch.setattr(routine_controller, "user_today", lambda user: day)
    monkeypatch.setattr(achievement_controller, "user_today", lambda user: day)
    return day


def scheduled_ids(routine: Routine, day: date) -> list[int]:
    return [s.id for s in routine.steps if is_scheduled(s.days_of_week, day)]


def complete_past(db: Session, user: User, routine: Routine, today: date, days: range) -> None:
    for n in days:
        day = today - timedelta(days=n)
        log(db, user, scheduled_ids(routine, day), day)


def tick_all_today(client: TestClient, headers: dict, routine: Routine, today: date) -> list[str]:
    """Tick every step scheduled today; returns the titles of the badges earned along the way."""
    earned = []
    for step_id in scheduled_ids(routine, today):
        body = client.post(f"/me/routine/steps/{step_id}/log", headers=headers).json()
        earned += [a["title"] for a in body["new_achievements"]]
    return earned


def my_badges(client: TestClient, headers: dict) -> dict[str, dict]:
    return {b["title"]: b for b in client.get("/me/achievements", headers=headers).json()}


# ---------- Streak badges ----------


def test_completing_the_third_day_earns_the_3_day_streak(
    client, db, user_headers, app_user, routine, today
):
    complete_past(db, app_user, routine, today, range(1, 3))  # the 2 days before today

    earned = tick_all_today(client, user_headers, routine, today)

    # announced exactly once, on the tick that completed the day. (Other badges may be earned
    # too: on some weekdays these 3 days reach the 20 ticks of "Consistent Care".)
    assert earned.count("3-Day Streak") == 1
    assert "7-Day Streak" not in earned
    badge = my_badges(client, user_headers)["3-Day Streak"]
    assert badge["earned"] is True and badge["progress"] == 3


def test_a_notification_is_saved_for_the_badge(client, db, user_headers, app_user, routine, today):
    complete_past(db, app_user, routine, today, range(1, 3))
    tick_all_today(client, user_headers, routine, today)

    notifications = db.query(Notification).filter_by(user_id=app_user.id).all()
    streak_notes = [n for n in notifications if "3-Day Streak" in n.message]

    assert len(streak_notes) == 1
    assert streak_notes[0].type == "achievement"


def test_progress_shows_the_current_streak(client, db, user_headers, app_user, routine, today):
    complete_past(db, app_user, routine, today, range(1, 3))  # 2-day streak so far

    badges = my_badges(client, user_headers)

    assert badges["7-Day Streak"]["progress"] == 2
    assert badges["7-Day Streak"]["criteria_value"] == 7
    assert badges["7-Day Streak"]["earned"] is False


def test_an_earlier_long_streak_still_earns_its_badge(
    client, db, user_headers, app_user, routine, today
):
    complete_past(db, app_user, routine, today, range(10, 17))  # 7 days in a row, weeks ago

    first_step = scheduled_ids(routine, today)[0]
    body = client.post(f"/me/routine/steps/{first_step}/log", headers=user_headers).json()

    earned = {a["title"] for a in body["new_achievements"]}
    assert {"3-Day Streak", "7-Day Streak"} <= earned  # (7 full days also exceed 20 ticks)
    assert "30-Day Streak" not in earned


# ---------- Kept forever, awarded once ----------


def test_badges_are_kept_and_never_awarded_twice(
    client, db, user_headers, app_user, routine, today
):
    complete_past(db, app_user, routine, today, range(1, 3))
    tick_all_today(client, user_headers, routine, today)
    last = scheduled_ids(routine, today)[-1]

    client.delete(f"/me/routine/steps/{last}/log", headers=user_headers)  # streak drops to 2...
    again = client.post(f"/me/routine/steps/{last}/log", headers=user_headers).json()

    assert my_badges(client, user_headers)["3-Day Streak"]["earned"] is True  # ...badge kept
    assert again["new_achievements"] == []  # not announced a second time
    three_day = db.query(Achievement).filter_by(title="3-Day Streak").one()
    count = db.query(UserAchievement).filter_by(user_id=app_user.id, achievement_id=three_day.id)
    assert count.count() == 1


# ---------- Other badge types ----------


def test_twenty_ticks_earn_consistent_care(client, db, user_headers, app_user, routine, today):
    complete_past(db, app_user, routine, today, range(5, 8))  # 3 old days: 18-21 ticks

    earned = tick_all_today(client, user_headers, routine, today)

    assert "Consistent Care" in earned
    assert my_badges(client, user_headers)["Consistent Care"]["progress"] == 20


def test_a_scan_earns_first_scan(client, db, user_headers, app_user, routine, today):
    db.add(
        ScanResult(
            user_id=app_user.id,
            image_url="https://example.com/x.jpg",
            image_public_id="x",
            model_version="test",
            scanned_at=datetime.now(UTC),
        )
    )
    db.flush()

    first_step = scheduled_ids(routine, today)[0]
    body = client.post(f"/me/routine/steps/{first_step}/log", headers=user_headers).json()

    assert "First Scan" in [a["title"] for a in body["new_achievements"]]


def test_switched_off_badges_are_not_awarded(client, db, user_headers, app_user, routine, today):
    db.query(Achievement).filter_by(title="3-Day Streak").one().is_active = False
    db.flush()
    complete_past(db, app_user, routine, today, range(1, 3))

    assert "3-Day Streak" not in tick_all_today(client, user_headers, routine, today)


def test_new_user_progress_is_zero(client, user_headers, today):
    assert all(b["progress"] == 0 for b in my_badges(client, user_headers).values())
