"""Distances on the Earth's surface (for "nearest pharmacy")."""

from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0
KM_PER_DEGREE_LATITUDE = 111.32


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line ("as the crow flies") distance with the haversine formula."""
    d_lat, d_lon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def box_around(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """(south, west, north, east) of a square containing the circle; the database filters by
    this cheap rectangle first, then the exact distance removes the corners."""
    d_lat = radius_km / KM_PER_DEGREE_LATITUDE
    d_lon = radius_km / (KM_PER_DEGREE_LATITUDE * max(cos(radians(lat)), 0.01))
    return lat - d_lat, lon - d_lon, lat + d_lat, lon + d_lon
