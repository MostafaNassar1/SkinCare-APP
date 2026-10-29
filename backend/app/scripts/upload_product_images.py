r"""Store our own copy of every catalogue product's picture on Cloudinary.

    cd backend; .venv\Scripts\activate
    python -m app.scripts.upload_product_images [--force] [--dry-run]

The pictures come from the brands' official websites (listed in data/product_images.json, never
a shop). Each one is saved as products.image_url (what the app shows); the brand's link is kept
in image_source_url as the internal record of where it came from (never sent to the app).
Products that already have a picture are skipped, so the script is safe to run again; --force
uploads them again. Each product is saved as soon as it is done (an error halfway keeps the rest).
"""

import argparse
import json
import re
import sys
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.models import Product
from app.services import image_storage_service
from app.services.image_storage_service import ImageStorageError

DATA_FILE = Path(__file__).parent / "data" / "product_images.json"
FOLDER = "skincare/products"


@dataclass
class Summary:
    uploaded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


def public_id(product: Product) -> str:
    """ "La Roche-Posay" + "Effaclar Duo+M" -> "skincare/products/la-roche-posay-effaclar-duo-m"."""
    text = unicodedata.normalize("NFKD", f"{product.brand} {product.name}")
    slug = re.sub(r"[^a-z0-9]+", "-", text.encode("ascii", "ignore").decode().lower()).strip("-")
    return f"{FOLDER}/{slug}"


def upload_images(
    db: Session,
    settings: Settings,
    *,
    force: bool = False,
    dry_run: bool = False,
    download: Callable[[str], bytes] = image_storage_service.download,
    upload: Callable[[Settings, bytes, str], str] = image_storage_service.upload,
) -> Summary:
    sources = {
        (item["brand"], item["name"]): item["image_source_url"]
        for item in json.loads(DATA_FILE.read_text(encoding="utf-8"))["images"]
    }
    summary = Summary()
    for product in db.scalars(select(Product).order_by(Product.brand, Product.name)):
        label = f"{product.brand} {product.name}"
        source = sources.get((product.brand, product.name))
        if source is None:
            summary.failed[label] = "no official picture listed"
            continue
        if product.image_url and not force:
            summary.skipped.append(label)
            continue
        if dry_run:
            summary.uploaded.append(label)
            continue
        try:
            image_url = upload(settings, download(source), public_id(product))
        except ImageStorageError as error:
            summary.failed[label] = str(error)
            continue
        product.image_url = image_url
        product.image_source_url = source
        db.commit()
        summary.uploaded.append(label)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Upload the product pictures to Cloudinary.")
    parser.add_argument("--force", action="store_true", help="upload pictures already stored")
    parser.add_argument("--dry-run", action="store_true", help="only list what would be done")
    args = parser.parse_args(argv)

    settings = get_settings()
    if not args.dry_run and not image_storage_service.is_configured(settings):
        print("Cloudinary is not configured: add CLOUDINARY_* to backend/.env", file=sys.stderr)
        return 1
    with SessionLocal() as db:
        summary = upload_images(db, settings, force=args.force, dry_run=args.dry_run)

    verb = "Would upload" if args.dry_run else "Uploaded"
    print(f"{verb} {len(summary.uploaded)}, skipped {len(summary.skipped)} (already stored), "
          f"failed {len(summary.failed)}")  # fmt: skip
    for label, reason in summary.failed.items():
        print(f"  FAILED {label}: {reason}", file=sys.stderr)
    return 1 if summary.failed else 0


if __name__ == "__main__":
    sys.exit(main())
