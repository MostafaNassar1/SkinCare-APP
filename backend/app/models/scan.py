from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    desc,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAt, IntPK, check_in
from app.models.choices import DETECTION_METHODS, DETECTION_SOURCES, SEVERITIES


class SkinConcern(Base):
    """The AI's vocabulary: the categories the system can report."""

    __tablename__ = "skin_concerns"
    __table_args__ = (check_in("detection_method", DETECTION_METHODS),)

    id: Mapped[IntPK]
    name: Mapped[str] = mapped_column(String(50), unique=True)  # acne, oiliness, ...
    display_name: Mapped[str] = mapped_column(String(100))  # "Dark spots"
    description: Mapped[str | None] = mapped_column(Text)
    detection_method: Mapped[str] = mapped_column(String(20), server_default="photo")


class ScanResult(Base):
    __tablename__ = "scan_results"
    __table_args__ = (
        CheckConstraint(
            "overall_skin_score BETWEEN 0 AND 100", name="overall_skin_score_check"
        ),
        Index("idx_scan_results_user_time", "user_id", desc("scanned_at")),  # progress charts
    )

    id: Mapped[IntPK]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    image_url: Mapped[str] = mapped_column(String(500))  # Cloudinary URL
    image_public_id: Mapped[str] = mapped_column(String(255))  # needed to delete the image
    model_version: Mapped[str] = mapped_column(String(50))  # which trained model produced it
    overall_skin_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    raw_model_output: Mapped[dict[str, Any] | None]  # every raw prediction, for transparency
    scanned_at: Mapped[CreatedAt]

    concerns: Mapped[list["ScanResultConcern"]] = relationship(
        back_populates="scan_result", cascade="all, delete-orphan", passive_deletes=True
    )


class ScanResultConcern(Base):
    """Only concerns that passed the detection threshold (or came from the quiz)."""

    __tablename__ = "scan_result_concerns"
    __table_args__ = (
        CheckConstraint("confidence_score BETWEEN 0 AND 1", name="confidence_score_check"),
        check_in("severity", SEVERITIES),
        check_in("detection_source", DETECTION_SOURCES),
        # a confidence score is required whenever the photo model was involved
        CheckConstraint(
            "detection_source = 'questionnaire' OR confidence_score IS NOT NULL", name="check"
        ),
        UniqueConstraint("scan_result_id", "skin_concern_id"),
        Index("idx_scan_concerns_concern", "skin_concern_id"),  # analytics
    )

    id: Mapped[IntPK]
    scan_result_id: Mapped[int] = mapped_column(ForeignKey("scan_results.id", ondelete="CASCADE"))
    skin_concern_id: Mapped[int] = mapped_column(
        ForeignKey("skin_concerns.id", ondelete="RESTRICT")
    )
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    severity: Mapped[str] = mapped_column(String(10))
    detection_source: Mapped[str] = mapped_column(String(30), server_default="photo")

    scan_result: Mapped[ScanResult] = relationship(back_populates="concerns")
