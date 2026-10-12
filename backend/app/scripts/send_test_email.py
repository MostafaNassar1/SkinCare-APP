r"""Send one sample verification email, to check the email settings in .env.

    cd backend; .venv\Scripts\activate
    python -m app.scripts.send_test_email --to your.own.address@gmail.com

Unlike the app (which sends in the background and only logs failures), this shows the error
directly, e.g. a wrong App Password.
"""

import argparse
import sys

from app.core.config import get_settings
from app.core.logging_config import setup_logging
from app.services import email_service
from app.services.email_templates import verification_code_email


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send a sample verification email.")
    parser.add_argument("--to", required=True, help="where to send the test email")
    args = parser.parse_args(argv)

    setup_logging()
    settings = get_settings()
    email = verification_code_email(args.to, name="Test", code="123456", minutes=10)
    try:
        email_service._deliver(email)  # not send_email(): we want to see errors here
    except Exception as exc:
        print(f"Sending failed ({settings.email_backend} mode): {exc}", file=sys.stderr)
        return 1

    if settings.email_backend == "console":
        print("Console mode: the email was printed above, not sent. Set EMAIL_BACKEND=smtp to send.")
    else:
        print(f"Sent to {args.to} from {settings.smtp_username}. Check the inbox (and spam folder).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
