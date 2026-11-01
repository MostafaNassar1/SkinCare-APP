r"""Make the to-do list of a labelling round (close-ups of expert acne circles to type).

    cd ml; .venv\Scripts\activate; $env:PYTHONPATH = "."
    python scripts/make_label_queue.py --round 1 --size 600

Writes C:\SkinCareData\prepared\lesion_types\round<N>_queue.json (never overwrites a round).
Circles answered in earlier rounds are never picked again. See skincare_ml/lesion_types.py.
"""

import argparse
import json
import sys
from collections import Counter

from skincare_ml import config
from skincare_ml.lesion_types import load_answers, make_queue


def rounds_dir():
    return config.prepared_dir() / "lesion_types"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Make a lesion-type labelling round.")
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--size", type=int, default=600, help="new close-ups (repeats added)")
    args = parser.parse_args(argv)

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
    queue = make_queue(manifest["images"], args.size, seed=2026 + args.round, skip=done)
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
