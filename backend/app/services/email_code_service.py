"""6-digit email codes: issuing, checking and the resend waiting time.

Shared by email verification and password reset.
"""

import math
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.security import code_matches, generate_code, hash_code
from app.repositories import email_token_repository

VERIFICATION = "email_verification"
PASSWORD_RESET = "password_reset"


def code_expired() -> AppError:
    return AppError(400, "code_expired", "This code has expired. Please request a new one.")


def code_recently_sent(wait_seconds: int) -> AppError:
    return AppError(
        429,
        "code_recently_sent",
        f"Please wait {wait_seconds} seconds before requesting a new code.",
        details={"retry_after": wait_seconds},
        headers={"Retry-After": str(wait_seconds)},
    )


def seconds_until_resend(db: Session, user_id: int, purpose: str) -> int:
    """0 if a new code may be sent now, otherwise how many seconds to wait."""
    latest = email_token_repository.get_latest(db, user_id=user_id, purpose=purpose)
    if latest is None:
        return 0
    elapsed = (datetime.now(UTC) - latest.created_at).total_seconds()
    return max(0, math.ceil(get_settings().email_code_resend_seconds - elapsed))


def issue_code(db: Session, user_id: int, purpose: str) -> str:
    """Create a new code (older unused ones stop working) and return it. The caller commits."""
    now = datetime.now(UTC)
    email_token_repository.invalidate_active(db, user_id=user_id, purpose=purpose, used_at=now)
    code = generate_code()
    email_token_repository.create(
        db,
        user_id=user_id,
        purpose=purpose,
        token_hash=hash_code(code, user_id=user_id, purpose=purpose),
        expires_at=now + timedelta(minutes=get_settings().email_code_expire_minutes),
    )
    return code


def check_code(db: Session, user_id: int, purpose: str, code: str) -> None:
    """Accept the code (it can never be used again) or raise. The caller commits on success."""
    settings = get_settings()
    now = datetime.now(UTC)
    token = email_token_repository.get_active_for_update(db, user_id=user_id, purpose=purpose)
    if (
        token is None
        or token.expires_at <= now
        or token.attempts >= settings.email_code_max_attempts
    ):
        raise code_expired()

    if not code_matches(code, token.token_hash, user_id=user_id, purpose=purpose):
        token.attempts += 1
        attempts_left = settings.email_code_max_attempts - token.attempts
        if attempts_left == 0:
            token.used_at = now  # too many wrong guesses: this code is dead
        db.commit()  # the wrong guess must be counted even though this request fails
        raise AppError(
            400,
            "invalid_code",
            "Incorrect code." if attempts_left else "Incorrect code. Please request a new one.",
            details={"attempts_left": attempts_left},
        )

    token.used_at = now
