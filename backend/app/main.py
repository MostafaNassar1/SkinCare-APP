from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, get_settings
from app.core.logging_config import setup_logging
from app.core.scheduler import build_scheduler
from app.middleware.error_handlers import register_error_handlers
from app.middleware.logging_middleware import REQUEST_ID_HEADER, RequestLoggingMiddleware
from app.routes import (
    achievement_routes,
    admin_auth_routes,
    appointment_routes,
    auth_routes,
    device_routes,
    forecast_routes,
    health_routes,
    internal_routes,
    ingredient_routes,
    notification_routes,
    places_routes,
    profile_routes,
    reference_routes,
    routine_routes,
    skin_quiz_routes,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application. Tests can build their own copy with different settings."""
    settings = settings or get_settings()
    setup_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # the background jobs run while the server runs (off in tests: SCHEDULER_ENABLED=false)
        scheduler = build_scheduler(settings) if settings.scheduler_enabled else None
        if scheduler:
            scheduler.start()
        yield
        if scheduler:
            scheduler.shutdown(wait=False)

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    register_error_handlers(app)

    # The middleware added LAST runs FIRST. CORS is outermost so even error responses carry
    # the CORS headers the browser needs to read them.
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,  # tokens travel in the Authorization header, not in cookies
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=[REQUEST_ID_HEADER],
    )

    app.include_router(health_routes.router)
    app.include_router(auth_routes.router)
    app.include_router(admin_auth_routes.router)
    app.include_router(profile_routes.router)
    app.include_router(skin_quiz_routes.router)
    app.include_router(ingredient_routes.router)
    app.include_router(device_routes.router)
    app.include_router(reference_routes.router)
    app.include_router(achievement_routes.router)
    app.include_router(routine_routes.router)
    app.include_router(routine_routes.streak_router)
    app.include_router(places_routes.router)
    app.include_router(appointment_routes.router)
    app.include_router(notification_routes.router)
    app.include_router(forecast_routes.router)
    app.include_router(internal_routes.router)
    return app


app = create_app()
