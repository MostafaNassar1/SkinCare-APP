"""Our own copies of pictures on Cloudinary (free plan; decided 2026-10-29).

The picture is downloaded by us first (like a browser would), then uploaded as a file, so a
brand's server can never block Cloudinary's fetcher and a failure names the real cause. Large
pictures are shrunk on upload (at most 800 x 800 px) to save the free plan's storage.
"""

import cloudinary
import cloudinary.uploader
import requests

from app.core.config import Settings

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
)
MAX_SIZE = {"width": 800, "height": 800, "crop": "limit"}
MAX_BYTES = 10 * 1024 * 1024  # the free plan's limit per picture


class ImageStorageError(RuntimeError):
    """The picture could not be stored (not configured, download or upload failed)."""


def is_configured(settings: Settings) -> bool:
    return bool(
        settings.cloudinary_cloud_name
        and settings.cloudinary_api_key
        and settings.cloudinary_api_secret.get_secret_value()
    )


def download(url: str) -> bytes:
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
        response.raise_for_status()
    except requests.RequestException as error:
        raise ImageStorageError(f"download failed: {error}") from error
    if not response.headers.get("Content-Type", "").startswith("image/"):
        raise ImageStorageError("the link is not a picture")
    if len(response.content) > MAX_BYTES:
        raise ImageStorageError("the picture is larger than 10 MB")
    return response.content


def upload(settings: Settings, picture: bytes, public_id: str) -> str:
    """Store the picture under `public_id` (replacing an older copy); returns its https URL."""
    if not is_configured(settings):
        raise ImageStorageError("Cloudinary is not configured (CLOUDINARY_* in .env)")
    try:
        result = cloudinary.uploader.upload(
            picture,
            public_id=public_id,
            overwrite=True,
            resource_type="image",
            transformation=[MAX_SIZE],
            cloud_name=settings.cloudinary_cloud_name,
            api_key=settings.cloudinary_api_key,
            api_secret=settings.cloudinary_api_secret.get_secret_value(),
            secure=True,
        )
    except cloudinary.exceptions.Error as error:
        raise ImageStorageError(f"upload failed: {error}") from error
    return result["secure_url"]
