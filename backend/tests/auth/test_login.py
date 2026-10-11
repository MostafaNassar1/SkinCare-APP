from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.models import RefreshToken, User
from app.services import auth_service
from tests.auth.conftest import EMAIL, PASSWORD, login

# ---------- Success ----------


def test_login_returns_tokens_and_the_user(client: TestClient, registered: dict):
    response = login(client)

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["id"] == registered["user"]["id"]
    assert decode_access_token(body["access_token"]).subject_id == registered["user"]["id"]
    assert body["refresh_token"] != registered["refresh_token"]


def test_email_case_does_not_matter(client: TestClient, registered: dict):
    assert login(client, email="AYA@Example.COM").status_code == 200


def test_spaces_around_the_email_are_ignored(client: TestClient, registered: dict):
    assert login(client, email=f"  {EMAIL} ").status_code == 200


def test_spaces_in_the_password_are_not_ignored(client: TestClient, registered: dict):
    assert login(client, password=f" {PASSWORD}").status_code == 401


def test_each_login_is_a_separate_session(client: TestClient, db: Session, registered: dict):
    login(client)
    login(client)

    count = db.scalar(
        select(func.count()).where(RefreshToken.user_id == registered["user"]["id"])
    )
    assert count == 3  # register + 2 logins: one refresh token per device/session


# ---------- No hints about what was wrong ----------


def test_wrong_password_is_rejected(client: TestClient, registered: dict):
    response = login(client, password="wrong-password")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_unknown_email_gets_the_same_answer_as_a_wrong_password(
    client: TestClient, registered: dict
):
    wrong_password = login(client, password="wrong-password")
    unknown_email = login(client, email="nobody@example.com")

    assert unknown_email.status_code == wrong_password.status_code == 401
    assert unknown_email.json() == wrong_password.json()


def test_google_only_account_gets_the_same_answer(client: TestClient, google_only_user: User):
    response = login(client, email=google_only_user.email, password="anything-at-all")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_unknown_email_still_runs_a_password_check(client: TestClient, monkeypatch):
    # equal work for known and unknown emails, so timing does not reveal registered emails
    calls = []
    real_verify = auth_service.verify_password
    monkeypatch.setattr(
        auth_service, "verify_password", lambda *args: calls.append(1) or real_verify(*args)
    )

    login(client, email="nobody@example.com")

    assert len(calls) == 1


def test_overlong_password_is_just_invalid_credentials(client: TestClient, registered: dict):
    assert login(client, password="a" * 500).status_code == 401


# ---------- Disabled accounts ----------


def test_disabled_account_with_correct_password_is_told(
    client: TestClient, db: Session, registered: dict
):
    db.get(User, registered["user"]["id"]).is_active = False
    db.flush()

    response = login(client)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_disabled"


def test_disabled_account_with_wrong_password_reveals_nothing(
    client: TestClient, db: Session, registered: dict
):
    db.get(User, registered["user"]["id"]).is_active = False
    db.flush()

    assert login(client, EMAIL, PASSWORD + "x").json()["error"]["code"] == "invalid_credentials"
