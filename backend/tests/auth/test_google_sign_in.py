"""POST /auth/google and the account-linking policy (fake Google: tests/google_fake.py)."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.models import EmailToken, User
from app.repositories import user_repository
from tests.auth.conftest import EMAIL, PASSWORD, bearer, login
from tests.google_fake import FakeGoogle


def google(client: TestClient, token: str):
    return client.post("/auth/google", json={"id_token": token})


def error_code(response) -> str:
    return response.json()["error"]["code"]


# ---------- New account / returning user ----------


def test_new_email_creates_a_verified_google_account(
    client: TestClient, db: Session, fake_google: FakeGoogle
):
    response = google(client, fake_google.token(email="new@gmail.com", name="New Person"))

    assert response.status_code == 200
    body = response.json()
    assert body["is_new_user"] is True
    assert body["user"]["email"] == "new@gmail.com"
    assert body["user"]["email_verified"] is True
    assert body["user"]["auth_provider"] == "google"
    user = db.get(User, body["user"]["id"])
    assert user.full_name == "New Person"
    assert user.password_hash is None
    assert user.google_sub == "google-sub-1"
    assert user.profile is not None
    assert client.get("/auth/me", headers=bearer(body["access_token"])).status_code == 200


def test_returning_google_user_logs_in(client: TestClient, fake_google: FakeGoogle):
    first = google(client, fake_google.token()).json()
    second = google(client, fake_google.token()).json()

    assert second["is_new_user"] is False
    assert second["user"]["id"] == first["user"]["id"]


def test_returning_user_is_found_by_google_id_even_if_the_email_changed(
    client: TestClient, fake_google: FakeGoogle
):
    first = google(client, fake_google.token(email="old@gmail.com")).json()
    second = google(client, fake_google.token(email="renamed@gmail.com")).json()

    assert second["user"]["id"] == first["user"]["id"]


# ---------- Linking with an existing password account ----------


def test_verified_password_account_is_linked(
    client: TestClient, db: Session, fake_google: FakeGoogle, registered: dict
):
    response = google(client, fake_google.token(email=EMAIL))

    body = response.json()
    assert response.status_code == 200
    assert body["is_new_user"] is False
    assert body["user"]["id"] == registered["user"]["id"]  # the SAME account, not a second one
    user = db.get(User, body["user"]["id"])
    assert user.google_sub == "google-sub-1"
    # both login methods now open the same account
    assert login(client).status_code == 200
    assert google(client, fake_google.token(email=EMAIL)).json()["user"]["id"] == user.id


def test_unverified_password_account_is_taken_over_and_its_password_deleted(
    client: TestClient, db: Session, fake_google: FakeGoogle, unverified: User
):
    response = google(client, fake_google.token(email=EMAIL, name="Real Owner"))

    body = response.json()
    assert body["user"]["id"] == unverified.id
    assert body["is_new_user"] is True
    db.refresh(unverified)
    assert unverified.password_hash is None
    assert unverified.auth_provider == "google"
    assert unverified.email_verified is True
    assert unverified.full_name == "Real Owner"
    # whoever registered first with a password can no longer get in
    assert login(client, password=PASSWORD).json()["error"]["code"] == "invalid_credentials"
    # and their pending verification code is dead
    codes = db.query(EmailToken).filter_by(user_id=unverified.id).all()
    assert codes and all(code.used_at is not None for code in codes)


def test_email_of_a_different_google_account_is_refused(
    client: TestClient, fake_google: FakeGoogle, google_only_user: User
):
    token = fake_google.token(email=google_only_user.email, sub="a-different-google-id")
    response = google(client, token)

    assert response.status_code == 409
    assert error_code(response) == "google_account_mismatch"


# ---------- Refused ----------


def test_google_email_not_verified_is_refused(
    client: TestClient, db: Session, fake_google: FakeGoogle
):
    token = fake_google.token(email="unconfirmed@company.com", email_verified=False)
    response = google(client, token)

    assert response.status_code == 401
    assert error_code(response) == "google_email_not_verified"
    assert user_repository.get_by_email(db, "unconfirmed@company.com") is None


def test_token_for_another_app_is_refused(client: TestClient, fake_google: FakeGoogle):
    response = google(client, fake_google.token(aud="another-app.apps.googleusercontent.com"))

    assert response.status_code == 401
    assert error_code(response) == "invalid_google_token"


def test_garbage_token_is_refused(client: TestClient, fake_google: FakeGoogle):
    assert error_code(google(client, "not-a-token")) == "invalid_google_token"


def test_disabled_account_cannot_sign_in(
    client: TestClient, db: Session, fake_google: FakeGoogle
):
    user_id = google(client, fake_google.token()).json()["user"]["id"]
    db.get(User, user_id).is_active = False
    db.flush()

    response = google(client, fake_google.token())

    assert response.status_code == 403
    assert error_code(response) == "account_disabled"


def test_google_sign_in_off_without_client_ids(client: TestClient, fake_google, monkeypatch):
    monkeypatch.setattr(get_settings(), "google_client_ids", [])

    response = google(client, fake_google.token())

    assert response.status_code == 503
    assert error_code(response) == "google_sign_in_unavailable"


def test_the_access_token_belongs_to_the_user(client: TestClient, fake_google: FakeGoogle):
    body = google(client, fake_google.token()).json()
    assert decode_access_token(body["access_token"]).subject_id == body["user"]["id"]
