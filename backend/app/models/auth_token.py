from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, IntPK, check_in
from app.models.choices import EMAIL_TOKEN_PURPOSES


class RefreshToken(Base):
    """Refresh token of a user (mobile) or an admin (web); only a hash is stored."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        # belongs to exactly one account
        CheckConstraint("num_nonnulls(user_id, admin_id) = 1", name="check"),
        Index("idx_refresh_tokens_user", "user_id"),
        Index("idx_refresh_tokens_admin", "admin_id"),
    )

    id: Mapped[IntPK]
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    admin_id: Mapped[int | None] = mapped_column(ForeignKey("admins.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(255), unique=True)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]  # set on logout or rotation
    created_at: Mapped[CreatedAt]


class EmailToken(Base):
    """One-time token sent by email (password reset, email verification)."""

    __tablename__ = "email_tokens"
    __table_args__ = (
        check_in("purpose", EMAIL_TOKEN_PURPOSES),
        Index("idx_email_tokens_user", "user_id"),
    )

    id: Mapped[IntPK]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(String(30))
    token_hash: Mapped[str] = mapped_column(String(255), unique=True)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
    created_at: Mapped[CreatedAt]
