from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.choices import NOTIFICATION_TYPES


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: Literal[NOTIFICATION_TYPES]  # reminder / weather_alert / achievement / appointment_update
    title: str | None
    message: str
    is_read: bool
    sent_at: datetime


class NotificationListOut(BaseModel):
    unread_count: int  # for the badge on the bell icon
    notifications: list[NotificationOut]  # newest first
    next_before_id: int | None  # pass as ?before_id= to load older ones; None = no more


class UnreadCountOut(BaseModel):
    unread_count: int
