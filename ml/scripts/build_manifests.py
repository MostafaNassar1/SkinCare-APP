"""Step 1.4: one manifest per model (every photo, its labels, its group and its split).

Reads the downloaded data; writes <data folder>/prepared/manifests/pimples.json (YOLO detector)
and segmentation.json (U-Net). Training formats are produced from these in Steps 3 and 4.

From ml/ with the venv active (PowerShell):
    $env:PYTHONPATH = "."; python scripts/build_manifests.py
"""

import hashlib
import json
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from skincare_ml import config
from skincare_ml.acne04 import (
    circle_to_box,
    hayashi_grade,
    load_split_file_grades,
    load_v2_annotations,
    pick_unique,
)
from skincare_ml.faces import FaceDetector, FaceRecognizer
from skincare_ml.memi import REGION_COLOURS, VIEW_REGIONS, parse_name
from skincare_ml.splits import (
    SEED,
    connected_groups,
    difference_hash,
    near_identical,
    split_groups,
)

# the source circles of this photo lie partly outside it (DATASETS.md): left out until relabelled
EXCLUDED_ACNE = {"levle2_130.jpg": "49 source circles outside the photo; to re-annotate by hand"}
YUNET = "face_detection_yunet_2023mar.onnx"
SFACE = "face_recognition_sface_2021dec.onnx"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pimples_manifest(sources: Path) -> dict:
    folder = sources / "acne04" / "Classification"
    photos = folder / "JPEGImages"
    expert = load_split_file_grades(folder)
    images = load_v2_annotations(sources / "acne04v2" / "Acne04-v2_annotations.json")
    unique = pick_unique(images, {i.file_name: sha256(photos / i.file_name) for i in images})
    kept = [i for i in unique if i.file_name not in EXCLUDED_ACNE]

    # ACNE04 has no person ids: photos are linked when they are near-identical copies (hash) or
    # show the same person (SFace fingerprints, only where YuNet finds a face)
    detector = FaceDetector(config.kit_dir() / "models" / YUNET)
    recognizer = FaceRecognizer(config.data_dir() / "models" / SFACE)
    hashes, fingerprints = {}, {}
    for count, image in enumerate(kept, 1):
        photo = cv2.imread(str(photos / image.file_name))
        hashes[image.file_name] = difference_hash(cv2.cvtColor(photo, cv2.COLOR_BGR2GRAY))
        faces = detector.detect(photo)
        if faces:
            fingerprints[image.file_name] = recognizer.fingerprint(photo, faces[0])
        if count % 200 == 0:
            print(f"  fingerprints {count}/{len(kept)}", flush=True)

    def linked(first: str, second: str) -> bool:
        if near_identical(hashes[first], hashes[second]):
            return True
        if first in fingerprints and second in fingerprints:
            similarity = recognizer.similarity(fingerprints[first], fingerprints[second])
            return similarity >= FaceRecognizer.SAME_PERSON
        return False

    groups = connected_groups([i.file_name for i in kept], linked)
    splits = split_groups(groups, strata={i.file_name: expert[i.file_name][0] for i in kept})

    entries = []
    for image in kept:
        grade, count = expert[image.file_name]
        entries.append(
            {
                "file": f"acne04/Classification/JPEGImages/{image.file_name}",
                "width": image.width,
                "height": image.height,
                "expert_grade": grade,
                "original_lesion_count": count,
                "v2_circle_grade": hayashi_grade(len(image.lesions)),
                # lesion type: "lesion" until labelled whitehead / pustule / other (Step 3)
                "boxes": [
                    {
                        "type": "lesion",
                        "box": [round(v, 1) for v in circle_to_box(lesion, image.width, image.height)],
                    }
                    for lesion in image.lesions
                ],
                "group": groups[image.file_name],
                "split": splits[image.file_name],
            }
        )
    return {
        "seed": SEED,
        "removed_duplicates": len(images) - len(unique),
        "excluded": EXCLUDED_ACNE,
        "photos_with_face_fingerprint": len(fingerprints),
        "group_sizes": dict(sorted(Counter(Counter(groups.values()).values()).items())),
        "images": entries,
    }


