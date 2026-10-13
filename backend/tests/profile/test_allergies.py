import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import User, UserAllergy, UserProfile
from app.repositories import ingredient_repository


@pytest.fixture
def ids(db: Session) -> dict[str, int]:
    """Ingredient name -> id, from the seeded reference data."""
    return {i.name: i.id for i in ingredient_repository.list_all(db)}


def put(client: TestClient, headers: dict, ingredient_ids: list[int], notes=None):
    body = {"ingredient_ids": ingredient_ids, "other_allergies_notes": notes}
    return client.put("/me/allergies", headers=headers, json=body)


def test_no_allergies_at_first(client: TestClient, user_headers):
    response = client.get("/me/allergies", headers=user_headers)

    assert response.status_code == 200
    assert response.json() == {"ingredients": [], "other_allergies_notes": None}


def test_save_allergies_and_notes(client: TestClient, user_headers, ids):
    response = put(client, user_headers, [ids["Retinol"], ids["Salicylic Acid"]], "  Nickel  ")

    assert response.status_code == 200
    body = response.json()
    assert [i["name"] for i in body["ingredients"]] == ["Retinol", "Salicylic Acid"]
    assert body["other_allergies_notes"] == "Nickel"
    assert client.get("/me/allergies", headers=user_headers).json() == body


def test_saving_replaces_the_whole_list(client: TestClient, user_headers, ids):
    put(client, user_headers, [ids["Retinol"], ids["Salicylic Acid"]], "Nickel")

    body = put(client, user_headers, [ids["Niacinamide"]]).json()

    assert [i["name"] for i in body["ingredients"]] == ["Niacinamide"]
    assert body["other_allergies_notes"] is None


def test_empty_list_clears_all_allergies(client: TestClient, user_headers, ids):
    put(client, user_headers, [ids["Retinol"]])
    assert put(client, user_headers, []).json()["ingredients"] == []


def test_duplicates_are_merged(client: TestClient, db: Session, user_headers, app_user, ids):
    put(client, user_headers, [ids["Retinol"], ids["Retinol"]])

    assert db.query(UserAllergy).filter_by(user_id=app_user.id).count() == 1


def test_unknown_ingredient_is_rejected_and_nothing_changes(
    client: TestClient, user_headers, ids
):
    put(client, user_headers, [ids["Retinol"]])

    response = put(client, user_headers, [ids["Niacinamide"], 999_999])

    assert response.status_code == 422
    assert "999999" in response.json()["error"]["details"][0]["message"]
    saved = client.get("/me/allergies", headers=user_headers).json()["ingredients"]
    assert [i["name"] for i in saved] == ["Retinol"]


def test_allergies_are_private_to_each_user(client: TestClient, db: Session, user_headers, ids):
    other = User(
        full_name="Other",
        email="other@example.com",
        password_hash="x",
        email_verified=True,
        profile=UserProfile(),
    )
    db.add(other)
    db.flush()
    other_headers = {"Authorization": f"Bearer {create_access_token(other.id, 'user')}"}
    put(client, user_headers, [ids["Retinol"]])

    assert client.get("/me/allergies", headers=other_headers).json()["ingredients"] == []


@pytest.mark.parametrize(
    "body",
    [
        {"ingredient_ids": "Retinol"},  # not a list
        {"other_allergies_notes": "x"},  # list missing
        {"ingredient_ids": [], "other_allergies_notes": "x" * 1001},
        {"ingredient_ids": [], "user_id": 1},  # unknown field
    ],
)
def test_invalid_bodies_are_rejected(client: TestClient, user_headers, body):
    assert client.put("/me/allergies", headers=user_headers, json=body).status_code == 422


def test_allergies_require_login(client: TestClient):
    assert client.get("/me/allergies").status_code == 401
    assert client.put("/me/allergies", json={"ingredient_ids": []}).status_code == 401
