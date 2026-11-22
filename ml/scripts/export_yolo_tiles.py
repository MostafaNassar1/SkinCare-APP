r"""Export the tile dataset for fine-tuning runs B and C (once).

    cd ml; .venv\Scripts\activate; $env:PYTHONPATH = "."
    python scripts/export_yolo_tiles.py

Writes C:\SkinCareData\prepared\yolo_pimples_tiles\ (see skincare_ml/yolo_tiles.py): training and
validation tiles at full resolution, plus one phone-like copy of every training tile. Like
yolo_pimples\, this folder goes to the GPU laptop; the test photos are not in it.
"""

import json
import sys
import time

from skincare_ml import config
from skincare_ml.yolo_tiles import export_tiles


def main() -> int:
    prepared = config.prepared_dir()
    manifest = json.loads((prepared / "manifests" / "pimples.json").read_text(encoding="utf-8"))
    started = time.time()
    try:
        sources, out = config.data_dir() / "sources", prepared / "yolo_pimples_tiles"
        counts = export_tiles(manifest, sources, out)
    except FileExistsError as error:
        print(error, file=sys.stderr)
        return 1
    print(json.dumps(counts, indent=1))
    print(f"Done in {(time.time() - started) / 60:.1f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
