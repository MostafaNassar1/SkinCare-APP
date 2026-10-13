from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import User


def get(client: TestClient, headers: dict):
    return client.get("/me/profile", headers=headers)


def patch(client: TestClient, headers: dict, **fields):
    return client.patch("/me/profile", headers=headers, json=fields)


def invalid_fields(response) -> list[str]:
    assert response.status_code == 422
    return [detail["field"] for detail in response.json()["error"]["details"]]


def years_ago(years: int, days: int = 0) -> str:
    today = date.today()
    try:
        then = today.replace(year=today.year - years)
    except ValueError:  # 29 February in a year that has none
        then = today.replace(year=today.year - years, day=28)
    return (then + timedelta(days=days)).isoformat()


# ---------- Reading ----------


def test_new_profile_has_sensible_defaults(client: TestClient, user_headers, app_user: User):
    response = get(client, user_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == app_user.id
    assert body["email"] == "user@example.com"
    assert body["timezone"] == "Asia/Beirut"
    assert body["has_password"] is True
    assert body["skin"] == {
        "skin_type": None,
        "fitzpatrick_scale": None,
        "skin_quiz_completed_at": None,
        "is_pregnant_or_breastfeeding": False,
        "skin_notes": None,
    }
    assert "password_hash" not in response.text


def test_profile_requires_login(client: TestClient):
    assert get(client, {}).status_code == 401
    assert client.patch("/me/profile", json={"full_name": "X"}).status_code == 401


def test_google_only_account_has_no_password(client: TestClient, db: Session):
    user = User(
        full_name="G",
        email="g@gmail.com",
        auth_provider="google",
        google_sub="sub-g",
        email_verified=True,
    )
    db.add(user)
    db.flush()
    headers = {"Authorization": f"Bearer {create_access_token(user.id, 'user')}"}

    body = get(client, headers).json()

    assert body["has_password"] is False
    assert body["skin"]["is_pregnant_or_breastfeeding"] is False  # profile created on demand


# ---------- Updating ----------


def test_update_every_field(client: TestClient, user_headers):
    response = patch(
        client,
        user_headers,
        full_name="  Aya Nassar  ",
        phone_number="+961 70-123456",
        date_of_birth=years_ago(22),
        gender="female",
        timezone="Europe/Paris",
        is_pregnant_or_breastfeeding=True,
        skin_notes="  Breakouts before my period.  ",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Aya Nassar"
    assert body["phone_number"] == "+961 70-123456"
    assert body["date_of_birth"] == years_ago(22)
    assert body["gender"] == "female"
    assert body["timezone"] == "Europe/Paris"
    assert body["skin"]["is_pregnant_or_breastfeeding"] is True
    assert body["skin"]["skin_notes"] == "Breakouts before my period."
    assert get(client, user_headers).json() == body  # saved


def test_only_sent_fields_change(client: TestClient, user_headers):
    patch(client, user_headers, phone_number="+96170123456", gender="male")

    body = patch(client, user_headers, full_name="New Name").json()

    assert body["full_name"] == "New Name"
    assert body["phone_number"] == "+96170123456"
    assert body["gender"] == "male"


def test_empty_update_changes_nothing(client: TestClient, user_headers):
    before = get(client, user_headers).json()
    assert patch(client, user_headers).json() == before


def test_null_clears_optional_fields(client: TestClient, user_headers):
    patch(client, user_headers, phone_number="+96170123456", gender="male", skin_notes="x")

    body = patch(client, user_headers, phone_number=None, gender=None, skin_notes=None).json()

    assert body["phone_number"] is None
    assert body["gender"] is None
    assert body["skin"]["skin_notes"] is None


def test_blank_notes_become_no_notes(client: TestClient, user_headers):
    assert patch(client, user_headers, skin_notes="   ").json()["skin"]["skin_notes"] is None


# ---------- Validation ----------


@pytest.mark.parametrize("field", ["full_name", "timezone", "is_pregnant_or_breastfeeding"])
def test_required_fields_cannot_be_cleared(client: TestClient, user_headers, field):
    response = patch(client, user_headers, **{field: None})
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("fields", "invalid"),
    [
        ({"timezone": "Mars/Olympus"}, "timezone"),
        ({"date_of_birth": (date.today() + timedelta(days=1)).isoformat()}, "date_of_birth"),
        ({"date_of_birth": "1850-01-01"}, "date_of_birth"),
        ({"phone_number": "call me"}, "phone_number"),
        ({"gender": "robot"}, "gender"),
        ({"skin_notes": "x" * 1001}, "skin_notes"),
        ({"full_name": "   "}, "full_name"),
    ],
)
def test_invalid_values_are_rejected(client: TestClient, user_headers, fields, invalid):
    assert invalid_fields(patch(client, user_headers, **fields)) == [invalid]


def test_must_be_at_least_13(client: TestClient, user_headers):
    turns_13_tomorrow = years_ago(13, days=1)
    assert invalid_fields(patch(client, user_headers, date_of_birth=turns_13_tomorrow)) == [
        "date_of_birth"
    ]
    assert patch(client, user_headers, date_of_birth=years_ago(13)).status_code == 200


def test_unknown_fields_are_rejected(client: TestClient, user_headers):
    # a typo, or an attempt to change the email or verification status through the profile
    for field in ["fulname", "email", "email_verified", "password_hash"]:
        assert patch(client, user_headers, **{field: "x"}).status_code == 422


def test_rejected_values_are_not_saved(client: TestClient, user_headers):
    patch(client, user_headers, full_name="Kept", timezone="Mars/Olympus")
    assert get(client, user_headers).json()["full_name"] == "Test User"
