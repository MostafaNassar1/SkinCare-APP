"""iCalendar (.ics, RFC 5545) files, so users can add their events to Google / Apple Calendar.

Written by hand instead of with a library: the format needed here is small (one VEVENT per
event), and the rules that matter are applied below:
- lines end with CRLF and are folded at 75 bytes (a continuation line starts with a space)
- text escapes backslash, semicolon, comma and new lines
- times are written in UTC ("Z"), so every calendar app shows them in its own time zone
- each event has a stable UID, so importing the file again updates events instead of
  duplicating them
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

PRODUCT_ID = "-//SkinCare-APP//Calendar 1.0//EN"
UID_DOMAIN = "skincare-app"


@dataclass(frozen=True)
class IcsEvent:
    uid: str  # e.g. "appointment-12"; made globally unique with UID_DOMAIN
    title: str
    starts_at: datetime  # timezone-aware
    duration: timedelta
    description: str | None = None
    location: str | None = None
    cancelled: bool = False
    alarm_before: timedelta | None = None  # the phone's own reminder


def escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def fold(line: str) -> list[str]:
    """Split a content line into pieces of at most 75 bytes (UTF-8), never inside a character."""
    pieces, current, size = [], "", 0
    for char in line:
        width = len(char.encode("utf-8"))
        limit = 75 if not pieces else 74  # continuation lines start with one space
        if size + width > limit:
            pieces.append(current)
            current, size = "", 0
        current += char
        size += width
    pieces.append(current)
    return [pieces[0], *(" " + piece for piece in pieces[1:])]


def utc(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def duration(value: timedelta) -> str:
    minutes = int(value.total_seconds() // 60)
    hours, minutes = divmod(minutes, 60)
    return "PT" + (f"{hours}H" if hours else "") + (f"{minutes}M" if minutes or not hours else "")


def _event_lines(event: IcsEvent, stamp: datetime) -> list[str]:
    lines = [
        "BEGIN:VEVENT",
        f"UID:{event.uid}@{UID_DOMAIN}",
        f"DTSTAMP:{utc(stamp)}",
        f"DTSTART:{utc(event.starts_at)}",
        f"DURATION:{duration(event.duration)}",
        f"SUMMARY:{escape(event.title)}",
    ]
    if event.location:
        lines.append(f"LOCATION:{escape(event.location)}")
    if event.description:
        lines.append(f"DESCRIPTION:{escape(event.description)}")
    lines.append("STATUS:CANCELLED" if event.cancelled else "STATUS:CONFIRMED")
    if event.alarm_before and not event.cancelled:
        lines += [
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{escape(event.title)}",
            f"TRIGGER:-{duration(event.alarm_before)}",
            "END:VALARM",
        ]
    lines.append("END:VEVENT")
    return lines


def build_calendar(
    events: list[IcsEvent], *, name: str, now: datetime | None = None
) -> str:
    stamp = now or datetime.now(UTC)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODUCT_ID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape(name)}",
    ]
    for event in events:
        lines += _event_lines(event, stamp)
    lines.append("END:VCALENDAR")
    return "".join(piece + "\r\n" for line in lines for piece in fold(line))
