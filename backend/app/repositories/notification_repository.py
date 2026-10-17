from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import Notification


def create(
    db: Session,
    *,
    user_id: int,
    type: str,
    message: str,
    title: str | None = None,
    dedupe_key: str | None = None,
) -> Notification | None:
    """Save a notification. Returns None if one with the same dedupe_key already exists for this
    user (ON CONFLICT DO NOTHING: the same automatic notification is never stored twice)."""
    new_id = db.scalar(
        pg_insert(Notification)
        .values(user_id=user_id, type=type, title=title, message=message, dedupe_key=dedupe_key)
        .on_conflict_do_nothing(index_elements=["user_id", "dedupe_key"])
        .returning(Notification.id)
    )
    return db.get(Notification, new_id) if new_id is not None else None


def list_for_user(
    db: Session, user_id: int, *, limit: int, before_id: int | None = None
) -> list[Notification]:
    """Newest first; `before_id` gives the next page (older notifications)."""
    query = select(Notification).where(Notification.user_id == user_id)
    if before_id is not None:
        query = query.where(Notification.id < before_id)
    return list(db.scalars(query.order_by(Notification.id.desc()).limit(limit)))


def unread_count(db: Session, user_id: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
    )


def mark_read(db: Session, user_id: int, notification_id: int | None = None) -> None:
    """Mark one notification (or all, when no id is given) of this user as read."""
    query = update(Notification).where(
        Notification.user_id == user_id, Notification.is_read.is_(False)
    )
    if notification_id is not None:
        query = query.where(Notification.id == notification_id)
    db.execute(query.values(is_read=True))


def get_for_user(db: Session, user_id: int, notification_id: int) -> Notification | None:
    return db.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user_id
        )
    )


def get_by_dedupe_key(db: Session, user_id: int, dedupe_key: str) -> Notification | None:
    return db.scalar(
        select(Notification).where(
            Notification.user_id == user_id, Notification.dedupe_key == dedupe_key
        )
    )
