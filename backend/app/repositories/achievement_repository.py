from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Achievement, UserAchievement


def list_active(db: Session) -> list[Achievement]:
    """Badges currently offered (an admin can switch one off without deleting history)."""
    return list(
        db.scalars(select(Achievement).where(Achievement.is_active).order_by(Achievement.id))
    )


def earned_dates(db: Session, user_id: int) -> dict[int, datetime]:
    """achievement id -> when this user earned it."""
    rows = db.execute(
        select(UserAchievement.achievement_id, UserAchievement.earned_at).where(
            UserAchievement.user_id == user_id
        )
    )
    return {achievement_id: earned_at for achievement_id, earned_at in rows}
