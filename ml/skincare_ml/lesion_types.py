"""Labelling the TYPE of each expert acne circle (Phase 3 Step 3, decided 2026-11-01).

Two stages (the student's decision): YOLO learns to FIND every pimple from all the expert circles
(1,167 photos, no new labels needed); a small second model learns the TYPE of each found pimple
from close-ups labelled by the student here. Five answers per close-up:

- whitehead: small closed bump, skin-coloured or white, not red
- papule:    small red bump without a white / yellow centre (inflamed)
- pustule:   red base with a white / yellow centre of pus (inflamed)
- other:     blackhead, large deep lump (nodule), mark or scar
- unclear:   not a pimple, or cannot tell (blurry, hair, freckle, circle on nothing)

Papule + pustule = inflamed lesions, which the Hayashi scale counts (counting every circle agreed
with the expert grade on only 31% of photos, Step 1). Definitions follow the American Academy of
Dermatology; the report states that the types were labelled by a non-expert.

A round is a queue of close-ups: test-set photos first (so their labels can be frozen before any
training), at most a few circles per photo (variety), tiny circles skipped, and ~10% hidden
repeats placed far after their first showing, to measure the labeller's self-consistency.
Answers are appended to a JSON-lines file (the last answer for an item wins), never rewritten.
"""

import hashlib
import json
import random
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

TYPES = ("whitehead", "papule", "pustule", "other", "unclear")
INFLAMED = ("papule", "pustule")
SPLIT_ORDER = ("test", "val", "train")  # test first: frozen before training
MIN_BOX_PX = 10  # smaller circles cannot be typed by eye
MAX_PER_PHOTO = 3
REPEAT_SHARE = 0.10
REPEAT_GAP = 50  # a repeat comes at least this many close-ups after the first showing


@dataclass(frozen=True)
class Item:
    id: str  # "<photo file>#<circle index>", or "repeat:<id>" for a hidden repeat
    file: str  # photo path inside the sources folder
    box: tuple[float, float, float, float]  # x1, y1, x2, y2 in pixels
    split: str
    grade: str

    @property
    def circle_id(self) -> str:
        return self.id.removeprefix("repeat:")

    @property
    def is_repeat(self) -> bool:
        return self.id.startswith("repeat:")


def make_queue(
    images: list[dict],
    size: int,
    seed: int,
    skip: Iterable[str] = (),
    splits: Iterable[str] = SPLIT_ORDER,
    grade_weights: dict[str, float] | None = None,
) -> list[Item]:
    """`size` new close-ups from the manifest's images (+ ~10% hidden repeats), test first.

    The share of each split follows the photos (about 70 / 15 / 15); circles already labelled in
    earlier rounds (`skip`) are never picked again. `splits` limits the photo sets (round 2: the
    training photos only, the test labels being frozen); `grade_weights` makes photos of some expert
    grades more likely (round 2: more moderate / severe photos, where pustules are common). Only
    training data may be weighted, so the test set keeps the real mix.
    """
    rng = random.Random(seed)
    skip = set(skip)
    splits = tuple(s for s in SPLIT_ORDER if s in set(splits))
    by_split: dict[str, list[Item]] = {split: [] for split in splits}
    for image in images:
        if image["split"] not in by_split:
            continue
        candidates = [
            Item(f"{image['file']}#{index}", image["file"], tuple(b["box"]), image["split"],
                 image["expert_grade"])
            for index, b in enumerate(image["boxes"])
            if b["box"][2] - b["box"][0] >= MIN_BOX_PX
            and f"{image['file']}#{index}" not in skip
        ]  # fmt: skip
        rng.shuffle(candidates)
        by_split[image["split"]].extend(candidates[:MAX_PER_PHOTO])

    total = sum(len(items) for items in by_split.values())
    picked: list[Item] = []
    for split in splits:
        pool = by_split[split]
        rng.shuffle(pool)
        if grade_weights:
            # weighted order without replacement (Efraimidis-Spirakis): key = u ** (1 / weight)
            keys = {id(i): rng.random() ** (1 / grade_weights.get(i.grade, 1.0)) for i in pool}
            pool.sort(key=lambda i: keys[id(i)], reverse=True)
        share = round(size * len(pool) / total) if total else 0
        chosen = pool[:share]
        chosen.sort(key=lambda item: item.file)  # same photo together: faster to load
        picked.extend(chosen)
    picked = picked[:size]
    return _add_repeats(picked, rng)


