"""Importing real clinics and pharmacies in Lebanon from OpenStreetMap.

Source: Geofabrik's free daily extract of OpenStreetMap for Lebanon (a .osm.pbf file). Chosen over
live Overpass requests after the public Overpass server answered "504 busy" repeatedly
(2026-10-14): the map is served from our own database, fast and always available.

Kept: pharmacies, hospitals, clinics and doctors (no dermatologist category: 0 places in Lebanon
are tagged with that specialty). Every place keeps its OpenStreetMap id, so each import updates
places instead of duplicating them; places that disappeared are marked inactive (not deleted, so
appointments that point to them keep working).
"""

import shutil
import urllib.request
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import osmium
from sqlalchemy import func, literal_column, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import Clinic

GEOFABRIK_LEBANON_URL = "https://download.geofabrik.de/asia/lebanon-latest.osm.pbf"

# Lebanon with a small margin: latitude 33.0-34.75, longitude 35.0-36.75
LEBANON_BOUNDS = (Decimal("33.0"), Decimal("35.0"), Decimal("34.75"), Decimal("36.75"))

# a new import must find at least this share of the places we already have, otherwise the file is
# probably broken and the import stops instead of marking real places as closed
MIN_SHARE_OF_PREVIOUS = 0.8

CATEGORY_LABELS = {"clinic": "Clinic", "doctor": "Doctor", "hospital": "Hospital",
                   "pharmacy": "Pharmacy"}  # fmt: skip


@dataclass(frozen=True)
class PlaceRecord:
    osm_id: str  # "node/123" or "way/456"
    category: str
    name: str
    address: str | None
    phone_number: str | None
    website: str | None
    opening_hours: str | None
    latitude: Decimal
    longitude: Decimal


@dataclass(frozen=True)
class ImportResult:
    found: int
    created: int
    updated: int
    deactivated: int


class ImportAborted(Exception):
    """The new data looks incomplete; nothing was changed."""


# ---------- Reading OpenStreetMap tags ----------


def category_of(tags: Mapping[str, str]) -> str | None:
    amenity, healthcare = tags.get("amenity"), tags.get("healthcare")
    if amenity == "pharmacy" or healthcare == "pharmacy":
        return "pharmacy"
    if amenity == "hospital" or healthcare == "hospital":
        return "hospital"
    if amenity == "clinic" or healthcare == "clinic":
        return "clinic"
    if amenity == "doctors" or healthcare == "doctor":
        return "doctor"
    return None


def _clip(value: str | None, length: int) -> str | None:
    value = (value or "").strip()
    return value[:length] if value else None


def name_of(tags: Mapping[str, str], category: str) -> str:
    """English name if mapped, else the local name, else a label ("Pharmacy")."""
    for key in ("name:en", "name", "name:ar"):
        if tags.get(key, "").strip():
            return tags[key].strip()[:200]
    return CATEGORY_LABELS[category]


def address_of(tags: Mapping[str, str]) -> str | None:
    if tags.get("addr:full"):
        return _clip(tags["addr:full"], 300)
    street = " ".join(p for p in (tags.get("addr:housenumber"), tags.get("addr:street")) if p)
    parts = [p for p in (street, tags.get("addr:city") or tags.get("addr:place")) if p]
    return _clip(", ".join(parts), 300)


def phone_of(tags: Mapping[str, str]) -> str | None:
    phone = tags.get("phone") or tags.get("contact:phone") or ""
    return _clip(phone.split(";")[0], 30)  # several numbers are separated by ";"


def website_of(tags: Mapping[str, str]) -> str | None:
    return _clip(tags.get("website") or tags.get("contact:website"), 500)


def opening_hours_of(tags: Mapping[str, str]) -> str | None:
    hours = (tags.get("opening_hours") or "").strip()
    return hours if 0 < len(hours) <= 255 else None  # a cut-off schedule would be wrong


