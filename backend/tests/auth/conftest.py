"""Fixtures shared by the auth tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User

EMAIL = "aya@example.com"
PASSWORD = "long-enough-1"


def login(client: TestClient, email: str = EMAIL, password: str = PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def registered(client: TestClient) -> dict:
    """A registered email/password user; returns the /auth/register response body."""
    response = client.post(
        "/auth/register", json={"full_name": "Aya Test", "email": EMAIL, "password": PASSWORD}
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def google_only_user(db: Session) -> User:
    """An account created with Google sign-in, so it has no password."""
    user = User(
        full_name="Google User",
        email="google@example.com",
        auth_provider="google",
        google_sub="google-sub-123",
    )
    db.add(user)
    db.flush()
    return user
