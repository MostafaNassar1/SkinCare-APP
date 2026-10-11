from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.auth import TokenResponse


class AdminOut(BaseModel):
    """The admin data the dashboard may see (never the password hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    role: str
    clinic_id: int | None  # set only for clinic managers
    created_at: datetime


class AdminAuthResponse(TokenResponse):
    admin: AdminOut
