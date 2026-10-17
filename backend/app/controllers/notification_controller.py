from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models import User
from app.repositories import notification_repository
from app.schemas.notification import NotificationListOut, NotificationOut, UnreadCountOut


def list_notifications(
    db: Session, user: User, limit: int, before_id: int | None
) -> NotificationListOut:
    page = notification_repository.list_for_user(db, user.id, limit=limit + 1, before_id=before_id)
    has_more = len(page) > limit  # one extra row tells whether older ones exist
    page = page[:limit]
    return NotificationListOut(
        unread_count=notification_repository.unread_count(db, user.id),
        notifications=[NotificationOut.model_validate(n) for n in page],
        next_before_id=page[-1].id if has_more else None,
    )


def mark_read(db: Session, user: User, notification_id: int) -> UnreadCountOut:
    if notification_repository.get_for_user(db, user.id, notification_id) is None:
        raise AppError(404, "notification_not_found", "This notification does not exist.")
    notification_repository.mark_read(db, user.id, notification_id)
    db.commit()
    return UnreadCountOut(unread_count=notification_repository.unread_count(db, user.id))


def mark_all_read(db: Session, user: User) -> UnreadCountOut:
    notification_repository.mark_read(db, user.id)
    db.commit()
    return UnreadCountOut(unread_count=0)
