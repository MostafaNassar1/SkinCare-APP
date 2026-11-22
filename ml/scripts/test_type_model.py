r"""The ONE-TIME final test of the chosen lesion-type model (decided 2026-11-22, end of Step 3).

    cd ml; .venv\Scripts\activate; $env:PYTHONPATH = "."
    python scripts/test_type_model.py

The chosen model (lesion_type_model.pt = "large", chosen on validation on 2026-11-04) is scored on
the student's FROZEN test labels (prepared/lesion_types/test_labels_frozen.json, frozen on
2026-11-01 before any training; its SHA-256 is checked). Only whitehead / papule / pustule are
scored ("other" / "unclear" are not learned). Bootstrap 95% ranges over the close-ups. It refuses
to run a second time; the result is prepared/lesion_types/type_model_final_test.json.
"""

import argparse
import json
import sys
from datetime import datetime

import numpy as np
import torch

from skincare_ml import config
from skincare_ml.lesion_types import LEARNED, fingerprint
from skincare_ml.type_model import build_model, evaluate, load_close_ups, predict

FROZEN_SHA256 = "70d4051325ec8697f68fb65717f1cb49e91faade82a394a0e6140cfb32a29db5"
RESULT = "type_model_final_test.json"


def test_items(folder) -> list[dict]:
    """The frozen test labels with their photo and box (from the labelling queues)."""
    frozen = json.loads((folder / "test_labels_frozen.json").read_text(encoding="utf-8"))
    if fingerprint(frozen["labels"]) != FROZEN_SHA256 or frozen["sha256"] != FROZEN_SHA256:
        raise ValueError("the frozen test labels have changed")
    queued = {}
    for queue_file in sorted(folder.glob("round*_queue.json")):
        for item in json.loads(queue_file.read_text(encoding="utf-8"))["items"]:
            queued.setdefault(item["id"], item)
    return [{**queued[item_id], "label": label} for item_id, label in frozen["labels"].items()
            if label in LEARNED]  # fmt: skip


def balanced_ranges(labels: np.ndarray, predicted: np.ndarray, rounds: int = 1000,
                    seed: int = 2026) -> list[float]:  # fmt: skip
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(rounds):
        pick = rng.integers(0, len(labels), len(labels))
        recalls = [(predicted[pick][labels[pick] == k] == k).mean()
                   for k in range(len(LEARNED)) if (labels[pick] == k).any()]  # fmt: skip
        values.append(np.mean(recalls))
    return [round(float(v), 3) for v in np.percentile(values, [2.5, 97.5])]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One-time final test of the lesion-type model.")
    parser.parse_args(argv)
    folder = config.prepared_dir() / "lesion_types"
    target = folder / RESULT
    if target.exists():
        parser.error("the final test has already been run: its result stands")
    items = test_items(folder)
    checkpoint = torch.load(config.data_dir() / "models" / "lesion_type_model.pt",
                            map_location="cpu", weights_only=False)  # our own file
    model = build_model(pretrained=False, architecture=checkpoint["architecture"])
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    images = load_close_ups(items, config.data_dir() / "sources", size=checkpoint["size"])
    labels = np.array([LEARNED.index(item["label"]) for item in items])
    probabilities = predict(model, images)
    result = evaluate(labels.tolist(), probabilities)
    inflamed = labels > 0  # papule or pustule
    result |= {
        "when": datetime.now().isoformat(),
        "close_ups": len(items),
        "label_counts": {name: int((labels == k).sum()) for k, name in enumerate(LEARNED)},
        "balanced_accuracy_ranges_95": balanced_ranges(labels, probabilities.argmax(axis=1)),
        "inflamed_called_inflamed": round(float((probabilities.argmax(axis=1)[inflamed] > 0).mean()), 3)
        if inflamed.any() else None,
        "model": "lesion_type_model.pt (MobileNetV3-large, 96 px)",
        "frozen_labels_sha256": FROZEN_SHA256,
    }  # fmt: skip
    target.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
