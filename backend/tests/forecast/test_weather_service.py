"""Reading Open-Meteo's answers (the HTTP call itself is replaced)."""

from datetime import date
from decimal import Decimal

import pytest
import requests

from app.services import weather_service
from app.services.weather_service import AIR_QUALITY_URL, FORECAST_URL, WeatherUnavailable
from app.services.weather_service import _get as real_get  # before no_weather_api replaces it
from tests.forecast.conftest import air_quality_answer, forecast_answer

BEIRUT = (Decimal("33.89"), Decimal("35.50"))


def fake_api(monkeypatch, forecast, air_quality, calls: list | None = None) -> None:
    def get(url, params):
        if calls is not None:
            calls.append((url, params))
        answer = forecast if url == FORECAST_URL else air_quality
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(weather_service, "_get", get)


def test_reads_the_daily_values(monkeypatch):
    calls = []
    night_peak = [90] * 8 + [40] * 13 + [95] * 3  # very bad at night only
    fake_api(monkeypatch, forecast_answer(), air_quality_answer(night_peak), calls)

    today = weather_service.fetch_today(*BEIRUT)

    assert today.day == date(2026, 10, 17)
    assert (today.temp_max, today.temp_min, today.humidity) == (25.3, 21.6, 70.0)
    assert (today.uv_index, today.wind_max) == (5.7, 26.8)
    assert today.air_quality == 40  # daytime (08:00-20:00) maximum
    forecast_params = calls[0][1]
    assert forecast_params["latitude"] == "33.89" and forecast_params["timezone"] == "auto"


def test_air_quality_is_optional(monkeypatch):
    fake_api(monkeypatch, forecast_answer(), requests.ConnectionError("down"))

    assert weather_service.fetch_today(*BEIRUT).air_quality is None


def test_air_quality_with_gaps(monkeypatch):
    fake_api(monkeypatch, forecast_answer(), air_quality_answer([None] * 10 + [61] + [None] * 13))

    assert weather_service.fetch_today(*BEIRUT).air_quality == 61


@pytest.mark.parametrize(
    "answer",
    [
        requests.Timeout("slow"),
        requests.HTTPError("503"),
        {"error": True, "reason": "Too many requests"},
        forecast_answer(uv_index_max=[None]),
        forecast_answer(temperature_2m_max=[]),
    ],
)
def test_unusable_forecast(monkeypatch, answer):
    fake_api(monkeypatch, answer, air_quality_answer([30] * 24))

    with pytest.raises(WeatherUnavailable):
        weather_service.fetch_today(*BEIRUT)


def test_tests_never_reach_the_internet():
    with pytest.raises(AssertionError, match="weather API"):
        weather_service._get(AIR_QUALITY_URL, {})


def test_sends_a_standard_user_agent(monkeypatch):
    """Open-Meteo answered 503 to free-text User-Agents (found in a live test, 2026-10-17)."""
    sent = {}

    class Answer:
        def raise_for_status(self):
            pass

        def json(self):
            return {}

    def get(url, params, timeout, headers):
        sent.update(headers=headers, timeout=timeout)
        return Answer()

    monkeypatch.setattr(weather_service.requests, "get", get)
    real_get(FORECAST_URL, {})

    assert sent["headers"]["User-Agent"] == "SkinCare-APP/1.0 (FYP)"
    assert sent["timeout"] == 10
