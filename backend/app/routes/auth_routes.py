from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.controllers import auth_controller
from app.core.dependencies import CurrentUser, get_db
from app.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
    UserAuthResponse,
)
from app.schemas.user import UserOut

router = APIRouter(prefix="/auth", tags=["Auth"])

DB = Annotated[Session, Depends(get_db)]


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserAuthResponse)
def register(data: RegisterRequest, db: DB):
    return auth_controller.register(db, data)


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
