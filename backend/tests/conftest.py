"""Shared test setup.

Tests run against a separate database (skincare_app_test by default), never the development one.
At the start of each test run it is recreated from scratch with `alembic upgrade head`, so the
migrations themselves are tested every time. Each test then runs inside a transaction that is
rolled back afterwards, so tests cannot affect each other.
"""

import os
from collections.abc import Generator
from pathlib import Path

# Must happen before anything from `app` is imported: the settings (and the app's engine) are
# created once, on first import, and must point at the test database.
TEST_DB_NAME = os.environ.get("TEST_DB_NAME", "skincare_app_test")
os.environ["DB_NAME"] = TEST_DB_NAME
# tests must not depend on the internet (DNS); the domain check has its own tests with fake answers
os.environ["EMAIL_CHECK_DELIVERABILITY"] = "false"
# fast bcrypt in tests (production default is 12, see test_passwords.py)
os.environ["BCRYPT_ROUNDS"] = "4"
# never send real emails from tests, whatever .env says (the outbox fixture also catches them)
os.environ["EMAIL_BACKEND"] = "console"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from google.oauth2 import id_token  # noqa: E402
from sqlalchemy import Connection, create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.dependencies import get_db  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import email_service  # noqa: E402
from app.services.email_service import Email  # noqa: E402
from tests.google_fake import CLIENT_ID as GOOGLE_CLIENT_ID  # noqa: E402
from tests.google_fake import FakeGoogle  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _recreate_database(name: str, *, create: bool) -> None:
    # safety net: this drops a database, so refuse anything that is not a test database
    if not name.endswith("_test"):
        raise RuntimeError(f"Refusing to drop {name!r}: test database names must end in '_test'")
    server_url = get_settings().database_url.set(database="postgres")
    admin_engine = create_engine(server_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        if create:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin_engine.dispose()


def alembic_config(connection: Connection) -> Config:
    """Alembic config that runs on the given connection (see alembic/env.py)."""
    config = Config()  # no ini file, so Alembic does not reconfigure pytest's logging
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.attributes["connection"] = connection
    return config


@pytest.fixture(scope="session", autouse=True)
def test_database() -> Generator[None, None, None]:
    """Build the test database from the migrations once per test run, drop it at the end."""
    assert get_settings().db_name == TEST_DB_NAME
    _recreate_database(TEST_DB_NAME, create=True)
    with engine.begin() as connection:
        command.upgrade(alembic_config(connection), "head")
    yield
    engine.dispose()  # close the app's pooled connections so the database can be dropped
    _recreate_database(TEST_DB_NAME, create=False)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """A session whose changes are rolled back after the test, even if the code commits."""
    connection = engine.connect()
    transaction = connection.begin()
    # commits inside the code under test only release a savepoint, the outer transaction stays
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        # same settings as the app's SessionLocal, so tests see the same behaviour
        autoflush=False,
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    """HTTP client for the API, using the rolled-back test session instead of a real one."""
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def outbox(monkeypatch) -> list[Email]:
    """Every email the code sends during a test lands here instead of being delivered."""
    sent: list[Email] = []
    monkeypatch.setattr(email_service, "_deliver", sent.append)
    return sent


@pytest.fixture
def fake_google(monkeypatch) -> FakeGoogle:
    """Google sign-in configured for the test client id, with Google's keys replaced by ours."""
    google = FakeGoogle()
    monkeypatch.setattr(id_token, "_fetch_certs", lambda request, url: google.certs)
    monkeypatch.setattr(get_settings(), "google_client_ids", [GOOGLE_CLIENT_ID])
    return google
