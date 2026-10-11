import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, hash_token, verify_password
from app.models import RefreshToken, User
from app.repositories import user_repository

VALID = {"full_name": "Aya Test", "email": "Aya@Example.com", "password": "long-enough-1"}


def register(client: TestClient, **changes):
    return client.post("/auth/register", json=VALID | changes)


# ---------- Success ----------


def test_register_creates_the_account_and_logs_in(client: TestClient):
    response = register(client)

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 15 * 60
    assert body["user"]["full_name"] == "Aya Test"
    assert body["user"]["email"] == "aya@example.com"  # stored in lowercase
    assert body["user"]["email_verified"] is False
    assert body["user"]["auth_provider"] == "email"
    # the access token belongs to the new user
    token = decode_access_token(body["access_token"])
    assert (token.subject_id, token.subject_type) == (body["user"]["id"], "user")


def test_password_is_stored_only_as_a_bcrypt_hash(client: TestClient, db: Session):
    response = register(client)

    assert "long-enough-1" not in response.text
    assert "password" not in response.json()["user"]
    user = db.get(User, response.json()["user"]["id"])
    assert user.password_hash != "long-enough-1"
    assert verify_password("long-enough-1", user.password_hash)


def test_an_empty_profile_is_created(client: TestClient, db: Session):
    user = db.get(User, register(client).json()["user"]["id"])

    assert user.profile is not None
    assert user.profile.skin_type is None


def test_only_the_refresh_token_hash_is_stored(client: TestClient, db: Session):
    body = register(client).json()

    stored = db.scalars(select(RefreshToken).where(RefreshToken.user_id == body["user"]["id"]))
    stored = stored.all()
    assert len(stored) == 1
    assert stored[0].token_hash == hash_token(body["refresh_token"])
    assert stored[0].token_hash != body["refresh_token"]
    assert stored[0].revoked_at is None


def test_name_is_trimmed(client: TestClient):
    assert register(client, full_name="  Aya Test  ").json()["user"]["full_name"] == "Aya Test"


def test_password_with_spaces_is_kept_as_typed(client: TestClient, db: Session):
    user_id = register(client, password="  spaced pass  ").json()["user"]["id"]
    assert verify_password("  spaced pass  ", db.get(User, user_id).password_hash)


# ---------- Duplicate email ----------


def test_same_email_in_another_case_is_refused(client: TestClient):
    register(client)
    response = register(client, email="AYA@EXAMPLE.COM")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


def test_simultaneous_sign_up_returns_409_not_500(client: TestClient, monkeypatch):
    register(client)
    # simulate the race: the "does it exist?" check misses the account created a moment earlier
    monkeypatch.setattr(user_repository, "get_by_email", lambda db, email: None)

    response = register(client)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


# ---------- Invalid input ----------


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"email": "not-an-email"}, "email"),
        ({"password": "short7!"}, "password"),  # 7 characters
        ({"password": "a" * 73}, "password"),  # over bcrypt's 72 bytes
        ({"password": "é" * 37}, "password"),  # 37 characters but 74 bytes
        ({"full_name": "   "}, "full_name"),
        ({"full_name": "x" * 151}, "full_name"),
    ],
)
def test_invalid_input_is_rejected(client: TestClient, changes, field):
    response = register(client, **changes)

    assert response.status_code == 422
    assert [d["field"] for d in response.json()["error"]["details"]] == [field]


def test_missing_fields_are_listed(client: TestClient):
    response = client.post("/auth/register", json={})

    fields = {d["field"] for d in response.json()["error"]["details"]}
    assert fields == {"full_name", "email", "password"}


def test_rejected_password_is_not_echoed(client: TestClient):
    assert "tiny123" not in register(client, password="tiny123").text
