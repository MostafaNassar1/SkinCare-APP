import pytest

from skincare_ml.memi import REGION_COLOURS, VIEW_REGIONS, parse_name


def test_parse_name_gives_person_and_view():
    assert parse_name("27_F") == ("27", "F")
    assert parse_name("7_L") == ("7", "L")


@pytest.mark.parametrize("stem", ["27", "27_X", "a_F", "27_F_2"])
def test_unknown_names_are_refused(stem):
    with pytest.raises(ValueError):
        parse_name(stem)


def test_every_region_belongs_to_exactly_one_view():
    regions = [region for view in VIEW_REGIONS.values() for region in view]

    assert sorted(regions) == sorted(REGION_COLOURS.values())
