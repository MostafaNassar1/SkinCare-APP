"""The rules: weather -> conditions -> the best tip for this user -> the message."""

import pytest
from sqlalchemy.orm import Session

from app.models import SkinConcern
from app.repositories import weather_tip_repository
from app.services.skin_forecast_service import (
    MILD_DAY,
    build_message,
    choose_tip,
    conditions,
    uv_level,
)
from tests.forecast.conftest import weather


@pytest.fixture
def tips(db: Session):
    return weather_tip_repository.list_active(db)


def concern_id(db: Session, name: str) -> int:
    return db.query(SkinConcern).filter_by(name=name).one().id


# ---------- Conditions ----------


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({}, []),
        ({"temp_max": 30}, ["hot"]),
        ({"temp_max": 29.9}, []),
        ({"temp_min": 10}, ["cold"]),
        ({"humidity": 70}, ["humid"]),
        ({"humidity": 35}, ["dry"]),
        ({"uv_index": 6}, ["high_uv"]),
        ({"uv_index": 5.4}, []),
        ({"uv_index": 5.7}, ["high_uv"]),  # shown as "UV 6 (high)", so treated as high
        ({"wind_max": 30}, ["windy"]),
        ({"air_quality": 60}, ["polluted"]),
        ({"air_quality": None}, []),  # unknown air quality is not "polluted"
        ({"temp_max": 34, "humidity": 80, "uv_index": 9}, ["hot", "humid", "high_uv"]),
    ],
)
def test_conditions(changes, expected):
    assert conditions(weather(**changes)) == expected


@pytest.mark.parametrize(
    ("uv", "level"),
    [(0, "low"), (2.4, "low"), (3, "moderate"), (6, "high"), (8, "very high"), (11, "extreme")],
)
def test_who_uv_levels(uv, level):
    assert uv_level(uv) == level


# ---------- Choosing the tip ----------


def test_a_tip_for_the_users_skin_type_wins(tips):
    chosen = choose_tip(tips, ["humid"], "oily", set())

    assert chosen.skin_type == "oily"
    assert "oily skin feel greasier" in chosen.tip_text


def test_without_a_skin_type_only_general_tips(tips):
    chosen = choose_tip(tips, ["humid"], None, set())

    assert chosen.skin_type is None
    assert "double cleanse" in chosen.tip_text


def test_tips_for_another_skin_type_are_never_used(tips):
    chosen = choose_tip(tips, ["humid"], "dry", set())  # only oily/combination + general exist

    assert chosen.skin_type is None


def test_a_concern_from_the_latest_scan_comes_next(db: Session, tips):
    chosen = choose_tip(tips, ["high_uv"], None, {concern_id(db, "dark_spots")})

    assert "darken existing spots" in chosen.tip_text


def test_then_the_priority_sunscreen_first(tips):
    chosen = choose_tip(tips, ["humid", "high_uv", "windy"], "normal", set())

    assert chosen.weather_condition == "high_uv"


def test_no_condition_no_tip(tips):
    assert choose_tip(tips, [], "oily", set()) is None


# ---------- The message ----------


def test_message_on_a_humid_sunny_day_for_oily_skin(tips):
    message = build_message(weather(humidity=78, uv_index=7.2, temp_max=29), tips, "oily", set())

    assert message.startswith("19-29°C, humidity 78%, UV 7 (high). Humid air makes oily skin")
    assert message.endswith("Don't forget sunscreen (SPF 30+) if you go out.")


def test_no_extra_sunscreen_line_when_the_tip_is_about_the_sun(tips):
    message = build_message(weather(uv_index=9), tips, None, set())

    assert "sunscreen" in message  # one of the two general high-UV tips
    assert "Don't forget sunscreen" not in message


def test_a_mild_day(tips):
    assert build_message(weather(), tips, "normal", set()) == (
        f"19-25°C, humidity 55%, UV 2 (low). {MILD_DAY}"
    )


def test_wind_and_pollution_are_mentioned(tips):
    message = build_message(weather(wind_max=41, air_quality=72), tips, None, set())

    assert "wind up to 41 km/h, poor air quality (AQI 72)." in message
