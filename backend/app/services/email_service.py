"""Sending emails: printed in the terminal ("console") or really sent through Gmail ("smtp")."""

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import get_settings

logger = logging.getLogger("app.email")


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    text: str  # plain-text version, for email apps that do not show HTML
    html: str


def mask_address(address: str) -> str:
    """a***@gmail.com: enough to recognise in a log line without exposing the full address."""
    name, _, domain = address.partition("@")
    return f"{name[:1]}***@{domain}"


def _send_console(email: Email) -> None:
    # development only: shows the whole email, including any code, in the server terminal
    logger.info(
        "Email (console mode, not sent) to %s\nSubject: %s\n\n%s",
        email.to,
        email.subject,
        email.text,
    )


def _send_smtp(email: Email) -> None:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = formataddr((settings.email_from_name, settings.smtp_username))
    message["To"] = email.to
    message["Subject"] = email.subject
    message.set_content(email.text)
    message.add_alternative(email.html, subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
        # encrypt the connection before the password is sent
        server.starttls(context=ssl.create_default_context())
        server.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        server.send_message(message)
    logger.info("Email sent to %s: %s", mask_address(email.to), email.subject)


def _deliver(email: Email) -> None:
    if get_settings().email_backend == "smtp":
        _send_smtp(email)
    else:
        _send_console(email)


def send_email(email: Email) -> None:
    """Send an email. Runs in the background after the response, so it never raises: a failure is
    logged, and the user can ask for a new code."""
    try:
        _deliver(email)
    except Exception:
        logger.exception("Could not send email to %s: %s", mask_address(email.to), email.subject)
