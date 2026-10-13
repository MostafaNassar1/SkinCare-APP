from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SkinConcern


def list_all(db: Session) -> list[SkinConcern]:
    # seed order: acne, oiliness, dryness, redness, dark spots, wrinkles
    return list(db.scalars(select(SkinConcern).order_by(SkinConcern.id)))
