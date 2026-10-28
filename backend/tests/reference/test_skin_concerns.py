from fastapi.testclient import TestClient


def test_skin_concerns_are_public_and_in_seed_order(client: TestClient):
    response = client.get("/skin-concerns")

    assert response.status_code == 200
    names = [concern["name"] for concern in response.json()]
    assert names == [
        "acne", "oiliness", "dryness", "redness", "dark_spots", "wrinkles", "whiteheads",
        "pustules",
    ]  # fmt: skip


def test_each_concern_has_what_the_app_displays(client: TestClient):
    by_name = {c["name"]: c for c in client.get("/skin-concerns").json()}

    assert by_name["dark_spots"]["display_name"] == "Dark spots"
    assert by_name["acne"]["description"]
    assert set(by_name["acne"]) == {
        "id", "name", "display_name", "description", "detection_method",
    }  # fmt: skip


def test_quiz_concerns_and_photo_concerns(client: TestClient):
    methods = {c["name"]: c["detection_method"] for c in client.get("/skin-concerns").json()}

    # no reliable licensed photo data for these three: the skin quiz alone (migration 0010)
    assert methods["oiliness"] == methods["dryness"] == methods["redness"] == "questionnaire"
    for photo_concern in ("acne", "whiteheads", "pustules", "wrinkles", "dark_spots"):
        assert methods[photo_concern] == "photo"
