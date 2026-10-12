"""Verifying Google ID tokens ("Continue with Google")."""

from dataclasses import dataclass

from google.auth import exceptions as google_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.core.config import get_settings


@dataclass(frozen=True)
class GoogleIdentity:
    """What Google vouches for about the person who signed in."""

    sub: str  # Google's permanent user id; never changes, unlike the email
    email: str
    email_verified: bool
    name: str


class GoogleSignInUnavailable(Exception):
    """Google sign-in is not configured, or Google's keys could not be downloaded."""


class InvalidGoogleToken(Exception):
    """The token is forged, expired, for another app, or not from Google."""


# reused between requests (keeps the HTTP connection to Google open)
_http = google_requests.Request()


def verify_id_token(token: str) -> GoogleIdentity:
    """Check Google's signature, the issuer, the expiry and that the token is for OUR app."""
    client_ids = get_settings().google_client_ids
    if not client_ids:
        # audience=None would make google-auth skip the audience check and accept tokens issued
        # for any app on the internet, so no client id means no Google sign-in at all
        raise GoogleSignInUnavailable("GOOGLE_CLIENT_IDS is not configured")

    try:
        claims = id_token.verify_oauth2_token(
            token, _http, audience=client_ids, clock_skew_in_seconds=10
        )
    except google_exceptions.TransportError as exc:
        raise GoogleSignInUnavailable("Could not reach Google to verify the token") from exc
    except (ValueError, google_exceptions.GoogleAuthError) as exc:
        raise InvalidGoogleToken(str(exc)) from exc

    email = str(claims.get("email", "")).lower()
    if not claims.get("sub") or not email:
        raise InvalidGoogleToken("The token has no user id or email")
    return GoogleIdentity(
        sub=str(claims["sub"]),
        email=email,
        email_verified=claims.get("email_verified") is True,
        name=str(claims.get("name") or email.split("@")[0]),
    )
