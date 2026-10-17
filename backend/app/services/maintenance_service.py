"""Housekeeping jobs, run by the scheduler (and by their manual commands in app/scripts/)."""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.repositories import user_repository
from app.services import osm_import_service
from app.services.osm_import_service import GEOFABRIK_LEBANON_URL, ImportResult

UNVERIFIED_MAX_AGE_HOURS = 24


def cleanup_unverified(
    db: Session,
    *,
    max_age_hours: int = UNVERIFIED_MAX_AGE_HOURS,
    dry_run: bool = False,
    now: datetime | None = None,
) -> int:
    """Delete email sign-ups never verified after `max_age_hours` (nobody received their code,
    so they can never be used). Returns how many were (or, in a dry run, would be) deleted."""
    cutoff = (now or datetime.now(UTC)) - timedelta(hours=max_age_hours)
    if dry_run:
        return user_repository.count_never_verified(db, created_before=cutoff)
    deleted = user_repository.delete_never_verified(db, created_before=cutoff)
    db.commit()
    return deleted


def refresh_places(db: Session) -> ImportResult:
    """Download the latest Lebanon extract and refresh the clinics and pharmacies.

    Raises ImportAborted (nothing changed) if the file looks incomplete; the downloaded file is
    deleted afterwards.
    """
    with tempfile.TemporaryDirectory() as tmp:
        path = osm_import_service.download(GEOFABRIK_LEBANON_URL, Path(tmp) / "lebanon.osm.pbf")
        records = osm_import_service.read_places(path)
    result = osm_import_service.import_places(db, records)
    db.commit()
    return result
