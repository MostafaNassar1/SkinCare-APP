r"""Part 4.1: look at the U-Net data before designing anything (decided 2026-11-22).

    cd ml; .venv\Scripts\activate; $env:PYTHONPATH = "."
    python scripts/inspect_segmentation.py

For every photo of segmentation.json (1,000 FFHQ-Wrinkle + 131 MEMI-DS) it checks:
- YuNet: is exactly one face found, and how big is it (pixels)?
- the face crop the app will use (20% margin): how much of the mask survives it?
- the share of the face covered (first idea of the severity range);
- wrinkles: the width of the lines, and how many wrinkle pixels survive when the face crop is
  shrunk to 256 ... 1,024 px (decides the input size of the U-Net);
- MEMI: where each region (forehead, nose, chin, cheeks) lies relative to the face box (decides
  how the unknown regions are ignored in training), the patches' size and count.
Writes prepared/reports/segmentation_inspection.json (summary + every photo) and a few overlay
pictures in prepared/reports/segmentation_overlays/ (never committed: they show faces).
"""

import json
import sys
from collections import Counter
from datetime import datetime

import cv2
import numpy as np

from skincare_ml import config
from skincare_ml.faces import FaceDetector, crop_box
from skincare_ml.segmentation_data import (
    REGIONS,
    kept_at_size,
    line_width,
    load_sample,
    patches,
    relative_spread,
    share_inside,
)

SIZES = (256, 384, 512, 768, 1024)
MARGIN = 0.2
YUNET = "face_detection_yunet_2023mar.onnx"
OVERLAYS_PER_SOURCE = 6
LANDMARKS = ("right_eye", "left_eye", "nose_tip", "mouth_right", "mouth_left")


def overlay(image: np.ndarray, mask: np.ndarray, box, colour=(0, 255, 255)) -> np.ndarray:
    """The face crop with the marked pixels painted, shrunk to 900 px."""
    left, top, right, bottom = box
    crop = image[top:bottom, left:right].copy()
    painted = crop.copy()
    painted[mask[top:bottom, left:right] > 0] = colour
    out = cv2.addWeighted(crop, 0.45, painted, 0.55, 0)
    scale = 900 / max(out.shape[:2])
    return cv2.resize(out, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)


def inspect(entry: dict, detector: FaceDetector, data_dir) -> tuple[dict, np.ndarray | None]:
    sample = load_sample(entry, data_dir)
    height, width = sample.image.shape[:2]
    mask = sample.wrinkles if sample.wrinkles is not None else sample.dark_spots
    faces = detector.detect(sample.image)
    row = {"file": entry["file"], "source": entry["source"], "split": entry["split"],
           "view": entry.get("view"), "photo": [width, height], "faces": len(faces),
           "marked_pixels": int(mask.sum())}  # fmt: skip
    if not faces:
        return row, None
    face = faces[0]
    box = crop_box(face, width, height, MARGIN)
    left, top, right, bottom = box
    crop_mask = mask[top:bottom, left:right]
    face_area = face.width * face.height
    row |= {
        "face_width": round(face.width),
        "crop": [right - left, bottom - top],
        "kept_in_crop": share_inside(mask, box),
        "percent_of_face": round(float(crop_mask.sum()) / face_area * 100, 3),
        "kept_at_size": {str(s): kept_at_size(crop_mask, s) for s in SIZES},
        "landmarks": {name: [round((x - face.x) / face.width, 2), round((y - face.y) / face.height, 2)]
                      for name, (x, y) in zip(LANDMARKS, face.landmarks, strict=True)},
    }  # fmt: skip
    if sample.wrinkles is not None:
        row["line_width_px"] = line_width(crop_mask)
    else:
        row["regions"] = {}
        for number, region in enumerate(REGIONS, 1):
            region_mask = (sample.regions == number).astype(np.uint8)
            if region_mask.any():
                row["regions"][region] = {"spread": relative_spread(region_mask, face),
                                          **patches(region_mask, face_area)}  # fmt: skip
    return row, overlay(sample.image, mask, box)


