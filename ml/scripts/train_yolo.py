r"""Train the pimple finder (Ultralytics YOLO11): v1, then the fine-tuning runs A, B and C.

On the GPU laptop (see ml/TRAINING_GPU.md):
    cd ml; .venv\Scripts\activate; $env:PYTHONPATH = "."
    python scripts/train_yolo.py --run A --epoch-confidence
    python scripts/train_yolo.py --run B --epoch-confidence
    python scripts/train_yolo.py --run C --epoch-confidence
Here, only to prove a run's pipeline works (a few images, one epoch, CPU; not a usable model):
    python scripts/train_yolo.py --run B --smoke

Runs (each one change, chosen later on VALIDATION only; decided 2026-11-06):
- v1  (done 2026-11-05 on an RTX 5070 Laptop, 8 GB): yolo11s from the COCO-pretrained weights,
  whole photos shrunk to 1,280 px, automatic batch (it fell back to 1), AdamW lr 0.0025, 150 epochs.
  Validation mAP50 0.506, test 0.497 (recall 0.45): half the pimples are under 16 px at 1,280.
- A: continue from v1 with a FIXED batch of 4 (batch 1 weakens the normalisation layers), lower lr.
- B: continue from v1 on TILES of the full-resolution photos (1,024 px pieces, pimples at their real
  size of ~30-40 px instead of ~16): the strongest known fix for tiny objects.
- C: as B, plus "phone-like" copies of every training tile (blur, shrink, JPEG, brightness), so the
  model also learns selfie-quality pimples.
Shared settings (decided 2026-11-03): no hue shift and a gentler saturation change (the colour of a
spot is information), no upside-down flips, fixed seed. Runs are saved in
C:\SkinCareData\prepared\yolo_runs\ (never in the repository); weights in C:\SkinCareData\models.
If a run stops with "CUDA out of memory", rerun it with --batch 2.
"""

import argparse
import math
import os
import sys

from skincare_ml import config

