"""Step 1.3: inspect the downloaded datasets and write a report for the FYP.

Checks counts, exact duplicates, image sizes, ACNE04 grades vs lesion counts, mask contents and
whether YuNet finds exactly one face in every photo. Reads only; writes the report to
<data folder>/prepared/reports/inspection.json.

From ml/ with the venv active (PowerShell):
    $env:PYTHONPATH = "."; python scripts/inspect_datasets.py   (~25 min: YuNet on ~2,600 photos)
    $env:PYTHONPATH = "."; python scripts/inspect_datasets.py --no-faces
"""

import argparse
import hashlib
import json
import tarfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

from skincare_ml import config
from skincare_ml.acne04 import GRADES, grade_from_file_name, hayashi_grade, load_v2_annotations
from skincare_ml.faces import FaceDetector


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def duplicate_groups(paths: list[Path]) -> list[list[str]]:
    by_hash = defaultdict(list)
    for path in paths:
        by_hash[sha256(path)].append(path.name)
    return sorted(sorted(names) for names in by_hash.values() if len(names) > 1)


def agreement(pairs: list[tuple[str, str | None]]) -> dict:
    """Confusion table expert grade -> grade from a lesion count, plus the share that agrees."""
    table = Counter(pairs)
    return {
        "agree_share": round(sum(table[(g, g)] for g in GRADES) / len(pairs), 3),
        "rows": {g: {str(h): table[(g, h)] for h in (None, *GRADES)} for g in GRADES},
    }


def extract_acne04(archive: Path, target: Path) -> Path:
    images = target / "Classification" / "JPEGImages"
    if not images.exists():
        with tarfile.open(archive) as tar:
            tar.extractall(target, filter="data")  # "data" refuses absolute paths, "..", links
    return target / "Classification"


def inspect_acne04(raw: Path, sources: Path) -> dict:
    folder = extract_acne04(raw / "ACNE04" / "Classification.tar", sources / "acne04")
    photos = sorted((folder / "JPEGImages").glob("*.jpg"))
    # fold 0 (trainval + test) lists every photo once: "file grade count"
    counts, split_grades, conflicts = {}, {}, {}
    for line in (folder / "NNEW_trainval_0.txt").read_text().splitlines() + (
        folder / "NNEW_test_0.txt"
    ).read_text().splitlines():
        name, grade, count = line.split()
        counts[name], split_grades[name] = int(count), GRADES[int(grade)]
        if split_grades[name] != grade_from_file_name(name):
            conflicts[name] = {
                "file_name": grade_from_file_name(name),
                "split_file": split_grades[name],
                "count": int(count),
                "hayashi": hayashi_grade(int(count)),
            }
    folds_agree = all(
        {
            tuple(line.split()[:2])
            for f in ("trainval", "test")
            for line in (folder / f"NNEW_{f}_{k}.txt").read_text().splitlines()
        }
        == {(n, str(GRADES.index(g))) for n, g in split_grades.items()}
        for k in range(5)
    )

    v2 = load_v2_annotations(sources / "acne04v2" / "Acne04-v2_annotations.json")
    on_disk = {photo.name for photo in photos}
    v2_photos = [folder / "JPEGImages" / image.file_name for image in v2]
    return {
        "photos": len(photos),
        "grades": dict(Counter(grade_from_file_name(p.name) for p in photos)),
        "original_lesions": sum(counts.values()),
        "photos_without_count": sorted(on_disk - counts.keys()),
        "five_folds_give_the_same_grades": folds_agree,
        "grade_conflicts_file_name_vs_split_file": conflicts,
        "exact_duplicates": duplicate_groups(photos),
        "split_grade_vs_original_count": agreement(
            [(split_grades[n], hayashi_grade(c)) for n, c in counts.items()]
        ),
        "file_name_grade_vs_original_count": agreement(
            [(grade_from_file_name(n), hayashi_grade(c)) for n, c in counts.items()]
        ),
        "v2": {
            "entries": len(v2),
            "missing_photos": sorted(i.file_name for i in v2 if i.file_name not in on_disk),
            "valid_circles": sum(len(i.lesions) for i in v2),
            "invalid_circles": {i.file_name: len(i.invalid_lesions) for i in v2 if i.invalid_lesions},
            "exact_duplicates": duplicate_groups([p for p in v2_photos if p.exists()]),
            "grade_vs_v2_circle_count": agreement(
                [(i.grade, hayashi_grade(len(i.lesions))) for i in v2]
            ),
            "circles_vs_original_count": {
                "v2_more": sum(len(i.lesions) > counts[i.file_name] for i in v2),
                "equal": sum(len(i.lesions) == counts[i.file_name] for i in v2),
                "v2_fewer": sum(len(i.lesions) < counts[i.file_name] for i in v2),
            },
        },
    }


