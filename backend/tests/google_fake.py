"""A fake "Google" for tests: signs ID tokens with our own RSA key, so the REAL google-auth
verification code can check them (signature, issuer, audience, expiry) without the internet."""

import time
from datetime import UTC, datetime, timedelta
from functools import cache

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from google.auth import crypt
from google.auth import jwt as google_jwt

CLIENT_ID = "test-client.apps.googleusercontent.com"
KEY_ID = "fake-google-key"


def make_key_and_certificate(owner: str) -> tuple[bytes, str]:
    """A new RSA private key (PEM) and a matching self-signed certificate (PEM)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, owner)])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return key_pem, certificate.public_bytes(serialization.Encoding.PEM).decode()


@cache
def _google_key_and_certificate() -> tuple[bytes, str]:
    return make_key_and_certificate("fake-google")  # generated once per test run


class FakeGoogle:
    def __init__(self) -> None:
        key_pem, certificate_pem = _google_key_and_certificate()
        self.signer = crypt.RSASigner.from_string(key_pem, KEY_ID)
        # what google-auth would download from Google: key id -> certificate
        self.certs = {KEY_ID: certificate_pem}

    def token(self, **claims) -> str:
        """A signed ID token; pass a claim as None to leave it out."""
        now = int(time.time())
        defaults = {
            "iss": "https://accounts.google.com",
            "aud": CLIENT_ID,
            "sub": "google-sub-1",
            "email": "aya@gmail.com",
            "email_verified": True,
            "name": "Aya Google",
            "iat": now,
            "exp": now + 3600,
        }
        payload = {key: value for key, value in (defaults | claims).items() if value is not None}
        return google_jwt.encode(self.signer, payload).decode()
