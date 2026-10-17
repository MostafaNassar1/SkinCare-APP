"""The daily skin forecast: sent at 11:00 user-local, personal, once a day, and shown on a card."""

import logging
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import (
    Notification,
    ScanResult,
    ScanResultConcern,
    SkinConcern,
    User,
    UserDevice,
    UserProfile,
)
from app.services import weather_service
from app.services.scheduler_service import run_due
from app.services.weather_service import ATTRIBUTION, WeatherUnavailable
from tests.forecast.conftest import weather

BEIRUT = ZoneInfo("Asia/Beirut")
BEIRUT_PLACE = (Decimal("33.89"), Decimal("35.50"))


def at(hour: int, minute: int = 0, day: int = 19) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=BEIRUT)


@pytest.fixture
def located_user(db: Session, app_user: User) -> User:
    app_user.last_latitude, app_user.last_longitude = BEIRUT_PLACE
    db.flush()
    return app_user


@pytest.fixture
def api(monkeypatch) -> list:
    """Replaces Open-Meteo with a humid day; the list records each requested place."""
    calls = []

    def fetch_today(latitude, longitude):
        calls.append((latitude, longitude))
        return weather(humidity=80, uv_index=4)

    monkeypatch.setattr(weather_service, "fetch_today", fetch_today)
    return calls


def forecasts(db: Session, user: User) -> list[Notification]:
    return db.query(Notification).filter_by(user_id=user.id, type="weather_alert").all()


# ---------- When ----------


@pytest.mark.parametrize(
    ("hour", "minute", "sent"),
    [(10, 59, 0), (11, 0, 1), (12, 59, 1), (13, 0, 0)],  # 11:00, retried until 13:00
)
def test_sent_at_11_local_time(db, located_user, api, hour, minute, sent):
    assert run_due(db, at(hour, minute)).forecasts == sent


def test_once_a_day_and_no_extra_weather_requests(db, located_user, api):
    run_due(db, at(11, 0))
    run_due(db, at(11, 5))
    run_due(db, at(11, 0, day=20))

    assert [n.dedupe_key for n in forecasts(db, located_user)] == [
        "forecast:2026-10-19",
        "forecast:2026-10-20",
    ]
    assert len(api) == 2  # the 11:05 run did not ask Open-Meteo again


def test_in_the_users_own_time_zone(db, located_user: User, api):
    located_user.timezone = "Europe/Paris"  # 11:00 in Paris = 12:00 in Beirut
    db.flush()

    assert run_due(db, at(11, 30)).forecasts == 0
    assert run_due(db, at(12, 0)).forecasts == 1


# ---------- Who ----------


def test_no_location_no_forecast(db, app_user, api):
    assert run_due(db, at(11, 0)).forecasts == 0
    assert api == []


def test_switched_off(db, located_user: User, api):
    located_user.profile.daily_forecast_enabled = False
    db.flush()

    assert run_due(db, at(11, 0)).forecasts == 0


@pytest.mark.parametrize("field", ["email_verified", "is_active"])
def test_unverified_or_disabled_accounts_get_nothing(db, located_user: User, api, field):
    setattr(located_user, field, False)
    db.flush()

    assert run_due(db, at(11, 0)).forecasts == 0


def test_neighbours_share_one_weather_request(db: Session, located_user, api):
    neighbour = User(
        full_name="Neighbour",
        email="neighbour@example.com",
        password_hash="x",
        email_verified=True,
        last_latitude=BEIRUT_PLACE[0],
        last_longitude=BEIRUT_PLACE[1],
        profile=UserProfile(),
    )
    db.add(neighbour)
    db.flush()

    assert run_due(db, at(11, 0)).forecasts == 2
    assert len(api) == 1


# ---------- What ----------


def test_the_message(db, located_user, api):
    run_due(db, at(11, 0))

    [forecast] = forecasts(db, located_user)
    assert forecast.title == "🌤️ Today's skin forecast"
    assert forecast.message == (
        "19-25°C, humidity 80%, UV 4 (moderate). High humidity can clog pores — a gentle double "
        "cleanse tonight is a good idea. Don't forget sunscreen (SPF 30+) if you go out."
    )


