"""The YOLO training set of the pimple finder (Phase 3 Step 3, decided 2026-11-03).

One class, "pimple": the first stage only FINDS pimples (the type model then types each one).
Every expert circle of `pimples.json` becomes a box; the test photos of the missed-pimple check
also get the student's frozen additions (prepared/corrections/missed_pimples_frozen.json).

Images are copied shrunk to MAX_SIDE px on the longest side (the originals are 3-5,000 px: slow to
load at every epoch); YOLO labels are relative to the image size, so they do not change. Training
then runs at 1,280 px. Layout (Ultralytics): images/<split>/<name>.jpg + labels/<split>/<name>.txt,
data.yaml, and test_checked.txt listing the 50 checked test photos (a second, cleaner test).
"""

import json
from pathlib import Path

from PIL import Image

MAX_SIDE = 1600
CLASS_NAMES = ("pimple",)
SPLITS = ("train", "val", "test")


def yolo_line(box: list[float], width: int, height: int) -> str:
    """'0 cx cy w h', relative to the image (0-1), clipped to the photo."""
    x1, y1 = max(box[0], 0.0), max(box[1], 0.0)
    x2, y2 = min(box[2], float(width)), min(box[3], float(height))
    cx, cy = (x1 + x2) / 2 / width, (y1 + y2) / 2 / height
    w, h = (x2 - x1) / width, (y2 - y1) / height
    return f"0 {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"


def added_boxes(frozen: dict | None) -> dict[str, list[list[float]]]:
    """photo -> boxes around the student's added circles (x, y, r)."""
    if not frozen:
        return {}
    return {
        photo: [[c["x"] - c["r"], c["y"] - c["r"], c["x"] + c["r"], c["y"] + c["r"]]
                for c in circles]
        for photo, circles in frozen["added"].items()
    }  # fmt: skip


def label_lines(image: dict, extra: dict[str, list[list[float]]]) -> list[str]:
    boxes = [b["box"] for b in image["boxes"]]
    if image["split"] == "test":  # the additions are test corrections only
        boxes += extra.get(image["file"], [])
    return [yolo_line(box, image["width"], image["height"]) for box in boxes]


def export(manifest: dict, sources: Path, out: Path, frozen_additions: dict | None) -> dict:
    """Write the YOLO dataset; returns counts per split. Refuses to write into an existing one."""
    if out.exists():
        raise FileExistsError(f"{out} already exists; delete it to export again")
    extra = added_boxes(frozen_additions)
    counts = {split: {"images": 0, "boxes": 0} for split in SPLITS}
    checked = []
    for image in manifest["images"]:
        split, name = image["split"], Path(image["file"]).stem
        lines = label_lines(image, extra)
        image_path = out / "images" / split / f"{name}.jpg"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(sources / image["file"]) as photo:
            photo = photo.convert("RGB")
            photo.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
            photo.save(image_path, "JPEG", quality=95)
        label_path = out / "labels" / split / f"{name}.txt"
        label_path.parent.mkdir(parents=True, exist_ok=True)
        label_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        counts[split]["images"] += 1
        counts[split]["boxes"] += len(lines)
        if split == "test" and frozen_additions and image["file"] in frozen_additions["added"]:
            checked.append(image_path.relative_to(out).as_posix())
    (out / "test_checked.txt").write_text("\n".join(f"./{p}" for p in checked) + "\n")
    names = "\n".join(f"  {i}: {n}" for i, n in enumerate(CLASS_NAMES))
    (out / "data.yaml").write_text(
        f"path: {out.as_posix()}\ntrain: images/train\nval: images/val\ntest: images/test\n"
        f"names:\n{names}\n",
        encoding="utf-8",
    )
    counts["test_checked"] = len(checked)
    (out / "export.json").write_text(json.dumps(counts, indent=1) + "\n", encoding="utf-8")
    return counts
