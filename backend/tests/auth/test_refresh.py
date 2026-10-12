from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_token
from app.models import Admin, RefreshToken, User
from app.services import token_service
from tests.auth.conftest import bearer, last_code, login, sign_up, verify


def refresh(client: TestClient, token: str):
    return client.post("/auth/refresh", json={"refresh_token": token})


def assert_rejected(response):
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_refresh_token"


# ---------- Rotation ----------


def test_refresh_returns_a_new_working_pair(client: TestClient, registered: dict):
    response = refresh(client, registered["refresh_token"])

    assert response.status_code == 200
    body = response.json()
    assert body["refresh_token"] != registered["refresh_token"]
    assert body["expires_in"] == 15 * 60
    # the new access token works, and so does the new refresh token
    assert client.get("/auth/me", headers=bearer(body["access_token"])).status_code == 200
    assert refresh(client, body["refresh_token"]).status_code == 200


def test_old_refresh_token_cannot_be_used_twice(client: TestClient, registered: dict):
    refresh(client, registered["refresh_token"])

    assert_rejected(refresh(client, registered["refresh_token"]))


def test_reuse_revokes_every_session_of_the_account(client: TestClient, registered: dict):
    phone = registered["refresh_token"]
    tablet = login(client).json()["refresh_token"]
    new_phone = refresh(client, phone).json()["refresh_token"]

    # an attacker replays the stolen, already-rotated phone token
    assert_rejected(refresh(client, phone))

    # every session of that account is now closed and needs a fresh login
    assert_rejected(refresh(client, new_phone))
    assert_rejected(refresh(client, tablet))


def test_reuse_does_not_affect_other_accounts(client: TestClient, outbox, registered: dict):
    sign_up(client, email="other@example.com")
    other = verify(client, last_code(outbox, to="other@example.com"), email="other@example.com")
    other = other.json()
    refresh(client, registered["refresh_token"])
    refresh(client, registered["refresh_token"])  # reuse on the first account

    assert refresh(client, other["refresh_token"]).status_code == 200


# ---------- Rejected tokens ----------


def test_expired_refresh_token_is_rejected(client: TestClient, db: Session, registered: dict):
    stored = db.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_token(registered["refresh_token"])
        )
    )
    stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()

    assert_rejected(refresh(client, registered["refresh_token"]))


def test_unknown_refresh_token_is_rejected(client: TestClient):
    assert_rejected(refresh(client, "made-up-token"))


def test_admin_refresh_token_does_not_work_for_users(client: TestClient, db: Session):
    admin = Admin(full_name="Admin", email="admin@example.com", password_hash="hash")
    db.add(admin)
    db.flush()
    admin_tokens = token_service.issue_token_pair(db, admin.id, "admin")

    assert_rejected(refresh(client, admin_tokens.refresh_token))


def test_disabled_account_cannot_refresh(client: TestClient, db: Session, registered: dict):
    db.get(User, registered["user"]["id"]).is_active = False
    db.flush()

    response = refresh(client, registered["refresh_token"])

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_disabled"
