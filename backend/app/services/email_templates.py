"""The emails the app sends. Every value inserted into HTML is escaped, so a user's name cannot
inject HTML or links into an email."""

from html import escape

from app.core.config import get_settings
from app.services.email_service import Email


def _code_email(to: str, name: str, code: str, subject: str, intro: str, minutes: int) -> Email:
    app_name = get_settings().email_from_name
    text = (
        f"Hi {name},\n\n"
        f"{intro}\n\n"
        f"    {code}\n\n"
        f"This code expires in {minutes} minutes.\n"
        f"If you did not request it, you can ignore this email.\n\n"
        f"{app_name}"
    )
    html = f"""\
<div style="font-family: Arial, sans-serif; max-width: 480px; margin: auto; color: #222;">
  <h2 style="color: #1F4E79;">{escape(app_name)}</h2>
  <p>Hi {escape(name)},</p>
  <p>{escape(intro)}</p>
  <p style="font-size: 32px; font-weight: bold; letter-spacing: 8px; text-align: center;
            background: #F2F2F2; padding: 16px; border-radius: 8px;">{escape(code)}</p>
  <p>This code expires in {minutes} minutes.</p>
  <p style="color: #777; font-size: 13px;">If you did not request it, you can ignore this email.</p>
</div>"""
    return Email(to=to, subject=subject, text=text, html=html)


def verification_code_email(to: str, name: str, code: str, minutes: int) -> Email:
    return _code_email(
        to,
        name,
        code,
        subject=f"{code} is your SkinCare verification code",
        intro="Enter this code in the app to verify your email address:",
        minutes=minutes,
    )


def password_reset_code_email(to: str, name: str, code: str, minutes: int) -> Email:
    return _code_email(
        to,
        name,
        code,
        subject=f"{code} is your SkinCare password reset code",
        intro="Enter this code in the app to choose a new password:",
        minutes=minutes,
    )
