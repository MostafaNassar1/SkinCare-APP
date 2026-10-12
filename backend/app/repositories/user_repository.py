from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import User, UserProfile


def get_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_by_email(db: Session, email: str) -> User | None:
    # LOWER(email) matches the case-insensitive unique index uq_users_email_lower
    return db.scalar(select(User).where(func.lower(User.email) == email.lower()))


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
