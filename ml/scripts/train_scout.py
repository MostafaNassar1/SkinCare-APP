r"""Train the throw-away "scout" type model on this laptop's CPU and score the untyped circles.

    cd ml; .venv\Scripts\activate; $env:PYTHONPATH = "."
    python scripts/train_scout.py
    python scripts/make_label_queue.py --round 3 --from-scout --size 400

Learns whitehead / papule / pustule from every labelling round so far (training photos; checked
on the validation photos; the frozen test labels are never used), then scores every training
circle nobody has typed yet. Writes, in C:\SkinCareData\prepared\lesion_types\:
scout_report.json (its validation results, for the report) and scout_scores.json (each circle's
pustule probability and how sure it is), used to build round 3. Never used by the app.
"""

import json
import sys
import time

from skincare_ml import config
from skincare_ml.lesion_types import LEARNED, MIN_BOX_PX, labelled_examples, load_answers
from skincare_ml.type_model import (
    build_model,
    evaluate,
    load_close_ups,
    predict,
    seed_everything,
    train,
)

SEED = 2026


def main() -> int:
    folder = config.prepared_dir() / "lesion_types"
    sources = config.data_dir() / "sources"
    queues, answers = [], {}
    for queue_file in sorted(folder.glob("round*_queue.json")):
        queues.append(json.loads(queue_file.read_text(encoding="utf-8"))["items"])
        answers_name = queue_file.name.replace("_queue.json", "_answers.jsonl")
        answers |= load_answers(queue_file.with_name(answers_name))
    examples = labelled_examples(queues, answers)
    train_items = [e for e in examples if e["split"] == "train"]
    val_items = [e for e in examples if e["split"] == "val"]
    if not train_items or not val_items:
        print("Not enough answers to train the scout yet", file=sys.stderr)
        return 1
    print(f"Learning from {len(train_items)} training and {len(val_items)} validation close-ups")

    started = time.time()
    train_images = load_close_ups(train_items, sources)
    val_images = load_close_ups(val_items, sources)
    to_index = {name: index for index, name in enumerate(LEARNED)}
    seed_everything(SEED)
    model = build_model(pretrained=True)
    history = train(
        model, train_images, [to_index[e["label"]] for e in train_items],
        val_images, [to_index[e["label"]] for e in val_items], progress=print,
    )  # fmt: skip
    best = max(history, key=lambda h: h["balanced_accuracy"])
    print(f"Best epoch {best['epoch']}: balanced accuracy {best['balanced_accuracy']}, "
          f"recall {best['recall']}")  # fmt: skip

    # every training circle nobody has typed yet (round 3 takes training photos only)
    manifest = json.loads(
        (config.prepared_dir() / "manifests" / "pimples.json").read_text(encoding="utf-8")
    )
    typed = {item.removeprefix("repeat:") for item in answers}
    candidates = [
        {"id": f"{image['file']}#{index}", "file": image["file"], "box": box["box"],
         "split": image["split"], "grade": image["expert_grade"]}
        for image in manifest["images"] if image["split"] == "train"
        for index, box in enumerate(image["boxes"])
        if box["box"][2] - box["box"][0] >= MIN_BOX_PX
        and f"{image['file']}#{index}" not in typed
    ]  # fmt: skip
    print(f"Scoring {len(candidates)} untyped training circles (each photo opened once)...")
    probabilities = predict(model, load_close_ups(candidates, sources, progress=print))
    pustule = LEARNED.index("pustule")
    for candidate, row in zip(candidates, probabilities, strict=True):
        top = sorted(row, reverse=True)
        candidate["pustule"] = round(float(row[pustule]), 4)
        candidate["margin"] = round(float(top[0] - top[1]), 4)
        candidate["predicted"] = LEARNED[int(row.argmax())]

    (folder / "scout_scores.json").write_text(json.dumps(candidates) + "\n", encoding="utf-8")
    predicted = {name: sum(c["predicted"] == name for c in candidates) for name in LEARNED}
    report = {
        "purpose": "throw-away scout for active learning (labelling round 3); never in the app",
        "model": "MobileNetV3-small, ImageNet-pretrained, fine-tuned on CPU",
        "seed": SEED,
        "trained_on": len(train_items),
        "validated_on": len(val_items),
        "label_counts": {
            split: {n: sum(e["label"] == n for e in items) for n in LEARNED}
            for split, items in (("train", train_items), ("val", val_items))
        },
        "best_epoch": best,
        "history": history,
        "scored_circles": len(candidates),
        "predicted_on_untyped": predicted,
        "minutes": round((time.time() - started) / 60, 1),
    }
    (folder / "scout_report.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(f"Scout predictions on untyped circles: {predicted}")
    print(f"Done in {report['minutes']} min -> scout_scores.json, scout_report.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
