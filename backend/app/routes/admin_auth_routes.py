from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.controllers import admin_auth_controller
from app.core.dependencies import CurrentAdmin, get_db
from app.schemas.admin import AdminAuthResponse, AdminOut
from app.schemas.auth import LoginRequest, RefreshTokenRequest, TokenResponse

router = APIRouter(prefix="/admin/auth", tags=["Admin auth"])

DB = Annotated[Session, Depends(get_db)]


@router.post("/login", response_model=AdminAuthResponse)
def login(data: LoginRequest, db: DB):
    return admin_auth_controller.login(db, data)


@router.post("/refresh", response_model=TokenResponse)
def refresh(data: RefreshTokenRequest, db: DB):
    return admin_auth_controller.refresh(db, data)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(data: RefreshTokenRequest, db: DB):
    admin_auth_controller.logout(db, data)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=AdminOut)
def me(admin: CurrentAdmin):
    return admin
