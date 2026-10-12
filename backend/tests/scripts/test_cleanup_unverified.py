from contextlib import nullcontext
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import EmailToken, User, UserProfile
from app.scripts import cleanup_unverified as script
from app.scripts.cleanup_unverified import cleanup


def make_user(db: Session, email: str, *, hours_old: int, verified=False, provider="email"):
    user = User(
        full_name="Someone",
        email=email,
        password_hash="hash" if provider == "email" else None,
        auth_provider=provider,
        google_sub="sub-" + email if provider == "google" else None,
        email_verified=verified,
        created_at=datetime.now(UTC) - timedelta(hours=hours_old),
        profile=UserProfile(),
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def accounts(db: Session) -> dict[str, User]:
    return {
        "old_unverified": make_user(db, "fake@il.com", hours_old=25),
        "new_unverified": make_user(db, "waiting@gmail.com", hours_old=2),
        "old_verified": make_user(db, "real@gmail.com", hours_old=500, verified=True),
        "old_google": make_user(
            db, "google@gmail.com", hours_old=500, verified=True, provider="google"
        ),
    }


def remaining_emails(db: Session) -> set[str]:
    return {email for (email,) in db.query(User.email)}


def test_only_old_never_verified_sign_ups_are_deleted(db: Session, accounts):
    deleted = cleanup(db, max_age_hours=24, dry_run=False)

    assert deleted == 1
    assert remaining_emails(db) == {"waiting@gmail.com", "real@gmail.com", "google@gmail.com"}


def test_their_profile_and_codes_go_with_them(db: Session, accounts):
    old = accounts["old_unverified"]
    db.add(
        EmailToken(
            user_id=old.id,
            purpose="email_verification",
            token_hash="x",
            expires_at=datetime.now(UTC),
        )
    )
    db.flush()

    cleanup(db, max_age_hours=24, dry_run=False)
    db.expire_all()

    assert db.query(UserProfile).filter_by(user_id=old.id).count() == 0
    assert db.query(EmailToken).filter_by(user_id=old.id).count() == 0


def test_dry_run_only_counts(db: Session, accounts):
    assert cleanup(db, max_age_hours=24, dry_run=True) == 1
    assert len(remaining_emails(db)) == 4


def test_command_line(db: Session, accounts, monkeypatch, capsys):
    # the command closes its session when done; give it the test session without closing it
    monkeypatch.setattr(script, "SessionLocal", lambda: nullcontext(db))

    assert script.main(["--dry-run"]) == 0
    assert "1 never-verified account(s) older than 24 h would be deleted" in capsys.readouterr().out

    assert script.main([]) == 0
    assert "Deleted 1 never-verified account(s)" in capsys.readouterr().out
    assert len(remaining_emails(db)) == 3
