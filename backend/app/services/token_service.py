"""Issuing access + refresh token pairs; shared by register, login, refresh and admin login."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    SubjectType,
    create_access_token,
    generate_token,
    hash_token,
    refresh_token_expires_at,
)
from app.repositories import refresh_token_repository


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str  # the raw token: sent to the client once, only its hash is stored
    expires_in: int  # access token lifetime in seconds


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
