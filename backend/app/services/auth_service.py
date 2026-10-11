"""Password login checks shared by user login and admin login."""

from functools import cache
from typing import Protocol

from app.core.exceptions import AppError, account_disabled
from app.core.security import generate_token, hash_password, verify_password


class PasswordAccount(Protocol):
    """What the check needs from an account: users and admins both have these."""

    password_hash: str | None
    is_active: bool


def invalid_credentials() -> AppError:
    # one answer for unknown email, wrong password and accounts without a password
    return AppError(401, "invalid_credentials", "Incorrect email or password")


@cache
def _dummy_password_hash() -> str:
    """A real bcrypt hash of a random password, computed once and never matched."""
    return hash_password(generate_token())


def check_password_login(account: PasswordAccount | None, password: str) -> None:
    """Raise unless `account` exists, is active and `password` is its password."""
    if account is None or account.password_hash is None:
        # Still run a full bcrypt check, so this answer takes as long as a wrong password and the
        # response time does not reveal which emails have an account.
        verify_password(password, _dummy_password_hash())
        raise invalid_credentials()
    if not verify_password(password, account.password_hash):
        raise invalid_credentials()
    # only revealed to someone who knows the password
    if not account.is_active:
        raise account_disabled()
