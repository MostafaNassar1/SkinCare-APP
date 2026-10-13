from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, get_settings
from app.core.logging_config import setup_logging
from app.middleware.error_handlers import register_error_handlers
from app.middleware.logging_middleware import REQUEST_ID_HEADER, RequestLoggingMiddleware
from app.routes import (
    admin_auth_routes,
    auth_routes,
    device_routes,
    health_routes,
    ingredient_routes,
    profile_routes,
    skin_quiz_routes,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application. Tests can build their own copy with different settings."""
    settings = settings or get_settings()
    setup_logging()

    app = FastAPI(title=settings.app_name)
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
    return app


app = create_app()
