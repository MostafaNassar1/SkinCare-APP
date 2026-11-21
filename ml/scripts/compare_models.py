r"""Score pimple-finder models the same way on whole VALIDATION photos (decided 2026-11-06).

    cd ml; .venv\Scripts\activate; $env:PYTHONPATH = "."
    python scripts/compare_models.py --model v1=yolo_pimples_v1.pt:whole `
        --model B=yolo_pimples_B.pt:tiled
    python scripts/compare_models.py --model v1=yolo_pimples_v1.pt:whole --limit 20   # quick look
    python scripts/compare_models.py --face-crop --phone-factor 0.4 --phone-factor 0.6 `
        --model A=...:whole --model C=...:tiled --model C-whole=...:whole   # as in the app

Each model is NAME=FILE:MODE, FILE in C:\SkinCareData\models (or a full path), MODE "whole" (the
photo shrunk to 1,280 px: v1, run A) or "tiled" (1,024 px tiles at full resolution: runs B, C).
Every model is scored on the ORIGINAL validation photos (photo pixels, skincare_ml/
detection_metrics.py) and on phone-like versions of them (--phone-factor times the size, blurred,
compressed: roughly a selfie; 0.4 by default), each at its own best-F1 cutoff.
--face-crop (added 2026-11-21) scores what the app will see: only the face found by YuNet (plus a
20% margin), and only the expert boxes inside it; photos where YuNet finds no face are left out
(the app would ask for another photo). The face is found once on the original photo, so every
version and every model is scored on exactly the same photos and boxes.
Bootstrap 95% ranges (1,000 draws of the photos, paired between models) show which differences are
real. The test photos need --final-test: they are used ONCE, for the chosen model, never to choose
between models.
Writes C:\SkinCareData\prepared\yolo_evaluations\compare_<split>_<time>.json (+ the raw
predictions as .pkl, to redo the analysis without rerunning the models) and prints a table.
"""

import argparse
import json
import os
import pickle
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

from skincare_ml import config
from skincare_ml.detection_metrics import bootstrap, score
from skincare_ml.tiled_predict import predict_tiled, predict_whole
from skincare_ml.yolo_data import added_boxes
from skincare_ml.yolo_tiles import phone_photo

FLOOR = 0.01  # lowest confidence kept, so the precision-recall curve is complete enough
PHONE_FACTOR = 0.4
FACE_MARGIN = 0.2
YUNET = "face_detection_yunet_2023mar.onnx"


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


def crop_to_face(photo: Image.Image, truth: np.ndarray, face: list[float],
                 factor: float = 1.0) -> tuple[Image.Image, np.ndarray]:  # fmt: skip
    """The face area (`face` in ORIGINAL photo pixels, scaled by `factor` for a phone version) and
    the expert boxes whose centre is inside it, moved to the crop's pixels and cut at its edge."""
    left, top, right, bottom = (round(v * factor) for v in face)
    right, bottom = min(right, photo.width), min(bottom, photo.height)
    centre_x = (truth[:, 0] + truth[:, 2]) / 2
    centre_y = (truth[:, 1] + truth[:, 3]) / 2
    inside = (centre_x >= left) & (centre_x < right) & (centre_y >= top) & (centre_y < bottom)
    moved = truth[inside] - np.array([left, top, left, top], dtype=float)
    moved = np.clip(moved, 0, [right - left, bottom - top] * 2)
    return photo.crop((left, top, right, bottom)), moved.reshape(-1, 4)


def find_faces(photos: list[dict], sources: Path, model_path: Path) -> dict[str, list[float]]:
    """file -> face box (left, top, right, bottom with the margin, original pixels), for the
    photos where YuNet finds a face (the most confident one)."""
    import cv2

    from skincare_ml.faces import FaceDetector, crop_box

    detector = FaceDetector(model_path)
    faces = {}
    for image in photos:
        picture = cv2.imread(str(sources / image["file"]))
        found = detector.detect(picture) if picture is not None else []
        if found:
            height, width = picture.shape[:2]
            faces[image["file"]] = list(crop_box(found[0], width, height, FACE_MARGIN))
    return faces


def predict_rows(model, mode: str, photos: list[dict], sources: Path, phone: float | None,
                 device, faces: dict | None = None) -> list[dict]:  # fmt: skip
    """Predictions + expert boxes of every photo (in the pixels of the picture the model saw)."""
    rows = []
    for image in photos:
        with Image.open(sources / image["file"]) as photo:
            photo = photo.convert("RGB")
        truth = np.array([b["box"] for b in image["boxes"]], dtype=float).reshape(-1, 4)
        factor = 1.0
        if phone:
            factor = phone
            photo = phone_photo(photo, random.Random(f"phone:{image['file']}"), factor)
            truth = truth * factor
        if faces is not None:
            photo, truth = crop_to_face(photo, truth, faces[image["file"]], factor)
        if mode == "whole":
            found = predict_whole(model, photo, FLOOR, device=device)
        else:
            found = predict_tiled(model, photo, FLOOR, device=device)
        rows.append({"file": image["file"], "pred": found.boxes, "scores": found.scores,
                     "truth": truth, "expert_count": image.get("original_lesion_count")})  # fmt: skip
    return rows


