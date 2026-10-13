from sqlalchemy.orm import Session

from app.models import User
from app.repositories import achievement_repository
from app.schemas.reference import AchievementOut, MyAchievementOut


def list_achievements(db: Session) -> list[AchievementOut]:
    return [AchievementOut.model_validate(a) for a in achievement_repository.list_active(db)]


def list_my_achievements(db: Session, user: User) -> list[MyAchievementOut]:
    """Every active badge, locked or unlocked for this user (progress comes with Step 9)."""
    earned = achievement_repository.earned_dates(db, user.id)
    return [
        MyAchievementOut(
            **AchievementOut.model_validate(achievement).model_dump(),
            earned=achievement.id in earned,
            earned_at=earned.get(achievement.id),
        )
        for achievement in achievement_repository.list_active(db)
    ]
