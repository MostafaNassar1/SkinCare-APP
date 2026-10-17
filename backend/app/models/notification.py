from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, IntPK, check_in
from app.models.choices import DEVICE_PLATFORMS, NOTIFICATION_TYPES


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        check_in("type", NOTIFICATION_TYPES),
        Index("idx_notifications_user_unread", "user_id", "is_read"),
        # the same automatic notification (e.g. "forecast:2026-10-17") is never stored twice
        UniqueConstraint("user_id", "dedupe_key"),
    )

    id: Mapped[IntPK]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(30))
    title: Mapped[str | None] = mapped_column(String(100))  # push title (migration 0008)
    message: Mapped[str] = mapped_column(Text)
    # identifies an automatic notification, e.g. "appointment-2h:42"; NULL for one-off ones
    dedupe_key: Mapped[str | None] = mapped_column(String(100))
    is_read: Mapped[bool] = mapped_column(server_default=false())
    sent_at: Mapped[CreatedAt]


class UserDevice(Base):
    """Firebase Cloud Messaging token (one user can have several devices)."""

    __tablename__ = "user_devices"
    __table_args__ = (
        check_in("platform", DEVICE_PLATFORMS),
        Index("idx_user_devices_user", "user_id"),
    )

    id: Mapped[IntPK]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    fcm_token: Mapped[str] = mapped_column(String(512), unique=True)
    platform: Mapped[str] = mapped_column(String(10))
    last_seen_at: Mapped[CreatedAt]
    created_at: Mapped[CreatedAt]
