from datetime import date

from pydantic import BaseModel

from app.schemas.notification import NotificationOut


class SkinForecastOut(BaseModel):
    date: date  # the user's today
    enabled: bool  # the 11:00 push is switched on
    has_location: bool  # without a location there is no local weather (PUT /me/location)
    forecast: NotificationOut | None  # None until today's forecast was made at 11:00
    attribution: str  # Open-Meteo's licence asks for it wherever their data is shown
