from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, hash_token
from app.models import Admin, Clinic, RefreshToken
from app.scripts.create_admin import NewAdmin, create_admin
from tests.auth.conftest import EMAIL, PASSWORD, bearer, login

ADMIN_EMAIL = "boss@example.com"
ADMIN_PASSWORD = "admin-password-12"


@pytest.fixture
def admin(db: Session) -> Admin:
    return create_admin(
        db, NewAdmin(full_name="Boss Admin", email=ADMIN_EMAIL, password=ADMIN_PASSWORD)
    )


def admin_login(client: TestClient, email: str = ADMIN_EMAIL, password: str = ADMIN_PASSWORD):
    return client.post("/admin/auth/login", json={"email": email, "password": password})


# ---------- Login ----------


def test_admin_login_returns_tokens_and_the_admin(client: TestClient, admin: Admin):
    response = admin_login(client)

    assert response.status_code == 200
    body = response.json()
    assert body["admin"]["id"] == admin.id
    assert body["admin"]["role"] == "super_admin"
    assert body["admin"]["clinic_id"] is None
    assert "password_hash" not in body["admin"]
    token = decode_access_token(body["access_token"])
    assert (token.subject_id, token.subject_type) == (admin.id, "admin")


def test_admin_session_lasts_12_hours(client: TestClient, db: Session, admin: Admin):
    body = admin_login(client).json()

    stored = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(body["refresh_token"]))
    )
    assert stored.admin_id == admin.id and stored.user_id is None
    expected = datetime.now(UTC) + timedelta(hours=12)
    assert abs(stored.expires_at - expected) < timedelta(seconds=5)


def test_clinic_manager_sees_their_clinic(client: TestClient, db: Session):
    clinic = Clinic(
        name="Skin Clinic",
        latitude=Decimal("33.89"),
        longitude=Decimal("35.50"),
        source="admin_added",
    )
    db.add(clinic)
    db.flush()
    create_admin(
        db,
        NewAdmin(
            full_name="Manager",
            email="manager@example.com",
            password=ADMIN_PASSWORD,
            role="clinic_manager",
            clinic_id=clinic.id,
        ),
    )

    body = admin_login(client, email="manager@example.com").json()

    assert body["admin"]["role"] == "clinic_manager"
    assert body["admin"]["clinic_id"] == clinic.id


def test_wrong_password_and_unknown_email_get_the_same_answer(client: TestClient, admin: Admin):
    wrong_password = admin_login(client, password="wrong-password-12")
    unknown_email = admin_login(client, email="nobody@example.com")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.json()["error"]["code"] == "invalid_credentials"


def test_disabled_admin_cannot_log_in(client: TestClient, db: Session, admin: Admin):
    admin.is_active = False
    db.flush()

    response = admin_login(client)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_disabled"


# ---------- Users and admins are kept apart ----------


def test_app_user_cannot_log_in_to_the_dashboard(client: TestClient, registered: dict):
    assert admin_login(client, email=EMAIL, password=PASSWORD).status_code == 401


def test_admin_cannot_log_in_to_the_mobile_app(client: TestClient, admin: Admin):
    assert login(client, email=ADMIN_EMAIL, password=ADMIN_PASSWORD).status_code == 401


def test_admin_access_token_only_opens_admin_routes(client: TestClient, admin: Admin):
    token = admin_login(client).json()["access_token"]

    assert client.get("/admin/auth/me", headers=bearer(token)).json()["email"] == ADMIN_EMAIL
    assert client.get("/auth/me", headers=bearer(token)).status_code == 401


def test_user_access_token_cannot_open_admin_routes(client: TestClient, registered: dict):
    response = client.get("/admin/auth/me", headers=bearer(registered["access_token"]))
    assert response.status_code == 401


def test_user_refresh_token_does_not_work_for_admins(client: TestClient, registered: dict):
    response = client.post(
        "/admin/auth/refresh", json={"refresh_token": registered["refresh_token"]}
    )
    assert response.status_code == 401


# ---------- Refresh and logout ----------


def test_admin_refresh_rotates_the_token(client: TestClient, admin: Admin):
    old = admin_login(client).json()["refresh_token"]

    response = client.post("/admin/auth/refresh", json={"refresh_token": old})

    assert response.status_code == 200
    assert response.json()["refresh_token"] != old
    reuse = client.post("/admin/auth/refresh", json={"refresh_token": old})
    assert reuse.json()["error"]["code"] == "invalid_refresh_token"


def test_admin_logout_ends_the_session(client: TestClient, admin: Admin):
    token = admin_login(client).json()["refresh_token"]

    assert client.post("/admin/auth/logout", json={"refresh_token": token}).status_code == 204
    after = client.post("/admin/auth/refresh", json={"refresh_token": token})
    assert after.status_code == 401
