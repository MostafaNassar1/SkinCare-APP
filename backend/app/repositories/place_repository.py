from collections.abc import Iterable
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Clinic


def in_area(
    db: Session,
    *,
    south: Decimal,
    west: Decimal,
    north: Decimal,
    east: Decimal,
    categories: Iterable[str],
    limit: int,
) -> list[Clinic]:
    """Active places inside a rectangle (the visible map area), at most `limit`."""
    return list(
        db.scalars(
            select(Clinic)
            .where(
                Clinic.is_active,
                Clinic.category.in_(list(categories)),
                Clinic.latitude.between(south, north),
                Clinic.longitude.between(west, east),
            )
            .order_by(Clinic.id)
            .limit(limit)
        )
    )


def get_active(db: Session, place_id: int) -> Clinic | None:
    return db.scalar(select(Clinic).where(Clinic.id == place_id, Clinic.is_active))
