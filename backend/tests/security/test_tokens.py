from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.core.security import (
    JWT_ALGORITHM,
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    generate_token,
    hash_token,
    refresh_token_expires_at,
)

# ---------- Access tokens ----------


def test_user_token_round_trip():
    data = decode_access_token(create_access_token(42, "user"))

    assert data.subject_id == 42
    assert data.subject_type == "user"


def test_admin_token_keeps_its_subject_type():
    assert decode_access_token(create_access_token(7, "admin")).subject_type == "admin"


def test_token_expires_after_the_configured_minutes():
    payload = jwt.decode(
        create_access_token(1, "user"), get_settings().jwt_secret, algorithms=[JWT_ALGORITHM]
    )
    assert payload["exp"] - payload["iat"] == get_settings().access_token_expire_minutes * 60


def test_expired_token_is_rejected():
    token = create_access_token(1, "user", expires_delta=timedelta(seconds=-1))
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_tampered_token_is_rejected():
    token = create_access_token(1, "user")
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}.{signature[:-4]}AAAA"
    with pytest.raises(InvalidTokenError):
        decode_access_token(tampered)


def test_token_signed_with_another_secret_is_rejected():
    now = datetime.now(UTC)
    claims = {"sub": "1", "sub_type": "admin", "iat": now, "exp": now + timedelta(minutes=5)}
    forged = jwt.encode(claims, "an-attacker-secret-that-is-long-enough!!", algorithm="HS256")
    with pytest.raises(InvalidTokenError):
        decode_access_token(forged)


def test_unsigned_alg_none_token_is_rejected():
    now = datetime.now(UTC)
    claims = {"sub": "1", "sub_type": "admin", "iat": now, "exp": now + timedelta(minutes=5)}
    unsigned = jwt.encode(claims, key=None, algorithm="none")
    with pytest.raises(InvalidTokenError):
        decode_access_token(unsigned)


@pytest.mark.parametrize(
    "claims",
    [
        {"sub": "1"},  # no subject type
        {"sub": "1", "sub_type": "superuser"},  # unknown subject type
        {"sub": "abc", "sub_type": "user"},  # id is not a number
        {"sub_type": "user"},  # no subject
    ],
)
def test_token_with_bad_claims_is_rejected(claims):
    now = datetime.now(UTC)
    token = jwt.encode(
        claims | {"iat": now, "exp": now + timedelta(minutes=5)},
        get_settings().jwt_secret,
        algorithm=JWT_ALGORITHM,
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_garbage_is_rejected():
    with pytest.raises(InvalidTokenError):
        decode_access_token("not-a-jwt")


# ---------- One-time tokens ----------


def test_generated_tokens_are_long_and_unique():
    tokens = {generate_token() for _ in range(100)}
    assert len(tokens) == 100
    assert all(len(token) >= 43 for token in tokens)  # 32 random bytes in base64


def test_token_hash_is_sha256_and_repeatable():
    token = generate_token()

    assert hash_token(token) == hash_token(token)  # same input, same hash: can be looked up
    assert len(hash_token(token)) == 64
    assert hash_token(token) != token
    assert hash_token(token) != hash_token(generate_token())


def test_user_refresh_token_lasts_the_configured_days():
    expected = datetime.now(UTC) + timedelta(days=get_settings().refresh_token_expire_days)
    assert abs(refresh_token_expires_at("user") - expected) < timedelta(seconds=5)


def test_admin_refresh_token_lasts_the_configured_hours():
    hours = get_settings().admin_refresh_token_expire_hours
    expected = datetime.now(UTC) + timedelta(hours=hours)
    assert abs(refresh_token_expires_at("admin") - expected) < timedelta(seconds=5)
