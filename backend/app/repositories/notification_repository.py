from sqlalchemy.orm import Session

from app.models import Notification


def create(db: Session, *, user_id: int, type: str, message: str) -> Notification:
    """Saved for the in-app list; Step 11 also pushes it to the user's phones."""
    notification = Notification(user_id=user_id, type=type, message=message)
    db.add(notification)
    db.flush()
    return notification
