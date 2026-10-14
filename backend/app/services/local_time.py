"""Dates as the user lives them: "today" and "that day" in the user's own time zone.

The server never trusts a date sent by the app (history could be faked), and never uses its own
clock's date: 23:30 in Beirut is already "tomorrow" in UTC.
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.models import User


def user_zone(user: User) -> ZoneInfo:
    return ZoneInfo(user.timezone)


def user_today(user: User, now: datetime | None = None) -> date:
    """The user's current local date (`now` can be given in tests)."""
    return (now or datetime.now(UTC)).astimezone(user_zone(user)).date()


def local_date(moment: datetime, user: User) -> date:
    """The user's local date at a stored moment (e.g. when a routine was created)."""
    return moment.astimezone(user_zone(user)).date()
