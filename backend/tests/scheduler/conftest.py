"""Fixtures for scheduler tests: fixed moments in Beirut and the sample routine."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from app.models import Notification, Routine, User
from app.scripts.create_sample_routine import create_sample_routine

BEIRUT = ZoneInfo("Asia/Beirut")


def beirut(day: int, hour: int, minute: int = 0) -> datetime:
    """A moment in Beirut in October 2026, e.g. beirut(19, 21, 5) = Monday 19 October, 21:05."""
    return datetime(2026, 10, day, hour, minute, tzinfo=BEIRUT)


def saved(db: Session, user: User) -> list[Notification]:
    return db.query(Notification).filter_by(user_id=user.id).order_by(Notification.id).all()


@pytest.fixture
def routine(db: Session, app_user: User) -> Routine:
    """Mild-acne sample routine: 4 morning steps; evening Cleanse, Acne Treatment (Mon/Wed/Fri
    only), Moisturize. Reminders at the defaults, 08:00 and 21:00 (Asia/Beirut)."""
    return create_sample_routine(db, app_user)
