from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models import Clinic
from app.repositories import place_repository
from app.schemas.places import (
    CATEGORIES_BY_TYPE,
    NearbyPlaceOut,
    NearbyPlacesOut,
    PlaceDetailOut,
    PlaceMarkerOut,
    PlacesInAreaOut,
    PlaceType,
)
from app.services.geo import box_around, distance_km

MAX_MARKERS = 500  # zoomed out over all of Lebanon there are ~1,300: the app asks to zoom in
NEARBY_CANDIDATES = 5000


def _invalid_bbox(reason: str) -> AppError:
    return AppError(
        422,
        "invalid_bbox",
        f"bbox must be 'south,west,north,east' in degrees: {reason}",
        details=[{"field": "bbox", "message": reason}],
    )


def parse_bbox(bbox: str) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    try:
        south, west, north, east = (Decimal(part.strip()) for part in bbox.split(","))
    except (ValueError, InvalidOperation):
        raise _invalid_bbox("four numbers separated by commas are expected") from None
    if not (-90 <= south < north <= 90):
        raise _invalid_bbox("south must be below north, both between -90 and 90")
    if not (-180 <= west < east <= 180):
        raise _invalid_bbox("west must be left of east, both between -180 and 180")
    return south, west, north, east


def _marker(place: Clinic) -> PlaceMarkerOut:
    return PlaceMarkerOut(
        id=place.id,
        name=place.name,
        category=place.category,
        latitude=float(place.latitude),
        longitude=float(place.longitude),
    )


def places_in_area(db: Session, bbox: str, place_type: PlaceType) -> PlacesInAreaOut:
    """Markers for the visible map area."""
    south, west, north, east = parse_bbox(bbox)
    places = place_repository.in_area(
        db,
        south=south,
        west=west,
        north=north,
        east=east,
        categories=CATEGORIES_BY_TYPE[place_type],
        limit=MAX_MARKERS + 1,  # one extra tells whether there are more
    )
    return PlacesInAreaOut(
        truncated=len(places) > MAX_MARKERS,
        places=[_marker(p) for p in places[:MAX_MARKERS]],
    )


def nearby_places(
    db: Session, lat: float, lon: float, place_type: PlaceType, radius_km: float, limit: int
) -> NearbyPlacesOut:
    """The closest places first, within radius_km."""
    south, west, north, east = box_around(lat, lon, radius_km)
    candidates = place_repository.in_area(
        db,
        south=Decimal(str(south)),
        west=Decimal(str(west)),
        north=Decimal(str(north)),
        east=Decimal(str(east)),
        categories=CATEGORIES_BY_TYPE[place_type],
        limit=NEARBY_CANDIDATES,
    )
    measured = [
        (distance_km(lat, lon, float(p.latitude), float(p.longitude)), p) for p in candidates
    ]
    closest = sorted((m for m in measured if m[0] <= radius_km), key=lambda m: m[0])[:limit]
    return NearbyPlacesOut(
        places=[
            NearbyPlaceOut(**_marker(p).model_dump(), distance_km=round(d, 2)) for d, p in closest
        ]
    )


def place_detail(db: Session, place_id: int) -> PlaceDetailOut:
    place = place_repository.get_active(db, place_id)
    if place is None:
        raise AppError(404, "place_not_found", "This place does not exist or has closed.")
    return PlaceDetailOut(
        id=place.id,
        name=place.name,
        category=place.category,
        address=place.address,
        phone_number=place.phone_number,
        website=place.website,
        opening_hours=place.opening_hours,
        latitude=float(place.latitude),
        longitude=float(place.longitude),
        osm_url=f"https://www.openstreetmap.org/{place.osm_id}" if place.osm_id else None,
        last_synced_at=place.last_synced_at,
    )
