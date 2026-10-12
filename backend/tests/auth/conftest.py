"""Fixtures and helpers shared by the auth tests."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import EmailToken, User
from app.services.email_service import Email

NAME = "Aya Test"
EMAIL = "aya@example.com"
PASSWORD = "long-enough-1"


def login(client: TestClient, email: str = EMAIL, password: str = PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def sign_up(client: TestClient, **changes):
    body = {"full_name": NAME, "email": EMAIL, "password": PASSWORD} | changes
    return client.post("/auth/register", json=body)


def last_code(outbox: list[Email], to: str = EMAIL) -> str:
    """The code in the newest email sent to `to` (the subject starts with it)."""
    emails = [email for email in outbox if email.to == to]
    assert emails, f"no email was sent to {to}"
    return emails[-1].subject[:6]


def verify(client: TestClient, code: str, email: str = EMAIL, password: str = PASSWORD):
    return client.post(
        "/auth/verify-email", json={"email": email, "password": password, "code": code}
    )


def age_codes(db: Session, user_id: int, seconds: int) -> None:
    """Pretend this user's codes were sent `seconds` ago (to get past the resend waiting time)."""
    db.execute(
        update(EmailToken)
        .where(EmailToken.user_id == user_id)
        .values(created_at=EmailToken.created_at - timedelta(seconds=seconds))
    )
    db.flush()


@pytest.fixture
def unverified(client: TestClient, db: Session) -> User:
    """A user who signed up but has not entered the code yet."""
    assert sign_up(client).status_code == 201
    return db.query(User).filter_by(email=EMAIL).one()


@pytest.fixture
def registered(client: TestClient, outbox: list[Email]) -> dict:
    """A verified, logged-in user; returns the /auth/verify-email response body."""
    assert sign_up(client).status_code == 201
    response = verify(client, last_code(outbox))
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def google_only_user(db: Session) -> User:
    """An account created with Google sign-in, so it has no password."""
    user = User(
        full_name="Google User",
        email="google@example.com",
        auth_provider="google",
        google_sub="google-sub-123",
        email_verified=True,
    )
    db.add(user)
    db.flush()
    return user
