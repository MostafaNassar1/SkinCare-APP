r"""Score pimple-finder models the same way on whole VALIDATION photos (decided 2026-11-06).

    cd ml; .venv\Scripts\activate; $env:PYTHONPATH = "."
    python scripts/compare_models.py --model v1=yolo_pimples_v1.pt:whole `
        --model B=yolo_pimples_B.pt:tiled
    python scripts/compare_models.py --model v1=yolo_pimples_v1.pt:whole --limit 20   # quick look

Each model is NAME=FILE:MODE, FILE in C:\SkinCareData\models (or a full path), MODE "whole" (the
photo shrunk to 1,280 px: v1, run A) or "tiled" (1,024 px tiles at full resolution: runs B, C).
Every model is scored on the ORIGINAL validation photos (photo pixels, skincare_ml/
detection_metrics.py) and on phone-like versions of them (40% of the size, blurred, compressed:
roughly a selfie), both at its own best-F1 cutoff. The test photos need --final-test: they are used
ONCE, for the chosen model, never to choose between models.
Writes C:\SkinCareData\prepared\yolo_evaluations\compare_<time>.json and prints a table.
"""

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

from skincare_ml import config
from skincare_ml.detection_metrics import score
from skincare_ml.tiled_predict import predict_tiled, predict_whole
from skincare_ml.yolo_data import added_boxes
from skincare_ml.yolo_tiles import phone_photo

FLOOR = 0.01  # lowest confidence kept, so the precision-recall curve is complete enough
PHONE_FACTOR = 0.4


def parse_model(text: str) -> tuple[str, Path, str]:
    name, _, rest = text.partition("=")
    file, _, mode = rest.rpartition(":")
    if not name or not file or mode not in ("whole", "tiled"):
        raise argparse.ArgumentTypeError("use NAME=FILE:whole or NAME=FILE:tiled")
    path = Path(file)
    if not path.is_absolute():
        path = config.data_dir() / "models" / file
    return name, path, mode


def spearman(a: list[float], b: list[float]) -> float | None:
    """Rank correlation (ties get their average rank)."""
    if len(a) < 3:
        return None

    def ranks(values):
        values = np.asarray(values, dtype=float)
        order = values.argsort(kind="stable")
        result = np.empty(len(values))
        result[order] = np.arange(len(values))
        for value in np.unique(values):
            same = values == value
            result[same] = result[same].mean()
        return result

    ra, rb = ranks(a), ranks(b)
    if ra.std() == 0 or rb.std() == 0:
        return None
    return round(float(np.corrcoef(ra, rb)[0, 1]), 3)


def evaluate(model, mode: str, photos: list[dict], sources: Path, phone: bool,
             device) -> dict:  # fmt: skip
    rows, counts = [], []
    for image in photos:
        with Image.open(sources / image["file"]) as photo:
            photo = photo.convert("RGB")
        truth = np.array([b["box"] for b in image["boxes"]], dtype=float).reshape(-1, 4)
        if phone:
            photo = phone_photo(photo, random.Random(f"phone:{image['file']}"), PHONE_FACTOR)
            truth = truth * PHONE_FACTOR
        if mode == "whole":
            found = predict_whole(model, photo, FLOOR, device=device)
        else:
            found = predict_tiled(model, photo, FLOOR, device=device)
        rows.append({"pred": found.boxes, "scores": found.scores, "truth": truth})
        counts.append(image.get("original_lesion_count"))
    result = score(rows)
    predicted = [int((r["scores"] >= result["cutoff"]).sum()) for r in rows]
    known = [(p, c) for p, c in zip(predicted, counts, strict=True) if c is not None]
    result["count_vs_acne04_expert_count_spearman"] = spearman(*zip(*known)) if known else None
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare pimple-finder models on validation.")
    parser.add_argument("--model", type=parse_model, action="append", required=True)
    parser.add_argument("--limit", type=int, help="only the first N photos (a quick look)")
    parser.add_argument("--no-phone", action="store_true", help="skip the phone-like versions")
    parser.add_argument("--final-test", action="store_true",
                        help="score the TEST photos (once, for the chosen model only)")
    parser.add_argument("--device", default=None, help="e.g. cpu or 0 (default: automatic)")
    args = parser.parse_args(argv)

    os.environ.setdefault("YOLO_AUTOINSTALL", "false")
    os.environ.setdefault("YOLO_VERBOSE", "false")
    from ultralytics import YOLO

    prepared = config.prepared_dir()
    manifest = json.loads((prepared / "manifests" / "pimples.json").read_text(encoding="utf-8"))
    split = "test" if args.final_test else "val"
    photos = [i for i in manifest["images"] if i["split"] == split]
    if split == "test":
        print("FINAL TEST: the test photos are scored once, for the chosen model only")
        frozen = prepared / "corrections" / "missed_pimples_frozen.json"
        extra = added_boxes(json.loads(frozen.read_text(encoding="utf-8")))
        photos = [{**p, "boxes": p["boxes"] + [{"box": b} for b in extra.get(p["file"], [])]}
                  for p in photos]  # fmt: skip
    photos = sorted(photos, key=lambda p: p["file"])[: args.limit]
    sources = config.data_dir() / "sources"

    report = {"split": split, "photos": len(photos), "when": datetime.now().isoformat(),
              "models": {}}  # fmt: skip
    for name, path, mode in args.model:
        model = YOLO(str(path))
        for phone in ((False,) if args.no_phone else (False, True)):
            started = time.time()
            result = evaluate(model, mode, photos, sources, phone, args.device)
            result["seconds"] = round(time.time() - started)
            key = f"{name} ({'phone-like' if phone else 'original'})"
            report["models"][key] = {"file": str(path), "mode": mode, **result}
            print(f"{key:24} AP50 {result['AP50']:.3f}  P {result['precision']:.3f}  "
                  f"R {result['recall']:.3f} @ {result['cutoff']:.2f}  "
                  f"recall by size {[v['recall'] for v in result['recall_by_size'].values()]}  "
                  f"count bias {result['count_mean_bias']:+.1f}  ({result['seconds']} s)",
                  flush=True)  # fmt: skip

    out = prepared / "yolo_evaluations"
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"compare_{split}_{datetime.now():%Y%m%d_%H%M%S}.json"
    target.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(f"-> {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
