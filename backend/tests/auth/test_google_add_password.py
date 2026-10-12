"""A Google-only account adds a password through 'Forgot password' (the code proves the inbox)."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User
from tests.auth.conftest import last_code, login
from tests.google_fake import FakeGoogle

GOOGLE_EMAIL = "google@example.com"
NEW_PASSWORD = "my-first-password"


def add_password(client: TestClient, outbox) -> None:
    client.post("/auth/forgot-password", json={"email": GOOGLE_EMAIL})
    response = client.post(
        "/auth/reset-password",
        json={
            "email": GOOGLE_EMAIL,
            "code": last_code(outbox, to=GOOGLE_EMAIL),
            "new_password": NEW_PASSWORD,
        },
    )
    assert response.status_code == 200


def test_google_only_account_receives_a_code(client: TestClient, outbox, google_only_user: User):
    client.post("/auth/forgot-password", json={"email": GOOGLE_EMAIL})

    assert outbox[-1].to == GOOGLE_EMAIL
    assert "password reset" in outbox[-1].subject


def test_after_adding_a_password_both_methods_open_the_same_account(
    client: TestClient, db: Session, outbox, fake_google: FakeGoogle, google_only_user: User
):
    assert login(client, GOOGLE_EMAIL, NEW_PASSWORD).status_code == 401  # no password yet

    add_password(client, outbox)

    by_password = login(client, GOOGLE_EMAIL, NEW_PASSWORD).json()
    google_token = fake_google.token(sub=google_only_user.google_sub, email=GOOGLE_EMAIL)
    by_google = client.post("/auth/google", json={"id_token": google_token}).json()
    assert by_password["user"]["id"] == by_google["user"]["id"] == google_only_user.id


def test_sign_up_method_is_still_recorded_as_google(
    client: TestClient, db: Session, outbox, google_only_user: User
):
    add_password(client, outbox)

    db.refresh(google_only_user)
    assert google_only_user.auth_provider == "google"
    assert google_only_user.password_hash is not None
