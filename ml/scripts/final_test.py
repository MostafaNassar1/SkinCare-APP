r"""The ONE-TIME final test of the chosen pimple finder (decided 2026-11-21).

    cd ml; .venv\Scripts\activate; $env:PYTHONPATH = "."
    python scripts/final_test.py --device cpu

Uses only the frozen C:\SkinCareData\models\pimple_detector_settings.json (written by
freeze_detector_settings.py from VALIDATION) and checks the weights' SHA-256 against it. Scores the
TEST photos (with the student's frozen missed-pimple additions) as the app will see them: YuNet
face crop, the frozen mode and cutoffs, original quality + the selfie-like versions. Nothing is
tuned here. It refuses to run a second time (a test used twice is no longer a test); the result
is C:\SkinCareData\prepared\yolo_evaluations\final_test_<time>.json.
"""

import argparse
import json
import os
import sys
from datetime import datetime

import compare_models
from freeze_detector_settings import SETTINGS, expert_grades, sha256

from skincare_ml import config
from skincare_ml.detector_report import describe, summarise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One-time final test of the chosen model.")
    parser.add_argument("--device", default=None, help="e.g. cpu or 0 (default: automatic)")
    args = parser.parse_args(argv)

    models = config.data_dir() / "models"
    settings_file = models / SETTINGS
    if not settings_file.exists():
        parser.error("freeze the settings first (scripts/freeze_detector_settings.py)")
    settings = json.loads(settings_file.read_text(encoding="utf-8"))
    weights = models / settings["model"]["file"]
    if sha256(weights) != settings["model"]["sha256"]:
        parser.error(f"{weights} is not the frozen model (SHA-256 differs)")
    out = config.prepared_dir() / "yolo_evaluations"
    if list(out.glob("final_test_*.json")):
        parser.error("the final test has already been run: its result stands")

    os.environ.setdefault("YOLO_AUTOINSTALL", "false")
    os.environ.setdefault("YOLO_VERBOSE", "false")
    from ultralytics import YOLO

    print("FINAL TEST: the test photos are scored once, with the frozen settings")
    photos = compare_models.load_photos("test")
    sources = config.data_dir() / "sources"
    faces = compare_models.find_faces(photos, sources,
                                      config.kit_dir() / "models" / compare_models.YUNET)  # fmt: skip
    without_face = len(photos) - len(faces)
    photos = [p for p in photos if p["file"] in faces]
    print(f"face found on {len(photos)} test photos ({without_face} left out)")
    model = YOLO(str(weights))
    limits = (settings["grade_limits"]["mild_up_to"], settings["grade_limits"]["moderate_up_to"])
    grades = expert_grades()
    report = {"when": datetime.now().isoformat(), "settings": str(settings_file),
              "model": settings["model"], "photos_without_a_face": without_face,
              "conditions": {}}  # fmt: skip
    for factor in [None, *settings["final_test_phone_factors"]]:
        rows = compare_models.predict_rows(model, settings["model"]["mode"], photos, sources,
                                           factor, args.device, faces)  # fmt: skip
        name = compare_models.condition_name(factor)
        summary = summarise(rows, settings["count_cutoff"], settings["display_cutoff"], limits,
                            grades)  # fmt: skip
        report["conditions"][name] = summary
        print(describe(name, summary), flush=True)

    out.mkdir(parents=True, exist_ok=True)
    target = out / f"final_test_{datetime.now():%Y%m%d_%H%M%S}.json"
    target.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(f"-> {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
