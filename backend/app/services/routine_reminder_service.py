"""The text of routine reminder notifications.

The scheduler (Step 11) calls this at the user's morning/evening reminder time with the steps
scheduled for that day, then sends the result as a push notification.
"""

from dataclasses import dataclass
from datetime import time

SLOT_EMOJI = {"morning": "☀️", "evening": "🌙"}


@dataclass(frozen=True)
class Reminder:
    title: str
    body: str


def clock(at: time) -> str:
    """21:00 -> "9:00 PM" (12-hour clock, no leading zero)."""
    hour = at.hour % 12 or 12
    return f"{hour}:{at.minute:02d} {'AM' if at.hour < 12 else 'PM'}"


def build_reminder(time_of_day: str, step_titles: list[str], at: time) -> Reminder | None:
    """E.g. "🌙 It's 9:00 PM" / "Time for your evening routine: Cleanse → Retinol → Moisturize."

    None when nothing is scheduled for that part of the day: no pointless notification.
    """
    if not step_titles:
        return None
    return Reminder(
        title=f"{SLOT_EMOJI[time_of_day]} It's {clock(at)}",
        body=f"Time for your {time_of_day} routine: {' → '.join(step_titles)}.",
    )
