from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ScanResult, ScanResultConcern, SkinConcern


def count_for_user(db: Session, user_id: int) -> int:
    """Scans taken (for the "scans completed" badges); scans themselves arrive in Phase 3."""
    return db.scalar(
        select(func.count()).select_from(ScanResult).where(ScanResult.user_id == user_id)
    )


def latest_concern_ids(db: Session, user_id: int) -> set[int]:
    """The concerns found in the user's most recent scan (empty before the first scan)."""
    latest = (
        select(ScanResult.id)
        .where(ScanResult.user_id == user_id)
        .order_by(ScanResult.scanned_at.desc(), ScanResult.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    return set(
        db.scalars(
            select(ScanResultConcern.skin_concern_id).where(
                ScanResultConcern.scan_result_id == latest
            )
        )
    )


def latest_scan_concerns(db: Session, user_id: int) -> tuple[int | None, dict[str, str]]:
    """(id of the user's most recent scan, concern name -> severity); (None, {}) before any."""
    scan_id = db.scalar(
        select(ScanResult.id)
        .where(ScanResult.user_id == user_id)
        .order_by(ScanResult.scanned_at.desc(), ScanResult.id.desc())
        .limit(1)
    )
    if scan_id is None:
        return None, {}
    rows = db.execute(
        select(SkinConcern.name, ScanResultConcern.severity)
        .join(SkinConcern, SkinConcern.id == ScanResultConcern.skin_concern_id)
        .where(ScanResultConcern.scan_result_id == scan_id)
    )
    return scan_id, {name: severity for name, severity in rows}
