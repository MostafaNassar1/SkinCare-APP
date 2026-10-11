"""Issuing, rotating and revoking token pairs; shared by user and admin authentication."""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.security import (
    SubjectType,
    create_access_token,
    generate_token,
    hash_token,
    refresh_token_expires_at,
)
from app.models import RefreshToken
from app.repositories import refresh_token_repository


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str  # the raw token: sent to the client once, only its hash is stored
    expires_in: int  # access token lifetime in seconds


def _invalid_refresh_token() -> AppError:
    return AppError(401, "invalid_refresh_token", "Session expired. Please log in again.")


def _owner_id(token: RefreshToken, subject_type: SubjectType) -> int | None:
    return token.user_id if subject_type == "user" else token.admin_id


def issue_token_pair(db: Session, subject_id: int, subject_type: SubjectType) -> TokenPair:
    """Create an access token and store a new refresh token. The caller commits."""
    refresh_token = generate_token()
    refresh_token_repository.create(
        db,
        token_hash=hash_token(refresh_token),
        expires_at=refresh_token_expires_at(),
        user_id=subject_id if subject_type == "user" else None,
        admin_id=subject_id if subject_type == "admin" else None,
    )
    return TokenPair(
        access_token=create_access_token(subject_id, subject_type),
        refresh_token=refresh_token,
        expires_in=get_settings().access_token_expire_minutes * 60,
    )


def rotate_refresh_token(
    db: Session, raw_token: str, subject_type: SubjectType
) -> tuple[int, TokenPair]:
    """Exchange a valid refresh token for a new pair; the old one can never be used again.

    Returns the owner's id and the new pair. The caller commits.
    """
    now = datetime.now(UTC)
    stored = refresh_token_repository.get_by_hash_for_update(db, hash_token(raw_token))
    owner_id = _owner_id(stored, subject_type) if stored is not None else None
    if owner_id is None:  # unknown token, or a token of the other account type
        raise _invalid_refresh_token()

    if stored.revoked_at is not None:
        # Reuse of an already rotated/revoked token: it was probably stolen and both the
        # attacker and the real owner hold a copy. Revoke the whole family of this account's
        # tokens so everyone must log in again (OAuth 2.0 Security Best Current Practice).
        refresh_token_repository.revoke_all_active(
            db, revoked_at=now, **{f"{subject_type}_id": owner_id}
        )
        db.commit()  # must be saved even though this request fails
        raise _invalid_refresh_token()

    if stored.expires_at <= now:
        raise _invalid_refresh_token()

    stored.revoked_at = now
    return owner_id, issue_token_pair(db, owner_id, subject_type)


def revoke_refresh_token(db: Session, raw_token: str, subject_type: SubjectType) -> None:
    """Logout: revoke the token if it is a live token of this account type. The caller commits."""
    stored = refresh_token_repository.get_by_hash_for_update(db, hash_token(raw_token))
    if stored is not None and _owner_id(stored, subject_type) and stored.revoked_at is None:
        stored.revoked_at = datetime.now(UTC)
