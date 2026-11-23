r"""Part 4.2: the U-Net training data, made once on the development laptop (2026-11-23).

    cd ml; .venv\Scripts\activate; $env:PYTHONPATH = "."
    python scripts/export_unet_data.py

For every photo of segmentation.json with a YuNet face: the U-Net face crop
(segmentation_data.CROP_MARGINS), its labels (wrinkles from FFHQ-Wrinkle, dark spots from MEMI-DS
with the checked ignore zones; the other channel unknown), both shrunk to a 640 px longest side.
Writes prepared/unet_data/ (images/*.jpg, labels/*.png, index.json with every file's SHA-256):
this folder is what goes to the GPU laptop. Photos without a face are left out (listed).
"""

import hashlib
import json
import sys
from collections import Counter
from datetime import datetime

import cv2

from skincare_ml import config
from skincare_ml.faces import FaceDetector
from skincare_ml.segmentation_data import known_dark_spots, load_sample, unet_crop_box
from skincare_ml.unet_data import STORED_SIDE, encode_labels, shrink

YUNET = "face_detection_yunet_2023mar.onnx"


def sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    data_dir = config.data_dir()
    manifest = json.loads((config.prepared_dir() / "manifests" / "segmentation.json")
                          .read_text(encoding="utf-8"))  # fmt: skip
    detector = FaceDetector(config.kit_dir() / "models" / YUNET)
    out = config.prepared_dir() / "unet_data"
    if (out / "index.json").exists():
        print(f"{out} already exists: delete it first to export again", file=sys.stderr)
        return 1
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "labels").mkdir(parents=True, exist_ok=True)

    items, without_face = [], []
    for count, entry in enumerate(manifest["images"], 1):
        sample = load_sample(entry, data_dir)
        faces = detector.detect(sample.image)
        if not faces:
            without_face.append(entry["file"])
            continue
        face = faces[0]
        height, width = sample.image.shape[:2]
        left, top, right, bottom = unet_crop_box(face, width, height)
        if entry["source"] == "ffhq_wrinkle":
            labels = encode_labels(sample.image.shape, wrinkles=sample.wrinkles)
        else:
            known = known_dark_spots(face, entry["view"], sample.dark_spots)
            labels = encode_labels(sample.image.shape, dark_spots=sample.dark_spots, known_dark=known)
        crop, marks = shrink(sample.image[top:bottom, left:right], labels[top:bottom, left:right],
                             STORED_SIDE)  # fmt: skip
        stem = f"{'ffhq' if entry['source'] == 'ffhq_wrinkle' else 'memi'}_" + \
            entry["file"].rsplit("/", 1)[1].rsplit(".", 1)[0]  # fmt: skip
        image_path, label_path = out / "images" / f"{stem}.jpg", out / "labels" / f"{stem}.png"
        cv2.imwrite(str(image_path), crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
        cv2.imwrite(str(label_path), marks)
        items.append({"file": entry["file"], "source": entry["source"], "split": entry["split"],
                      "view": entry.get("view"), "image": f"images/{stem}.jpg",
                      "labels": f"labels/{stem}.png", "size": [crop.shape[1], crop.shape[0]],
                      "image_sha256": sha256(image_path),
                      "labels_sha256": sha256(label_path)})  # fmt: skip
        if count % 100 == 0:
            print(f"  {count}/{len(manifest['images'])}", flush=True)

    counts = Counter((i["source"], i["split"]) for i in items)
    index = {"when": datetime.now().isoformat(), "stored_side": STORED_SIDE,
             "label_channels": "OpenCV channel 0 = wrinkles, 1 = dark spots; 0 no, 1 yes, 255 unknown",
             "counts": {f"{s} {p}": n for (s, p), n in sorted(counts.items())},
             "without_face": without_face, "items": items}  # fmt: skip
    (out / "index.json").write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(index["counts"], indent=1), f"\nwithout a face: {len(without_face)}")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
