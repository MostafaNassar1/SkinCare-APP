r"""Train the pimple finder (Ultralytics YOLO11) on the exported dataset.

On the GPU laptop:
    cd ml; .venv\Scripts\activate; $env:PYTHONPATH = "."
    python scripts/train_yolo.py
Here, only to prove the pipeline works (a few photos, one epoch, CPU; not a usable model):
    python scripts/train_yolo.py --smoke

Settings (decided 2026-11-03):
- yolo11s (small): a good balance of accuracy and speed for a CPU server later.
- 1,280 px images: the median pimple is ~42 px on a ~3,300 px photo, so ~16 px at 1,280.
- batch -1: Ultralytics measures the GPU and picks the largest batch that fits (GPU unknown yet).
- Augmentation: no hue shift (hsv_h = 0) and a gentler saturation change than the default: the
  colour of a spot is information; no upside-down flips (faces are upright in selfies).
- Early stop after 25 epochs without improvement on the validation photos; fixed seed.
Runs are saved in C:\SkinCareData\prepared\yolo_runs\ (never in the repository).
"""

import argparse
import sys

from skincare_ml import config

SETTINGS = {
    "imgsz": 1280,
    "epochs": 150,
    "patience": 25,
    "batch": -1,
    "seed": 2026,
    "deterministic": True,
    "hsv_h": 0.0,
    "hsv_s": 0.3,
    "hsv_v": 0.3,
    "fliplr": 0.5,
    "flipud": 0.0,
    "degrees": 0.0,
    "plots": True,
}
SMOKE = {"imgsz": 640, "epochs": 1, "batch": 2, "fraction": 0.01, "device": "cpu", "workers": 0,
         "plots": False}  # fmt: skip


def data_yaml() -> str:
    """data.yaml pointing at THIS computer's dataset folder (the GPU laptop's may differ)."""
    dataset = config.prepared_dir() / "yolo_pimples"
    if not (dataset / "images" / "train").exists():
        raise FileNotFoundError(f"{dataset} not found: run scripts/export_yolo.py first")
    target = dataset / "data_here.yaml"
    target.write_text(
        f"path: {dataset.as_posix()}\ntrain: images/train\nval: images/val\ntest: images/test\n"
        "names:\n  0: pimple\n",
        encoding="utf-8",
    )
    return str(target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train the YOLO pimple finder.")
    parser.add_argument("--model", default="yolo11s.pt")
    parser.add_argument("--smoke", action="store_true", help="tiny CPU run to test the pipeline")
    parser.add_argument("--name", default=None, help="run name (default: pimples or smoke)")
    args = parser.parse_args(argv)

    from ultralytics import YOLO  # heavy import: only when training

    settings = SETTINGS | (SMOKE if args.smoke else {})
    model = YOLO(args.model)
    model.train(
        data=data_yaml(),
        project=str(config.prepared_dir() / "yolo_runs"),
        name=args.name or ("smoke" if args.smoke else "pimples"),
        exist_ok=args.smoke,
        **settings,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
