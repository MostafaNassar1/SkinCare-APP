"""Map endpoints, on the places of the small sample map file.

sample.osm: Mazen Pharmacy (Hamra, Beirut), an unnamed pharmacy (Beirut), a doctor (Beirut),
a hospital outline (Beirut) and Care Clinic (Tripoli, ~70 km north).
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.controllers import places_controller
from app.models import Clinic
from app.services.geo import distance_km
from app.services.osm_import_service import import_places, read_places

SAMPLE = Path(__file__).parent / "sample.osm"
BEIRUT = "33.85,35.45,33.95,35.55"
LEBANON = "33.0,35.0,34.75,36.75"
HAMRA = (33.8938, 35.4985)  # ~300 m west of Mazen Pharmacy


@pytest.fixture
def places(db: Session) -> dict[str, Clinic]:
    import_places(db, read_places(SAMPLE))
    db.flush()
    return {c.osm_id: c for c in db.query(Clinic)}


def names(body: dict) -> set[str]:
    return {p["name"] for p in body["places"]}


# ---------- Places in the visible map area ----------


def test_places_in_the_visible_area(client: TestClient, places):
    response = client.get("/places", params={"bbox": BEIRUT})

    assert response.status_code == 200
    body = response.json()
    assert names(body) == {"Mazen Pharmacy", "Pharmacy", "عيادة الدكتور", "Test Hospital"}
    assert body["truncated"] is False
    assert body["attribution"] == "© OpenStreetMap contributors"  # required by the ODbL licence
    assert set(body["places"][0]) == {"id", "name", "category", "latitude", "longitude"}


@pytest.mark.parametrize(
    ("place_type", "expected"),
    [
        ("pharmacies", {"Mazen Pharmacy", "Pharmacy"}),
        ("clinics", {"عيادة الدكتور", "Test Hospital", "Care Clinic"}),  # doctor + hospital too
    ],
)
def test_the_two_map_filters(client: TestClient, places, place_type, expected):
    body = client.get("/places", params={"bbox": LEBANON, "type": place_type}).json()
    assert names(body) == expected


def test_too_many_markers_asks_to_zoom_in(client: TestClient, places, monkeypatch):
    monkeypatch.setattr(places_controller, "MAX_MARKERS", 2)

    body = client.get("/places", params={"bbox": LEBANON}).json()

    assert len(body["places"]) == 2
    assert body["truncated"] is True


@pytest.mark.parametrize(
    "bbox",
    ["33.9,35.5,33.8", "a,b,c,d", "33.9,35.4,33.8,35.5", "33.8,35.5,33.9,35.4", "-91,0,0,1"],
)
def test_invalid_areas_are_rejected(client: TestClient, places, bbox):
    response = client.get("/places", params={"bbox": bbox})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_bbox"


def test_bbox_is_required(client: TestClient):
    assert client.get("/places").status_code == 422


# ---------- Nearest places ----------


def test_nearest_pharmacies_first_with_distance(client: TestClient, places):
    lat, lon = HAMRA
    body = client.get(
        "/places/nearby", params={"lat": lat, "lon": lon, "type": "pharmacies"}
    ).json()

    assert [p["name"] for p in body["places"]] == ["Mazen Pharmacy", "Pharmacy"]
    distances = [p["distance_km"] for p in body["places"]]
    assert distances == sorted(distances)
    assert distances[0] == pytest.approx(0.3, abs=0.05)
    assert body["attribution"]


def test_radius_excludes_far_places(client: TestClient, places):
    lat, lon = HAMRA
    nearby = client.get("/places/nearby", params={"lat": lat, "lon": lon, "radius_km": 10})
    far = client.get("/places/nearby", params={"lat": lat, "lon": lon, "radius_km": 50})

    assert "Care Clinic" not in names(nearby.json())  # Tripoli is ~70 km away
    assert "Care Clinic" not in names(far.json())
    assert len(far.json()["places"]) == 4


def test_limit(client: TestClient, places):
    lat, lon = HAMRA
    body = client.get("/places/nearby", params={"lat": lat, "lon": lon, "limit": 1}).json()
    assert len(body["places"]) == 1


@pytest.mark.parametrize(
    "params",
    [
        {"lat": 91, "lon": 35.5},
        {"lat": 33.9, "lon": 35.5, "radius_km": 0},
        {"lat": 33.9, "lon": 35.5, "radius_km": 51},
        {"lat": 33.9, "lon": 35.5, "limit": 51},
        {"lat": 33.9, "lon": 35.5, "type": "dentists"},
    ],
)
def test_invalid_nearby_queries(client: TestClient, params):
    assert client.get("/places/nearby", params=params).status_code == 422


def test_distance_formula():
    beirut, tripoli = (33.8938, 35.5018), (34.4367, 35.8497)
    assert distance_km(*beirut, *tripoli) == pytest.approx(69, abs=2)


# ---------- One place ----------


def test_place_details(client: TestClient, places):
    mazen = places["node/1"]

    body = client.get(f"/places/{mazen.id}").json()

    assert body["name"] == "Mazen Pharmacy"
    assert body["phone_number"] == "+961 1 234567"
    assert body["opening_hours"] == "Mo-Sa 08:00-22:00"
    assert body["address"] == "12 Hamra Street, Beirut"
    assert body["osm_url"] == "https://www.openstreetmap.org/node/1"
    assert (body["latitude"], body["longitude"]) == (33.8938, 35.5018)


def test_unknown_place(client: TestClient, places):
    response = client.get("/places/999999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "place_not_found"


# ---------- Closed places and caching ----------


def test_closed_places_never_appear(client: TestClient, db: Session, places):
    mazen = places["node/1"]
    mazen.is_active = False
    db.flush()
    lat, lon = HAMRA

    assert "Mazen Pharmacy" not in names(client.get("/places", params={"bbox": BEIRUT}).json())
    nearby = client.get("/places/nearby", params={"lat": lat, "lon": lon}).json()
    assert "Mazen Pharmacy" not in names(nearby)
    assert client.get(f"/places/{mazen.id}").status_code == 404


def test_map_data_is_public_and_cacheable(client: TestClient, places):
    response = client.get("/places", params={"bbox": BEIRUT})  # no login

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "public, max-age=3600"
