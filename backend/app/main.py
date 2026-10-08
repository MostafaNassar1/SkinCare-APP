from fastapi import FastAPI

from app.core.config import get_settings
from app.routes import health_routes

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.include_router(health_routes.router)
