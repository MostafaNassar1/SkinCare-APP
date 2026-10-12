"""Checks that an email address's domain can receive email (DNS lookup)."""

from email_validator import EmailNotValidError, validate_email


def can_receive_email(email: str) -> bool:
    """False when the domain does not exist or does not accept email (e.g. user@exasad.com).

    Looks up the domain's mail server (MX record) in DNS. It cannot tell whether the mailbox
    itself exists (nobody123@gmail.com passes); the verification code proves that.
    If DNS does not answer in time, the address is accepted rather than blocking sign-up.
    """
    try:
        validate_email(email, check_deliverability=True)
    except EmailNotValidError:
        return False
    return True
