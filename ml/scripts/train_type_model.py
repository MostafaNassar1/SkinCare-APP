r"""Train the final lesion-type model (whitehead / papule / pustule) on this laptop's CPU.

    cd ml; .venv\Scripts\activate; $env:PYTHONPATH = "."
    python scripts/train_type_model.py                    # the base model (done 2026-11-03)
    python scripts/train_type_model.py --variant 160px    # sharper close-ups
    python scripts/train_type_model.py --variant large    # MobileNetV3-large

The second stage of the pimple pipeline (decided 2026-11-03: small enough for the CPU; only YOLO
needs the GPU laptop). Same code as the scout (skincare_ml/type_model.py), trained on every usable
label of the labelling rounds (training photos), the best epoch chosen on the validation photos.
The frozen test labels are NOT used here: the test is run once, at the end, on the final models.
Writes C:\SkinCareData\models\lesion_type_model_<variant>.pt and
prepared/lesion_types/type_model_report_<variant>.json; lesion_type_model.pt is a copy of the CHOSEN
variant (2026-11-04: "large", see lesion_type_model_chosen.json), never written here. Only two
variants were tried (decided 2026-11-03), the best on VALIDATION kept: trying many would make
the validation score unreliable too.
"""

import argparse
import json
import sys
import time

import torch

from skincare_ml import config
from skincare_ml.lesion_types import LEARNED, labelled_examples, load_answers
from skincare_ml.type_model import (
    CLOSE_UP,
    build_model,
    load_close_ups,
    seed_everything,
    train,
)

SEED = 2026
EPOCHS = 20
# variant -> (network, close-up size in px)
VARIANTS = {"base": ("small", 96), "160px": ("small", 160), "large": ("large", 96)}


def all_rounds(folder):
    queues, answers = [], {}
    for queue_file in sorted(folder.glob("round*_queue.json")):
        queue = json.loads(queue_file.read_text(encoding="utf-8"))
        if "drift_check_of" in queue:
            continue  # the drift check's rechecks are never learned from
        queues.append(queue["items"])
        answers_name = queue_file.name.replace("_queue.json", "_answers.jsonl")
        answers |= load_answers(queue_file.with_name(answers_name))
    return queues, answers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train the lesion-type model.")
    parser.add_argument("--variant", choices=VARIANTS, default="base")
    args = parser.parse_args(argv)
    architecture, size = VARIANTS[args.variant]
    suffix = f"_{args.variant}"  # never the chosen model's file name

    folder = config.prepared_dir() / "lesion_types"
    examples = labelled_examples(*all_rounds(folder))
    train_items = [e for e in examples if e["split"] == "train"]
    val_items = [e for e in examples if e["split"] == "val"]
    print(f"Variant {args.variant} (MobileNetV3-{architecture}, {size} px): learning from "
          f"{len(train_items)} training and {len(val_items)} validation close-ups")

    started = time.time()
    sources = config.data_dir() / "sources"
    to_index = {name: index for index, name in enumerate(LEARNED)}
    seed_everything(SEED)
    model = build_model(pretrained=True, architecture=architecture)
    history = train(
        model, load_close_ups(train_items, sources, size=size),
        [to_index[e["label"]] for e in train_items],
        load_close_ups(val_items, sources, size=size), [to_index[e["label"]] for e in val_items],
        epochs=EPOCHS, progress=print,
    )  # fmt: skip
    best = max(history, key=lambda h: h["balanced_accuracy"])

    models = config.data_dir() / "models"
    models.mkdir(parents=True, exist_ok=True)
    weights_file = models / f"lesion_type_model{suffix}.pt"
    checkpoint = {"state_dict": model.state_dict(), "classes": LEARNED, "close_up": CLOSE_UP,
                  "size": size, "architecture": architecture, "seed": SEED}  # fmt: skip
    torch.save(checkpoint, weights_file)
    report = {
        "variant": args.variant,
        "model": f"MobileNetV3-{architecture}, ImageNet-pretrained, fine-tuned on CPU",
        "close_up_px": size,
        "classes": LEARNED,
        "seed": SEED,
        "epochs": EPOCHS,
        "label_counts": {
            split: {n: sum(e["label"] == n for e in items) for n in LEARNED}
            for split, items in (("train", train_items), ("val", val_items))
        },
        "best_epoch": best,
        "history": history,
        "minutes": round((time.time() - started) / 60, 1),
        "test": "not evaluated yet: run once, at the end, on the final models",
    }
    (folder / f"type_model_report{suffix}.json").write_text(json.dumps(report, indent=1) + "\n")
    print(f"Best epoch {best['epoch']}: balanced accuracy {best['balanced_accuracy']}, recall "
          f"{best['recall']}\nconfusion (rows = your answer, columns = model) {best['confusion']}"
          f"\nDone in {report['minutes']} min -> {weights_file}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
