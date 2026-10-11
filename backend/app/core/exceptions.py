from typing import Any

from fastapi import HTTPException


class AppError(HTTPException):
    """An HTTP error with a specific, machine-readable code for the client app.

    Example: raise AppError(409, "email_taken", "This email is already registered")
    Plain HTTPExceptions also work; their code is derived from the status (e.g. 404 -> not_found).
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=message, headers=headers)
        self.code = code
        self.details = details


def account_disabled() -> AppError:
    """The account exists but was deactivated (used at login, refresh and on every request)."""
    return AppError(403, "account_disabled", "Account is disabled")
