"""Weather samples for the forecast tests (no internet: see no_weather_api in tests/conftest.py)."""

from datetime import date

from app.services.weather_service import DailyWeather


def weather(**changes) -> DailyWeather:
    """A mild day in Beirut; pass changes for the condition under test."""
    values = {
        "day": date(2026, 10, 19),
        "temp_max": 25.0,
        "temp_min": 19.0,
        "humidity": 55.0,
        "uv_index": 2.0,
        "wind_max": 12.0,
        "air_quality": 30,
    } | changes
    return DailyWeather(**values)


def forecast_answer(**daily) -> dict:
    """The shape of Open-Meteo's forecast answer (as seen on 2026-10-17)."""
    values = {
        "temperature_2m_max": [25.3],
        "temperature_2m_min": [21.6],
        "uv_index_max": [5.7],
        "wind_speed_10m_max": [26.8],
        "relative_humidity_2m_mean": [70],
    } | daily
    return {"timezone": "Asia/Beirut", "daily": {"time": ["2026-10-17"], **values}}


def air_quality_answer(values: list[int | None]) -> dict:
    return {
        "hourly": {
            "time": [f"2026-10-17T{hour:02d}:00" for hour in range(24)],
            "european_aqi": values,
        }
    }