def memi_regions(mask_path: Path) -> dict[str, int]:
    """Melasma pixel count per region colour present in a mask."""
    mask = cv2.imread(str(mask_path))
    found = {}
    for colour, region in REGION_COLOURS.items():
        pixels = int(np.count_nonzero(np.all(mask == colour, axis=2)))
        if pixels:
            found[region] = pixels
    return found


def segmentation_manifest(raw: Path) -> dict:
    entries, problems = [], []
    for photo in sorted((raw / "FFHQ" / "images1024x1024").glob("*.png")):
        entries.append(
            {
                "source": "ffhq_wrinkle",
                "file": f"starter_kit/data/raw/FFHQ/images1024x1024/{photo.name}",
                "mask": f"FFHQ_Wrinkle/manual_wrinkle_masks.zip:{photo.stem}",
                "known": {"wrinkles": "whole_face", "dark_spots": None},
                # FFHQ gives no person ids: each photo is treated as its own person (limitation)
                "group": f"ffhq:{photo.stem}",
            }
        )
    for photo in sorted((raw / "MEMI_DS" / "images").glob("*.jpg")):
        person, view = parse_name(photo.stem)
        regions = memi_regions(raw / "MEMI_DS" / "masks" / f"{photo.stem}.png")
        unexpected = set(regions) - set(VIEW_REGIONS[view])
        if unexpected:
            problems.append({photo.stem: sorted(unexpected)})
        entries.append(
            {
                "source": "memi_ds",
                "file": f"starter_kit/data/raw/MEMI_DS/images/{photo.name}",
                "mask": f"starter_kit/data/raw/MEMI_DS/masks/{photo.stem}.png",
                "view": view,
                # only the regions of this view were annotated; the rest of the face is unknown
                "known": {"wrinkles": None, "dark_spots": list(VIEW_REGIONS[view])},
                "dark_spot_pixels": regions,
                "group": f"memi:{person}",
            }
        )
    splits = split_groups(
        {e["file"]: e["group"] for e in entries}, strata={e["file"]: e["source"] for e in entries}
    )
    for entry in entries:
        entry["split"] = splits[entry["file"]]
    return {"seed": SEED, "regions_outside_their_view": problems, "images": entries}


def summary(name: str, manifest: dict, key: str) -> None:
    table = Counter((e[key], e["split"]) for e in manifest["images"])
    print(f"\n{name}: {len(manifest['images'])} photos")
    for value in sorted({k for k, _ in table}):
        row = "  ".join(f"{s} {table[(value, s)]:4}" for s in ("train", "val", "test"))
        print(f"  {value:<14} {row}")


def main() -> int:
    sources, raw = config.data_dir() / "sources", config.raw_dir()
    output = config.prepared_dir() / "manifests"
    output.mkdir(parents=True, exist_ok=True)

    pimples = pimples_manifest(sources)
    (output / "pimples.json").write_text(json.dumps(pimples, indent=1), encoding="utf-8")
    summary("pimples (YOLO)", pimples, "expert_grade")
    print(f"  removed duplicates {pimples['removed_duplicates']}, excluded {len(pimples['excluded'])}")
    print(f"  face fingerprints {pimples['photos_with_face_fingerprint']}")
    print(f"  group sizes {pimples['group_sizes']}")
    print(f"  boxes {sum(len(e['boxes']) for e in pimples['images'])}")

    segmentation = segmentation_manifest(raw)
    (output / "segmentation.json").write_text(json.dumps(segmentation, indent=1), encoding="utf-8")
    summary("segmentation (U-Net)", segmentation, "source")
    print(f"  regions outside their view: {segmentation['regions_outside_their_view']}")
    print(f"\nManifests written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
