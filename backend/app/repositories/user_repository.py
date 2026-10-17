from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, contains_eager

from app.models import User, UserProfile


def get_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_by_email(db: Session, email: str) -> User | None:
    # LOWER(email) matches the case-insensitive unique index uq_users_email_lower
    return db.scalar(select(User).where(func.lower(User.email) == email.lower()))


def delete_account(db: Session, user_id: int) -> None:
    """Permanently delete the account. ON DELETE CASCADE in the database removes everything that
    belongs to it (profile, allergies, scans, routines, logs, devices, tokens, codes,
    appointments, notifications). The caller commits."""
    db.execute(delete(User).where(User.id == user_id))


def get_or_create_profile(db: Session, user: User) -> UserProfile:
    """Every account gets a profile at sign-up; this also covers any account created before."""
    if user.profile is None:
        user.profile = UserProfile()
        db.flush()
    return user.profile


def get_by_google_sub(db: Session, google_sub: str) -> User | None:
    return db.scalar(select(User).where(User.google_sub == google_sub))


def create_google_user(db: Session, *, full_name: str, email: str, google_sub: str) -> User:
    """A new "Continue with Google" account: verified by Google, no password."""
    user = User(
        full_name=full_name,
        email=email,
        google_sub=google_sub,
        auth_provider="google",
        email_verified=True,
        profile=UserProfile(),
    )
    db.add(user)
    db.flush()
    return user


def _never_verified_before(cutoff: datetime):
    return (
        User.auth_provider == "email",
        User.email_verified.is_(False),
        User.created_at < cutoff,
    )


def count_never_verified(db: Session, *, created_before: datetime) -> int:
    return db.scalar(
        select(func.count()).select_from(User).where(*_never_verified_before(created_before))
    )


def delete_never_verified(db: Session, *, created_before: datetime) -> int:
    """Delete email sign-ups that were never verified; ON DELETE CASCADE removes their profile
    and codes. Returns how many accounts were deleted. The caller commits."""
    result = db.execute(delete(User).where(*_never_verified_before(created_before)))
    return result.rowcount


def create_email_user(db: Session, *, full_name: str, email: str, password_hash: str) -> User:
    """A new email/password account with an empty profile (filled in later by the skin quiz)."""
    user = User(
        full_name=full_name,
        email=email,
        password_hash=password_hash,
        auth_provider="email",
        profile=UserProfile(),
    )
    db.add(user)
    db.flush()  # sends the INSERTs now, so the id exists and unique violations surface here
    return user


def list_forecast_candidates(db: Session) -> list[User]:
    """Users who may get the daily skin forecast: active, verified, forecast on, and with a
    location (no location = no local weather). Profiles loaded for the scheduler."""
    return list(
        db.scalars(
            select(User)
            .join(UserProfile, UserProfile.user_id == User.id)
            .where(
                User.is_active,
                User.email_verified,
                User.last_latitude.is_not(None),
                User.last_longitude.is_not(None),
                UserProfile.daily_forecast_enabled,
            )
            .options(contains_eager(User.profile))
            .order_by(User.id)
        )
    )
