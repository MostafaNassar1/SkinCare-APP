"""Folders shared by the ML scripts.

The datasets are NOT in the repository: they are large, some licences forbid redistributing them,
and the repository is public. They live in a data folder outside OneDrive (so gigabytes of face
photos are not synced to the cloud): C:\\SkinCareData by default, or wherever the environment
variable SKINCARE_DATA_DIR points (e.g. another drive on the GPU laptop).
"""

import os
from pathlib import Path

DEFAULT_DATA_DIR = Path("C:/SkinCareData")
# ml/skincare_ml/config.py -> the repository root
REPO_ROOT = Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    """The data folder; refuses a folder inside the repository (images must never be committed)."""
    value = os.environ.get("SKINCARE_DATA_DIR")
    path = (Path(value).expanduser() if value else DEFAULT_DATA_DIR).resolve()
    if path == REPO_ROOT or REPO_ROOT in path.parents:
        raise ValueError(f"The data folder {path} is inside the repository; choose one outside it.")
    return path


def kit_dir() -> Path:
    """Copy of the student's research kit (download script, source manifests, labelling app)."""
    return data_dir() / "starter_kit"


def raw_dir() -> Path:
    """Original downloaded photos, annotations and masks (written by the kit's download script)."""
    return kit_dir() / "data" / "raw"


def prepared_dir() -> Path:
    """Our own outputs: face crops, YOLO / U-Net training formats, splits."""
    return data_dir() / "prepared"
