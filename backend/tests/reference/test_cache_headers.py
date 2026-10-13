"""Reference lists may be cached by the phone for an hour; personal data and errors may not."""

import pytest
from fastapi.testclient import TestClient

CACHED = "public, max-age=3600"


@pytest.mark.parametrize("path", ["/ingredients", "/skin-concerns"])
def test_reference_lists_can_be_cached(client: TestClient, path: str):
    assert client.get(path).headers["Cache-Control"] == CACHED


def test_personal_data_is_not_marked_cacheable(client: TestClient, user_headers):
    response = client.get("/me/allergies", headers=user_headers)

    assert response.status_code == 200
    assert "Cache-Control" not in response.headers


def test_errors_are_not_marked_cacheable(client: TestClient):
    response = client.get("/skin-concerns/unknown")

    assert response.status_code == 404
    assert "Cache-Control" not in response.headers
