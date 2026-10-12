import logging

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings, get_settings
from app.services import email_service
from app.services.email_service import Email, mask_address, send_email

EMAIL = Email(to="aya@gmail.com", subject="Hello", text="Plain text 482913", html="<p>Hi</p>")


# ---------- Tests never send real emails ----------


def test_tests_run_in_console_mode():
    assert get_settings().email_backend == "console"


def test_sent_emails_land_in_the_outbox(outbox):
    send_email(EMAIL)
    assert outbox == [EMAIL]


# ---------- Console mode ----------


def test_console_mode_prints_the_whole_email(caplog):
    with caplog.at_level(logging.INFO, logger="app.email"):
        email_service._send_console(EMAIL)

    assert "aya@gmail.com" in caplog.text
    assert "Plain text 482913" in caplog.text


# ---------- SMTP mode (with a fake server) ----------


class FakeSMTP:
    """Records what the code does with the mail server, in order."""

    calls: list = []

    def __init__(self, host, port, timeout):
        FakeSMTP.calls = [("connect", host, port)]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context):
        FakeSMTP.calls.append(("starttls",))

    def login(self, username, password):
        FakeSMTP.calls.append(("login", username, password))

    def send_message(self, message):
        FakeSMTP.calls.append(("send", message))


@pytest.fixture
def smtp_settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_username", "skincare.app@gmail.com")
    monkeypatch.setattr(settings, "smtp_password", SecretStr("app-password"))
    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    return settings


def test_smtp_encrypts_before_logging_in(smtp_settings):
    email_service._send_smtp(EMAIL)

    steps = [call[0] for call in FakeSMTP.calls]
    assert steps == ["connect", "starttls", "login", "send"]
    assert FakeSMTP.calls[0] == ("connect", "smtp.gmail.com", 587)
    assert FakeSMTP.calls[2] == ("login", "skincare.app@gmail.com", "app-password")


def test_smtp_message_has_sender_recipient_and_both_versions(smtp_settings):
    email_service._send_smtp(EMAIL)

    message = FakeSMTP.calls[-1][1]
    assert message["From"] == "SkinCare App <skincare.app@gmail.com>"
    assert message["To"] == "aya@gmail.com"
    assert message["Subject"] == "Hello"
    types = [part.get_content_type() for part in message.iter_parts()]
    assert types == ["text/plain", "text/html"]


# ---------- Failures ----------


def test_a_failed_send_is_logged_not_raised(monkeypatch, caplog):
    def broken(email):
        raise ConnectionError("Gmail is unreachable")

    monkeypatch.setattr(email_service, "_deliver", broken)

    send_email(EMAIL)  # must not raise: it runs after the response was sent

    assert "Could not send email to a***@gmail.com" in caplog.text
    assert "aya@gmail.com" not in caplog.text  # the address is masked


def test_mask_address():
    assert mask_address("aya@gmail.com") == "a***@gmail.com"


# ---------- Settings ----------


def test_smtp_mode_needs_credentials():
    with pytest.raises(ValidationError, match="SMTP_USERNAME and SMTP_PASSWORD"):
        Settings(email_backend="smtp", smtp_username="", smtp_password="")


def test_app_password_spaces_are_removed():
    settings = Settings(
        email_backend="smtp", smtp_username="a@gmail.com", smtp_password="abcd efgh ijkl mnop"
    )
    assert settings.smtp_password.get_secret_value() == "abcdefghijklmnop"


def test_app_password_is_hidden_when_printed():
    settings = Settings(smtp_username="a@gmail.com", smtp_password="abcdefghijklmnop")
    assert "abcdefghijklmnop" not in repr(settings)
