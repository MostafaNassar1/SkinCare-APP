r"""Export the YOLO dataset of the pimple finder (once).

    cd ml; .venv\Scripts\activate; $env:PYTHONPATH = "."
    python scripts/export_yolo.py

Writes C:\SkinCareData\prepared\yolo_pimples\ (see skincare_ml/yolo_data.py). This folder is
what the GPU laptop needs (with this repository), not the original photos.
"""

import json
import sys

from skincare_ml import config
from skincare_ml.yolo_data import export


def main() -> int:
    prepared = config.prepared_dir()
    manifest = json.loads((prepared / "manifests" / "pimples.json").read_text(encoding="utf-8"))
    frozen_file = prepared / "corrections" / "missed_pimples_frozen.json"
    frozen = json.loads(frozen_file.read_text(encoding="utf-8")) if frozen_file.exists() else None
    if frozen is None:
        print("Warning: no frozen missed-pimple corrections; exporting expert circles only")
    try:
        counts = export(manifest, config.data_dir() / "sources", prepared / "yolo_pimples", frozen)
    except FileExistsError as error:
        print(error, file=sys.stderr)
        return 1
    print(json.dumps(counts, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
