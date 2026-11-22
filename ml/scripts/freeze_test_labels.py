r"""Freeze the test-set lesion types of a round before any training (correction rule 4).

    cd ml; .venv\Scripts\activate; $env:PYTHONPATH = "."
    python scripts/freeze_test_labels.py --round 1     # freeze (once)
    python scripts/freeze_test_labels.py --check       # later: prove they never changed

Writes C:\SkinCareData\prepared\lesion_types\test_labels_frozen.json with a SHA-256 fingerprint.
Later rounds never pick test circles again (make_label_queue refuses the test set once frozen).
"""

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime

from skincare_ml import config
from skincare_ml.lesion_types import fingerprint, frozen_test_record, load_answers


def frozen_file():
    return config.prepared_dir() / "lesion_types" / "test_labels_frozen.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze or check the test-set lesion types.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--round", type=int, help="freeze the test answers of this round")
    action.add_argument("--check", action="store_true", help="check the frozen fingerprint")
    args = parser.parse_args(argv)

    target = frozen_file()
    if args.check:
        if not target.exists():
            print("No frozen test labels yet", file=sys.stderr)
            return 1
        record = json.loads(target.read_text(encoding="utf-8"))
        if fingerprint(record["labels"]) != record["sha256"]:
            print("CHANGED: the frozen test labels no longer match their fingerprint",
                  file=sys.stderr)  # fmt: skip
            return 1
        count, short = len(record["labels"]), record["sha256"][:12]
        print(f"OK: {count} frozen test labels, unchanged ({short})")
        return 0

    if target.exists():
        print(f"{target} already exists: test labels are frozen once", file=sys.stderr)
        return 1
    folder = target.parent
    queue = json.loads((folder / f"round{args.round}_queue.json").read_text(encoding="utf-8"))
    answers = load_answers(folder / f"round{args.round}_answers.jsonl")
    record = frozen_test_record(queue["items"], answers)
    record = {"round": args.round, "frozen_at": datetime.now(UTC).isoformat(), **record}
    target.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    print(f"Frozen {len(record['labels'])} test labels {dict(Counter(record['labels'].values()))}"
          f"\nfingerprint {record['sha256']}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