def median(values) -> float | None:
    values = [v for v in values if v is not None]
    return round(float(np.median(values)), 3) if values else None


def percentiles(values, points=(5, 50, 95)) -> list | None:
    values = [v for v in values if v is not None]
    return [round(float(v), 3) for v in np.percentile(values, points)] if values else None


def summarise(rows: list[dict]) -> dict:
    out = {}
    for source in ("ffhq_wrinkle", "memi_ds"):
        mine = [r for r in rows if r["source"] == source]
        found = [r for r in mine if r["faces"]]
        s = {
            "photos": len(mine),
            "faces_found": dict(sorted(Counter(min(r["faces"], 2) for r in mine).items())),
            "face_width_px": percentiles([r["face_width"] for r in found]),
            "kept_in_crop": percentiles([r["kept_in_crop"] for r in found], (1, 5, 50)),
            "photos_losing_over_5pct_in_crop": sum(1 for r in found if (r["kept_in_crop"] or 1) < 0.95),
            "percent_of_face": percentiles([r["percent_of_face"] for r in found]),
            "kept_at_size_median": {str(z): median(r["kept_at_size"][str(z)] for r in found)
                                    for z in SIZES},
            "kept_at_size_p10": {str(z): percentiles([r["kept_at_size"][str(z)] for r in found], (10,))[0]
                                 for z in SIZES},
        }  # fmt: skip
        if source == "ffhq_wrinkle":
            s["line_width_px"] = percentiles([r.get("line_width_px") for r in found])
        else:
            s["regions"] = {}
            for region in REGIONS:
                spreads = [r["regions"][region] for r in found if region in r.get("regions", {})]
                if spreads:
                    s["regions"][region] = {
                        "photos": len(spreads),
                        "x_5_95_median": [median(p["spread"]["x"][i] for p in spreads) for i in (0, 1)],
                        "y_5_95_median": [median(p["spread"]["y"][i] for p in spreads) for i in (0, 1)],
                        "patches_median": median(p["count"] for p in spreads),
                        "patch_percent_of_face_median": median(p["median_percent_of_face"] for p in spreads),
                    }  # fmt: skip
            s["views"] = dict(Counter(r["view"] for r in mine))
            s["landmarks_median"] = {
                name: [median(r["landmarks"][name][i] for r in found) for i in (0, 1)]
                for name in LANDMARKS
            }
        out[source] = s
    return out


def main() -> int:
    data_dir = config.data_dir()
    manifest = json.loads((config.prepared_dir() / "manifests" / "segmentation.json")
                          .read_text(encoding="utf-8"))  # fmt: skip
    detector = FaceDetector(config.kit_dir() / "models" / YUNET)
    reports = config.prepared_dir() / "reports"
    overlays = reports / "segmentation_overlays"
    overlays.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(2026)
    chosen = set()
    for source in ("ffhq_wrinkle", "memi_ds"):
        files = [e["file"] for e in manifest["images"] if e["source"] == source]
        chosen |= set(rng.choice(files, OVERLAYS_PER_SOURCE, replace=False).tolist())

    rows = []
    for count, entry in enumerate(manifest["images"], 1):
        row, picture = inspect(entry, detector, data_dir)
        rows.append(row)
        if picture is not None and entry["file"] in chosen:
            name = entry["file"].rsplit("/", 1)[1].rsplit(".", 1)[0]
            cv2.imwrite(str(overlays / f"{entry['source']}_{name}.jpg"), picture)
        if count % 100 == 0:
            print(f"  {count}/{len(manifest['images'])}", flush=True)

    report = {"when": datetime.now().isoformat(), "margin": MARGIN, "sizes": SIZES,
              "summary": summarise(rows), "photos": rows}  # fmt: skip
    target = reports / "segmentation_inspection.json"
    target.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=1))
    print(f"-> {target}\n-> {overlays}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
