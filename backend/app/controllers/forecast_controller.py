from sqlalchemy.orm import Session

from app.models import User
from app.repositories import notification_repository, user_repository
from app.schemas.forecast import SkinForecastOut
from app.schemas.notification import NotificationOut
from app.services.local_time import user_today
from app.services.weather_service import ATTRIBUTION


def get_today(db: Session, user: User) -> SkinForecastOut:
    """Today's card. It shows the forecast saved at 11:00 instead of asking Open-Meteo on every
    app opening: one request per place per day, and the card always matches the push."""
    today = user_today(user)
    profile = user_repository.get_or_create_profile(db, user)
    saved = notification_repository.get_by_dedupe_key(db, user.id, f"forecast:{today.isoformat()}")
    return SkinForecastOut(
        date=today,
        enabled=profile.daily_forecast_enabled,
        has_location=user.last_latitude is not None,
        forecast=NotificationOut.model_validate(saved) if saved else None,
        attribution=ATTRIBUTION,
    )
