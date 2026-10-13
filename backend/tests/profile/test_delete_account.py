from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models import EmailToken, RefreshToken, User, UserAllergy, UserDevice, UserProfile
from app.repositories import ingredient_repository
from app.services import token_service
from tests.google_fake import FakeGoogle

PASSWORD = "long-enough-1"  # app_user's password


def delete_me(client: TestClient, headers: dict, **body):
    return client.request("DELETE", "/me", headers=headers, json=body)


def bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, 'user')}"}


@pytest.fixture
def full_account(client: TestClient, db: Session, user_headers, app_user: User) -> User:
    """app_user with some of everything: allergies, a phone, a session, a code."""
    retinol = next(i for i in ingredient_repository.list_all(db) if i.name == "Retinol")
    client.put("/me/allergies", headers=user_headers, json={"ingredient_ids": [retinol.id]})
    client.post(
        "/me/devices",
        headers=user_headers,
        json={"fcm_token": "phone-token-" + "x" * 30, "platform": "android"},
    )
    token_service.issue_token_pair(db, app_user.id, "user")
    db.add(
        EmailToken(
            user_id=app_user.id,
            purpose="password_reset",
            token_hash="x",
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
    )
    db.flush()
    return app_user


def rows_of(db: Session, user_id: int) -> dict[str, int]:
    db.expire_all()
    return {
        model.__tablename__: db.query(model).filter_by(user_id=user_id).count()
        for model in (UserProfile, UserAllergy, UserDevice, RefreshToken, EmailToken)
    }


# ---------- With the password ----------


def test_delete_with_password_removes_everything(
    client: TestClient, db: Session, outbox, user_headers, full_account: User
):
    user_id = full_account.id

    response = delete_me(client, user_headers, password=PASSWORD)

    assert response.status_code == 204
    assert db.get(User, user_id) is None
    assert set(rows_of(db, user_id).values()) == {0}  # nothing left behind


def test_confirmation_email_is_sent(client: TestClient, outbox, user_headers, app_user: User):
    delete_me(client, user_headers, password=PASSWORD)

    assert outbox[-1].to == "user@example.com"
    assert outbox[-1].subject == "Your SkinCare account was deleted"


def test_after_deletion_the_old_token_no_longer_works(client: TestClient, user_headers, app_user):
    delete_me(client, user_headers, password=PASSWORD)

    assert client.get("/me/profile", headers=user_headers).status_code == 401
    login = client.post("/auth/login", json={"email": "user@example.com", "password": PASSWORD})
    assert login.status_code == 401


def test_wrong_password_deletes_nothing(
    client: TestClient, db: Session, outbox, user_headers, app_user: User
):
    response = delete_me(client, user_headers, password="wrong-password")

    assert response.status_code == 403  # not 401: the session is fine, the app stays logged in
    assert response.json()["error"]["code"] == "reauthentication_failed"
    assert db.get(User, app_user.id) is not None
    assert outbox == []


def test_a_proof_is_required(client: TestClient, user_headers, app_user):
    assert delete_me(client, user_headers).status_code == 422
    assert delete_me(client, user_headers, password="").status_code == 422


def test_other_accounts_are_untouched(client: TestClient, db: Session, user_headers, app_user):
    other = User(
        full_name="Other",
        email="other@example.com",
        password_hash=hash_password("other-password"),
        email_verified=True,
        profile=UserProfile(),
    )
    db.add(other)
    db.flush()

    delete_me(client, user_headers, password=PASSWORD)

    assert client.get("/me/profile", headers=bearer(other)).status_code == 200


# ---------- With Google ----------


@pytest.fixture
def google_user(db: Session) -> User:
    user = User(
        full_name="Google User",
        email="aya@gmail.com",
        auth_provider="google",
        google_sub="google-sub-1",  # the fake Google's default user
        email_verified=True,
        profile=UserProfile(),
    )
    db.add(user)
    db.flush()
    return user


def test_google_account_confirms_by_signing_in_again(
    client: TestClient, db: Session, fake_google: FakeGoogle, google_user: User
):
    user_id = google_user.id

    response = delete_me(client, bearer(google_user), google_id_token=fake_google.token())

    assert response.status_code == 204
    assert db.get(User, user_id) is None


def test_a_different_google_account_cannot_confirm(
    client: TestClient, db: Session, fake_google: FakeGoogle, google_user: User
):
    token = fake_google.token(sub="someone-else")

    response = delete_me(client, bearer(google_user), google_id_token=token)

    assert response.status_code == 403
    assert db.get(User, google_user.id) is not None


def test_google_only_account_cannot_use_a_password(client: TestClient, google_user: User):
    response = delete_me(client, bearer(google_user), password="anything-at-all")
    assert response.status_code == 403


def test_linked_account_may_use_either_method(
    client: TestClient, db: Session, fake_google: FakeGoogle, app_user: User
):
    app_user.google_sub = "google-sub-1"  # password account linked to Google
    db.flush()

    response = delete_me(client, bearer(app_user), google_id_token=fake_google.token())

    assert response.status_code == 204


def test_forged_google_token_is_refused(client: TestClient, fake_google, google_user: User):
    response = delete_me(client, bearer(google_user), google_id_token="not-a-token")
    assert response.json()["error"]["code"] == "invalid_google_token"


def test_deleting_requires_login(client: TestClient):
    assert delete_me(client, {}, password=PASSWORD).status_code == 401
