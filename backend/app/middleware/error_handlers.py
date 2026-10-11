"""One JSON error format for every error the API returns:

    {"error": {"code": "not_found", "message": "Not Found", "details": null}}

The client app can rely on `code` (stable, machine-readable) and show `message` to the user.
"""

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "too_many_requests",
    500: "internal_error",
    503: "service_unavailable",
}


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "details": details}}
    return JSONResponse(status_code=status_code, content=body, headers=headers)


def internal_error_response() -> JSONResponse:
    # deliberately generic: internal details stay in the server log only
    return error_response(500, "internal_error", "Something went wrong. Please try again later.")


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """HTTPException / AppError raised by our code, and Starlette's own 404 / 405."""
    code = getattr(exc, "code", None) or STATUS_CODES.get(exc.status_code, "error")
    if isinstance(exc.detail, str):
        message, details = exc.detail, getattr(exc, "details", None)
    else:  # structured detail: keep it in details, with a standard message
        message, details = HTTPStatus(exc.status_code).phrase, exc.detail
    return error_response(exc.status_code, code, message, details, getattr(exc, "headers", None))


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Request body / query / path values that do not match the expected types."""
    details = [
        {
            # e.g. ("body", "email") -> "email"; the location prefix is not useful to the app
            "field": ".".join(str(part) for part in error["loc"][1:]) or str(error["loc"][0]),
            "message": error["msg"],
            "type": error["type"],
        }
        # the submitted "input" is left out on purpose: it could be a password
        for error in exc.errors()
    ]
    return error_response(422, "validation_error", "Some fields are invalid", details)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    # unexpected exceptions are caught by RequestLoggingMiddleware, so they can be logged with
    # their request id and still get the standard format (see internal_error_response)
