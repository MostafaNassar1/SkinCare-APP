"""upload_product_images: our own copies of the official product pictures (fake Cloudinary)."""

import json
import re

import pytest
import requests
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Product
from app.scripts import upload_product_images as script
from app.scripts.upload_product_images import public_id, upload_images
from app.services import image_storage_service
from app.services.image_storage_service import ImageStorageError
from tests.recommendations.conftest import add_scan

SHOPS = re.compile(r"mazen|drugstore|skinsociety|everyoung", re.IGNORECASE)


class FakeCloudinary:
    def __init__(self, fail_for: str | None = None):
        self.downloaded: list[str] = []
        self.uploaded: list[str] = []
        self.fail_for = fail_for

    def download(self, url: str) -> bytes:
        if self.fail_for and self.fail_for in url:
            raise ImageStorageError("download failed: 404")
        self.downloaded.append(url)
        return b"picture"

    def upload(self, settings, picture: bytes, public_id: str) -> str:
        self.uploaded.append(public_id)
        return f"https://res.cloudinary.com/demo/image/upload/{public_id}.png"


def run(db: Session, fake: FakeCloudinary, **options):
    return upload_images(db, get_settings(), download=fake.download, upload=fake.upload, **options)


def test_every_product_gets_its_official_picture(db: Session):
    fake = FakeCloudinary()

    summary = run(db, fake)

    assert len(summary.uploaded) == 32 and not summary.failed and not summary.skipped
    products = db.scalars(select(Product)).all()
    assert all(p.image_url.startswith("https://res.cloudinary.com/") for p in products)
    # where each picture came from is recorded, and it is always the brand, never a shop
    assert all(p.image_source_url.startswith("https://") for p in products)
    assert not any(SHOPS.search(p.image_source_url) for p in products)


def test_the_picture_list_names_only_brand_websites():
    data = json.loads(script.DATA_FILE.read_text(encoding="utf-8"))

    assert len(data["images"]) == 32
    assert not any(SHOPS.search(item["image_source_url"]) for item in data["images"])


def test_running_again_skips_stored_pictures_unless_forced(db: Session):
    run(db, FakeCloudinary())

    again = run(db, FakeCloudinary())
    forced = run(db, FakeCloudinary(), force=True)

    assert (len(again.uploaded), len(again.skipped)) == (0, 32)
    assert len(forced.uploaded) == 32


def test_one_failure_keeps_the_others(db: Session):
    summary = run(db, FakeCloudinary(fail_for="cosrx.com"))

    assert len(summary.failed) == 6  # the 6 COSRX products
    assert all(reason == "download failed: 404" for reason in summary.failed.values())
    cosrx = db.scalars(select(Product).where(Product.brand == "COSRX")).all()
    assert all(p.image_url is None for p in cosrx)
    assert len(summary.uploaded) == 26


def test_dry_run_changes_nothing(db: Session):
    fake = FakeCloudinary()

    summary = run(db, fake, dry_run=True)

    assert len(summary.uploaded) == 32 and fake.uploaded == []
    assert db.scalar(select(Product.image_url).where(Product.image_url.is_not(None))) is None


def test_public_ids_are_readable_and_unique(db: Session):
    products = db.scalars(select(Product)).all()
    ids = {public_id(p) for p in products}

    assert len(ids) == 32
    duo = next(p for p in products if p.name == "Effaclar Duo+M")
    assert public_id(duo) == "skincare/products/la-roche-posay-effaclar-duo-m"
    avene = next(p for p in products if p.name == "SPF 50+ Mineral Fluid")
    assert public_id(avene) == "skincare/products/avene-spf-50-mineral-fluid"


def test_the_app_shows_our_copy_never_the_source(
    client: TestClient, db: Session, app_user, user_headers
):
    run(db, FakeCloudinary())
    add_scan(db, app_user, acne="mild")

    text = client.get("/me/recommendations", headers=user_headers).text

    assert "res.cloudinary.com" in text
    assert "laroche-posay-me.com" not in text and "cosrx.com" not in text


# ---------- the Cloudinary service ----------


def test_upload_needs_the_cloudinary_settings():
    settings = get_settings().model_copy(update={"cloudinary_api_secret": SecretStr("")})

    with pytest.raises(ImageStorageError, match="not configured"):
        image_storage_service.upload(settings, b"x", "skincare/products/test")


class FakeResponse:
    def __init__(self, content_type: str, content: bytes = b"x", status: int = 200):
        self.headers = {"Content-Type": content_type}
        self.content = content
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(f"{self.status} Client Error")


@pytest.mark.parametrize(
    ("response", "message"),
    [(FakeResponse("text/html"), "not a picture"),
     (FakeResponse("image/png", status=404), "download failed"),
     (FakeResponse("image/png", content=b"x" * (10 * 1024 * 1024 + 1)), "larger than 10 MB")],
)  # fmt: skip
def test_download_refuses_what_is_not_a_picture(monkeypatch, response, message):
    monkeypatch.setattr(image_storage_service.requests, "get", lambda *a, **k: response)

    with pytest.raises(ImageStorageError, match=message):
        image_storage_service.download("https://example.com/product.png")


def test_script_refuses_to_run_without_settings(monkeypatch, capsys):
    monkeypatch.setattr(script.image_storage_service, "is_configured", lambda settings: False)

    assert script.main([]) == 1
    assert "not configured" in capsys.readouterr().err
