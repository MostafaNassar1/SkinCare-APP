from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.choices import DEVICE_PLATFORMS


class DeviceRegister(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # the Firebase Cloud Messaging token of this phone (given to the app by Firebase)
    fcm_token: str = Field(min_length=20, max_length=512, pattern=r"^[A-Za-z0-9_:\-]+$")
    platform: Literal[DEVICE_PLATFORMS]


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    platform: str
    last_seen_at: datetime
    created_at: datetime
