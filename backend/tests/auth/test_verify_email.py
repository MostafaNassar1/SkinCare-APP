from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, hash_token
from app.models import EmailToken, RefreshToken, User
from tests.auth.conftest import (
    EMAIL,
    PASSWORD,
    age_codes,
    bearer,
    last_code,
    sign_up,
    verify,
)


def wrong(code: str) -> str:
    """A 6-digit code that is certainly not `code`."""
    return f"{(int(code) + 1) % 1_000_000:06d}"


def error_code(response) -> str:
    return response.json()["error"]["code"]


# ---------- Success ----------


def test_correct_code_verifies_and_logs_in(client: TestClient, db: Session, outbox, unverified):
    response = verify(client, last_code(outbox))

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email_verified"] is True
    assert decode_access_token(body["access_token"]).subject_id == unverified.id
    assert client.get("/auth/me", headers=bearer(body["access_token"])).status_code == 200
    stored = db.query(RefreshToken).filter_by(user_id=unverified.id).one()
    assert stored.token_hash == hash_token(body["refresh_token"])


def test_a_code_works_only_once(client: TestClient, outbox, unverified):
    code = last_code(outbox)
    verify(client, code)

    assert error_code(verify(client, code)) == "already_verified"


def test_verified_user_can_log_in(client: TestClient, registered: dict):
    response = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 200


# ---------- Wrong codes and the 5-attempt limit ----------


def test_wrong_code_shows_attempts_left(client: TestClient, outbox, unverified):
    response = verify(client, wrong(last_code(outbox)))

    assert response.status_code == 400
    assert error_code(response) == "invalid_code"
    assert response.json()["error"]["details"] == {"attempts_left": 4}


def test_code_dies_after_5_wrong_attempts(client: TestClient, db: Session, outbox, unverified):
    code = last_code(outbox)
    for attempts_left in [4, 3, 2, 1, 0]:
        response = verify(client, wrong(code))
        assert response.json()["error"]["details"] == {"attempts_left": attempts_left}

    # even the correct code is refused now: guessing 1,000,000 codes is impossible
    assert error_code(verify(client, code)) == "code_expired"
    assert db.get(User, unverified.id).email_verified is False


def test_expired_code_is_refused(client: TestClient, db: Session, outbox, unverified):
    token = db.query(EmailToken).filter_by(user_id=unverified.id).one()
    token.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()

    assert error_code(verify(client, last_code(outbox))) == "code_expired"


def test_badly_formed_code_is_a_validation_error(client: TestClient, unverified):
    for code in ["12ab56", "12345", "1234567", ""]:
        assert verify(client, code).status_code == 422


def test_another_users_code_does_not_work(client: TestClient, outbox, unverified):
    sign_up(client, email="other@example.com")
    other_code = last_code(outbox, to="other@example.com")
    if other_code == last_code(outbox):  # 1 in a million: same digits, skip the comparison
        return

    assert error_code(verify(client, other_code)) == "invalid_code"


def test_old_code_stops_working_when_a_new_one_is_sent(
    client: TestClient, db: Session, outbox, unverified
):
    old_code = last_code(outbox)
    age_codes(db, unverified.id, seconds=120)
    client.post("/auth/resend-verification", json={"email": EMAIL, "password": PASSWORD})
    new_code = last_code(outbox)
    if new_code == old_code:  # 1 in a million
        return

    assert error_code(verify(client, old_code)) == "invalid_code"
    assert verify(client, new_code).status_code == 200


# ---------- The password is required too ----------


def test_wrong_password_with_the_right_code_is_refused(client: TestClient, outbox, unverified):
    response = verify(client, last_code(outbox), password="not-the-password")

    assert response.status_code == 401
    assert error_code(response) == "invalid_credentials"


def test_attacker_who_reclaims_the_email_cannot_take_over(
    client: TestClient, db: Session, outbox, unverified
):
    # Aya signed up but has not typed her code yet. An attacker signs up again with her email
    # and their own password (allowed, since the account is unverified)...
    age_codes(db, unverified.id, seconds=120)
    sign_up(client, password="attacker-password")
    # ...Aya receives the new code in her inbox and types it with HER password:
    response = verify(client, last_code(outbox), password=PASSWORD)

    # refused, so the account is never verified with the attacker's password
    assert error_code(response) == "invalid_credentials"
    assert db.get(User, unverified.id).email_verified is False
    # the attacker cannot verify either: the code is in Aya's inbox, not theirs
