"""Tiles of the full-resolution photos for fine-tuning runs B and C (decided 2026-11-06).

v1 saw whole photos shrunk to 1,280 px, where half the pimples are under 16 px (its main
weakness). Here every ORIGINAL photo (3-5,000 px) is cut into overlapping TILE x TILE pieces at
full resolution, so a pimple keeps its real size (~30-40 px). The app will run the model the same
way, on overlapping tiles of each close-up photo (skincare_ml/tiled_predict.py).

- A box is kept in a tile when at least MIN_VISIBLE of its area is inside, clipped to the tile;
  boxes cut more than that are left out (a sliver of a pimple at the edge would teach nonsense).
- Tiles without any pimple: EMPTY_SHARE of them are kept (skin and background the model must learn
  to ignore), chosen with a fixed seed per photo.
- Phone-like copies (run C), training tiles only: each tile shrunk and enlarged again, a little
  blurred, JPEG-compressed, made brighter or darker, with at most a +/-5% warm / cool shift; never a
  hue change (redness is information). Same labels as the clean tile.
Layout: images/{train,train_phone,val}/<photo>_<x>_<y>.jpg + labels/..., as Ultralytics expects.
Validation tiles only follow training; models are compared on WHOLE validation photos
(scripts/compare_models.py). The test photos are not tiled here (they stay frozen until the end).
"""

import io
import json
import random
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

TILE = 1024
OVERLAP = 256
MIN_VISIBLE = 0.5
EMPTY_SHARE = 0.25
SPLITS = ("train", "val")


def tile_origins(length: int, tile: int = TILE, overlap: int = OVERLAP) -> list[int]:
    """Start positions covering 0..length with tiles overlapping by `overlap` (the last tile ends
    exactly at the edge, so nothing is cut off and no tile goes outside the photo)."""
    if length <= tile:
        return [0]
    stride = tile - overlap
    starts = list(range(0, length - tile, stride))
    return starts + [length - tile]


def boxes_in_tile(
    boxes: list[list[float]], left: int, top: int, size_x: int, size_y: int,
    min_visible: float = MIN_VISIBLE,
) -> list[list[float]]:  # fmt: skip
    """Boxes (photo pixels) in tile coordinates, clipped, kept if enough of them is inside."""
    kept = []
    for x1, y1, x2, y2 in boxes:
        cx1, cy1 = max(x1, left), max(y1, top)
        cx2, cy2 = min(x2, left + size_x), min(y2, top + size_y)
        if cx2 <= cx1 or cy2 <= cy1:
            continue
        area = (x2 - x1) * (y2 - y1)
        if area <= 0 or (cx2 - cx1) * (cy2 - cy1) / area < min_visible:
            continue
        kept.append([cx1 - left, cy1 - top, cx2 - left, cy2 - top])
    return kept


def yolo_lines(boxes: list[list[float]], width: int, height: int) -> list[str]:
    return [
        f"0 {(x1 + x2) / 2 / width:.6f} {(y1 + y2) / 2 / height:.6f} "
        f"{(x2 - x1) / width:.6f} {(y2 - y1) / height:.6f}"
        for x1, y1, x2, y2 in boxes
    ]


def phone_like(image: Image.Image, rng: random.Random) -> Image.Image:
    """A selfie-quality version of a tile (same size, so the labels stay valid)."""
    width, height = image.size
    factor = rng.uniform(0.3, 0.6)  # a phone selfie has 2-3x fewer pixels per pimple
    small = image.resize((max(1, int(width * factor)), max(1, int(height * factor))),
                         Image.BILINEAR)  # fmt: skip
    out = small.resize((width, height), Image.BILINEAR)
    out = out.filter(ImageFilter.GaussianBlur(rng.uniform(0.0, 1.2)))
    out = ImageEnhance.Brightness(out).enhance(rng.uniform(0.7, 1.2))
    warm = rng.uniform(-0.05, 0.05)  # mild white-balance shift, never a hue change
    r, g, b = out.split()
    r = r.point(lambda v: min(255, int(v * (1 + warm))))
    b = b.point(lambda v: min(255, int(v * (1 - warm))))
    out = Image.merge("RGB", (r, g, b))
    buffer = io.BytesIO()
    out.save(buffer, "JPEG", quality=rng.randint(35, 75))
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")


def phone_photo(image: Image.Image, rng: random.Random,
                factor: float = 0.4) -> Image.Image:  # fmt: skip
    """A whole photo as a phone selfie might give it: `factor` times smaller (boxes must be
    scaled by the same factor), then blurred, compressed, brighter or darker. Used to score the
    models on selfie-like versions of the validation photos."""
    width, height = image.size
    small = image.resize((max(1, int(width * factor)), max(1, int(height * factor))),
                         Image.LANCZOS)  # fmt: skip
    small = small.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 1.0)))
    small = ImageEnhance.Brightness(small).enhance(rng.uniform(0.75, 1.15))
    buffer = io.BytesIO()
    small.save(buffer, "JPEG", quality=rng.randint(45, 75))
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")


def export_tiles(manifest: dict, sources: Path, out: Path, seed: int = 2026,
                 phone: bool = True) -> dict:  # fmt: skip
    """Write the tile dataset; returns counts. Refuses to write into an existing one."""
    if out.exists():
        raise FileExistsError(f"{out} already exists; delete it to export again")
    counts = {name: {"tiles": 0, "boxes": 0, "empty": 0} for name in (*SPLITS, "train_phone")}
    for image in manifest["images"]:
        split = image["split"]
        if split not in SPLITS:
            continue  # test photos stay whole and frozen
        rng = random.Random(f"{seed}:{image['file']}")
        boxes = [b["box"] for b in image["boxes"]]
        stem = Path(image["file"]).stem
        with Image.open(sources / image["file"]) as photo:
            photo = photo.convert("RGB")
            width, height = photo.size
            for top in tile_origins(height):
                for left in tile_origins(width):
                    size_x, size_y = min(TILE, width), min(TILE, height)
                    inside = boxes_in_tile(boxes, left, top, size_x, size_y)
                    if not inside and rng.random() >= EMPTY_SHARE:
                        continue
                    tile = photo.crop((left, top, left + size_x, top + size_y))
                    lines = yolo_lines(inside, size_x, size_y)
                    name = f"{stem}_{left}_{top}"
                    targets = [(split, tile)]
                    if phone and split == "train":
                        targets.append(("train_phone", phone_like(tile, rng)))
                    for folder, picture in targets:
                        _write(out, folder, name, picture, lines)
                        counts[folder]["tiles"] += 1
                        counts[folder]["boxes"] += len(lines)
                        counts[folder]["empty"] += not lines
    (out / "export.json").write_text(json.dumps(counts, indent=1) + "\n", encoding="utf-8")
    return counts


def _write(out: Path, folder: str, name: str, picture: Image.Image, lines: list[str]) -> None:
    image_path = out / "images" / folder / f"{name}.jpg"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    picture.save(image_path, "JPEG", quality=92)
    label_path = out / "labels" / folder / f"{name}.txt"
    label_path.parent.mkdir(parents=True, exist_ok=True)
    label_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
