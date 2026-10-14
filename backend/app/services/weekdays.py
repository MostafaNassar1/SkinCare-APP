"""Scheduled days of a routine step, stored as a 7-bit number (one bit per weekday).

Monday = 1, Tuesday = 2, Wednesday = 4, Thursday = 8, Friday = 16, Saturday = 32, Sunday = 64.
Every day = 127; Mon/Wed/Fri = 1 + 4 + 16 = 21. The API only ever shows readable names
("mon", "wed", ...); the number stays inside the backend.
"""

from collections.abc import Iterable
from datetime import date

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")  # date.weekday() order
EVERY_DAY = 0b1111111  # 127


def to_mask(days: Iterable[str]) -> int:
    """["mon", "wed", "fri"] -> 21. Raises ValueError for an unknown name or no days."""
    mask = 0
    for day in days:
        if day not in WEEKDAYS:
            raise ValueError(f"Unknown weekday {day!r}; use one of {', '.join(WEEKDAYS)}")
        mask |= 1 << WEEKDAYS.index(day)
    if mask == 0:
        raise ValueError("A step needs at least one day")
    return mask


def from_mask(mask: int) -> list[str]:
    """21 -> ["mon", "wed", "fri"] (always in weekday order)."""
    return [day for index, day in enumerate(WEEKDAYS) if mask & (1 << index)]


def is_scheduled(mask: int, on: date) -> bool:
    return bool(mask & (1 << on.weekday()))
