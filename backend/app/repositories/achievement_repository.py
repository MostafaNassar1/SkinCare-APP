from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
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


def award(db: Session, *, user_id: int, achievement_id: int) -> bool:
    """Save an earned badge. Returns False if the user already had it (ON CONFLICT DO NOTHING:
    two requests reaching the goal at the same moment cannot award it twice).

    RETURNING id tells whether a row was really inserted; rowcount is not reliable here (the
    driver reports -1 for inserts sent through the ORM session).
    """
    new_id = db.scalar(
        pg_insert(UserAchievement)
        .values(user_id=user_id, achievement_id=achievement_id)
        .on_conflict_do_nothing(index_elements=["user_id", "achievement_id"])
        .returning(UserAchievement.id)
    )
    return new_id is not None