def score_rows(rows: list[dict]) -> dict:
    result = score(rows)
    predicted = [int((r["scores"] >= result["cutoff"]).sum()) for r in rows]
    known = [(p, r["expert_count"]) for p, r in zip(predicted, rows, strict=True)
             if r["expert_count"] is not None]  # fmt: skip
    result["count_vs_acne04_expert_count_spearman"] = spearman(*zip(*known)) if known else None
    return result


def evaluate(model, mode: str, photos: list[dict], sources: Path, phone=False, device=None,
             faces: dict | None = None) -> dict:  # fmt: skip
    factor = PHONE_FACTOR if phone is True else (phone or None)
    return score_rows(predict_rows(model, mode, photos, sources, factor, device, faces))


def condition_name(factor: float | None) -> str:
    return "original" if factor is None else f"phone x{factor:g}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare pimple-finder models on validation.")
    parser.add_argument("--model", type=parse_model, action="append", required=True)
    parser.add_argument("--limit", type=int, help="only the first N photos (a quick look)")
    parser.add_argument("--no-phone", action="store_true", help="skip the phone-like versions")
    parser.add_argument("--phone-factor", type=float, action="append",
                        help="size of the phone-like versions (repeatable; default 0.4)")
    parser.add_argument("--face-crop", action="store_true",
                        help="score only the face found by YuNet, as the app will")
    parser.add_argument("--bootstrap", type=int, default=1000,
                        help="draws for the 95%% ranges (0 = none)")
    parser.add_argument("--final-test", action="store_true",
                        help="score the TEST photos (once, for the chosen model only)")
    parser.add_argument("--device", default=None, help="e.g. cpu or 0 (default: automatic)")
    args = parser.parse_args(argv)
    factors = args.phone_factor or [PHONE_FACTOR]
    if any(not 0 < f <= 1 for f in factors):
        parser.error("--phone-factor must be between 0 and 1")

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

    faces = None
    report = {"split": split, "when": datetime.now().isoformat(), "face_crop": args.face_crop,
              "models": {}}  # fmt: skip
    if args.face_crop:
        faces = find_faces(photos, sources, config.kit_dir() / "models" / YUNET)
        report["photos_without_a_face"] = len(photos) - len(faces)
        photos = [p for p in photos if p["file"] in faces]
        print(f"face found on {len(photos)} photos ({report['photos_without_a_face']} left out)")
    report["photos"] = len(photos)

    conditions = [None] + ([] if args.no_phone else factors)
    rows = {condition_name(c): {} for c in conditions}
    cutoffs = {condition_name(c): {} for c in conditions}
    for name, path, mode in args.model:
        model = YOLO(str(path))
        for factor in conditions:
            started = time.time()
            found = predict_rows(model, mode, photos, sources, factor, args.device, faces)
            result = score_rows(found)
            result["seconds"] = round(time.time() - started)
            condition = condition_name(factor)
            rows[condition][name] = found
            cutoffs[condition][name] = result["cutoff"]
            key = f"{name} ({condition})"
            report["models"][key] = {"file": str(path), "mode": mode, **result}
            print(f"{key:24} AP50 {result['AP50']:.3f}  P {result['precision']:.3f}  "
                  f"R {result['recall']:.3f} @ {result['cutoff']:.2f}  "
                  f"recall by size {[v['recall'] for v in result['recall_by_size'].values()]}  "
                  f"count bias {result['count_mean_bias']:+.1f}  ({result['seconds']} s)",
                  flush=True)  # fmt: skip

    if args.bootstrap > 0:
        report["bootstrap"] = {}
        for condition, by_model in rows.items():
            ranges = bootstrap(by_model, cutoffs[condition], rounds=args.bootstrap)
            report["bootstrap"][condition] = ranges
            print(f"\n95% ranges ({condition}, {ranges['rounds']} draws of the photos)")
            for name, values in ranges["models"].items():
                print(f"  {name:10} AP50 {values['AP50']}  P {values['precision']}  "
                      f"R {values['recall']}")
            for pair, values in ranges["pairs"].items():
                print(f"  {pair:20} AP50 difference {values['AP50_difference_95']}  "
                      f"first better in {values['first_better_share']:.0%} of draws")

    out = prepared / "yolo_evaluations"
    out.mkdir(parents=True, exist_ok=True)
    stamp = f"{split}_{datetime.now():%Y%m%d_%H%M%S}"
    target = out / f"compare_{stamp}.json"
    target.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    with open(out / f"predictions_{stamp}.pkl", "wb") as file:
        pickle.dump({"rows": rows, "cutoffs": cutoffs}, file)
    print(f"-> {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
