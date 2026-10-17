from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers import forecast_controller
from app.core.dependencies import CurrentUser, get_db
from app.schemas.forecast import SkinForecastOut

router = APIRouter(prefix="/me", tags=["Skin forecast"])


@router.get("/skin-forecast", response_model=SkinForecastOut)
def get_skin_forecast(user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """Today's skin forecast (weather + your skin type), made every day at 11:00 your time."""
    return forecast_controller.get_today(db, user)
