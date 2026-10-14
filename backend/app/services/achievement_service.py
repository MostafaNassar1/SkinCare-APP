"""Achievement progress and automatic awarding.

- streak_days: progress shows the CURRENT streak; the badge is awarded when the LONGEST streak
  reaches the goal (a user who already had 7 days in a row is not left out).
- routine_adherence: steps ticked in total.
- scans_completed: scans taken (Phase 3 calls award_new after a scan).
A badge, once earned, is kept forever, even if steps are unticked or the streak breaks later.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.models import Achievement, User
from app.repositories import (
    achievement_repository,
    notification_repository,
    routine_repository,
    scan_repository,
)
from app.services import streak_service


@dataclass(frozen=True)
class Stats:
    current_streak: int
    longest_streak: int
    steps_logged: int
    scans: int


def user_stats(db: Session, user: User, today: date) -> Stats:
    streak = streak_service.compute_streak(db, user, today)
    return Stats(
        current_streak=streak.current_days,
        longest_streak=streak.longest_days,
        steps_logged=routine_repository.count_logs(db, user.id),
        scans=scan_repository.count_for_user(db, user.id),
    )


def progress(achievement: Achievement, stats: Stats) -> int:
    """How far along the user is, capped at the goal (e.g. 4 for "4 / 7 days")."""
    value = {
        "streak_days": stats.current_streak,
        "routine_adherence": stats.steps_logged,
        "scans_completed": stats.scans,
    }[achievement.criteria_type]
    return min(value, achievement.criteria_value)


def is_reached(achievement: Achievement, stats: Stats) -> bool:
    value = {
        "streak_days": stats.longest_streak,
        "routine_adherence": stats.steps_logged,
        "scans_completed": stats.scans,
    }[achievement.criteria_type]
    return value >= achievement.criteria_value


def award_new(db: Session, user: User, today: date) -> list[Achievement]:
    """Award every active badge whose goal is now reached, each with a notification.

    Returns the badges earned just now (for the app's celebration pop-up). The caller commits.
    """
    stats = user_stats(db, user, today)
    already = achievement_repository.earned_dates(db, user.id)
    new = []
    for achievement in achievement_repository.list_active(db):
        if achievement.id in already or not is_reached(achievement, stats):
            continue
        if achievement_repository.award(db, user_id=user.id, achievement_id=achievement.id):
            message = f"🏆 You earned “{achievement.title}”! {achievement.description or ''}"
            notification_repository.create(
                db, user_id=user.id, type="achievement", message=message.strip()
            )
            new.append(achievement)
    return new
