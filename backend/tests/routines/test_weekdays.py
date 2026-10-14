from datetime import date

import pytest

from app.services.weekdays import EVERY_DAY, from_mask, is_scheduled, to_mask

MONDAY = date(2026, 10, 12)  # a Monday


def test_every_day_is_127():
    assert to_mask(["mon", "tue", "wed", "thu", "fri", "sat", "sun"]) == EVERY_DAY == 127


def test_retinol_nights_mon_wed_fri_is_21():
    assert to_mask(["mon", "wed", "fri"]) == 21
    assert from_mask(21) == ["mon", "wed", "fri"]


def test_order_and_duplicates_do_not_matter():
    assert to_mask(["fri", "mon", "fri"]) == to_mask(["mon", "fri"])


@pytest.mark.parametrize("days", [[], ["funday"]])
def test_invalid_days_are_rejected(days):
    with pytest.raises(ValueError):
        to_mask(days)


def test_is_scheduled_checks_the_weekday():
    mon_wed_fri = to_mask(["mon", "wed", "fri"])

    assert is_scheduled(mon_wed_fri, MONDAY)
    assert not is_scheduled(mon_wed_fri, date(2026, 10, 13))  # Tuesday
    assert is_scheduled(EVERY_DAY, date(2026, 10, 18))  # Sunday
