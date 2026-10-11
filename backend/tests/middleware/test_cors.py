from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app

ADMIN_ORIGIN = "http://localhost:5173"


def preflight(client: TestClient, origin: str):
    """What a browser sends before a cross-origin request with an Authorization header."""
    return client.options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )


def cors_client(origins: list[str]) -> TestClient:
    settings = get_settings().model_copy(update={"cors_origins": origins})
    return TestClient(create_app(settings))


def test_no_browser_origin_is_allowed_by_default():
    assert get_settings().cors_origins == []
    response = preflight(cors_client([]), ADMIN_ORIGIN)

    assert "access-control-allow-origin" not in response.headers


def test_configured_origin_is_allowed():
    response = preflight(cors_client([ADMIN_ORIGIN]), ADMIN_ORIGIN)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ADMIN_ORIGIN
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_other_origins_are_still_refused():
    response = preflight(cors_client([ADMIN_ORIGIN]), "http://evil.example.com")

    assert "access-control-allow-origin" not in response.headers


def test_browser_can_read_the_request_id():
    response = cors_client([ADMIN_ORIGIN]).get("/health", headers={"Origin": ADMIN_ORIGIN})

    assert response.headers["access-control-allow-origin"] == ADMIN_ORIGIN
    assert "x-request-id" in response.headers["access-control-expose-headers"].lower()
