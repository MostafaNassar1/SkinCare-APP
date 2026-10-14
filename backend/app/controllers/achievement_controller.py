from sqlalchemy.orm import Session

from app.models import User
from app.repositories import achievement_repository
from app.schemas.reference import AchievementOut, MyAchievementOut
from app.services import achievement_service
from app.services.local_time import user_today


def list_achievements(db: Session) -> list[AchievementOut]:
    return [AchievementOut.model_validate(a) for a in achievement_repository.list_active(db)]


def list_my_achievements(db: Session, user: User) -> list[MyAchievementOut]:
    """Every active badge, locked or unlocked for this user, with progress towards its goal."""
    earned = achievement_repository.earned_dates(db, user.id)
    stats = achievement_service.user_stats(db, user, user_today(user))
    return [
        MyAchievementOut(
            **AchievementOut.model_validate(achievement).model_dump(),
            earned=achievement.id in earned,
            earned_at=earned.get(achievement.id),
            progress=(
                achievement.criteria_value
                if achievement.id in earned
                else achievement_service.progress(achievement, stats)
            ),
        )
        for achievement in achievement_repository.list_active(db)
    ]