SHARED = {
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
FINE_TUNE = {"epochs": 60, "patience": 20, "lr0": 0.001, "warmup_epochs": 1.0, "batch": 4}
# tiles: 11,403 training tiles (22,806 with the phone copies) instead of 818 photos, so one epoch
# shows the model ~9x (C: ~18x) more pimples: far fewer epochs are needed (2026-11-06)
TILE_TUNE = FINE_TUNE | {"epochs": 20, "patience": 8, "close_mosaic": 5, "imgsz": 1024}
# run -> (dataset folder, starting weights in C:\SkinCareData\models, phone copies, settings)
RUNS = {
    "v1": ("yolo_pimples", "yolo11s.pt", False,
           {"imgsz": 1280, "epochs": 150, "patience": 25, "batch": -1, "lr0": 0.0025}),
    "A": ("yolo_pimples", "yolo_pimples_v1.pt", False, FINE_TUNE | {"imgsz": 1280}),
    "B": ("yolo_pimples_tiles", "yolo_pimples_v1.pt", False, TILE_TUNE),
    "C": ("yolo_pimples_tiles", "yolo_pimples_v1.pt", True, TILE_TUNE),
}  # fmt: skip
SMOKE = {"epochs": 1, "batch": 2, "fraction": 0.01, "device": "cpu", "workers": 0, "plots": False,
         "imgsz": 640, "val": False}  # fmt: skip  (validation was proven by v1's smoke run)


def data_yaml(dataset_name: str, phone_copies: bool = False) -> str:
    """data.yaml pointing at THIS computer's dataset folder (the GPU laptop's may differ)."""
    dataset = config.prepared_dir() / dataset_name
    if not (dataset / "images" / "train").exists():
        raise FileNotFoundError(f"{dataset} not found: export it first (see TRAINING_GPU.md)")
    train = "images/train"
    if phone_copies:
        if not (dataset / "images" / "train_phone").exists():
            raise FileNotFoundError(f"{dataset}/images/train_phone not found: export the copies")
        train = "\n  - images/train\n  - images/train_phone"  # both folders
    target = dataset / ("data_here_phone.yaml" if phone_copies else "data_here.yaml")
    target.write_text(
        f"path: {dataset.as_posix()}\ntrain: {train}\nval: images/val\n"
        "names:\n  0: pimple\n",
        encoding="utf-8",
    )
    return str(target)


def starting_weights(name: str):
    """Starting weights, kept in C:/SkinCareData/models (Ultralytics downloads them into the
    current folder, which would be inside the repository)."""
    folder = config.data_dir() / "models"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / name
    if not target.exists():
        if not name.startswith("yolo11"):
            raise FileNotFoundError(f"{target} not found (copy it there first)")
        from ultralytics.utils.downloads import attempt_download_asset

        here = os.getcwd()
        os.chdir(folder)  # the download lands in the current folder
        try:
            attempt_download_asset(name)
        finally:
            os.chdir(here)
    return target


def run_settings(run: str, smoke: bool = False, batch: int | None = None,
                 lr: float | None = None) -> dict:  # fmt: skip
    """Every setting of a run, as passed to Ultralytics."""
    settings = SHARED | RUNS[run][3]
    # explicit AdamW so the requested lr is applied (Ultralytics' automatic choice ignores lr0);
    # momentum and bias warmup as its automatic AdamW (as used for v1 on 2026-11-05)
    settings |= {"optimizer": "AdamW", "momentum": 0.9, "warmup_bias_lr": 0.0}
    if lr is not None:
        settings["lr0"] = lr
    if batch is not None:
        settings["batch"] = batch
    if smoke:
        settings |= SMOKE
    return settings


def print_epoch_confidence(trainer) -> None:
    """One summary per saved epoch, with the confidence cutoff of the best validation F1
    (added on the GPU laptop, 2026-11-05)."""
    from ultralytics.utils.metrics import smooth

    box = trainer.validator.metrics.box
    f1_curve = getattr(box, "f1_curve", None)
    confidence = "n/a"
    if f1_curve is not None and f1_curve.size and f1_curve.max() > 0:
        # the smoothed F1 peak Ultralytics uses to report precision and recall
        best_index = smooth(f1_curve.mean(axis=0), 0.1).argmax()
        confidence = f"{box.px[best_index]:.3f}"
    losses = trainer.label_loss_items(trainer.tloss)
    summary = (
        f"Epoch {trainer.epoch + 1}/{trainer.epochs} | "
        f"lr={trainer.optimizer.param_groups[0]['lr']:.6f} | "
        f"box_loss={losses['train/box_loss']:.3f} cls_loss={losses['train/cls_loss']:.3f} "
        f"dfl_loss={losses['train/dfl_loss']:.3f} | "
        f"val P={box.mp:.3f} R={box.mr:.3f} mAP50={box.map50:.3f} mAP50-95={box.map:.3f} | "
        f"best-F1 confidence={confidence}"
    )
    border = "#" * len(summary)
    print(f"{border}\n{summary}\n{border}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train the YOLO pimple finder.")
    parser.add_argument("--run", choices=RUNS, default="A")
    parser.add_argument("--smoke", action="store_true", help="tiny CPU run to test the pipeline")
    parser.add_argument("--batch", type=int,
                        help="override the run's batch (e.g. 2 if out of memory)")
    parser.add_argument("--lr", type=float, help="override the run's base learning rate (AdamW)")
    parser.add_argument("--name", default=None, help="run name (default: pimples_<run>)")
    parser.add_argument("--epoch-confidence", action="store_true",
                        help="only epoch summaries (with best-F1 confidence), warnings and errors")
    args = parser.parse_args(argv)
    if args.lr is not None and (not math.isfinite(args.lr) or args.lr <= 0):
        parser.error("--lr must be a finite number greater than zero")
    if args.batch is not None and args.batch < 1:
        parser.error("--batch must be at least 1")

    # never let Ultralytics pip-install missing packages at runtime: it would pull opencv-python
    # (possibly OpenCV 5, which breaks YuNet); only the pinned requirements are used
    os.environ.setdefault("YOLO_AUTOINSTALL", "false")
    if args.epoch_confidence:
        os.environ["YOLO_VERBOSE"] = "false"
    from ultralytics import YOLO  # heavy import: only when training

    if args.epoch_confidence:
        from ultralytics.utils import LOGGER

        LOGGER.setLevel("WARNING")  # also hides the batch progress bars

    dataset, weights, phone, _ = RUNS[args.run]
    model = YOLO(str(starting_weights(weights)))
    if args.epoch_confidence:
        model.add_callback("on_model_save", print_epoch_confidence)
    model.train(
        data=data_yaml(dataset, phone),
        project=str(config.prepared_dir() / "yolo_runs"),
        name=args.name or (f"smoke_{args.run}" if args.smoke else f"pimples_{args.run}"),
        exist_ok=args.smoke,
        **run_settings(args.run, args.smoke, args.batch, args.lr),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
