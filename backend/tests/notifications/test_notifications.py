import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import Notification, User, UserDevice, UserProfile
from app.services import notification_service


@pytest.fixture
def other_user(db: Session) -> User:
    user = User(
        full_name="Other",
        email="other@example.com",
        password_hash="x",
        email_verified=True,
        profile=UserProfile(),
    )
    db.add(user)
    db.flush()
    return user


def notify(db: Session, user: User, message: str = "Hello", **kwargs) -> Notification | None:
    return notification_service.notify(
        db, user_id=user.id, type=kwargs.pop("type", "reminder"), message=message, **kwargs
    )


# ---------- Creating (no duplicates) ----------


def test_notification_gets_a_default_title(db: Session, app_user: User):
    assert notify(db, app_user).title == "⏰ Reminder"
    assert notify(db, app_user, type="achievement").title == "🏆 New badge"
    assert notify(db, app_user, title="Custom").title == "Custom"


def test_the_same_automatic_notification_is_stored_only_once(db: Session, app_user: User):
    first = notify(db, app_user, dedupe_key="forecast:2026-10-17")
    second = notify(db, app_user, dedupe_key="forecast:2026-10-17")

    assert first is not None
    assert second is None  # e.g. the scheduler ran twice
    assert db.query(Notification).filter_by(user_id=app_user.id).count() == 1


def test_keys_are_per_user(db: Session, app_user: User, other_user: User):
    assert notify(db, app_user, dedupe_key="forecast:2026-10-17") is not None
    assert notify(db, other_user, dedupe_key="forecast:2026-10-17") is not None


def test_notifications_without_a_key_never_collide(db: Session, app_user: User):
    notify(db, app_user)
    notify(db, app_user)
    assert db.query(Notification).filter_by(user_id=app_user.id).count() == 2


# ---------- Pushing (console mode until Phase 4) ----------


def test_push_goes_to_every_phone_of_the_user(db: Session, app_user: User, caplog):
    db.add_all(
        [
            UserDevice(user_id=app_user.id, fcm_token="phone-1-" + "x" * 30, platform="android"),
            UserDevice(user_id=app_user.id, fcm_token="phone-2-" + "x" * 30, platform="ios"),
        ]
    )
    db.flush()
    notification = notify(db, app_user, message="Time for your evening routine")

    with caplog.at_level(logging.INFO, logger="app.push"):
        sent = notification_service.push_all(db, [notification])

    assert sent == 2
    assert "Push (console mode, not sent) to 2 device(s): ⏰ Reminder" in caplog.text
    assert "Time for your evening routine" in caplog.text


def test_no_phone_no_push_but_still_in_the_inbox(db: Session, app_user: User, caplog):
    notification = notify(db, app_user)

    with caplog.at_level(logging.INFO, logger="app.push"):
        assert notification_service.push_all(db, [notification]) == 0

    assert "Push" not in caplog.text
    assert db.get(Notification, notification.id) is not None


# ---------- The inbox ----------


def inbox(client: TestClient, headers: dict, **params) -> dict:
    return client.get("/me/notifications", headers=headers, params=params or None).json()


def test_inbox_newest_first_with_unread_count(client, db, user_headers, app_user):
    for n in range(3):
        notify(db, app_user, message=f"message {n}")

    body = inbox(client, user_headers)

    assert [n["message"] for n in body["notifications"]] == ["message 2", "message 1", "message 0"]
    assert body["unread_count"] == 3
    assert body["next_before_id"] is None
    assert set(body["notifications"][0]) == {"id", "type", "title", "message", "is_read", "sent_at"}


def test_inbox_pages(client, db, user_headers, app_user):
    for n in range(5):
        notify(db, app_user, message=f"message {n}")

    first = inbox(client, user_headers, limit=2)
    second = inbox(client, user_headers, limit=2, before_id=first["next_before_id"])
    third = inbox(client, user_headers, limit=2, before_id=second["next_before_id"])

    seen = [n["message"] for page in (first, second, third) for n in page["notifications"]]
    assert seen == ["message 4", "message 3", "message 2", "message 1", "message 0"]
    assert third["next_before_id"] is None


def test_mark_one_and_all_as_read(client, db, user_headers, app_user):
    one, _, _ = (notify(db, app_user, message=str(n)) for n in range(3))

    after_one = client.post(f"/me/notifications/{one.id}/read", headers=user_headers).json()
    after_all = client.post("/me/notifications/read-all", headers=user_headers).json()

    assert after_one == {"unread_count": 2}
    assert after_all == {"unread_count": 0}
    assert all(n["is_read"] for n in inbox(client, user_headers)["notifications"])


def test_other_users_notifications_stay_private(client, db, user_headers, other_user):
    theirs = notify(db, other_user)

    assert inbox(client, user_headers)["notifications"] == []
    response = client.post(f"/me/notifications/{theirs.id}/read", headers=user_headers)
    assert response.status_code == 404
    assert db.get(Notification, theirs.id).is_read is False


def test_inbox_requires_login(client: TestClient):
    assert client.get("/me/notifications").status_code == 401
