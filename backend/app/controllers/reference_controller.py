from sqlalchemy.orm import Session

from app.repositories import skin_concern_repository, weather_tip_repository
from app.schemas.reference import SkinConcernOut, WeatherTipOut


def list_skin_concerns(db: Session) -> list[SkinConcernOut]:
    return [SkinConcernOut.model_validate(c) for c in skin_concern_repository.list_all(db)]


def list_weather_tips(db: Session) -> list[WeatherTipOut]:
    return [
        WeatherTipOut(
            id=tip.id,
            weather_condition=tip.weather_condition,
            skin_type=tip.skin_type,
            related_concern=tip.related_skin_concern.name if tip.related_skin_concern else None,
            priority=tip.priority,
            tip_text=tip.tip_text,
        )
        for tip in weather_tip_repository.list_active(db)
    ]
