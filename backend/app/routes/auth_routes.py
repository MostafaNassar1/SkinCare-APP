from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Response, status
from sqlalchemy.orm import Session

from app.controllers import auth_controller
from app.core.dependencies import CurrentUser, get_db
from app.schemas.auth import (
    CodeSentResponse,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshTokenRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserAuthResponse,
    VerifyEmailRequest,
)
from app.schemas.user import UserOut

router = APIRouter(prefix="/auth", tags=["Auth"])

DB = Annotated[Session, Depends(get_db)]


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=CodeSentResponse)
def register(data: RegisterRequest, db: DB, background: BackgroundTasks):
    return auth_controller.register(db, data, background)


@router.post("/verify-email", response_model=UserAuthResponse)
def verify_email(data: VerifyEmailRequest, db: DB):
    return auth_controller.verify_email(db, data)


@router.post(
    "/resend-verification", status_code=status.HTTP_202_ACCEPTED, response_model=CodeSentResponse
)
def resend_verification(data: LoginRequest, db: DB, background: BackgroundTasks):
    return auth_controller.resend_verification_code(db, data, background)


@router.post(
    "/forgot-password", status_code=status.HTTP_202_ACCEPTED, response_model=MessageResponse
)
def forgot_password(data: ForgotPasswordRequest, db: DB, background: BackgroundTasks):
    return auth_controller.forgot_password(db, data, background)


@router.post("/reset-password", response_model=UserAuthResponse)
def reset_password(data: ResetPasswordRequest, db: DB):
    return auth_controller.reset_password(db, data)


@router.post("/login", response_model=UserAuthResponse)
def login(data: LoginRequest, db: DB):
    return auth_controller.login(db, data)


@router.post("/refresh", response_model=TokenResponse)
def refresh(data: RefreshTokenRequest, db: DB):
    return auth_controller.refresh(db, data)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(data: RefreshTokenRequest, db: DB):
    auth_controller.logout(db, data)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user
