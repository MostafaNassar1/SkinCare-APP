from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ScanResult, ScanResultConcern, SkinConcern, User


def add_scan(db: Session, user: User, **concerns: str) -> ScanResult:
    """A scan result as the face scan will store it (Step 5): concern name -> severity."""
    result = ScanResult(user_id=user.id, image_url="https://example.com/x.jpg",
                        image_public_id="x", model_version="test")  # fmt: skip
    db.add(result)
    db.flush()
    for name, severity in concerns.items():
        concern_id = db.scalar(select(SkinConcern.id).where(SkinConcern.name == name))
        db.add(ScanResultConcern(scan_result_id=result.id, skin_concern_id=concern_id,
                                 severity=severity, confidence_score=0.9))  # fmt: skip
    db.flush()
    return result
