from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    false,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAt, IntPK, UpdatedAt, check_in
from app.models.choices import AUTH_PROVIDERS, GENDERS, SKIN_TYPES


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        check_in("auth_provider", AUTH_PROVIDERS),
        check_in("gender", GENDERS),
        CheckConstraint("last_latitude BETWEEN -90 AND 90", name="last_latitude_check"),
        CheckConstraint("last_longitude BETWEEN -180 AND 180", name="last_longitude_check"),
        # the sign-up method must actually be usable
        CheckConstraint("auth_provider <> 'email' OR password_hash IS NOT NULL", name="check"),
        CheckConstraint("auth_provider <> 'google' OR google_sub IS NOT NULL", name="check1"),
    )

    id: Mapped[IntPK]
    full_name: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(255))
    email_verified: Mapped[bool] = mapped_column(server_default=false())
    password_hash: Mapped[str | None] = mapped_column(String(255))  # NULL for Google-only accounts
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True)  # Google's user id
    auth_provider: Mapped[str] = mapped_column(String(20), server_default="email")
    phone_number: Mapped[str | None] = mapped_column(String(30))
    date_of_birth: Mapped[date | None]
    gender: Mapped[str | None] = mapped_column(String(20))
    profile_picture_url: Mapped[str | None] = mapped_column(String(500))
    timezone: Mapped[str] = mapped_column(String(50), server_default="Asia/Beirut")  # IANA name
    last_latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    last_longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    location_updated_at: Mapped[datetime | None]
    is_active: Mapped[bool] = mapped_column(server_default=true())
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    # passive_deletes: let PostgreSQL's ON DELETE CASCADE remove the profile
    profile: Mapped["UserProfile | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


# emails are unique regardless of letter case (Ali@x.com = ali@x.com)
Index("uq_users_email_lower", func.lower(User.email), unique=True)


class UserProfile(Base):
    __tablename__ = "user_profiles"
    __table_args__ = (
        check_in("skin_type", SKIN_TYPES),
        CheckConstraint("fitzpatrick_scale BETWEEN 1 AND 6", name="fitzpatrick_scale_check"),
    )

    id: Mapped[IntPK]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    skin_type: Mapped[str | None] = mapped_column(String(20))
    fitzpatrick_scale: Mapped[int | None] = mapped_column(SmallInteger)
    skin_quiz_answers: Mapped[dict[str, Any] | None]  # raw answers of the onboarding skin quiz
    skin_quiz_completed_at: Mapped[datetime | None]
    # excludes unsafe ingredients (e.g. retinoids) from routines
    is_pregnant_or_breastfeeding: Mapped[bool] = mapped_column(server_default=false())
    other_allergies_notes: Mapped[str | None] = mapped_column(Text)
    # free-text notes about the user's skin (migration 0004); shown to the user and shared with a
    # clinic only when they book an appointment; the rules engine does not read them
    skin_notes: Mapped[str | None] = mapped_column(String(1000))
    updated_at: Mapped[UpdatedAt]

    user: Mapped[User] = relationship(back_populates="profile")
