from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers import reference_controller
from app.core.dependencies import get_db, reference_cache
from app.schemas.reference import SkinConcernOut, WeatherTipOut

# public, read-only lists the app displays
router = APIRouter(tags=["Reference data"], dependencies=[Depends(reference_cache)])

DB = Annotated[Session, Depends(get_db)]


@router.get("/skin-concerns", response_model=list[SkinConcernOut])
def list_skin_concerns(db: DB):
    """The 6 visible skin concerns the app can detect (not diseases)."""
    return reference_controller.list_skin_concerns(db)


@router.get("/weather-tips", response_model=list[WeatherTipOut])
def list_weather_tips(db: DB):
    """The tips the daily skin forecast chooses from (rule-based, no AI text)."""
    return reference_controller.list_weather_tips(db)
