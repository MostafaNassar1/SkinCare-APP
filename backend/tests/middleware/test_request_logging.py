import logging
import re

from fastapi.testclient import TestClient


def test_every_response_has_a_unique_request_id(client: TestClient):
    first = client.get("/health").headers["X-Request-ID"]
    second = client.get("/health").headers["X-Request-ID"]

    assert re.fullmatch(r"[0-9a-f]{32}", first)
    assert first != second


def test_error_responses_also_have_a_request_id(client: TestClient):
    assert "X-Request-ID" in client.get("/does-not-exist").headers


def test_request_id_from_the_client_is_ignored(client: TestClient):
    # the server always generates its own, so a client cannot inject text into the logs
    response = client.get("/health", headers={"X-Request-ID": "fake\ninjected log line"})
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])


def test_one_log_line_per_request(client: TestClient, caplog):
    with caplog.at_level(logging.INFO, logger="app.requests"):
        response = client.get("/health")

    lines = [r.getMessage() for r in caplog.records if r.name == "app.requests"]
    assert len(lines) == 1
    assert lines[0].startswith("GET /health -> 200 in ")
    assert response.headers["X-Request-ID"] in lines[0]


def test_query_string_is_not_logged(client: TestClient, caplog):
    with caplog.at_level(logging.INFO, logger="app.requests"):
        client.get("/health?token=secret-reset-token")

    app_lines = [r.getMessage() for r in caplog.records if r.name == "app.requests"]
    assert app_lines and not any("secret-reset-token" in line for line in app_lines)


def test_uvicorn_access_log_is_silenced():
    # it would log the full URL with the query string; our middleware line replaces it
    assert not logging.getLogger("uvicorn.access").isEnabledFor(logging.INFO)
