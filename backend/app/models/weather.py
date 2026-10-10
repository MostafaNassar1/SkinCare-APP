from sqlalchemy import ForeignKey, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IntPK, check_in
from app.models.choices import WEATHER_CONDITIONS


class WeatherSkinTip(Base):
    __tablename__ = "weather_skin_tips"
    __table_args__ = (check_in("weather_condition", WEATHER_CONDITIONS),)

    id: Mapped[IntPK]
    weather_condition: Mapped[str] = mapped_column(String(20))
    tip_text: Mapped[str] = mapped_column(Text)
    related_skin_concern_id: Mapped[int | None] = mapped_column(
        ForeignKey("skin_concerns.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(server_default=true())
