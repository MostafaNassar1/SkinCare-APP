from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import WeatherSkinTip


def list_active(db: Session) -> list[WeatherSkinTip]:
    """Every active tip with its related concern (18 rows: loaded once per scheduler run)."""
    return list(
        db.scalars(
            select(WeatherSkinTip)
            .where(WeatherSkinTip.is_active)
            .options(selectinload(WeatherSkinTip.related_skin_concern))
            .order_by(WeatherSkinTip.weather_condition, WeatherSkinTip.id)
        )
    )
