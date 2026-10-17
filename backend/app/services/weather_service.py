"""Today's weather and air quality from Open-Meteo (free, no API key, decided 2026-10-12).

Two requests per place: the forecast API (temperature, humidity, UV, wind) and the air-quality API
(European AQI). Open-Meteo's free plan is for non-commercial use (an FYP is) with attribution
"Weather data by Open-Meteo.com" (CC BY 4.0); a commercial app would need their paid plan.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import requests

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"
TIMEOUT_SECONDS = 10
DAYTIME_HOURS = range(8, 21)  # air quality that matters: when people are outside
# The standard "product/version" form: Open-Meteo answered 503 to a free-text User-Agent (and to
# python-requests' default one) when tested on 2026-10-17.
USER_AGENT = "SkinCare-APP/1.0 (FYP)"

DAILY_FIELDS = {
    "temperature_2m_max": "temp_max",
    "temperature_2m_min": "temp_min",
    "relative_humidity_2m_mean": "humidity",
    "uv_index_max": "uv_index",
    "wind_speed_10m_max": "wind_max",
}


@dataclass(frozen=True)
class DailyWeather:
    day: date  # the place's local date
    temp_max: float  # °C
    temp_min: float
    humidity: float  # mean relative humidity, %
    uv_index: float  # daily maximum
    wind_max: float  # km/h
    air_quality: int | None  # highest daytime European AQI; None if that API failed


class WeatherUnavailable(Exception):
    """Open-Meteo did not answer (or answered something unusable); try again later."""


def _get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    response = requests.get(
        url,
        params=params,
        timeout=TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    return response.json()


def _air_quality(latitude: Decimal, longitude: Decimal) -> int | None:
    """Optional: without it the forecast still works, it just cannot warn about pollution."""
    try:
        data = _get(
            AIR_QUALITY_URL,
            {
                "latitude": str(latitude),
                "longitude": str(longitude),
                "hourly": "european_aqi",
                "timezone": "auto",
                "forecast_days": 1,
            },
        )
        hours = data["hourly"]["time"]
        values = data["hourly"]["european_aqi"]
        daytime = [
            v for t, v in zip(hours, values, strict=True)
            if v is not None and int(t[11:13]) in DAYTIME_HOURS
        ]
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None
    return round(max(daytime)) if daytime else None


def fetch_today(latitude: Decimal, longitude: Decimal) -> DailyWeather:
    try:
        data = _get(
            FORECAST_URL,
            {
                "latitude": str(latitude),
                "longitude": str(longitude),
                "daily": ",".join(DAILY_FIELDS),
                "timezone": "auto",  # the place's own day, from midnight to midnight
                "forecast_days": 1,
            },
        )
        daily = data["daily"]
        values = {name: daily[field][0] for field, name in DAILY_FIELDS.items()}
        day = date.fromisoformat(daily["time"][0])
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
        raise WeatherUnavailable(str(exc)) from exc
    if any(v is None for v in values.values()):
        raise WeatherUnavailable("missing values in the forecast")
    return DailyWeather(
        day=day,
        **{name: float(v) for name, v in values.items()},
        air_quality=_air_quality(latitude, longitude),
    )
