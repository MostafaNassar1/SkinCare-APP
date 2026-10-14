from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ScanResult


def count_for_user(db: Session, user_id: int) -> int:
    """Scans taken (for the "scans completed" badges); scans themselves arrive in Phase 3."""
    return db.scalar(
        select(func.count()).select_from(ScanResult).where(ScanResult.user_id == user_id)
    )
