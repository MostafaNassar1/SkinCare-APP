r"""Export the frozen pimple finder to ONNX for the server, and prove it finds the same pimples
(decided 2026-11-22).

    cd ml; .venv\Scripts\activate; $env:PYTHONPATH = "."
    python scripts/export_onnx.py              # export + check on 20 validation faces
    python scripts/export_onnx.py --check 0    # export only

Reads C:\SkinCareData\models\pimple_detector_settings.json, checks the weights' SHA-256, writes
yolo_pimples_final.onnx next to them (1,024 x 1,024 input = one tile; opset 17; no extra
simplifier package) and yolo_pimples_final.onnx.json (its SHA-256 and the check). The check runs
PyTorch and ONNX the app's way (face crop, tiles, frozen cutoffs) on VALIDATION faces (never the
test) and compares the pimples each one counts: ONNX must find the same ones (box overlap >= 0.9,
confidence within 0.02).
"""

import argparse
import json
import os
import sys
from datetime import datetime

import numpy as np

import compare_models
from freeze_detector_settings import SETTINGS, sha256

from skincare_ml import config
from skincare_ml.detection_metrics import iou_matrix

SAME_BOX = 0.9
SAME_SCORE = 0.02


def same_detections(first, second, cutoff: float) -> dict:
    """Compare two predictions of one photo above `cutoff`: counts, boxes matched one to one
    (IoU >= SAME_BOX), the largest confidence difference and the boxes found by only one."""
    a_keep, b_keep = first.scores >= cutoff, second.scores >= cutoff
    a_boxes, b_boxes = first.boxes[a_keep], second.boxes[b_keep]
    a_scores, b_scores = first.scores[a_keep], second.scores[b_keep]
    overlaps = iou_matrix(a_boxes, b_boxes)
    taken, differences, matched = set(), [], 0
    for i in np.argsort(-a_scores, kind="stable"):
        candidates = [j for j in range(len(b_boxes)) if j not in taken and overlaps[i, j] >= SAME_BOX]
        if candidates:
            j = max(candidates, key=lambda k: overlaps[i, k])
            taken.add(j)
            matched += 1
            differences.append(abs(float(a_scores[i]) - float(b_scores[j])))
    return {"first": len(a_boxes), "second": len(b_boxes), "matched": matched,
            "unmatched": len(a_boxes) + len(b_boxes) - 2 * matched,
            "largest_score_difference": round(max(differences, default=0.0), 4)}  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the frozen pimple finder to ONNX.")
    parser.add_argument("--check", type=int, default=20, help="validation faces to compare (0 = none)")
    args = parser.parse_args(argv)

    models = config.data_dir() / "models"
    settings_file = models / SETTINGS
    if not settings_file.exists():
        parser.error("freeze the settings first (scripts/freeze_detector_settings.py)")
    settings = json.loads(settings_file.read_text(encoding="utf-8"))
    weights = models / settings["model"]["file"]
    if sha256(weights) != settings["model"]["sha256"]:
        parser.error(f"{weights} is not the frozen model (SHA-256 differs)")

    os.environ.setdefault("YOLO_AUTOINSTALL", "false")
    os.environ.setdefault("YOLO_VERBOSE", "false")
    from ultralytics import YOLO

    exported = YOLO(str(weights)).export(format="onnx", imgsz=1024, opset=17, simplify=False,
                                         dynamic=False, device="cpu")  # fmt: skip
    onnx_file = models / weights.with_suffix(".onnx").name
    print(f"exported -> {exported}")
    record = {"when": datetime.now().isoformat(), "file": onnx_file.name,
              "sha256": sha256(onnx_file), "from": settings["model"],
              "input": "1 x 3 x 1024 x 1024 (one tile), RGB 0-1",
              "check": None}  # fmt: skip

    if args.check:
        photos = compare_models.load_photos("val")
        sources = config.data_dir() / "sources"
        faces = compare_models.find_faces(photos, sources,
                                          config.kit_dir() / "models" / compare_models.YUNET)  # fmt: skip
        photos = [p for p in photos if p["file"] in faces][: args.check]
        torch_rows = compare_models.predict_rows(YOLO(str(weights)), "tiled", photos, sources,
                                                 None, "cpu", faces)  # fmt: skip
        onnx_rows = compare_models.predict_rows(YOLO(str(onnx_file), task="detect"), "tiled",
                                                photos, sources, None, "cpu", faces)  # fmt: skip
        per_photo = []
        for a, b in zip(torch_rows, onnx_rows, strict=True):
            first = type("D", (), {"boxes": a["pred"], "scores": a["scores"]})
            second = type("D", (), {"boxes": b["pred"], "scores": b["scores"]})
            per_photo.append(same_detections(first, second, settings["count_cutoff"]))
        record["check"] = {
            "validation_faces": len(per_photo),
            "pytorch_pimples": sum(p["first"] for p in per_photo),
            "onnx_pimples": sum(p["second"] for p in per_photo),
            "unmatched": sum(p["unmatched"] for p in per_photo),
            "largest_score_difference": max(p["largest_score_difference"] for p in per_photo),
        }
        record["check"]["same"] = (record["check"]["unmatched"] == 0 and
                                   record["check"]["largest_score_difference"] <= SAME_SCORE)  # fmt: skip
        print(f"check on {len(per_photo)} validation faces: {record['check']}")

    target = models / (onnx_file.name + ".json")
    target.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    print(f"-> {target}")
    return 0 if record["check"] is None or record["check"]["same"] else 1


if __name__ == "__main__":
    sys.exit(main())
