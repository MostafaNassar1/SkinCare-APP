"""The migrations build the full schema and reference data, and the models match it."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from app.db.base import Base
from app.db.session import engine
from tests.conftest import alembic_config

# expected counts from database/seed_v2.sql (+ the 12 forecast tips of migration 0009, + 2
# concerns, 9 allergens and 3 rules of migration 0010)
SEED_COUNTS = {
    "skin_concerns": 8,
    "ingredients": 22,
    "ingredient_conflicts": 8,
    "concern_recommendation_mapping": 23,
    "achievements": 6,
    "weather_skin_tips": 18,
}


def _table_names(connection) -> set[str]:
    return set(inspect(connection).get_table_names()) - {"alembic_version"}


def test_upgrade_creates_all_tables_and_triggers():
    with engine.connect() as conn:
        assert _table_names(conn) == set(Base.metadata.tables)
        assert len(_table_names(conn)) == 30
        triggers = conn.execute(text("SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal"))
        assert triggers.scalar() == 7
        # the database is at the newest migration file, whichever that is
        head = ScriptDirectory.from_config(alembic_config(conn)).get_current_head()
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == head


def test_seed_reference_data_loaded():
    with engine.connect() as conn:
        for table, expected in SEED_COUNTS.items():
            count = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
            assert count == expected, f"{table}: expected {expected} rows, found {count}"
        base_steps = conn.execute(
            text("SELECT count(*) FROM concern_recommendation_mapping WHERE skin_concern_id IS NULL")
        )
        assert base_steps.scalar() == 3


def test_models_match_database():
    """Same check as `alembic check`: models and tables must not drift apart."""
    with engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []


def test_downgrade_to_empty_and_upgrade_again():
    with engine.begin() as conn:
        command.downgrade(alembic_config(conn), "base")
        assert _table_names(conn) == set()
        command.upgrade(alembic_config(conn), "head")
        assert len(_table_names(conn)) == 30
