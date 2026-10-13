from fastapi.testclient import TestClient


def test_ingredient_list_is_public_and_sorted(client: TestClient):
    response = client.get("/ingredients")

    assert response.status_code == 200
    names = [ingredient["name"] for ingredient in response.json()]
    assert len(names) == 13  # the seeded reference data
    assert names == sorted(names)


def test_ingredients_show_the_pregnancy_warning(client: TestClient):
    by_name = {i["name"]: i for i in client.get("/ingredients").json()}

    assert by_name["Retinol"]["avoid_during_pregnancy"] is True
    assert by_name["Niacinamide"]["avoid_during_pregnancy"] is False
    assert by_name["Niacinamide"]["description"]
    assert set(by_name["Retinol"]) == {"id", "name", "description", "avoid_during_pregnancy"}
