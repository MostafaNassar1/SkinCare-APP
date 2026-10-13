from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 2 decimals ~ 1.1 km: enough for local weather, without keeping the user's exact home location
LOCATION_PRECISION = Decimal("0.01")


class LocationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: Decimal = Field(ge=-90, le=90)
    longitude: Decimal = Field(ge=-180, le=180)

    @field_validator("latitude", "longitude")
    @classmethod
    def coarsen(cls, value: Decimal) -> Decimal:
        # privacy by design: only an area of about 1 km is stored
        return value.quantize(LOCATION_PRECISION, rounding=ROUND_HALF_UP)


class LocationOut(BaseModel):
    latitude: Decimal | None
    longitude: Decimal | None
    updated_at: datetime | None
