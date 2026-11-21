r"""Freeze the chosen pimple finder and its settings BEFORE the final test (decided 2026-11-21).

    cd ml; .venv\Scripts\activate; $env:PYTHONPATH = "."
    python scripts/freeze_detector_settings.py `
        --predictions C:\SkinCareData\prepared\yolo_evaluations\predictions_val_<time>.pkl `
        --model-name C --weights <handoff>\runs\pimples_C\weights\best.pt

Reads the VALIDATION predictions saved by compare_models.py (face crops), fits the grade limits
on them at the count cutoff, copies the weights to C:\SkinCareData\models\yolo_pimples_final.pt
and writes C:\SkinCareData\models\pimple_detector_settings.json (with the weights' SHA-256). The
file is never overwritten: the final test reads it, and nothing is changed after the test.
"""

import argparse
import hashlib
import json
import pickle
import shutil
import sys
from datetime import datetime
from pathlib import Path

from skincare_ml import config
from skincare_ml.detector_report import describe, summarise
from skincare_ml.grading import fit_limits

SETTINGS = "pimple_detector_settings.json"
WEIGHTS = "yolo_pimples_final.pt"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for block in iter(lambda: file.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def expert_grades() -> dict[str, str]:
    manifest = config.prepared_dir() / "manifests" / "pimples.json"
    images = json.loads(manifest.read_text(encoding="utf-8"))["images"]
    return {i["file"]: i["expert_grade"] for i in images}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze the chosen pimple finder's settings.")
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--model-name", required=True, help="the model's name in the predictions")
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--mode", choices=("whole", "tiled"), default="tiled")
    parser.add_argument("--count-cutoff", type=float, default=0.13)
    parser.add_argument("--display-cutoff", type=float, default=0.20)
    parser.add_argument("--phone-factor", type=float, action="append",
                        help="selfie-like versions scored in the final test (default 0.6)")
    args = parser.parse_args(argv)

    models = config.data_dir() / "models"
    target = models / SETTINGS
    if target.exists():
        parser.error(f"{target} already exists: frozen settings are never changed")
    saved = pickle.load(open(args.predictions, "rb"))  # our own file, written by compare_models
    rows = saved["rows"]["original"][args.model_name]
    grades = expert_grades()
    counts = [int((r["scores"] >= args.count_cutoff).sum()) for r in rows]
    limits = fit_limits(counts, [grades[r["file"]] for r in rows])
    validation = summarise(rows, args.count_cutoff, args.display_cutoff, limits, grades)
    print(describe("validation (fitted here: the grade agreement is optimistic)", validation))

    models.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.weights, models / WEIGHTS)
    settings = {
        "frozen_at": datetime.now().isoformat(),
        "model": {"name": args.model_name, "file": WEIGHTS, "sha256": sha256(models / WEIGHTS),
                  "source": str(args.weights), "mode": args.mode},  # fmt: skip
        "face_crop": True,
        "display_cutoff": args.display_cutoff,
        "count_cutoff": args.count_cutoff,
        "grade_limits": {"mild_up_to": limits[0], "moderate_up_to": limits[1]},
        "final_test_phone_factors": args.phone_factor or [0.6],
        "validation": {"predictions": str(args.predictions), **validation},
    }
    target.write_text(json.dumps(settings, indent=1) + "\n", encoding="utf-8")
    print(f"-> {target} (grade limits: mild <= {limits[0]}, moderate <= {limits[1]}, severe above)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
