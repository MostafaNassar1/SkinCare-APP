import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_code, verify_password
from app.models import EmailToken, User
from app.repositories import user_repository
from tests.auth.conftest import EMAIL, PASSWORD, age_codes, last_code, sign_up

# ---------- Success: an unverified account and a code ----------


def test_sign_up_sends_a_code_instead_of_logging_in(client: TestClient):
    response = sign_up(client, email="Aya@Example.com")

    assert response.status_code == 201
    assert response.json() == {
        "email": "aya@example.com",  # stored in lowercase
        "message": "We sent a 6-digit code to aya@example.com.",
        "code_expires_in": 600,
        "resend_available_in": 60,
    }
    assert "access_token" not in response.text  # no login before the email is proven


def test_account_is_created_unverified_with_an_empty_profile(client: TestClient, db: Session):
    sign_up(client)
    user = user_repository.get_by_email(db, EMAIL)

    assert user.email_verified is False
    assert user.profile is not None
    assert verify_password(PASSWORD, user.password_hash)


def test_the_code_is_emailed_to_the_user(client: TestClient, outbox):
    sign_up(client)

    assert len(outbox) == 1
    assert outbox[0].to == EMAIL
    code = last_code(outbox)
    assert code.isdigit() and len(code) == 6
    assert code in outbox[0].text and code in outbox[0].html


def test_only_an_hmac_of_the_code_is_stored(client: TestClient, db: Session, outbox):
    sign_up(client)
    user = user_repository.get_by_email(db, EMAIL)
    code = last_code(outbox)
    stored = db.query(EmailToken).filter_by(user_id=user.id).one()

    assert stored.token_hash != code
    assert stored.token_hash != hashlib.sha256(code.encode()).hexdigest()  # needs the secret
    assert stored.token_hash == hash_code(code, user_id=user.id, purpose="email_verification")
    assert stored.purpose == "email_verification"


def test_password_is_not_in_the_response(client: TestClient):
    assert PASSWORD not in sign_up(client).text


def test_name_is_trimmed(client: TestClient, db: Session):
    sign_up(client, full_name="  Aya Test  ")
    assert user_repository.get_by_email(db, EMAIL).full_name == "Aya Test"


def test_password_with_spaces_is_kept_as_typed(client: TestClient, db: Session):
    sign_up(client, password="  spaced pass  ")
    user = user_repository.get_by_email(db, EMAIL)
    assert verify_password("  spaced pass  ", user.password_hash)


# ---------- Email already used ----------


def test_verified_email_cannot_sign_up_again(client: TestClient, registered: dict):
    response = sign_up(client, email="AYA@EXAMPLE.COM")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


def test_google_account_email_cannot_sign_up_with_a_password(
    client: TestClient, google_only_user: User
):
    assert sign_up(client, email=google_only_user.email).status_code == 409


def test_unverified_email_can_be_claimed_by_signing_up_again(
    client: TestClient, db: Session, outbox, unverified: User
):
    # someone signed up with this address but never proved it; the real owner signs up again
    age_codes(db, unverified.id, seconds=120)

    response = sign_up(client, full_name="Real Owner", password="owner-password-1")

    assert response.status_code == 201
    db.refresh(unverified)
    assert unverified.full_name == "Real Owner"
    assert verify_password("owner-password-1", unverified.password_hash)
    assert len(outbox) == 2  # a fresh code was sent
    first, second = db.query(EmailToken).filter_by(user_id=unverified.id).order_by(EmailToken.id)
    assert first.used_at is not None  # the first code was retired
    assert second.used_at is None


def test_signing_up_again_too_soon_is_refused(client: TestClient, db: Session, unverified: User):
    response = sign_up(client, password="another-password-1")

    assert response.status_code == 429
    error = response.json()["error"]
    assert error["code"] == "code_recently_sent"
    assert 0 < error["details"]["retry_after"] <= 60
    assert response.headers["Retry-After"] == str(error["details"]["retry_after"])
    db.refresh(unverified)
    assert verify_password(PASSWORD, unverified.password_hash)  # nothing changed


def test_simultaneous_sign_up_returns_409_not_500(client: TestClient, monkeypatch, unverified):
    # simulate the race: the "does it exist?" check misses the account created a moment earlier
    monkeypatch.setattr(user_repository, "get_by_email", lambda db, email: None)

    response = sign_up(client)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


# ---------- Invalid input ----------


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"email": "not-an-email"}, "email"),
        ({"password": "short7!"}, "password"),  # 7 characters
        ({"password": "a" * 73}, "password"),  # over bcrypt's 72 bytes
        ({"password": "é" * 37}, "password"),  # 37 characters but 74 bytes
        ({"full_name": "   "}, "full_name"),
        ({"full_name": "x" * 151}, "full_name"),
    ],
)
def test_invalid_input_is_rejected(client: TestClient, outbox, changes, field):
    response = sign_up(client, **changes)

    assert response.status_code == 422
    assert [d["field"] for d in response.json()["error"]["details"]] == [field]
    assert outbox == []  # no email for a rejected sign-up


def test_missing_fields_are_listed(client: TestClient):
    response = client.post("/auth/register", json={})

    fields = {d["field"] for d in response.json()["error"]["details"]}
    assert fields == {"full_name", "email", "password"}


def test_rejected_password_is_not_echoed(client: TestClient):
    assert "tiny123" not in sign_up(client, password="tiny123").text
