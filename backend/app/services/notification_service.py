"""Creating notifications (in-app inbox) and pushing them to the user's phones.

Two steps on purpose: notify() saves the notification inside the caller's transaction; push_all()
is called AFTER the commit, so a push never announces something that was not saved.
"""

from sqlalchemy.orm import Session

from app.models import Notification
from app.repositories import device_repository, notification_repository
from app.services import push_service
from app.services.push_service import Push

DEFAULT_TITLES = {
    "reminder": "⏰ Reminder",
    "weather_alert": "🌤️ Today's skin forecast",
    "achievement": "🏆 New badge",
    "appointment_update": "📅 Appointment",
}


def notify(
    db: Session,
    *,
    user_id: int,
    type: str,
    message: str,
    title: str | None = None,
    dedupe_key: str | None = None,
) -> Notification | None:
    """Save a notification; None if this automatic notification (dedupe_key) already exists."""
    return notification_repository.create(
        db,
        user_id=user_id,
        type=type,
        title=title or DEFAULT_TITLES[type],
        message=message,
        dedupe_key=dedupe_key,
    )


def push_all(db: Session, notifications: list[Notification]) -> int:
    """Push saved notifications to their users' phones; returns the number of pushes sent."""
    sent = 0
    for notification in notifications:
        tokens = [d.fcm_token for d in device_repository.list_for_user(db, notification.user_id)]
        sent += push_service.send(
            tokens,
            Push(
                title=notification.title or DEFAULT_TITLES[notification.type],
                body=notification.message,
                data={"notification_id": str(notification.id), "type": notification.type},
            ),
        )
    return sent
