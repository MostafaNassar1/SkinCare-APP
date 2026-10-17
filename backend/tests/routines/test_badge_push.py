"""Earning a badge saves a notification and pushes it (after the commit)."""

import logging
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.controllers import routine_controller
from app.models import Notification, UserDevice
from app.services.weekdays import is_scheduled
from tests.routines.conftest import days_ago, log


def test_a_new_badge_is_pushed_to_the_phone(
    client: TestClient, db: Session, user_headers, app_user, routine, monkeypatch, caplog
):
    today = days_ago(app_user, 1)
    monkeypatch.setattr(routine_controller, "user_today", lambda user: today)
    db.add(UserDevice(user_id=app_user.id, fcm_token="phone-" + "x" * 30, platform="android"))
    for n in (1, 2):  # the two days before today are complete
        day = today - timedelta(days=n)
        log(db, app_user, [s.id for s in routine.steps if is_scheduled(s.days_of_week, day)], day)

    with caplog.at_level(logging.INFO, logger="app.push"):
        for step in routine.steps:
            if is_scheduled(step.days_of_week, today):
                client.post(f"/me/routine/steps/{step.id}/log", headers=user_headers)

    assert "🏆 New badge" in caplog.text and "3-Day Streak" in caplog.text
    saved = db.query(Notification).filter_by(user_id=app_user.id, type="achievement").all()
    assert any(n.dedupe_key and n.dedupe_key.startswith("achievement:") for n in saved)
