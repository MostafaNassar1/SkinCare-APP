"""The appointment tracker, on the places of the sample map file (tests/places/sample.osm)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import Appointment, Clinic, User, UserProfile
from app.services.osm_import_service import import_places, read_places

SAMPLE = Path(__file__).parents[1] / "places" / "sample.osm"
BEIRUT = ZoneInfo("Asia/Beirut")


def in_days(days: float) -> str:
    """An appointment time with its time zone, as the app sends it."""
    return (datetime.now(BEIRUT) + timedelta(days=days)).replace(microsecond=0).isoformat()


@pytest.fixture
def places(db: Session) -> dict[str, Clinic]:
    import_places(db, read_places(SAMPLE))
    db.flush()
    return {c.osm_id: c for c in db.query(Clinic)}


@pytest.fixture
def hospital(places) -> Clinic:
    return places["way/100"]  # "Test Hospital", Beirut


def book(client: TestClient, headers: dict, place: Clinic, **fields):
    body = {"place_id": place.id, "appointment_at": in_days(3)} | fields
    return client.post("/me/appointments", headers=headers, json=body)


def error_code(response) -> str:
    return response.json()["error"]["code"]


# ---------- Recording an appointment ----------


def test_record_an_appointment(client: TestClient, user_headers, hospital):
    response = book(
        client, user_headers, hospital, doctor_name="  Dr. Haddad  ", notes="Bring my products"
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "scheduled"
    assert body["doctor_name"] == "Dr. Haddad"
    assert body["notes"] == "Bring my products"
    assert body["place"]["name"] == "Test Hospital"
    assert body["place"]["phone_number"] == "+961 1 440800"  # "Call to reschedule"
    assert body["place"]["is_active"] is True


def test_doctors_and_clinics_are_accepted(client: TestClient, user_headers, places):
    assert book(client, user_headers, places["node/5"]).status_code == 201  # a doctor
    assert book(client, user_headers, places["node/6"]).status_code == 201  # a clinic


def test_not_at_a_pharmacy(client: TestClient, user_headers, places):
    response = book(client, user_headers, places["node/1"])

    assert response.status_code == 422
    assert error_code(response) == "not_a_clinic"


def test_unknown_or_closed_place(client: TestClient, db: Session, user_headers, hospital):
    hospital.is_active = False
    db.flush()

    assert error_code(book(client, user_headers, hospital)) == "place_not_found"
    response = client.post(
        "/me/appointments",
        headers=user_headers,
        json={"place_id": 999_999, "appointment_at": in_days(3)},
    )
    assert response.status_code == 404


@pytest.mark.parametrize("days", [-1, 366])
def test_time_must_be_in_the_next_year(client: TestClient, user_headers, hospital, days):
    response = book(client, user_headers, hospital, appointment_at=in_days(days))
    assert error_code(response) == "invalid_appointment_time"


def test_time_without_a_time_zone_is_refused(client: TestClient, user_headers, hospital):
    response = book(client, user_headers, hospital, appointment_at="2030-01-01T16:00:00")
    assert response.status_code == 422


def test_notes_are_limited(client: TestClient, user_headers, hospital):
    assert book(client, user_headers, hospital, notes="x" * 1001).status_code == 422


# ---------- Listing ----------


def add_passed(db: Session, user: User, place: Clinic, days_ago: int) -> Appointment:
    """An appointment whose time has passed (the API itself only accepts future times)."""
    appointment = Appointment(
        user_id=user.id,
        clinic_id=place.id,
        requested_datetime=datetime.now(UTC) - timedelta(days=days_ago),
    )
    db.add(appointment)
    db.flush()
    return appointment


def test_upcoming_soonest_first_and_past_most_recent_first(
    client: TestClient, db: Session, user_headers, app_user, hospital
):
    later = book(client, user_headers, hospital, appointment_at=in_days(10)).json()["id"]
    sooner = book(client, user_headers, hospital, appointment_at=in_days(2)).json()["id"]
    cancelled = book(client, user_headers, hospital, appointment_at=in_days(5)).json()["id"]
    client.post(f"/me/appointments/{cancelled}/cancel", headers=user_headers)
    old = add_passed(db, app_user, hospital, days_ago=30).id
    recent = add_passed(db, app_user, hospital, days_ago=2).id

    upcoming = client.get("/me/appointments", headers=user_headers).json()
    past = client.get("/me/appointments", headers=user_headers, params={"when": "past"}).json()

    assert [a["id"] for a in upcoming] == [sooner, later]
    assert [a["id"] for a in past] == [cancelled, recent, old]


def test_other_users_appointments_are_invisible(
    client: TestClient, db: Session, user_headers, hospital
):
    mine = book(client, user_headers, hospital).json()["id"]
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

    assert client.get("/me/appointments", headers=other_headers).json() == []
    assert client.get(f"/me/appointments/{mine}", headers=other_headers).status_code == 404
    assert client.delete(f"/me/appointments/{mine}", headers=other_headers).status_code == 404
    assert client.get(f"/me/appointments/{mine}", headers=user_headers).status_code == 200


# ---------- Changing ----------


def test_move_the_appointment_and_change_details(client: TestClient, user_headers, hospital):
    appointment_id = book(client, user_headers, hospital, notes="old note").json()["id"]
    new_time = in_days(7)

    body = client.patch(
        f"/me/appointments/{appointment_id}",
        headers=user_headers,
        json={"appointment_at": new_time, "doctor_name": "Dr. Khoury", "notes": None},
    ).json()

    assert datetime.fromisoformat(body["appointment_at"]) == datetime.fromisoformat(new_time)
    assert body["doctor_name"] == "Dr. Khoury"
    assert body["notes"] is None


@pytest.mark.parametrize(
    "fields", [{"appointment_at": None}, {"appointment_at": "2020-01-01T10:00:00+03:00"},
               {"place_id": 1}]
)  # fmt: skip
def test_invalid_changes(client: TestClient, user_headers, hospital, fields):
    appointment_id = book(client, user_headers, hospital).json()["id"]
    url = f"/me/appointments/{appointment_id}"
    assert client.patch(url, headers=user_headers, json=fields).status_code == 422


# ---------- Completing, cancelling, deleting ----------


def test_a_future_appointment_cannot_be_marked_done(client: TestClient, user_headers, hospital):
    appointment_id = book(client, user_headers, hospital).json()["id"]

    response = client.post(f"/me/appointments/{appointment_id}/complete", headers=user_headers)

    assert response.status_code == 409
    assert error_code(response) == "appointment_not_yet"


def test_a_passed_appointment_can_be_marked_done(
    client: TestClient, db: Session, user_headers, app_user, hospital
):
    appointment_id = add_passed(db, app_user, hospital, days_ago=1).id

    response = client.post(f"/me/appointments/{appointment_id}/complete", headers=user_headers)

    assert response.json()["status"] == "completed"


def test_cancel_then_nothing_more_can_change(client: TestClient, user_headers, hospital):
    appointment_id = book(client, user_headers, hospital).json()["id"]

    cancelled = client.post(f"/me/appointments/{appointment_id}/cancel", headers=user_headers)
    again = client.post(f"/me/appointments/{appointment_id}/cancel", headers=user_headers)
    edit = client.patch(
        f"/me/appointments/{appointment_id}", headers=user_headers, json={"notes": "x"}
    )

    assert cancelled.json()["status"] == "cancelled"
    assert error_code(again) == error_code(edit) == "appointment_closed"


def test_delete_a_wrong_entry(client: TestClient, user_headers, hospital):
    appointment_id = book(client, user_headers, hospital).json()["id"]

    url = f"/me/appointments/{appointment_id}"
    assert client.delete(url, headers=user_headers).status_code == 204
    assert client.get(url, headers=user_headers).status_code == 404


# ---------- Places that close later ----------


def test_appointment_survives_its_place_closing(
    client: TestClient, db: Session, user_headers, hospital
):
    appointment_id = book(client, user_headers, hospital).json()["id"]
    hospital.is_active = False  # e.g. gone from the next OpenStreetMap import
    db.flush()

    body = client.get(f"/me/appointments/{appointment_id}", headers=user_headers).json()

    assert body["place"]["name"] == "Test Hospital"
    assert body["place"]["is_active"] is False


def test_appointments_require_login(client: TestClient):
    assert client.get("/me/appointments").status_code == 401
