from fastapi.testclient import TestClient


def test_skin_concerns_are_public_and_in_seed_order(client: TestClient):
    response = client.get("/skin-concerns")

    assert response.status_code == 200
    names = [concern["name"] for concern in response.json()]
    assert names == ["acne", "oiliness", "dryness", "redness", "dark_spots", "wrinkles"]


def test_each_concern_has_what_the_app_displays(client: TestClient):
    by_name = {c["name"]: c for c in client.get("/skin-concerns").json()}

    assert by_name["dark_spots"]["display_name"] == "Dark spots"
    assert by_name["acne"]["description"]
    assert set(by_name["acne"]) == {
        "id", "name", "display_name", "description", "detection_method",
    }  # fmt: skip


def test_oiliness_and_dryness_use_the_hybrid_method(client: TestClient):
    methods = {c["name"]: c["detection_method"] for c in client.get("/skin-concerns").json()}

    assert methods["oiliness"] == methods["dryness"] == "hybrid"  # skin quiz + photo
    assert methods["acne"] == "photo"
