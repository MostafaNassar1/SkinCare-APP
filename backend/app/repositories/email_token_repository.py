from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import EmailToken


def create(
    db: Session, *, user_id: int, purpose: str, token_hash: str, expires_at: datetime
) -> EmailToken:
    token = EmailToken(
        user_id=user_id, purpose=purpose, token_hash=token_hash, expires_at=expires_at
    )
    db.add(token)
    db.flush()
    return token


def get_latest(db: Session, *, user_id: int, purpose: str) -> EmailToken | None:
    """The most recently issued code, used or not (for the resend waiting time)."""
    return db.scalar(
        select(EmailToken)
        .where(EmailToken.user_id == user_id, EmailToken.purpose == purpose)
        .order_by(EmailToken.created_at.desc(), EmailToken.id.desc())
        .limit(1)
    )


def get_active_for_update(db: Session, *, user_id: int, purpose: str) -> EmailToken | None:
    # FOR UPDATE: two guesses at the same moment are counted one after the other
    return db.scalar(
        select(EmailToken)
        .where(
            EmailToken.user_id == user_id,
            EmailToken.purpose == purpose,
            EmailToken.used_at.is_(None),
        )
        .order_by(EmailToken.created_at.desc(), EmailToken.id.desc())
        .limit(1)
        .with_for_update()
    )


def invalidate_active(db: Session, *, user_id: int, purpose: str, used_at: datetime) -> None:
    """Retire every unused code of this user and purpose (a new code replaces the old ones)."""
    db.execute(
        update(EmailToken)
        .where(
            EmailToken.user_id == user_id,
            EmailToken.purpose == purpose,
            EmailToken.used_at.is_(None),
        )
        .values(used_at=used_at)
    )
