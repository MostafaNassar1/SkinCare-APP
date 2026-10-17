"""The .ics writer follows RFC 5545 (what Google / Apple Calendar import)."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.services.ics_service import IcsEvent, build_calendar, duration, escape, fold

BEIRUT = ZoneInfo("Asia/Beirut")
NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


def event(**changes) -> IcsEvent:
    values = {
        "uid": "appointment-7",
        "title": "Appointment with Dr. Haddad",
        "starts_at": datetime(2026, 10, 20, 16, 0, tzinfo=BEIRUT),
        "duration": timedelta(hours=1),
    } | changes
    return IcsEvent(**values)


def unfold(text: str) -> list[str]:
    return text.replace("\r\n ", "").split("\r\n")


def test_escaping():
    assert escape("Hospital, Beirut; floor 2\nRoom 5 \\ B") == (
        "Hospital\\, Beirut\\; floor 2\\nRoom 5 \\\\ B"
    )


def test_long_lines_are_folded_at_75_bytes_without_breaking_characters():
    line = "DESCRIPTION:" + "Crème hydratante — مرطب " * 10

    pieces = fold(line)

    assert all(len(p.encode("utf-8")) <= 75 for p in pieces)
    assert all(p.startswith(" ") for p in pieces[1:])
    assert "".join([pieces[0], *(p[1:] for p in pieces[1:])]) == line


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (timedelta(hours=1), "PT1H"),
        (timedelta(minutes=30), "PT30M"),
        (timedelta(hours=2, minutes=15), "PT2H15M"),
        (timedelta(0), "PT0M"),
    ],
)
def test_durations(value, text):
    assert duration(value) == text


def test_a_calendar_file():
    text = build_calendar(
        [event(location="Rosary Sisters Hospital, Gemmayzeh", alarm_before=timedelta(hours=2))],
        name="SkinCare App",
        now=NOW,
    )

    assert text.endswith("\r\n") and "\n" not in text.replace("\r\n", "")
    lines = unfold(text)
    assert lines[:6] == [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//SkinCare-APP//Calendar 1.0//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:SkinCare App",
    ]
    assert "UID:appointment-7@skincare-app" in lines
    assert "DTSTART:20261020T130000Z" in lines  # 16:00 in Beirut = 13:00 UTC
    assert "DTSTAMP:20261017T120000Z" in lines
    assert "DURATION:PT1H" in lines
    assert "LOCATION:Rosary Sisters Hospital\\, Gemmayzeh" in lines
    assert "STATUS:CONFIRMED" in lines
    assert "TRIGGER:-PT2H" in lines
    assert lines[-2] == "END:VCALENDAR"


def test_a_cancelled_event_has_no_alarm():
    lines = unfold(
        build_calendar([event(cancelled=True, alarm_before=timedelta(hours=2))], name="x", now=NOW)
    )

    assert "STATUS:CANCELLED" in lines
    assert "BEGIN:VALARM" not in lines


def test_an_empty_calendar_is_still_valid():
    assert unfold(build_calendar([], name="x", now=NOW))[-2:] == ["END:VCALENDAR", ""]
