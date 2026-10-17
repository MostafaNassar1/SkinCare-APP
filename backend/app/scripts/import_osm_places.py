r"""Import (or refresh) the real clinics and pharmacies of Lebanon from OpenStreetMap.

    cd backend; .venv\Scripts\activate
    python -m app.scripts.import_osm_places              # downloads the latest Lebanon extract
    python -m app.scripts.import_osm_places --file lebanon-latest.osm.pbf
    python -m app.scripts.import_osm_places --dry-run    # only counts, changes nothing

Run it again any time (the scheduler also does it every Sunday at 04:00): known places are
updated, new ones added, vanished ones marked inactive. The downloaded file is deleted afterwards.
"""

import argparse
import sys
import tempfile
from collections import Counter
from pathlib import Path

from app.db.session import SessionLocal
from app.services import osm_import_service
from app.services.osm_import_service import GEOFABRIK_LEBANON_URL, ImportAborted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import clinics and pharmacies from OSM.")
    parser.add_argument("--file", type=Path, help="a local .osm.pbf file instead of downloading")
    parser.add_argument("--dry-run", action="store_true", help="count only, change nothing")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as tmp:
        path = args.file
        if path is None:
            print(f"Downloading {GEOFABRIK_LEBANON_URL} ...")
            path = osm_import_service.download(GEOFABRIK_LEBANON_URL, Path(tmp) / "lebanon.osm.pbf")
        records = osm_import_service.read_places(path)

    counts = Counter(r.category for r in records)
    summary = ", ".join(f"{n} {c}" for c, n in sorted(counts.items()))
    print(f"Found {len(records)} places: {summary}")
    if args.dry_run:
        print("Dry run: nothing was changed.")
        return 0

    with SessionLocal() as db:
        try:
            result = osm_import_service.import_places(db, records)
        except ImportAborted as exc:
            print(f"Import stopped: {exc}", file=sys.stderr)
            return 1
        db.commit()
    print(
        f"Imported: {result.created} new, {result.updated} updated, "
        f"{result.deactivated} marked inactive."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
