"""Model behaviour that depends on the database: defaults, triggers and constraints."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import EmailToken, User


def make_user(**overrides) -> User:
    fields = {"full_name": "Test User", "email": "test@example.com", "password_hash": "hash"}
    return User(**(fields | overrides))


def test_server_defaults_are_read_back(db: Session):
    user = make_user()
    db.add(user)
    db.flush()

    assert user.id is not None
    assert user.auth_provider == "email"
    assert user.timezone == "Asia/Beirut"
    assert user.is_active is True
    assert user.email_verified is False
    assert user.created_at is not None


def test_updated_at_is_refreshed_by_the_trigger(db: Session):
    old = datetime(2000, 1, 1, tzinfo=UTC)
    user = make_user(updated_at=old)  # an INSERT does not fire the update trigger
    db.add(user)
    db.flush()
    assert user.updated_at == old

    user.full_name = "Renamed"
    db.flush()

    # the trigger set a new value and SQLAlchemy read it back (no stale value in Python)
    assert user.updated_at > old


def test_email_is_unique_regardless_of_case(db: Session):
    db.add(make_user(email="ali@example.com"))
    db.flush()

    db.add(make_user(email="Ali@Example.com"))
    with pytest.raises(IntegrityError, match="uq_users_email_lower"):
        db.flush()


def test_email_account_requires_a_password(db: Session):
    db.add(make_user(password_hash=None))
    with pytest.raises(IntegrityError, match="users_check"):
        db.flush()


# ---------- email_tokens after migration 0003 ----------


def make_code(user: User, **overrides) -> EmailToken:
    fields = {
        "user_id": user.id,
        "purpose": "email_verification",
        "token_hash": "same-hash",
        "expires_at": datetime.now(UTC) + timedelta(minutes=10),
    }
    return EmailToken(**(fields | overrides))


def test_code_attempts_start_at_zero(db: Session):
    user = make_user()
    db.add(user)
    db.flush()
    code = make_code(user)
    db.add(code)
    db.flush()

    assert code.attempts == 0


def test_code_attempts_cannot_be_negative(db: Session):
    user = make_user()
    db.add(user)
    db.flush()
    db.add(make_code(user, attempts=-1))
    with pytest.raises(IntegrityError, match="email_tokens_attempts_check"):
        db.flush()


def test_two_users_can_hold_the_same_code_hash(db: Session):
    first, second = make_user(), make_user(email="other@example.com")
    db.add_all([first, second])
    db.flush()

    db.add_all([make_code(first), make_code(second)])
    db.flush()  # no unique violation: 6-digit codes can repeat across users
