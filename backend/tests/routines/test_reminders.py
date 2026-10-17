from datetime import time

import pytest
from fastapi.testclient import TestClient

from app.services.routine_reminder_service import build_reminder, clock

# ---------- Settings ----------


def test_default_reminders_are_8_am_and_9_pm(client: TestClient, user_headers):
    response = client.get("/me/reminders", headers=user_headers)

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "daily_forecast": True,
        "morning_time": "08:00",
        "evening_time": "21:00",
    }


def test_change_times_and_turn_off(client: TestClient, user_headers):
    body = client.patch(
        "/me/reminders",
        headers=user_headers,
        json={
            "morning_time": "07:30",
            "evening_time": "22:15:45",
            "enabled": False,
            "daily_forecast": False,
        },
    ).json()

    assert body == {
        "enabled": False,
        "daily_forecast": False,
        "morning_time": "07:30",
        "evening_time": "22:15",
    }
    assert client.get("/me/reminders", headers=user_headers).json() == body


def test_only_sent_fields_change(client: TestClient, user_headers):
    body = client.patch("/me/reminders", headers=user_headers, json={"evening_time": "20:00"})
    assert body.json() == {
        "enabled": True,
        "daily_forecast": True,
        "morning_time": "08:00",
        "evening_time": "20:00",
    }


@pytest.mark.parametrize(
    "fields",
    [
        {"morning_time": "13:00"},  # not a morning
        {"evening_time": "09:00"},  # not an evening
        {"morning_time": "25:00"},
        {"morning_time": None},
        {"enabled": None},
        {"daily_forecast": None},
        {"evening_time": "21:00+02:00"},  # time zone comes from the profile
        {"snooze": True},  # unknown field
    ],
)
def test_invalid_settings_are_rejected(client: TestClient, user_headers, fields):
    response = client.patch("/me/reminders", headers=user_headers, json=fields)
    assert response.status_code == 422


def test_reminders_require_login(client: TestClient):
    assert client.get("/me/reminders").status_code == 401


# ---------- The notification text ----------


@pytest.mark.parametrize(
    ("at", "text"),
    [(time(21, 0), "9:00 PM"), (time(8, 5), "8:05 AM"), (time(0, 30), "12:30 AM"),
     (time(12, 0), "12:00 PM")],
)  # fmt: skip
def test_clock_uses_the_12_hour_format(at, text):
    assert clock(at) == text


def test_evening_reminder_lists_the_steps_in_order():
    reminder = build_reminder("evening", ["Cleanse", "Acne Treatment", "Moisturize"], time(21, 0))

    assert reminder.title == "🌙 It's 9:00 PM"
    assert reminder.body == "Time for your evening routine: Cleanse → Acne Treatment → Moisturize."


def test_morning_reminder_has_a_sun():
    assert build_reminder("morning", ["Sunscreen"], time(8, 0)).title.startswith("☀️")


def test_no_reminder_when_nothing_is_scheduled():
    assert build_reminder("evening", [], time(21, 0)) is None
