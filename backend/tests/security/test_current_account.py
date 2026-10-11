"""get_current_user / get_current_admin, tested through a small test-only app."""

from collections.abc import Generator
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentAdmin, CurrentUser, get_db
from app.core.security import create_access_token
from app.models import Admin, User

# A separate app with one route per dependency, so no test-only routes are added to the real app
protected_app = FastAPI()


@protected_app.get("/user-only")
def user_only(user: CurrentUser):
    return {"id": user.id}


@protected_app.get("/admin-only")
def admin_only(admin: CurrentAdmin):
    return {"id": admin.id}


@pytest.fixture
def api(db: Session) -> Generator[TestClient, None, None]:
    protected_app.dependency_overrides[get_db] = lambda: db
    with TestClient(protected_app) as test_client:
        yield test_client
    protected_app.dependency_overrides.clear()


@pytest.fixture
def user(db: Session) -> User:
    user = User(full_name="Test User", email="user@example.com", password_hash="hash")
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def admin(db: Session) -> Admin:
    admin = Admin(full_name="Test Admin", email="admin@example.com", password_hash="hash")
    db.add(admin)
    db.flush()
    return admin


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------- Valid tokens ----------


def test_user_token_gives_access_to_user_route(api: TestClient, user: User):
    response = api.get("/user-only", headers=bearer(create_access_token(user.id, "user")))

    assert response.status_code == 200
    assert response.json() == {"id": user.id}


def test_admin_token_gives_access_to_admin_route(api: TestClient, admin: Admin):
    response = api.get("/admin-only", headers=bearer(create_access_token(admin.id, "admin")))

    assert response.status_code == 200
    assert response.json() == {"id": admin.id}


# ---------- Rejected with 401 ----------


@pytest.mark.parametrize("path", ["/user-only", "/admin-only"])
def test_missing_token_is_rejected(api: TestClient, path: str):
    response = api.get(path)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_garbage_token_is_rejected(api: TestClient):
    assert api.get("/user-only", headers=bearer("not-a-jwt")).status_code == 401


def test_non_bearer_scheme_is_rejected(api: TestClient, user: User):
    token = create_access_token(user.id, "user")
    response = api.get("/user-only", headers={"Authorization": f"Basic {token}"})

    assert response.status_code == 401


def test_expired_token_is_rejected(api: TestClient, user: User):
    token = create_access_token(user.id, "user", expires_delta=timedelta(seconds=-1))
    assert api.get("/user-only", headers=bearer(token)).status_code == 401


def test_user_token_cannot_open_admin_route(api: TestClient, user: User, admin: Admin):
    # even when an admin with the same id exists
    token = create_access_token(admin.id, "user")
    assert api.get("/admin-only", headers=bearer(token)).status_code == 401


def test_admin_token_cannot_open_user_route(api: TestClient, admin: Admin):
    token = create_access_token(admin.id, "admin")
    assert api.get("/user-only", headers=bearer(token)).status_code == 401


def test_token_of_deleted_account_is_rejected(api: TestClient, db: Session, user: User):
    token = create_access_token(user.id, "user")
    db.delete(user)
    db.flush()

    assert api.get("/user-only", headers=bearer(token)).status_code == 401


# ---------- Rejected with 403 ----------


def test_disabled_user_is_forbidden(api: TestClient, db: Session, user: User):
    user.is_active = False
    db.flush()

    response = api.get("/user-only", headers=bearer(create_access_token(user.id, "user")))

    assert response.status_code == 403
    assert response.json()["detail"] == "Account is disabled"


def test_disabled_admin_is_forbidden(api: TestClient, db: Session, admin: Admin):
    admin.is_active = False
    db.flush()

    response = api.get("/admin-only", headers=bearer(create_access_token(admin.id, "admin")))

    assert response.status_code == 403
