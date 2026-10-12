"""The sign-up domain check, with fake DNS answers (tests never use the internet)."""

import pytest
from email_validator import EmailUndeliverableError
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import User
from app.repositories import user_repository
from app.services import email_domain_service

SIGN_UP = {"full_name": "Aya Test", "email": "user@exasad.com", "password": "long-enough-1"}


# ---------- The service ----------


def test_domain_that_does_not_exist_cannot_receive_email(monkeypatch):
    def fake_dns(email, check_deliverability):
        raise EmailUndeliverableError("The domain name exasad.com does not exist.")

    monkeypatch.setattr(email_domain_service, "validate_email", fake_dns)

    assert email_domain_service.can_receive_email("user@exasad.com") is False


def test_domain_with_a_mail_server_can_receive_email(monkeypatch):
    monkeypatch.setattr(email_domain_service, "validate_email", lambda email, **kwargs: None)

    assert email_domain_service.can_receive_email("aya@gmail.com") is True


# ---------- At sign-up ----------


@pytest.fixture
def check_enabled(monkeypatch):
    """Turn the check on (tests run with it off) and choose what the fake DNS answers."""
    monkeypatch.setattr(get_settings(), "email_check_deliverability", True)

    def answer(accepts: bool) -> None:
        monkeypatch.setattr(email_domain_service, "can_receive_email", lambda email: accepts)

    return answer


def test_check_is_off_in_tests():
    assert get_settings().email_check_deliverability is False


def test_sign_up_with_a_domain_that_cannot_receive_email_is_refused(
    client: TestClient, db: Session, check_enabled
):
    check_enabled(False)

    response = client.post("/auth/register", json=SIGN_UP)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "email_undeliverable"
    assert error["details"][0]["field"] == "email"
    assert user_repository.get_by_email(db, SIGN_UP["email"]) is None  # nothing was created


def test_sign_up_with_a_real_domain_is_accepted(client: TestClient, db: Session, check_enabled):
    check_enabled(True)

    response = client.post("/auth/register", json=SIGN_UP | {"email": "aya@gmail.com"})

    assert response.status_code == 201
    assert db.get(User, response.json()["user"]["id"]) is not None
