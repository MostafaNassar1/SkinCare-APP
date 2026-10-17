from sqlalchemy import ForeignKey, SmallInteger, String, Text, text, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IntPK, check_in
from app.models.choices import SKIN_TYPES, WEATHER_CONDITIONS
from app.models.scan import SkinConcern


class WeatherSkinTip(Base):
    """A tip of the daily skin forecast, chosen when its weather condition happens today.

    skin_type and priority were added in migration 0009: a tip for the user's own skin type wins
    over a general one (NULL = any skin type); otherwise the higher priority wins.
    """

    __tablename__ = "weather_skin_tips"
    __table_args__ = (
        check_in("weather_condition", WEATHER_CONDITIONS),
        check_in("skin_type", SKIN_TYPES),
    )

    id: Mapped[IntPK]
    weather_condition: Mapped[str] = mapped_column(String(20))
    tip_text: Mapped[str] = mapped_column(Text)
    related_skin_concern_id: Mapped[int | None] = mapped_column(
        ForeignKey("skin_concerns.id", ondelete="SET NULL")
    )
    skin_type: Mapped[str | None] = mapped_column(String(20))
    priority: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(server_default=true())

    related_skin_concern: Mapped[SkinConcern | None] = relationship()
