from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAt, IntPK, UpdatedAt, check_in
from app.models.choices import CLINIC_SOURCES, PLACE_CATEGORIES


class Clinic(Base):
    __tablename__ = "clinics"
    __table_args__ = (
        CheckConstraint("latitude BETWEEN -90 AND 90", name="latitude_check"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="longitude_check"),
        check_in("source", CLINIC_SOURCES),
        check_in("category", PLACE_CATEGORIES),
        CheckConstraint("source <> 'osm_import' OR osm_id IS NOT NULL", name="check"),
        Index("idx_clinics_location", "latitude", "longitude"),  # nearby search
        Index("idx_clinics_category", "category"),
    )

    id: Mapped[IntPK]
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(300))
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    phone_number: Mapped[str | None] = mapped_column(String(30))
    website: Mapped[str | None] = mapped_column(String(500))
    opening_hours: Mapped[str | None] = mapped_column(String(255))  # OSM opening_hours format
    # clinic / doctor / hospital / pharmacy (migration 0006): the table holds every place on the map
    category: Mapped[str] = mapped_column(String(20), server_default="clinic")
    source: Mapped[str] = mapped_column(String(20), server_default="osm_import")
    osm_id: Mapped[str | None] = mapped_column(String(50), unique=True)  # "node/123", "way/456"
    # reserved for future partner clinics answering in-app requests (not used: no real partners)
    is_verified: Mapped[bool] = mapped_column(server_default=false())
    is_active: Mapped[bool] = mapped_column(server_default=true())
    last_synced_at: Mapped[datetime | None]  # last refresh from OSM
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    doctors: Mapped[list["Doctor"]] = relationship(
        back_populates="clinic", cascade="all, delete-orphan", passive_deletes=True
    )


class Doctor(Base):
    __tablename__ = "doctors"
    __table_args__ = (
        UniqueConstraint("id", "clinic_id"),  # target of the appointments composite FK
        Index("idx_doctors_clinic", "clinic_id"),
    )

    id: Mapped[IntPK]
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id", ondelete="CASCADE"))
    full_name: Mapped[str] = mapped_column(String(150))
    specialty: Mapped[str | None] = mapped_column(String(100))
    bio: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(server_default=true())

    clinic: Mapped[Clinic] = relationship(back_populates="doctors")
