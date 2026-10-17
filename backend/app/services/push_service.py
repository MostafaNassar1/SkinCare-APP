"""Sending push notifications to the user's phones.

PUSH_BACKEND=console (now): every push is printed in the server log instead of being sent. Real
sending through Firebase Cloud Messaging (free) is added in Phase 4, when the Flutter app exists
to receive pushes (decided 2026-10-17); only this file will change then.
"""

import logging
from dataclasses import dataclass

from app.core.config import get_settings

logger = logging.getLogger("app.push")


@dataclass(frozen=True)
class Push:
    title: str
    body: str
    data: dict[str, str]  # e.g. {"notification_id": "12", "type": "reminder"} for the app


def send(device_tokens: list[str], push: Push) -> int:
    """Send to every device of a user; returns how many devices it was sent to. Never raises:
    a push is a bonus, the notification is always in the in-app inbox anyway."""
    if not device_tokens:
        return 0
    try:
        if get_settings().push_backend == "console":
            logger.info(
                "Push (console mode, not sent) to %d device(s): %s | %s | %s",
                len(device_tokens),
                push.title,
                push.body,
                push.data,
            )
        return len(device_tokens)
    except Exception:
        logger.exception("Could not send push: %s", push.title)
        return 0
