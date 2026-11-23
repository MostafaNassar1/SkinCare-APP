r"""Check that prepared/unet_data/ arrived complete and unchanged (e.g. after a USB copy).

    cd ml; $env:PYTHONPATH = "."
    python scripts/verify_unet_data.py

Compares every picture with the SHA-256 written by export_unet_data.py and prints the index's own
SHA-256 (it must match the one in the handoff instructions). Exit code 0 = all good.
"""

import hashlib
import json
import sys

from skincare_ml import config


def sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    folder = config.prepared_dir() / "unet_data"
    index_file = folder / "index.json"
    if not index_file.exists():
        print(f"missing: {index_file}", file=sys.stderr)
        return 1
    items = json.loads(index_file.read_text(encoding="utf-8"))["items"]
    bad = []
    for item in items:
        for key in ("image", "labels"):
            path = folder / item[key]
            if not path.exists() or sha256(path) != item[f"{key}_sha256"]:
                bad.append(item[key])
    print(f"index.json SHA-256: {sha256(index_file)}")
    print(f"{len(items)} photos, {2 * len(items) - len(bad)} of {2 * len(items)} files correct")
    if bad:
        print("missing or damaged (copy them again):", *bad[:20], sep="\n  ")
        return 1
    print("OK: the training data is complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
