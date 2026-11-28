r"""Part 4.2: the U-Net training data, made once on the development laptop.

    cd ml; .venv\Scripts\activate; $env:PYTHONPATH = "."
    python scripts/export_unet_data.py                   # v2 labels -> prepared/unet_data_v2/
    python scripts/export_unet_data.py --labels v1       # the v1 data (2026-11-23) -> unet_data/

For every photo of segmentation.json with a YuNet face: the U-Net face crop
(segmentation_data.CROP_MARGINS) and its labels, both shrunk to a 640 px longest side. Wrinkles
come from FFHQ-Wrinkle (unknown on MEMI photos), dark spots from MEMI-DS with the checked ignore
zones. Label rules:
- v1: dark spots unknown on FFHQ photos. Result: the dark channel never saw a normal face and
  painted ~49% of every one (2026-11-28 check), so
- v2 (2026-11-28): FFHQ photos are "no dark patches" everywhere (assumption: FFHQ-Wrinkle faces
  were chosen for wrinkles and rarely show melasma-like patches; some small spots may be taught as
  "no", a limitation stated in DATASETS.md). The padding rule is in unet_data.place.
Writes images/*.jpg, labels/*.png and index.json (every file's SHA-256). Photos without a face are
left out (listed).
"""

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime

import cv2
import numpy as np

from skincare_ml import config
from skincare_ml.faces import FaceDetector
from skincare_ml.segmentation_data import known_dark_spots, load_sample, unet_crop_box
from skincare_ml.unet_data import STORED_SIDE, encode_labels, shrink

YUNET = "face_detection_yunet_2023mar.onnx"


def sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


FOLDERS = {"v1": "unet_data", "v2": "unet_data_v2"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the U-Net training data.")
    parser.add_argument("--labels", choices=sorted(FOLDERS), default="v2")
    args = parser.parse_args(argv)
    data_dir = config.data_dir()
    manifest = json.loads((config.prepared_dir() / "manifests" / "segmentation.json")
                          .read_text(encoding="utf-8"))  # fmt: skip
    detector = FaceDetector(config.kit_dir() / "models" / YUNET)
    out = config.prepared_dir() / FOLDERS[args.labels]
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
            no_dark = np.zeros(sample.image.shape[:2], np.uint8) if args.labels == "v2" else None
            labels = encode_labels(sample.image.shape, wrinkles=sample.wrinkles, dark_spots=no_dark)
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
    index = {"when": datetime.now().isoformat(), "label_rules": args.labels,
             "stored_side": STORED_SIDE,
             "label_channels": "OpenCV channel 0 = wrinkles, 1 = dark spots; 0 no, 1 yes, 255 unknown",
             "counts": {f"{s} {p}": n for (s, p), n in sorted(counts.items())},
             "without_face": without_face, "items": items}  # fmt: skip
    (out / "index.json").write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(index["counts"], indent=1), f"\nwithout a face: {len(without_face)}")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
