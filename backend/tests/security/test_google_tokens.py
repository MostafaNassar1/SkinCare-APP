"""Google ID token verification, run through the real google-auth code with a fake Google key."""

import time

import pytest
from google.auth import exceptions as google_exceptions
from google.oauth2 import id_token

from app.core.config import get_settings
from app.services.google_auth_service import (
    GoogleSignInUnavailable,
    InvalidGoogleToken,
    verify_id_token,
)
from tests.google_fake import KEY_ID, FakeGoogle, make_key_and_certificate


def test_valid_token_gives_the_identity(fake_google: FakeGoogle):
    identity = verify_id_token(fake_google.token(email="Aya@Gmail.com"))

    assert identity.sub == "google-sub-1"
    assert identity.email == "aya@gmail.com"
    assert identity.email_verified is True
    assert identity.name == "Aya Google"


def test_name_falls_back_to_the_email(fake_google: FakeGoogle):
    assert verify_id_token(fake_google.token(name=None)).name == "aya"


def test_unverified_google_email_is_reported(fake_google: FakeGoogle):
    assert verify_id_token(fake_google.token(email_verified=False)).email_verified is False


# ---------- Rejected tokens ----------


@pytest.mark.parametrize(
    "claims",
    [
        {"aud": "another-app.apps.googleusercontent.com"},  # issued for someone else's app
        {"iss": "https://evil.example.com"},  # not issued by Google
        {"exp": int(time.time()) - 60, "iat": int(time.time()) - 3660},  # expired
        {"email": None},  # no email
        {"sub": None},  # no user id
    ],
)
def test_bad_tokens_are_rejected(fake_google: FakeGoogle, claims):
    with pytest.raises(InvalidGoogleToken):
        verify_id_token(fake_google.token(**claims))


def test_token_signed_by_another_key_is_rejected(fake_google: FakeGoogle, monkeypatch):
    token = fake_google.token()
    # Google's published key no longer matches the one that signed the token
    other_key = {KEY_ID: make_key_and_certificate("attacker")[1]}
    monkeypatch.setattr(id_token, "_fetch_certs", lambda request, url: other_key)

    with pytest.raises(InvalidGoogleToken):
        verify_id_token(token)


def test_tampered_token_is_rejected(fake_google: FakeGoogle):
    header, payload, signature = fake_google.token().split(".")
    with pytest.raises(InvalidGoogleToken):
        verify_id_token(f"{header}.{payload}.{signature[:-4]}AAAA")


def test_garbage_is_rejected(fake_google: FakeGoogle):
    with pytest.raises(InvalidGoogleToken):
        verify_id_token("not-a-token")


# ---------- Not available ----------


def test_without_client_ids_google_sign_in_is_refused(fake_google: FakeGoogle, monkeypatch):
    # never fall back to "accept tokens issued for any app"
    monkeypatch.setattr(get_settings(), "google_client_ids", [])

    with pytest.raises(GoogleSignInUnavailable):
        verify_id_token(fake_google.token())


def test_google_unreachable_is_reported(fake_google: FakeGoogle, monkeypatch):
    def offline(request, url):
        raise google_exceptions.TransportError("no internet")

    monkeypatch.setattr(id_token, "_fetch_certs", offline)

    with pytest.raises(GoogleSignInUnavailable):
        verify_id_token(fake_google.token())

