r"""Make the to-do list of a labelling round (close-ups of expert acne circles to type).

    cd ml; .venv\Scripts\activate; $env:PYTHONPATH = "."
    python scripts/make_label_queue.py --round 1 --size 600
    python scripts/make_label_queue.py --round 2 --size 600 --splits train --favour-severe

Writes C:\SkinCareData\prepared\lesion_types\round<N>_queue.json (never overwrites a round).
Circles answered in earlier rounds are never picked again. See skincare_ml/lesion_types.py.
"""

import argparse
import json
import sys
from collections import Counter

from skincare_ml import config
from skincare_ml.lesion_types import SPLIT_ORDER, load_answers, make_queue

# round 2 (2026-11-01): pustules were only 11% of round 1, and are more common on moderate /
# severe faces; only TRAINING photos are weighted, so the test set keeps the real mix
FAVOUR_SEVERE = {"mild": 1.0, "moderate": 2.0, "severe": 4.0, "very_severe": 4.0}


def rounds_dir():
    return config.prepared_dir() / "lesion_types"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Make a lesion-type labelling round.")
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--size", type=int, default=600, help="new close-ups (repeats added)")
    parser.add_argument("--splits", nargs="+", choices=SPLIT_ORDER, default=list(SPLIT_ORDER))
    parser.add_argument("--favour-severe", action="store_true",
                        help="pick moderate / severe photos more often (training only)")
    args = parser.parse_args(argv)
    if "test" in args.splits and (rounds_dir() / "test_labels_frozen.json").exists():
        print("The test labels are frozen: no new test close-ups (use --splits val train)",
              file=sys.stderr)
        return 1
    if args.favour_severe and args.splits != ["train"]:
        print("--favour-severe is for training photos only (--splits train)", file=sys.stderr)
        return 1

    folder = rounds_dir()
    target = folder / f"round{args.round}_queue.json"
    if target.exists():
        print(f"{target} already exists: a round is never rebuilt", file=sys.stderr)
        return 1
    done = set()
    for answers in folder.glob("round*_answers.jsonl"):
        done |= {item for item in load_answers(answers) if not item.startswith("repeat:")}

    manifest = json.loads(
        (config.prepared_dir() / "manifests" / "pimples.json").read_text(encoding="utf-8")
    )
    queue = make_queue(
        manifest["images"], args.size, seed=2026 + args.round, skip=done, splits=args.splits,
        grade_weights=FAVOUR_SEVERE if args.favour_severe else None,
    )
    folder.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "round": args.round,
        "items": [{"id": i.id, "file": i.file, "box": list(i.box), "split": i.split,
                   "grade": i.grade} for i in queue],
    }, indent=1) + "\n", encoding="utf-8")  # fmt: skip

    repeats = sum(i.is_repeat for i in queue)
    splits = Counter(i.split for i in queue if not i.is_repeat)
    print(f"Round {args.round}: {len(queue) - repeats} close-ups + {repeats} hidden repeats "
          f"({dict(splits)}) -> {target}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
