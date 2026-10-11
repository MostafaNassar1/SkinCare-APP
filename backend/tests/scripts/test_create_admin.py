import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.models import Admin
from app.scripts import create_admin as script
from app.scripts.create_admin import AdminCreationError, NewAdmin, create_admin

VALID = {"full_name": "Boss Admin", "email": "Boss@Example.com", "password": "admin-password-12"}


# ---------- create_admin() ----------


def test_creates_a_super_admin_with_a_hashed_password(db: Session):
    admin = create_admin(db, NewAdmin(**VALID))

    assert admin.role == "super_admin"
    assert admin.email == "boss@example.com"
    assert admin.clinic_id is None
    assert verify_password("admin-password-12", admin.password_hash)


def test_duplicate_email_is_refused(db: Session):
    create_admin(db, NewAdmin(**VALID))
    with pytest.raises(AdminCreationError, match="already exists"):
        create_admin(db, NewAdmin(**VALID | {"email": "BOSS@example.com"}))


def test_clinic_manager_needs_an_existing_clinic(db: Session):
    data = NewAdmin(**VALID | {"role": "clinic_manager", "clinic_id": 999_999})
    with pytest.raises(AdminCreationError, match="clinic"):
        create_admin(db, data)


# ---------- Input rules ----------


@pytest.mark.parametrize(
    "changes",
    [
        {"password": "eleven-char"},  # admins need at least 12 characters
        {"password": "a" * 73},  # over bcrypt's 72 bytes
        {"email": "not-an-email"},
        {"full_name": "  "},
        {"role": "owner"},  # unknown role
        {"role": "clinic_manager"},  # manager without a clinic
        {"role": "super_admin", "clinic_id": 1},  # clinic for a non-manager
    ],
)
def test_invalid_admin_data_is_rejected(changes):
    with pytest.raises(ValidationError):
        NewAdmin(**VALID | changes)


# ---------- Command line ----------


@pytest.fixture
def cli(db: Session, monkeypatch):
    """Run main() with typed passwords and the test session instead of a real one."""
    monkeypatch.setattr(script, "SessionLocal", lambda: db)

    def run(args: list[str], passwords: list[str]) -> int:
        answers = iter(passwords)
        monkeypatch.setattr(script.getpass, "getpass", lambda prompt: next(answers))
        return script.main(args)

    return run


def test_cli_creates_the_admin(cli, db: Session, capsys):
    code = cli(["--name", "Boss", "--email", "boss@example.com"], ["admin-password-12"] * 2)

    assert code == 0
    assert "Created super_admin" in capsys.readouterr().out
    assert db.query(Admin).filter_by(email="boss@example.com").one()


def test_cli_refuses_mismatched_passwords(cli, db: Session, capsys):
    code = cli(["--name", "Boss", "--email", "boss@example.com"], ["admin-password-12", "other"])

    assert code == 1
    assert "do not match" in capsys.readouterr().err
    assert db.query(Admin).count() == 0


def test_cli_explains_invalid_input_without_echoing_the_password(cli, capsys):
    code = cli(["--name", "Boss", "--email", "boss@example.com"], ["short-pw"] * 2)

    errors = capsys.readouterr().err
    assert code == 1
    assert "password" in errors
    assert "short-pw" not in errors
