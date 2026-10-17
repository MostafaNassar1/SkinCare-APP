"""The daily skin forecast: today's weather + the user's skin -> one message (rule-based, no LLM).

1. The weather becomes conditions, with fixed thresholds (below).
2. Among the active tips for today's conditions, the best one for this user is chosen:
   a tip for their skin type (skin quiz) beats a general one; then a tip about a concern found in
   their latest scan; then the tip's priority (sunscreen highest); then the oldest tip.
   Tips for another skin type are never used.
3. When UV is 3 or more and the chosen tip is not already about the sun, a sunscreen line is
   added: sun protection is the one piece of advice that is never left out.
"""

from collections.abc import Iterable

from app.models import WeatherSkinTip
from app.services.weather_service import DailyWeather

# Thresholds (decided 2026-10-17), with where they come from:
HOT_C = 30  # daily max; heat increases sebum and sweat
COLD_C = 10  # daily min
HUMID_PERCENT = 70  # mean relative humidity
DRY_PERCENT = 35  # below the 40-60% usually advised for skin comfort
HIGH_UV = 6  # WHO UV index: 6-7 "high" (protection needed even for short times outdoors)
SUNSCREEN_UV = 3  # WHO: protection is needed from 3 ("moderate")
WINDY_KMH = 30  # Beaufort 5 "fresh breeze" (29-38 km/h) and above
POLLUTED_AQI = 60  # European AQI: 60-80 "poor"

MILD_DAY = "A mild day: your usual routine is all your skin needs."


def conditions(weather: DailyWeather) -> list[str]:
    found = []
    if weather.temp_max >= HOT_C:
        found.append("hot")
    if weather.temp_min <= COLD_C:
        found.append("cold")
    if weather.humidity >= HUMID_PERCENT:
        found.append("humid")
    if weather.humidity <= DRY_PERCENT:
        found.append("dry")
    # the WHO UV index is a whole number: 5.7 is UV 6, "high" (as the message shows it)
    if round(weather.uv_index) >= HIGH_UV:
        found.append("high_uv")
    if weather.wind_max >= WINDY_KMH:
        found.append("windy")
    if weather.air_quality is not None and weather.air_quality >= POLLUTED_AQI:
        found.append("polluted")
    return found


def uv_level(uv: float) -> str:
    """The WHO words for the UV index."""
    uv = round(uv)
    if uv <= 2:
        return "low"
    if uv <= 5:
        return "moderate"
    if uv <= 7:
        return "high"
    if uv <= 10:
        return "very high"
    return "extreme"


def choose_tip(
    tips: Iterable[WeatherSkinTip],
    today: list[str],
    skin_type: str | None,
    concern_ids: set[int],
) -> WeatherSkinTip | None:
    candidates = [
        tip
        for tip in tips
        if tip.is_active
        and tip.weather_condition in today
        and tip.skin_type in (None, skin_type)
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda tip: (
            tip.skin_type is not None,  # written for this skin type
            tip.related_skin_concern_id in concern_ids,  # about a concern in the latest scan
            tip.priority,
            -tip.id,  # stable choice: the oldest tip
        ),
    )


def facts(weather: DailyWeather, today: list[str]) -> str:
    """E.g. "21-31°C, humidity 78%, UV 9 (very high), wind up to 35 km/h"."""
    parts = [
        f"{round(weather.temp_min)}-{round(weather.temp_max)}°C",
        f"humidity {round(weather.humidity)}%",
        f"UV {round(weather.uv_index)} ({uv_level(weather.uv_index)})",
    ]
    if "windy" in today:
        parts.append(f"wind up to {round(weather.wind_max)} km/h")
    if "polluted" in today:
        parts.append(f"poor air quality (AQI {weather.air_quality})")
    return ", ".join(parts)


def build_message(
    weather: DailyWeather,
    tips: Iterable[WeatherSkinTip],
    skin_type: str | None,
    concern_ids: set[int],
) -> str:
    today = conditions(weather)
    tip = choose_tip(tips, today, skin_type, concern_ids)
    lines = [f"{facts(weather, today)}.", tip.tip_text if tip else MILD_DAY]
    sun_tip_given = tip is not None and tip.weather_condition == "high_uv"
    if round(weather.uv_index) >= SUNSCREEN_UV and not sun_tip_given:
        lines.append("Don't forget sunscreen (SPF 30+) if you go out.")
    return " ".join(lines)
