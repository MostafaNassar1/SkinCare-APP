from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.controllers import places_controller
from app.core.dependencies import get_db, reference_cache
from app.schemas.places import NearbyPlacesOut, PlaceDetailOut, PlacesInAreaOut, PlaceType

# Public, cacheable: real OpenStreetMap data (no personal data), imported for Lebanon
router = APIRouter(prefix="/places", tags=["Map"], dependencies=[Depends(reference_cache)])

DB = Annotated[Session, Depends(get_db)]


@router.get("", response_model=PlacesInAreaOut)
def places_in_area(
    db: DB,
    bbox: Annotated[str, Query(description="south,west,north,east of the visible map area")],
    place_type: Annotated[PlaceType, Query(alias="type")] = "all",
):
    """Markers inside the visible map area (at most 500; `truncated` = zoom in for more)."""
    return places_controller.places_in_area(db, bbox, place_type)


@router.get("/nearby", response_model=NearbyPlacesOut)
def nearby_places(
    db: DB,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
    place_type: Annotated[PlaceType, Query(alias="type")] = "all",
    radius_km: Annotated[float, Query(gt=0, le=50)] = 5,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    """The nearest clinics or pharmacies, closest first, with the distance."""
    return places_controller.nearby_places(db, lat, lon, place_type, radius_km, limit)


@router.get("/{place_id}", response_model=PlaceDetailOut)
def place_detail(place_id: int, db: DB):
    """Everything known about a place: phone, website, opening hours, address."""
    return places_controller.place_detail(db, place_id)