def _add_repeats(items: list[Item], rng: random.Random) -> list[Item]:
    count = round(len(items) * REPEAT_SHARE)
    if count == 0 or len(items) <= REPEAT_GAP:
        return items
    queue = list(items)
    for original in rng.sample(items[: len(items) - REPEAT_GAP], count):
        first = queue.index(original)
        position = rng.randint(first + REPEAT_GAP, len(queue))
        queue.insert(position, Item(f"repeat:{original.id}", original.file, original.box,
                                    original.split, original.grade))  # fmt: skip
    return queue


# ---------- close-ups ----------


def crop_square(
    box: tuple[float, float, float, float], width: int, height: int, scale: float, minimum: int
) -> tuple[int, int, int, int]:
    """A square around the circle, `scale` times its size (at least `minimum` px), inside the
    photo (shifted, not cut, at the edges)."""
    x1, y1, x2, y2 = box
    side = min(max(int(max(x2 - x1, y2 - y1) * scale), minimum), width, height)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    left = int(min(max(cx - side / 2, 0), width - side))
    top = int(min(max(cy - side / 2, 0), height - side))
    return left, top, left + side, top + side


# ---------- answers ----------


def save_answer(path: Path, item_id: str, label: str | None) -> None:
    """Append one answer (None = taken back with Backspace)."""
    if label is not None and label not in TYPES:
        raise ValueError(f"Unknown type {label!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"item": item_id, "label": label, "at": datetime.now(UTC).isoformat()}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def load_answers(path: Path) -> dict[str, str]:
    """item id -> its latest answer (items taken back and not answered again are left out)."""
    answers: dict[str, str | None] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                answers[record["item"]] = record["label"]
    return {item: label for item, label in answers.items() if label is not None}


def self_agreement(answers: dict[str, str]) -> dict:
    """How often the hidden repeats got the same answer as the first time (+ Cohen's kappa,
    which removes the agreement expected by chance)."""
    pairs = [
        (answers[item.removeprefix("repeat:")], label)
        for item, label in answers.items()
        if item.startswith("repeat:") and item.removeprefix("repeat:") in answers
    ]
    if not pairs:
        return {"pairs": 0, "agreement": None, "kappa": None}
    same = sum(a == b for a, b in pairs) / len(pairs)
    first, second = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    chance = sum(first[t] * second[t] for t in TYPES) / len(pairs) ** 2
    kappa = (same - chance) / (1 - chance) if chance < 1 else 1.0
    return {"pairs": len(pairs), "agreement": round(same, 3), "kappa": round(kappa, 3)}


# ---------- frozen test labels ----------


def frozen_test_record(queue_items: list[dict], answers: dict[str, str]) -> dict:
    """The test-set answers of a round, with a SHA-256 fingerprint: frozen before any training
    and never edited after seeing model results (correction rule 4, ml/DATASETS.md)."""
    labels = {
        item["id"]: answers[item["id"]]
        for item in queue_items
        if item["split"] == "test" and not item["id"].startswith("repeat:")
        and item["id"] in answers
    }  # fmt: skip
    return {"labels": labels, "sha256": fingerprint(labels)}


def fingerprint(labels: dict[str, str]) -> str:
    text = json.dumps(labels, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------- learning from the answers (the scout, then the real type model) ----------

LEARNED = ("whitehead", "papule", "pustule")  # other / unclear: too few to learn


def labelled_examples(queues: list[list[dict]], answers: dict[str, str]) -> list[dict]:
    """Every answered circle the type model can learn from: one of LEARNED, and the same answer on
    its hidden repeat when it had one (a circle the labeller answered differently is uncertain
    even to them, so it is left out). Test photos are never included (frozen labels)."""
    examples = []
    for queue in queues:
        for item in queue:
            label = answers.get(item["id"])
            if item["id"].startswith(("repeat:", "recheck:")) or item["split"] == "test"                     or label not in LEARNED:
                continue
            repeat = answers.get(f"repeat:{item['id']}")
            if repeat is not None and repeat != label:
                continue
            examples.append({**item, "label": label})
    return examples


def scout_queue(
    candidates: list[dict], size: int, seed: int, pustule_share: float = 0.7
) -> list[Item]:
    """Round 3: `size` close-ups chosen by the scout's scores (candidates = unlabelled training
    circles with "pustule" = its probability and "margin" = top-1 minus top-2 probability):
    `pustule_share` the likeliest pustules, the rest the circles it is least sure about; at most
    MAX_PER_PHOTO per photo; + ~10% hidden repeats. The order is shuffled so the labeller cannot
    tell which close-ups the scout thought were pustules."""
    rng = random.Random(seed)
    per_photo: Counter = Counter()
    chosen: list[dict] = []

    def take(ranked: list[dict], count: int) -> None:
        for candidate in ranked:
            if len(chosen) >= count:
                return
            if candidate in chosen or per_photo[candidate["file"]] >= MAX_PER_PHOTO:
                continue
            chosen.append(candidate)
            per_photo[candidate["file"]] += 1

    take(sorted(candidates, key=lambda c: -c["pustule"]), round(size * pustule_share))
    take(sorted(candidates, key=lambda c: c["margin"]), size)
    rng.shuffle(chosen)
    items = [Item(c["id"], c["file"], tuple(c["box"]), c["split"], c["grade"]) for c in chosen]
    return _add_repeats(items, rng)


# ---------- drift check (did the labeller's standard move between rounds?) ----------


def drift_check_queue(
    items: list[dict], answers: dict[str, str], per_type: int, seed: int
) -> list[Item]:
    """Close-ups answered in an earlier round, shown again blind as "recheck:<id>": `per_type` of
    each learned type (so a moved papule / pustule boundary can show), training photos only, not
    ones already shown as hidden repeats, shuffled."""
    rng = random.Random(seed)
    repeated = {i["id"].removeprefix("repeat:") for i in items if i["id"].startswith("repeat:")}
    chosen = []
    for kind in LEARNED:
        pool = [i for i in items if i["split"] == "train" and answers.get(i["id"]) == kind
                and not i["id"].startswith("repeat:") and i["id"] not in repeated]  # fmt: skip
        chosen += rng.sample(pool, min(per_type, len(pool)))
    rng.shuffle(chosen)
    return [Item(f"recheck:{i['id']}", i["file"], tuple(i["box"]), i["split"], i["grade"])
            for i in chosen]  # fmt: skip


def drift_report(earlier: dict[str, str], recheck: dict[str, str]) -> dict:
    """For each earlier answer, what the recheck said; and how often "pustule" was given."""
    pairs = [(earlier[k.removeprefix("recheck:")], v) for k, v in recheck.items()
             if k.startswith("recheck:") and k.removeprefix("recheck:") in earlier]  # fmt: skip
    table = {before: dict(Counter(after for b, after in pairs if b == before)) for before in LEARNED}
    return {
        "pairs": len(pairs),
        "same": round(sum(a == b for a, b in pairs) / len(pairs), 3) if pairs else None,
        "pustule_before": sum(a == "pustule" for a, _ in pairs),
        "pustule_now": sum(b == "pustule" for _, b in pairs),
        "by_earlier_answer": table,
    }
