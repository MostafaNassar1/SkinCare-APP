"""Importing clinics and pharmacies from OpenStreetMap, with a tiny hand-made map file."""

from contextlib import nullcontext
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.models import Clinic
from app.scripts import import_osm_places as script
from app.services import osm_import_service
from app.services.osm_import_service import (
    ImportAborted,
    address_of,
    category_of,
    import_places,
    name_of,
    opening_hours_of,
    phone_of,
    read_places,
)

SAMPLE = Path(__file__).parent / "sample.osm"


@pytest.fixture
def records():
    return read_places(SAMPLE)


def by_osm_id(records) -> dict:
    return {r.osm_id: r for r in records}


# ---------- Reading the tags ----------


@pytest.mark.parametrize(
    ("tags", "category"),
    [
        ({"amenity": "pharmacy"}, "pharmacy"),
        ({"healthcare": "pharmacy"}, "pharmacy"),
        ({"amenity": "hospital"}, "hospital"),
        ({"amenity": "clinic"}, "clinic"),
        ({"amenity": "doctors"}, "doctor"),
        ({"healthcare": "doctor"}, "doctor"),
        ({"amenity": "cafe"}, None),
        ({"healthcare": "dentist"}, None),
    ],
)
def test_category(tags, category):
    assert category_of(tags) == category


def test_english_name_first_then_local_then_a_label():
    assert name_of({"name": "صيدلية", "name:en": "Mazen Pharmacy"}, "pharmacy") == "Mazen Pharmacy"
    assert name_of({"name": "صيدلية"}, "pharmacy") == "صيدلية"
    assert name_of({}, "pharmacy") == "Pharmacy"


def test_only_the_first_phone_number_is_kept():
    assert phone_of({"phone": "+961 1 234567; +961 3 765432"}) == "+961 1 234567"
    assert phone_of({"contact:phone": "+961 3 111111"}) == "+961 3 111111"
    assert phone_of({}) is None


def test_address_is_built_from_its_parts():
    tags = {"addr:housenumber": "12", "addr:street": "Hamra Street", "addr:city": "Beirut"}
    assert address_of(tags) == "12 Hamra Street, Beirut"
    assert address_of({"addr:full": "Bliss St, Beirut"}) == "Bliss St, Beirut"
    assert address_of({}) is None


def test_too_long_opening_hours_are_dropped_not_cut():
    assert opening_hours_of({"opening_hours": "Mo-Fr 08:00-18:00"}) == "Mo-Fr 08:00-18:00"
    assert opening_hours_of({"opening_hours": "x" * 300}) is None


# ---------- Reading a map file ----------


def test_only_clinics_and_pharmacies_in_lebanon_are_kept(records):
    # node 3 is in Paris and node 4 is a cafe
    assert set(by_osm_id(records)) == {"node/1", "node/2", "node/5", "node/6", "way/100"}


def test_pharmacy_details(records):
    mazen = by_osm_id(records)["node/1"]

    assert (mazen.category, mazen.name) == ("pharmacy", "Mazen Pharmacy")
    assert mazen.phone_number == "+961 1 234567"
    assert mazen.address == "12 Hamra Street, Beirut"
    assert mazen.opening_hours == "Mo-Sa 08:00-22:00"
    assert (mazen.latitude, mazen.longitude) == (Decimal("33.893800"), Decimal("35.501800"))


def test_unnamed_place_gets_a_label_and_arabic_names_are_kept(records):
    assert by_osm_id(records)["node/2"].name == "Pharmacy"
    assert by_osm_id(records)["node/5"].name == "عيادة الدكتور"


def test_building_outline_uses_its_centre(records):
    hospital = by_osm_id(records)["way/100"]

    assert hospital.category == "hospital"
    # centre of the 4 corners (the repeated closing corner is not counted twice)
    assert (hospital.latitude, hospital.longitude) == (Decimal("33.905000"), Decimal("35.525000"))


# ---------- Saving ----------


def places(db: Session) -> dict[str, Clinic]:
    db.expire_all()
    return {c.osm_id: c for c in db.query(Clinic).filter_by(source="osm_import")}


def test_first_import_adds_every_place(db: Session, records):
    result = import_places(db, records)

    assert (result.found, result.created, result.updated, result.deactivated) == (5, 5, 0, 0)
    saved = places(db)["node/1"]
    assert (saved.category, saved.name, saved.is_active) == ("pharmacy", "Mazen Pharmacy", True)
    assert saved.last_synced_at is not None


def test_importing_again_updates_instead_of_duplicating(db: Session, records):
    import_places(db, records)
    renamed = [
        replace(r, name="Mazen Pharmacy (new)") if r.osm_id == "node/1" else r for r in records
    ]

    result = import_places(db, renamed)

    assert (result.created, result.updated) == (0, 5)
    assert len(places(db)) == 5
    assert places(db)["node/1"].name == "Mazen Pharmacy (new)"


def test_vanished_places_become_inactive_and_come_back(db: Session, records):
    import_places(db, records)
    without_clinic = [r for r in records if r.osm_id != "node/6"]

    assert import_places(db, without_clinic).deactivated == 1
    assert places(db)["node/6"].is_active is False  # kept (appointments may point to it)

    import_places(db, records)
    assert places(db)["node/6"].is_active is True


def test_suspiciously_small_import_changes_nothing(db: Session, records):
    import_places(db, records)

    with pytest.raises(ImportAborted):
        import_places(db, records[:1])  # 1 of 5: the file looks broken

    assert all(place.is_active for place in places(db).values())


# ---------- Command line ----------


def test_dry_run_only_counts(db: Session, monkeypatch, capsys):
    monkeypatch.setattr(script, "SessionLocal", lambda: nullcontext(db))

    assert script.main(["--file", str(SAMPLE), "--dry-run"]) == 0

    out = capsys.readouterr().out
    assert "Found 5 places: 1 clinic, 1 doctor, 1 hospital, 2 pharmacy" in out
    assert places(db) == {}


def test_import_from_a_file(db: Session, monkeypatch, capsys):
    monkeypatch.setattr(script, "SessionLocal", lambda: nullcontext(db))

    assert script.main(["--file", str(SAMPLE)]) == 0

    assert "5 new, 0 updated, 0 marked inactive" in capsys.readouterr().out
    assert len(places(db)) == 5


def test_without_a_file_the_latest_extract_is_downloaded(db, monkeypatch, capsys):
    downloads = []

    def fake_download(url, destination):
        downloads.append(url)
        return SAMPLE  # no real download in tests

    monkeypatch.setattr(osm_import_service, "download", fake_download)
    monkeypatch.setattr(script, "SessionLocal", lambda: nullcontext(db))

    assert script.main(["--dry-run"]) == 0
    assert downloads == [osm_import_service.GEOFABRIK_LEBANON_URL]
