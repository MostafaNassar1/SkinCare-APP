from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, IntPK, check_in
from app.models.choices import ACHIEVEMENT_CRITERIA


class Achievement(Base):
    __tablename__ = "achievements"
    __table_args__ = (
        check_in("criteria_type", ACHIEVEMENT_CRITERIA),
        CheckConstraint("criteria_value > 0", name="criteria_value_check"),
    )

    id: Mapped[IntPK]
    title: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    icon_url: Mapped[str | None] = mapped_column(String(500))
    criteria_type: Mapped[str] = mapped_column(String(30))
    criteria_value: Mapped[int]
    is_active: Mapped[bool] = mapped_column(server_default=true())
    created_at: Mapped[CreatedAt]


class UserAchievement(Base):
    __tablename__ = "user_achievements"
    __table_args__ = (UniqueConstraint("user_id", "achievement_id"),)

    id: Mapped[IntPK]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    achievement_id: Mapped[int] = mapped_column(ForeignKey("achievements.id", ondelete="CASCADE"))
    earned_at: Mapped[CreatedAt]
