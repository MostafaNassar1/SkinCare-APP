import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.controllers.auth_controller import FORGOT_PASSWORD_MESSAGE
from app.models import User
from app.repositories import user_repository
from tests.auth.conftest import EMAIL, PASSWORD, age_codes, last_code, login, verify

NEW_PASSWORD = "brand-new-password"


def forgot(client: TestClient, email: str = EMAIL):
    return client.post("/auth/forgot-password", json={"email": email})


def reset(client: TestClient, code: str, email: str = EMAIL, new_password: str = NEW_PASSWORD):
    return client.post(
        "/auth/reset-password", json={"email": email, "code": code, "new_password": new_password}
    )


def wrong(code: str) -> str:
    return f"{(int(code) + 1) % 1_000_000:06d}"


@pytest.fixture
def reset_code(client: TestClient, outbox, registered: dict) -> str:
    """A verified user asked for a reset; returns the code from the email."""
    forgot(client)
    return last_code(outbox)


# ---------- Forgot password: same answer for everyone ----------


def test_forgot_password_emails_a_reset_code(client: TestClient, outbox, registered: dict):
    response = forgot(client)

    assert response.status_code == 202
    assert response.json() == {"message": FORGOT_PASSWORD_MESSAGE}
    assert outbox[-1].to == EMAIL
    assert "password reset" in outbox[-1].subject


@pytest.mark.parametrize("who", ["unknown", "google_only", "disabled", "waiting"])
def test_forgot_password_reveals_nothing(
    client: TestClient, db: Session, outbox, registered: dict, google_only_user: User, who: str
):
    email = EMAIL
    if who == "unknown":
        email = "nobody@example.com"
    elif who == "google_only":
        email = google_only_user.email
    elif who == "disabled":
        user_repository.get_by_email(db, EMAIL).is_active = False
        db.flush()
    else:  # a reset code was sent less than 60 seconds ago
        forgot(client)
    emails_before = len(outbox)

    response = forgot(client, email)

    assert response.status_code == 202
    assert response.json() == {"message": FORGOT_PASSWORD_MESSAGE}
    assert len(outbox) == emails_before  # nothing was sent


def test_email_case_and_spaces_do_not_matter(client: TestClient, outbox, registered: dict):
    forgot(client, "  AYA@example.com ")
    assert outbox[-1].to == EMAIL


# ---------- Reset password ----------


def test_reset_sets_the_new_password_and_logs_in(client: TestClient, reset_code: str):
    response = reset(client, reset_code)

    assert response.status_code == 200
    assert response.json()["user"]["email"] == EMAIL
    assert login(client, password=NEW_PASSWORD).status_code == 200
    assert login(client, password=PASSWORD).status_code == 401


def test_reset_logs_out_every_other_device(
    client: TestClient, registered: dict, reset_code: str
):
    reset(client, reset_code)

    old_session = registered["refresh_token"]
    assert client.post("/auth/refresh", json={"refresh_token": old_session}).status_code == 401


def test_reset_code_works_only_once(client: TestClient, reset_code: str):
    reset(client, reset_code)

    assert reset(client, reset_code).json()["error"]["code"] == "code_expired"


def test_wrong_reset_code_counts_attempts(client: TestClient, reset_code: str):
    for attempts_left in [4, 3, 2, 1, 0]:
        response = reset(client, wrong(reset_code))
        assert response.json()["error"]["details"] == {"attempts_left": attempts_left}

    assert reset(client, reset_code).json()["error"]["code"] == "code_expired"


def test_unknown_email_gets_the_same_answer_as_no_code(client: TestClient):
    response = reset(client, "123456", email="nobody@example.com")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "code_expired"


def test_new_password_must_follow_the_rules(client: TestClient, reset_code: str):
    response = reset(client, reset_code, new_password="short")

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "new_password"
    assert '"short"' not in response.text  # the rejected password is not echoed


# ---------- Unverified accounts ----------


def test_reset_also_verifies_the_email(
    client: TestClient, db: Session, outbox, unverified: User
):
    age_codes(db, unverified.id, seconds=120)
    forgot(client)

    response = reset(client, last_code(outbox))

    assert response.status_code == 200
    assert db.get(User, unverified.id).email_verified is True


def test_verification_code_is_not_a_reset_code(
    client: TestClient, db: Session, outbox, unverified: User
):
    verification_code = last_code(outbox)
    age_codes(db, unverified.id, seconds=120)
    forgot(client)
    if last_code(outbox) == verification_code:  # 1 in a million
        return

    assert reset(client, verification_code).json()["error"]["code"] == "invalid_code"
    # and a reset code cannot verify the email through the verification screen either
    assert verify(client, last_code(outbox)).json()["error"]["code"] == "invalid_code"