def test_personal_for_the_quiz_skin_type(db, located_user: User, api):
    located_user.profile.skin_type = "oily"
    db.flush()

    run_due(db, at(11, 0))

    assert "Humid air makes oily skin feel greasier" in forecasts(db, located_user)[0].message


def test_uses_the_latest_scan(db: Session, located_user: User, monkeypatch):
    monkeypatch.setattr(weather_service, "fetch_today", lambda lat, lon: weather(air_quality=75))
    dark_spots = db.query(SkinConcern).filter_by(name="dark_spots").one()
    db.add(
        ScanResult(
            user_id=located_user.id,
            image_url="https://example.com/scan.jpg",
            image_public_id="scan",
            model_version="test",
            concerns=[
                ScanResultConcern(
                    skin_concern_id=dark_spots.id, severity="mild", confidence_score=Decimal("0.9")
                )
            ],
        )
    )
    db.flush()

    run_due(db, at(11, 0))

    assert "deepen dark spots" in forecasts(db, located_user)[0].message


def test_weather_down_is_retried_at_the_next_run(db, located_user, monkeypatch, caplog):
    def down(latitude, longitude):
        raise WeatherUnavailable("503")

    monkeypatch.setattr(weather_service, "fetch_today", down)
    with caplog.at_level(logging.WARNING, logger="app.scheduler"):
        assert run_due(db, at(11, 0)).forecasts == 0
    assert "Weather unavailable" in caplog.text

    monkeypatch.setattr(weather_service, "fetch_today", lambda lat, lon: weather())
    assert run_due(db, at(11, 5)).forecasts == 1


def test_pushed_to_the_phone(db: Session, located_user, api, caplog):
    db.add(UserDevice(user_id=located_user.id, fcm_token="phone-" + "x" * 30, platform="ios"))
    db.flush()

    with caplog.at_level(logging.INFO, logger="app.push"):
        assert run_due(db, at(11, 0)).pushes_sent == 1
    assert "Today's skin forecast" in caplog.text


# ---------- The card: GET /me/skin-forecast ----------


def test_card_before_11(client: TestClient, user_headers, located_user):
    body = client.get("/me/skin-forecast", headers=user_headers).json()

    assert body["forecast"] is None
    assert body["enabled"] is True and body["has_location"] is True
    assert body["attribution"] == ATTRIBUTION


def test_card_shows_todays_forecast(client: TestClient, db, user_headers, located_user, monkeypatch):
    monkeypatch.setattr(weather_service, "fetch_today", lambda lat, lon: weather())
    run_due(db, datetime.now(BEIRUT).replace(hour=11, minute=0, second=0, microsecond=0))

    body = client.get("/me/skin-forecast", headers=user_headers).json()

    assert body["forecast"]["type"] == "weather_alert"
    assert "A mild day" in body["forecast"]["message"]


def test_card_tells_the_app_a_location_is_needed(client: TestClient, user_headers):
    assert client.get("/me/skin-forecast", headers=user_headers).json()["has_location"] is False


def test_card_requires_login(client: TestClient):
    assert client.get("/me/skin-forecast").status_code == 401


def test_switch_off_in_the_settings(client: TestClient, user_headers):
    client.patch("/me/reminders", headers=user_headers, json={"daily_forecast": False})

    assert client.get("/me/skin-forecast", headers=user_headers).json()["enabled"] is False


# ---------- GET /weather-tips (public reference list) ----------


def test_weather_tips_list(client: TestClient):
    response = client.get("/weather-tips")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=3600"
    tips = response.json()
    assert len(tips) == 18
    assert {t["weather_condition"] for t in tips} == {
        "hot", "cold", "humid", "dry", "high_uv", "windy", "polluted",
    }  # fmt: skip
    oily_humid = next(
        t for t in tips if t["skin_type"] == "oily" and t["weather_condition"] == "humid"
    )
    assert oily_humid["related_concern"] == "oiliness"
