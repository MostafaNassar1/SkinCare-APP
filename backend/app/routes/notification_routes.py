from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.controllers import notification_controller
from app.core.dependencies import CurrentUser, get_db
from app.schemas.notification import NotificationListOut, UnreadCountOut

router = APIRouter(prefix="/me/notifications", tags=["Notifications"])

DB = Annotated[Session, Depends(get_db)]


@router.get("", response_model=NotificationListOut)
def list_notifications(
    user: CurrentUser,
    db: DB,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    before_id: Annotated[int | None, Query()] = None,
):
    """The in-app inbox, newest first, with the unread count."""
    return notification_controller.list_notifications(db, user, limit, before_id)


@router.post("/read-all", response_model=UnreadCountOut)
def mark_all_read(user: CurrentUser, db: DB):
    return notification_controller.mark_all_read(db, user)


@router.post("/{notification_id}/read", response_model=UnreadCountOut)
def mark_read(notification_id: int, user: CurrentUser, db: DB):
    return notification_controller.mark_read(db, user, notification_id)
