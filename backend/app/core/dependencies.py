from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import InvalidTokenError, SubjectType, decode_access_token
from app.db.session import SessionLocal
from app.models import Admin, User
from app.repositories import admin_repository, user_repository


def get_db() -> Generator[Session, None, None]:
    """Give each request its own database session and always close it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Reads "Authorization: Bearer <token>" and adds the "Authorize" button to /docs.
# auto_error=False so a missing token gets the same 401 response as an invalid one.
bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    # WWW-Authenticate tells the client which kind of credentials to send (RFC 6750)
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _subject_id_from_token(
    credentials: HTTPAuthorizationCredentials | None, expected_type: SubjectType
) -> int:
    """Return the account id in a valid access token of the expected type, else raise 401."""
    if credentials is None:
        raise _unauthorized("Not authenticated")
    try:
        token_data = decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise _unauthorized("Invalid or expired token") from None
    # users and admins have separate id sequences: user 5 and admin 5 are different people
    if token_data.subject_type != expected_type:
        raise _unauthorized("Invalid or expired token")
    return token_data.subject_id


def _account_disabled() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """The logged-in mobile app user. Add to a route to make it require a user token."""
    user = user_repository.get_by_id(db, _subject_id_from_token(credentials, "user"))
    if user is None:  # deleted after the token was issued
        raise _unauthorized("Invalid or expired token")
    if not user.is_active:
        raise _account_disabled()
    return user


def get_current_admin(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> Admin:
    """The logged-in admin dashboard user. Add to a route to make it require an admin token."""
    admin = admin_repository.get_by_id(db, _subject_id_from_token(credentials, "admin"))
    if admin is None:
        raise _unauthorized("Invalid or expired token")
    if not admin.is_active:
        raise _account_disabled()
    return admin


# Short forms for route signatures, e.g. `def get_profile(user: CurrentUser): ...`
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentAdmin = Annotated[Admin, Depends(get_current_admin)]
