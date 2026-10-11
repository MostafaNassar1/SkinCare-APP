from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import RefreshToken


def create(
    db: Session,
    *,
    token_hash: str,
    expires_at: datetime,
    user_id: int | None = None,
    admin_id: int | None = None,
) -> RefreshToken:
    refresh_token = RefreshToken(
        token_hash=token_hash, expires_at=expires_at, user_id=user_id, admin_id=admin_id
    )
    db.add(refresh_token)
    db.flush()
    return refresh_token


def get_by_hash_for_update(db: Session, token_hash: str) -> RefreshToken | None:
    # FOR UPDATE locks the row: two refreshes with the same token are handled one after the
    # other, so a token can never be rotated twice
    return db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
    )


def revoke_all_active(
    db: Session, *, revoked_at: datetime, user_id: int | None = None, admin_id: int | None = None
) -> None:
    """Revoke every not-yet-revoked refresh token of one user or one admin."""
    owner = RefreshToken.user_id == user_id if user_id is not None else (
        RefreshToken.admin_id == admin_id
    )
    db.execute(
        update(RefreshToken)
        .where(owner, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=revoked_at)
    )
