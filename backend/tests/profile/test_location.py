from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User


def put(client: TestClient, headers: dict, **body):
    return client.put("/me/location", headers=headers, json=body)


def test_no_location_at_first(client: TestClient, user_headers):
    response = client.get("/me/location", headers=user_headers)

    assert response.status_code == 200
    assert response.json() == {"latitude": None, "longitude": None, "updated_at": None}


def test_location_is_stored_rounded_to_about_1_km(
    client: TestClient, db: Session, user_headers, app_user: User
):
    # a precise point in Beirut
    response = put(client, user_headers, latitude=33.893791, longitude=35.501777)

    assert response.status_code == 200
    body = response.json()
    assert (Decimal(body["latitude"]), Decimal(body["longitude"])) == (
        Decimal("33.89"),
        Decimal("35.50"),
    )
    assert body["updated_at"] is not None
    db.refresh(app_user)
    assert app_user.last_latitude == Decimal("33.89")  # the precise point is never stored
    assert app_user.last_longitude == Decimal("35.50")


def test_halves_round_up(client: TestClient, user_headers):
    body = put(client, user_headers, latitude=10.005, longitude=-20.005).json()
    assert (Decimal(body["latitude"]), Decimal(body["longitude"])) == (
        Decimal("10.01"),
        Decimal("-20.01"),
    )


def test_new_location_replaces_the_old_one(client: TestClient, user_headers):
    put(client, user_headers, latitude=33.89, longitude=35.50)
    body = put(client, user_headers, latitude=48.86, longitude=2.35).json()

    assert Decimal(body["latitude"]) == Decimal("48.86")
    assert client.get("/me/location", headers=user_headers).json() == body


@pytest.mark.parametrize(
    "body",
    [
        {"latitude": 91, "longitude": 0},
        {"latitude": 0, "longitude": -181},
        {"latitude": "north", "longitude": 0},
        {"latitude": 0},
        {"latitude": 0, "longitude": 0, "altitude": 10},  # unknown field
    ],
)
def test_invalid_locations_are_rejected(client: TestClient, user_headers, body):
    assert client.put("/me/location", headers=user_headers, json=body).status_code == 422


def test_location_requires_login(client: TestClient):
    assert client.get("/me/location").status_code == 401
    assert put(client, {}, latitude=0, longitude=0).status_code == 401
