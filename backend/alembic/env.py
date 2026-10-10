from logging.config import fileConfig

from sqlalchemy import Connection, create_engine, pool

from alembic import context
from app.core.config import get_settings
from app.db.base import Base
import app.models  # noqa: F401  (registers every table on Base.metadata)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# the models, so `alembic revision --autogenerate` can compare them with the database
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Write the migration SQL to the screen instead of running it (`alembic upgrade --sql`)."""
    context.configure(
        url=get_settings().database_url.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run the migrations against a live database."""
    # Tests pass their own connection (to the test database); otherwise use the .env settings
    connection = config.attributes.get("connection")
    if connection is not None:
        do_run_migrations(connection)
        return

    engine = create_engine(get_settings().database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
