from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from sqlalchemy import CheckConstraint, DateTime, FetchedValue, MetaData, Numeric, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, mapped_column

# The same names PostgreSQL generates by default, so the models match the tables created by
# schema_v2.sql and future migrations can refer to every constraint by a predictable name.
NAMING_CONVENTION = {
    "pk": "%(table_name)s_pkey",
    "uq": "%(table_name)s_%(column_0_N_name)s_key",
    "fk": "%(table_name)s_%(column_0_N_name)s_fkey",
    "ck": "%(table_name)s_%(constraint_name)s",
    "ix": "idx_%(table_name)s_%(column_0_N_name)s",
}


class Base(DeclarativeBase):
    """Parent class of every model; holds the shared metadata and type mapping."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    type_annotation_map = {
        datetime: DateTime(timezone=True),  # TIMESTAMPTZ everywhere
        Decimal: Numeric,
        dict[str, Any]: JSONB,
    }

    # After INSERT/UPDATE, read back the values the database fills in itself (defaults and the
    # updated_at trigger). Without this, objects would keep stale values, because sessions use
    # expire_on_commit=False.
    __mapper_args__ = {"eager_defaults": True}


# Reusable column types
IntPK = Annotated[int, mapped_column(primary_key=True)]
CreatedAt = Annotated[datetime, mapped_column(server_default=func.current_timestamp())]
# updated_at is maintained by the set_updated_at() trigger; FetchedValue tells SQLAlchemy the
# database changes it on UPDATE, so the new value is read back instead of being written by Python
UpdatedAt = Annotated[
    datetime,
    mapped_column(server_default=func.current_timestamp(), server_onupdate=FetchedValue()),
]


def check_in(column: str, values: Iterable[str]) -> CheckConstraint:
    """CHECK (column IN (...)) named like PostgreSQL's default: <table>_<column>_check."""
    allowed = ", ".join(f"'{value}'" for value in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=f"{column}_check")
