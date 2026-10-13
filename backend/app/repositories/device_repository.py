from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import UserDevice


def get_by_token_for_update(db: Session, fcm_token: str) -> UserDevice | None:
    # locked: two registrations of the same phone at the same moment are handled one by one
    return db.scalar(
        select(UserDevice).where(UserDevice.fcm_token == fcm_token).with_for_update()
    )


def create(db: Session, *, user_id: int, fcm_token: str, platform: str) -> UserDevice:
    device = UserDevice(user_id=user_id, fcm_token=fcm_token, platform=platform)
    db.add(device)
    db.flush()
    return device


def list_for_user(db: Session, user_id: int) -> list[UserDevice]:
    return list(db.scalars(select(UserDevice).where(UserDevice.user_id == user_id)))


def delete_for_user(db: Session, *, user_id: int, fcm_token: str) -> None:
    """Only the user's own token is ever removed."""
    db.execute(
        delete(UserDevice).where(UserDevice.user_id == user_id, UserDevice.fcm_token == fcm_token)
    )


def touch(device: UserDevice, *, user_id: int, platform: str, seen_at: datetime) -> None:
    device.user_id = user_id
    device.platform = platform
    device.last_seen_at = seen_at
