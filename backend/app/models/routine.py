from datetime import date

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAt, IntPK, UpdatedAt, check_in
from app.models.choices import (
    RULE_TIMES_OF_DAY,
    SEVERITIES,
    SKIN_TYPES,
    STEP_CATEGORIES,
    STEP_TIMES_OF_DAY,
)


class ConcernRecommendationMapping(Base):
    """Admin-editable rule: concern (+ severity, skin type) -> routine step.

    The rules-engine algorithm that uses these rules is described in database/seed_v2.sql.
    """

    __tablename__ = "concern_recommendation_mapping"
    __table_args__ = (
        check_in("step_category", STEP_CATEGORIES),
        check_in("time_of_day", RULE_TIMES_OF_DAY),
        check_in("min_severity", SEVERITIES),
        check_in("skin_type", SKIN_TYPES),
        CheckConstraint("days_of_week BETWEEN 1 AND 127", name="days_of_week_check"),
        Index("idx_mapping_concern", "skin_concern_id"),
    )

    id: Mapped[IntPK]
    # NULL = base step for everyone
    skin_concern_id: Mapped[int | None] = mapped_column(
        ForeignKey("skin_concerns.id", ondelete="CASCADE")
    )
    step_category: Mapped[str] = mapped_column(String(20))
    step_title: Mapped[str] = mapped_column(String(100))  # "Cleanse"
    product_type: Mapped[str] = mapped_column(String(100))  # "Gentle foaming gel cleanser"
    ingredient_id: Mapped[int | None] = mapped_column(
        ForeignKey("ingredients.id", ondelete="RESTRICT")
    )
    recommended_concentration: Mapped[str | None] = mapped_column(String(50))  # "0.5-2%"
    time_of_day: Mapped[str] = mapped_column(String(10), server_default="both")
    min_severity: Mapped[str] = mapped_column(String(10), server_default="mild")
    skin_type: Mapped[str | None] = mapped_column(String(20))  # NULL = any skin type
    # higher wins when two rules fill the same slot
    priority: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    # weekdays the step is done, copied to routine_steps (migration 0010): retinoids start
    # "2-3 nights a week" = Mon, Wed, Fri = 21; 127 = every day (see services/weekdays.py)
    days_of_week: Mapped[int] = mapped_column(SmallInteger, server_default=text("127"))
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(server_default=true())
    updated_at: Mapped[UpdatedAt]


class Routine(Base):
    __tablename__ = "routines"
    __table_args__ = (
        Index("idx_routines_user_id", "user_id"),
        # at most one active routine per user
        Index(
            "uq_routines_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[IntPK]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    scan_result_id: Mapped[int | None] = mapped_column(
        ForeignKey("scan_results.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(server_default=true())
    created_at: Mapped[CreatedAt]

    steps: Mapped[list["RoutineStep"]] = relationship(
        back_populates="routine",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="(RoutineStep.time_of_day, RoutineStep.step_order)",
    )


class RoutineStep(Base):
    """A snapshot of the generated routine (later rule edits don't change it)."""

    __tablename__ = "routine_steps"
    __table_args__ = (
        check_in("time_of_day", STEP_TIMES_OF_DAY),
        check_in("step_category", STEP_CATEGORIES),
        CheckConstraint("days_of_week BETWEEN 1 AND 127", name="days_of_week_check"),
        # a step waiting for its product has no "ready" date yet
        CheckConstraint(
            "NOT (needs_product AND product_ready_on IS NOT NULL)", name="product_ready_check"
        ),
        UniqueConstraint("routine_id", "time_of_day", "step_order"),
    )

    id: Mapped[IntPK]
    routine_id: Mapped[int] = mapped_column(ForeignKey("routines.id", ondelete="CASCADE"))
    # the rule that produced this step
    mapping_id: Mapped[int | None] = mapped_column(
        ForeignKey("concern_recommendation_mapping.id", ondelete="SET NULL")
    )
    time_of_day: Mapped[str] = mapped_column(String(10))
    step_order: Mapped[int] = mapped_column(SmallInteger)
    step_category: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    product_type: Mapped[str] = mapped_column(String(100))
    ingredient_id: Mapped[int | None] = mapped_column(
        ForeignKey("ingredients.id", ondelete="SET NULL")
    )
    recommended_concentration: Mapped[str | None] = mapped_column(String(50))
    # the weekdays this step is done (migration 0005), one bit per day: Monday = 1, Tuesday = 2,
    # Wednesday = 4 ... Sunday = 64; 127 = every day. E.g. retinol "2-3 nights a week" = Mon, Wed,
    # Fri = 21. A streak day needs every step scheduled for that day. See services/weekdays.py.
    days_of_week: Mapped[int] = mapped_column(SmallInteger, server_default=text("127"))
    # real products (migration 0010): the product the user uses for this step (NULL = their own
    # or none chosen). needs_product = the user does not have it yet: the step is left out of
    # reminders and streaks until they tap "I have it now", which sets product_ready_on to
    # their local date (days before it are not counted either). NULL = counted from the start.
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT")
    )
    needs_product: Mapped[bool] = mapped_column(server_default=false())
    product_ready_on: Mapped[date | None]

    routine: Mapped[Routine] = relationship(back_populates="steps")


class RoutineLog(Base):
    __tablename__ = "routine_logs"
    __table_args__ = (
        UniqueConstraint("routine_step_id", "user_id", "log_date"),
        Index("idx_routine_logs_user_date", "user_id", "log_date"),  # streaks
    )

    id: Mapped[IntPK]
    routine_step_id: Mapped[int] = mapped_column(
        ForeignKey("routine_steps.id", ondelete="CASCADE")
    )
    # duplicated from the routine for fast streak queries; the API must check it matches
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    log_date: Mapped[date]  # the user's local date
    completed_at: Mapped[CreatedAt]
