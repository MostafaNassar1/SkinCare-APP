from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import User
from app.repositories import device_repository
from app.schemas.device import DeviceOut, DeviceRegister


def register_device(db: Session, user: User, data: DeviceRegister) -> DeviceOut:
    """Remember where to send this user's push notifications.

    One phone has one token. If the token belongs to another account (a shared phone), it moves
    to the account that logged in last, so the previous user's notifications stop arriving there.
    """
    now = datetime.now(UTC)
    device = device_repository.get_by_token_for_update(db, data.fcm_token)
    if device is None:
        try:
            device = device_repository.create(
                db, user_id=user.id, fcm_token=data.fcm_token, platform=data.platform
            )
        except IntegrityError:
            # the same token registered by another request at the same moment
            db.rollback()
            device = device_repository.get_by_token_for_update(db, data.fcm_token)
    if device is not None:
        device_repository.touch(device, user_id=user.id, platform=data.platform, seen_at=now)
    db.commit()
    return DeviceOut.model_validate(device)


def remove_device(db: Session, user: User, fcm_token: str) -> None:
    """At logout: this phone stops receiving the user's notifications. Always succeeds."""
    device_repository.delete_for_user(db, user_id=user.id, fcm_token=fcm_token)
    db.commit()
