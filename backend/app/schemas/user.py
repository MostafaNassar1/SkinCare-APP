from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserOut(BaseModel):
    """The account data the app may see (never the password hash or Google id)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    email_verified: bool
    auth_provider: str
    created_at: datetime
