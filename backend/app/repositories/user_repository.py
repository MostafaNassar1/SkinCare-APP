from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import User, UserProfile


def get_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_by_email(db: Session, email: str) -> User | None:
    # LOWER(email) matches the case-insensitive unique index uq_users_email_lower
    return db.scalar(select(User).where(func.lower(User.email) == email.lower()))


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
