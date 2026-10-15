from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.choices import PLACE_CATEGORIES

# OpenStreetMap data is free under the ODbL licence, which requires this credit next to the map
OSM_ATTRIBUTION = "© OpenStreetMap contributors"

PlaceType = Literal["clinics", "pharmacies", "all"]

# the app's two map filters, as groups of OpenStreetMap categories
CATEGORIES_BY_TYPE: dict[str, tuple[str, ...]] = {
    "clinics": ("clinic", "doctor", "hospital"),
    "pharmacies": ("pharmacy",),
    "all": PLACE_CATEGORIES,
}


class PlaceMarkerOut(BaseModel):
    """Just enough to draw a marker on the map."""

    id: int
    name: str
    category: Literal[PLACE_CATEGORIES]  # clinic / doctor / hospital / pharmacy
    latitude: float
    longitude: float


class PlacesInAreaOut(BaseModel):
    attribution: str = OSM_ATTRIBUTION
    truncated: bool  # more places in this area than returned: the app asks the user to zoom in
    places: list[PlaceMarkerOut]


class NearbyPlaceOut(PlaceMarkerOut):
    distance_km: float  # straight-line distance from the given point


class NearbyPlacesOut(BaseModel):
    attribution: str = OSM_ATTRIBUTION
    places: list[NearbyPlaceOut]  # closest first


class PlaceDetailOut(BaseModel):
    id: int
    name: str
    category: Literal[PLACE_CATEGORIES]
    address: str | None
    phone_number: str | None  # the app shows "Call" only when present
    website: str | None
    opening_hours: str | None  # OpenStreetMap format, e.g. "Mo-Sa 08:00-22:00"
    latitude: float  # the app opens directions with these
    longitude: float
    osm_url: str | None  # the place on openstreetmap.org (anyone can check or correct it)
    last_synced_at: datetime | None
    attribution: str = OSM_ATTRIBUTION
