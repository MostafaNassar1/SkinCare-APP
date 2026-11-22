r"""Make a drift-check round: close-ups of an earlier round shown again blind.

    cd ml; .venv\Scripts\activate; $env:PYTHONPATH = "."
    python scripts/make_drift_check.py --of-round 1 --round 5 --per-type 20
    python scripts/label_types.py --round 5
    python scripts/make_drift_check.py --report 5 --of-round 1

Checks whether the labeller's standard moved after the pustule-heavy round 3 (round 4, random,
gave 21% pustules against 11-13% in random round 1). Recheck answers are never used for training.
"""

import argparse
import json
import sys

from skincare_ml import config
from skincare_ml.lesion_types import drift_check_queue, drift_report, load_answers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Drift check of the lesion-type labels.")
    parser.add_argument("--of-round", type=int, required=True)
    parser.add_argument("--round", type=int, help="the new round to make")
    parser.add_argument("--per-type", type=int, default=20)
    parser.add_argument("--report", type=int, help="the drift-check round to report on")
    args = parser.parse_args(argv)

    folder = config.prepared_dir() / "lesion_types"
    items = json.loads((folder / f"round{args.of_round}_queue.json").read_text())["items"]
    earlier = load_answers(folder / f"round{args.of_round}_answers.jsonl")
    if args.report:
        report = drift_report(earlier, load_answers(folder / f"round{args.report}_answers.jsonl"))
        (folder / f"drift_round{args.report}.json").write_text(json.dumps(report, indent=1) + "\n")
        print(json.dumps(report, indent=1))
        return 0
    target = folder / f"round{args.round}_queue.json"
    if target.exists():
        print(f"{target} already exists: a round is never rebuilt", file=sys.stderr)
        return 1
    queue = drift_check_queue(items, earlier, args.per_type, seed=2026 + args.round)
    target.write_text(json.dumps({"round": args.round, "drift_check_of": args.of_round, "items": [
        {"id": i.id, "file": i.file, "box": list(i.box), "split": i.split, "grade": i.grade}
        for i in queue]}, indent=1) + "\n")  # fmt: skip
    print(f"Round {args.round}: {len(queue)} close-ups of round {args.of_round}, shown again blind")
    return 0


if __name__ == "__main__":
    sys.exit(main())