def _coordinate(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def in_lebanon(latitude: Decimal, longitude: Decimal) -> bool:
    lat_min, lon_min, lat_max, lon_max = LEBANON_BOUNDS
    return lat_min <= latitude <= lat_max and lon_min <= longitude <= lon_max


def record_from(osm_id: str, tags: Mapping[str, str], lat: float, lon: float) -> PlaceRecord | None:
    """A map place from one OpenStreetMap object, or None if it is not a clinic/pharmacy in
    Lebanon."""
    category = category_of(tags)
    if category is None:
        return None
    latitude, longitude = _coordinate(lat), _coordinate(lon)
    if not in_lebanon(latitude, longitude):
        return None
    return PlaceRecord(
        osm_id=osm_id,
        category=category,
        name=name_of(tags, category),
        address=address_of(tags),
        phone_number=phone_of(tags),
        website=website_of(tags),
        opening_hours=opening_hours_of(tags),
        latitude=latitude,
        longitude=longitude,
    )


def read_places(path: Path) -> list[PlaceRecord]:
    """Every clinic and pharmacy in an OpenStreetMap file (.osm.pbf or .osm).

    Points (nodes) use their own position; outlines (ways, e.g. a hospital building) use the
    centre of their corners. Large multi-part shapes (relations) are rare here and are skipped.
    """
    records = []
    processor = (
        osmium.FileProcessor(str(path))
        .with_locations()
        .with_filter(osmium.filter.KeyFilter("amenity", "healthcare"))
    )
    for obj in processor:
        tags = dict(obj.tags)
        if obj.is_node():
            if not obj.location.valid():
                continue
            lat, lon, osm_id = obj.location.lat, obj.location.lon, f"node/{obj.id}"
        elif obj.is_way():
            points = [(n.location.lat, n.location.lon) for n in obj.nodes if n.location.valid()]
            if len(points) > 1 and points[0] == points[-1]:
                points = points[:-1]  # a closed outline repeats its first corner at the end
            if not points:
                continue
            lat = sum(p[0] for p in points) / len(points)
            lon = sum(p[1] for p in points) / len(points)
            osm_id = f"way/{obj.id}"
        else:
            continue
        record = record_from(osm_id, tags, lat, lon)
        if record is not None:
            records.append(record)
    return records


def download(url: str, destination: Path) -> Path:
    request = urllib.request.Request(url, headers={"User-Agent": "SkinCare-APP (FYP) importer"})
    with urllib.request.urlopen(request, timeout=300) as response, destination.open("wb") as out:
        shutil.copyfileobj(response, out)
    return destination


# ---------- Saving ----------


def import_places(
    db: Session, records: Iterable[PlaceRecord], now: datetime | None = None
) -> ImportResult:
    """Add new places, update known ones (by OpenStreetMap id), deactivate vanished ones.

    The caller commits. Raises ImportAborted (changing nothing) if the data looks incomplete.
    """
    now = now or datetime.now(UTC)
    records = list({r.osm_id: r for r in records}.values())  # an id appears once
    previous = db.scalar(
        select(func.count())
        .select_from(Clinic)
        .where(Clinic.source == "osm_import", Clinic.is_active)
    )
    if previous and len(records) < MIN_SHARE_OF_PREVIOUS * previous:
        raise ImportAborted(
            f"Only {len(records)} places found, but {previous} are active: the file looks "
            "incomplete, nothing was changed."
        )

    created = updated = 0
    for start in range(0, len(records), 500):
        batch = records[start : start + 500]
        rows = [
            {
                "osm_id": r.osm_id,
                "category": r.category,
                "name": r.name,
                "address": r.address,
                "phone_number": r.phone_number,
                "website": r.website,
                "opening_hours": r.opening_hours,
                "latitude": r.latitude,
                "longitude": r.longitude,
                "source": "osm_import",
                "is_active": True,
                "last_synced_at": now,
            }
            for r in batch
        ]
        statement = pg_insert(Clinic).values(rows)
        statement = statement.on_conflict_do_update(
            index_elements=["osm_id"],
            set_={
                column: statement.excluded[column]
                for column in rows[0]
                if column not in ("osm_id", "source")
            },
        ).returning(literal_column("xmax = 0"))  # PostgreSQL: true when the row was inserted
        for (inserted,) in db.execute(statement):
            if inserted:
                created += 1
            else:
                updated += 1

    seen = [r.osm_id for r in records]
    result = db.execute(
        update(Clinic)
        .where(Clinic.source == "osm_import", Clinic.is_active, Clinic.osm_id.not_in(seen))
        .values(is_active=False)
        .returning(Clinic.id)
    )
    deactivated = len(result.all())
    return ImportResult(
        found=len(records), created=created, updated=updated, deactivated=deactivated
    )
