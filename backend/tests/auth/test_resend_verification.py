from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User
from tests.auth.conftest import EMAIL, PASSWORD, age_codes, login


def resend(client: TestClient, email: str = EMAIL, password: str = PASSWORD):
    return client.post("/auth/resend-verification", json={"email": email, "password": password})


def test_resend_too_soon_is_refused(client: TestClient, outbox, unverified: User):
    response = resend(client)

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "code_recently_sent"
    assert len(outbox) == 1  # only the sign-up email


def test_resend_after_the_waiting_time_sends_a_new_code(
    client: TestClient, db: Session, outbox, unverified: User
):
    age_codes(db, unverified.id, seconds=61)

    response = resend(client)

    assert response.status_code == 202
    assert response.json()["email"] == EMAIL
    assert len(outbox) == 2


def test_resend_needs_the_right_password(client: TestClient, db: Session, outbox, unverified):
    age_codes(db, unverified.id, seconds=61)

    response = resend(client, password="wrong-password")

    assert response.status_code == 401
    assert len(outbox) == 1  # nothing sent to a stranger's request


def test_resend_for_unknown_email_reveals_nothing(client: TestClient, outbox):
    response = resend(client, email="nobody@example.com")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"
    assert outbox == []


def test_resend_for_a_verified_account_is_refused(client: TestClient, registered: dict):
    assert resend(client).json()["error"]["code"] == "already_verified"


# ---------- Login of an unverified account ----------


def test_unverified_login_is_told_to_verify(client: TestClient, unverified: User):
    response = login(client)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "email_not_verified"


def test_unverified_login_with_wrong_password_reveals_nothing(client: TestClient, unverified):
    response = login(client, password="wrong-password")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"
