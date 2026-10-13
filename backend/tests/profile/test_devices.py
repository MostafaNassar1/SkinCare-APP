import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import User, UserDevice, UserProfile

TOKEN = "fcm-token_ABC:123-" + "x" * 40


@pytest.fixture
def other_user(db: Session) -> User:
    """A second user (e.g. someone else logging in on the same phone)."""
    user = User(
        full_name="Other",
        email="other@example.com",
        password_hash="x",
        email_verified=True,
        profile=UserProfile(),
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def other_headers(other_user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(other_user.id, 'user')}"}


def register(client: TestClient, headers: dict, token: str = TOKEN, platform: str = "android"):
    body = {"fcm_token": token, "platform": platform}
    return client.post("/me/devices", headers=headers, json=body)


def owners(db: Session) -> dict[str, int]:
    db.expire_all()
    return {device.fcm_token: device.user_id for device in db.query(UserDevice)}


def test_register_a_phone(client: TestClient, db: Session, user_headers, app_user: User):
    response = register(client, user_headers)

    assert response.status_code == 200
    assert response.json()["platform"] == "android"
    assert owners(db) == {TOKEN: app_user.id}


def test_registering_again_does_not_duplicate(client: TestClient, db: Session, user_headers):
    register(client, user_headers)
    register(client, user_headers, platform="ios")

    devices = db.query(UserDevice).all()
    assert len(devices) == 1
    assert devices[0].platform == "ios"


def test_a_user_can_have_several_phones(client: TestClient, db: Session, user_headers):
    register(client, user_headers, token=TOKEN)
    register(client, user_headers, token=TOKEN + "2")

    assert len(owners(db)) == 2


def test_shared_phone_moves_to_the_last_user_who_logged_in(
    client: TestClient, db: Session, user_headers, other_headers, other_user: User
):
    register(client, user_headers)
    register(client, other_headers)

    # one phone, one owner: the previous user's notifications no longer arrive there
    assert owners(db) == {TOKEN: other_user.id}


def test_logout_removes_the_phone(client: TestClient, db: Session, user_headers):
    register(client, user_headers)

    response = client.delete(f"/me/devices/{TOKEN}", headers=user_headers)

    assert response.status_code == 204
    assert owners(db) == {}


def test_cannot_remove_another_users_phone(
    client: TestClient, db: Session, user_headers, other_headers, app_user: User
):
    register(client, user_headers)

    response = client.delete(f"/me/devices/{TOKEN}", headers=other_headers)

    assert response.status_code == 204  # same answer, reveals nothing...
    assert owners(db) == {TOKEN: app_user.id}  # ...but nothing was removed


def test_removing_an_unknown_token_is_fine(client: TestClient, user_headers):
    assert client.delete("/me/devices/unknown-token", headers=user_headers).status_code == 204


@pytest.mark.parametrize(
    "body",
    [
        {"fcm_token": TOKEN, "platform": "windows"},
        {"fcm_token": "short", "platform": "android"},
        {"fcm_token": "has spaces and !" + "x" * 30, "platform": "android"},
        {"platform": "android"},
    ],
)
def test_invalid_registrations_are_rejected(client: TestClient, user_headers, body):
    assert client.post("/me/devices", headers=user_headers, json=body).status_code == 422


def test_devices_require_login(client: TestClient):
    assert register(client, {}).status_code == 401
    assert client.delete(f"/me/devices/{TOKEN}").status_code == 401
