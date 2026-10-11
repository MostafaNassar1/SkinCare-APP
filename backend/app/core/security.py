"""Password hashing, access tokens (JWT) and one-time tokens (refresh / email)."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, get_args

import bcrypt
import jwt

from app.core.config import get_settings

SubjectType = Literal["user", "admin"]

# Fixed in code, not in settings: the decoder only ever accepts this algorithm, which blocks
# attacks where a forged token says "alg: none" or switches to another algorithm.
JWT_ALGORITHM = "HS256"

# bcrypt only reads the first 72 bytes of a password; longer ones are rejected instead of being
# silently cut (two long passwords with the same first 72 bytes would otherwise match).
BCRYPT_MAX_BYTES = 72


class PasswordTooLongError(ValueError):
    """The password is longer than bcrypt can hash (72 bytes in UTF-8)."""


class InvalidTokenError(Exception):
    """The access token is missing, malformed, tampered with or expired."""


# ---------- Passwords (bcrypt) ----------


def hash_password(password: str) -> str:
    """Hash a password with bcrypt; a new random salt is generated for every hash."""
    encoded = password.encode("utf-8")
    if len(encoded) > BCRYPT_MAX_BYTES:
        raise PasswordTooLongError(f"Password must be at most {BCRYPT_MAX_BYTES} bytes")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """Check a password against a stored bcrypt hash."""
    encoded = password.encode("utf-8")
    if len(encoded) > BCRYPT_MAX_BYTES:
        return False  # could never have been hashed, so it cannot match
    return bcrypt.checkpw(encoded, password_hash.encode("ascii"))


# ---------- Access tokens (JWT) ----------


@dataclass(frozen=True)
class AccessTokenData:
    """What a valid access token says about its owner."""

    subject_id: int
    subject_type: SubjectType


def create_access_token(
    subject_id: int, subject_type: SubjectType, expires_delta: timedelta | None = None
) -> str:
    """Create a signed, short-lived access token for a user or an admin."""
    settings = get_settings()
    now = datetime.now(UTC)
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(subject_id),  # the JWT standard requires "sub" to be a string
        "sub_type": subject_type,  # users and admins are different tables with separate ids
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> AccessTokenData:
    """Verify the signature and expiry of an access token and return its contents."""
    try:
        payload = jwt.decode(
            token,
            get_settings().jwt_secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "exp", "iat"]},
        )
        subject_type = payload["sub_type"]
        if subject_type not in get_args(SubjectType):
            raise ValueError(f"Unknown subject type: {subject_type!r}")
        return AccessTokenData(subject_id=int(payload["sub"]), subject_type=subject_type)
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise InvalidTokenError("Invalid or expired token") from exc


# ---------- One-time tokens (refresh, password reset, email verification) ----------


def generate_token() -> str:
    """A random, URL-safe token with 256 bits of randomness (sent to the client once)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """SHA-256 of a token; only this hash is stored in the database.

    SHA-256 (not bcrypt) is enough here: the token is random with 256 bits, so guessing it is
    impossible, and a fast hash with the same result every time lets the database look it up.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def refresh_token_expires_at(subject_type: SubjectType) -> datetime:
    """Expiry time for a refresh token issued now (admins get much shorter sessions)."""
    settings = get_settings()
    if subject_type == "admin":
        lifetime = timedelta(hours=settings.admin_refresh_token_expire_hours)
    else:
        lifetime = timedelta(days=settings.refresh_token_expire_days)
    return datetime.now(UTC) + lifetime