def inspect_memi(raw: Path) -> dict:
    images = sorted((raw / "MEMI_DS" / "images").glob("*.jpg"))
    masks = sorted((raw / "MEMI_DS" / "masks").glob("*.png"))
    colours, coverage = Counter(), []
    for mask_path in masks:
        mask = cv2.imread(str(mask_path), cv2.IMREAD_UNCHANGED)
        pixels = mask.reshape(-1, mask.shape[2]) if mask.ndim == 3 else mask.reshape(-1, 1)
        values, numbers = np.unique(pixels, axis=0, return_counts=True)
        for value, number in zip(values, numbers):
            colours[tuple(int(v) for v in value)] += int(number)
        background = numbers[np.argmax(numbers)]
        coverage.append(1 - background / pixels.shape[0])
    total = sum(colours.values())
    return {
        "photos": len(images),
        "masks": len(masks),
        "unpaired": sorted({p.stem for p in images} ^ {m.stem for m in masks}),
        "views": dict(Counter(p.stem.split("_")[1] for p in images)),
        "subjects": len({p.stem.split("_")[0] for p in images}),
        "mask_colours": {str(c): round(n / total, 5) for c, n in colours.most_common(12)},
        "mask_coverage_mean": round(float(np.mean(coverage)), 4),
        "exact_duplicates": duplicate_groups(images),
    }


def inspect_ffhq(raw: Path) -> dict:
    photos = sorted((raw / "FFHQ" / "images1024x1024").glob("*.png"))
    archive = raw / "FFHQ_Wrinkle" / "manual_wrinkle_masks.zip"
    values, coverage, names = Counter(), [], set()
    with zipfile.ZipFile(archive) as masks:
        for member in masks.namelist():
            if not member.lower().endswith(".png"):
                continue
            names.add(Path(member).stem)
            data = np.frombuffer(masks.read(member), np.uint8)
            mask = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
            values.update(int(v) for v in np.unique(mask))
            coverage.append(float((mask > 0).mean()))
    return {
        "photos": len(photos),
        "masks": len(names),
        "unpaired": sorted({p.stem for p in photos} ^ names),
        "mask_values": dict(values),
        "mask_coverage_mean": round(float(np.mean(coverage)), 5),
        "masks_empty": sum(c == 0 for c in coverage),
        "exact_duplicates": duplicate_groups(photos),
    }


def inspect_faces(groups: dict[str, list[Path]], model: Path) -> dict:
    detector = FaceDetector(model)
    report = {}
    for name, photos in groups.items():
        found, problems = Counter(), {}
        for count, photo in enumerate(photos, 1):
            faces = detector.detect(cv2.imread(str(photo)))
            found[len(faces)] += 1
            if len(faces) != 1:
                problems[photo.name] = len(faces)
            if count % 200 == 0:
                print(f"  faces {name}: {count}/{len(photos)}", flush=True)
        report[name] = {"faces_per_photo": dict(found), "not_exactly_one": problems}
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-faces", action="store_true", help="skip the YuNet check")
    args = parser.parse_args()

    raw, sources = config.raw_dir(), config.data_dir() / "sources"
    report = {"acne04": inspect_acne04(raw, sources)}
    print("ACNE04 checked", flush=True)
    report["memi_ds"] = inspect_memi(raw)
    print("MEMI-DS checked", flush=True)
    report["ffhq_wrinkle"] = inspect_ffhq(raw)
    print("FFHQ-Wrinkle checked", flush=True)
    if not args.no_faces:
        report["faces"] = inspect_faces(
            {
                "acne04": sorted((sources / "acne04/Classification/JPEGImages").glob("*.jpg")),
                "memi_ds": sorted((raw / "MEMI_DS/images").glob("*.jpg")),
                "ffhq": sorted((raw / "FFHQ/images1024x1024").glob("*.png")),
            },
            config.kit_dir() / "models" / "face_detection_yunet_2023mar.onnx",
        )

    output = config.prepared_dir() / "reports" / "inspection.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
