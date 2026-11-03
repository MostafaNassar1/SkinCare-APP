"""The missed-pimple check (Phase 3 Step 3, decided 2026-11-03).

YOLO learns to FIND pimples from the expert circles; a visible pimple without a circle teaches it
"this is skin", and on the test photos it turns a correct find into a counted mistake. So the
student looks at whole test photos with every expert circle drawn and adds a circle on each CLEAR
miss (correction rules of ml/DATASETS.md: only clear misses, never move or delete an expert circle,
every change logged apart from the original files; test labels frozen before training).

The log is append-only JSON lines in prepared/corrections/missed_pimples.jsonl:
{"photo", "action": "add" | "remove" | "done", "id", "x", "y", "r", "at"}; replaying it gives the
current state (the latest action wins).
"""

import json
import random
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


def choose_photos(images: list[dict], count: int, seed: int, split: str = "test") -> list[dict]:
    """`count` photos of one split, spread over the expert grades like the split itself."""
    rng = random.Random(seed)
    pool = sorted((i for i in images if i["split"] == split), key=lambda i: i["file"])
    by_grade: dict[str, list[dict]] = {}
    for image in pool:
        by_grade.setdefault(image["expert_grade"], []).append(image)
    chosen = []
    for grade in sorted(by_grade):
        photos = by_grade[grade]
        rng.shuffle(photos)
        chosen += photos[: max(1, round(count * len(photos) / len(pool)))]
    rng.shuffle(chosen)
    return chosen[:count]


def default_radius(image: dict) -> float:
    """New circles start at the photo's median expert circle size (the experts' own scale)."""
    sizes = sorted((b["box"][2] - b["box"][0]) / 2 for b in image["boxes"])
    return sizes[len(sizes) // 2] if sizes else 20.0


@dataclass
class CheckState:
    added: dict[str, dict[str, dict]] = field(default_factory=dict)  # photo -> id -> circle
    done: set[str] = field(default_factory=set)


def _append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({**record, "at": datetime.now(UTC).isoformat()}) + "\n")


def add_circle(path: Path, photo: str, x: float, y: float, r: float) -> str:
    circle_id = secrets.token_hex(4)
    _append(path, {"photo": photo, "action": "add", "id": circle_id, "x": round(x, 1),
                   "y": round(y, 1), "r": round(r, 1)})  # fmt: skip
    return circle_id


def remove_circle(path: Path, photo: str, circle_id: str) -> None:
    _append(path, {"photo": photo, "action": "remove", "id": circle_id})


def mark_done(path: Path, photo: str, done: bool = True) -> None:
    _append(path, {"photo": photo, "action": "done" if done else "reopen"})


def load_state(path: Path) -> CheckState:
    state = CheckState()
    if not path.exists():
        return state
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        photo, action = record["photo"], record["action"]
        circles = state.added.setdefault(photo, {})
        if action == "add":
            circles[record["id"]] = {"x": record["x"], "y": record["y"], "r": record["r"]}
        elif action == "remove":
            circles.pop(record["id"], None)
        elif action == "done":
            state.done.add(photo)
        elif action == "reopen":
            state.done.discard(photo)
    return state


def summary(photos: list[dict], state: CheckState) -> dict:
    """How many pimples the experts missed, per checked photo (for the report)."""
    checked = [p for p in photos if p["file"] in state.done]
    added = [len(state.added.get(p["file"], {})) for p in checked]
    experts = sum(len(p["boxes"]) for p in checked)
    return {
        "photos_checked": len(checked),
        "missed_added": sum(added),
        "photos_with_a_miss": sum(1 for n in added if n),
        "missed_per_photo": round(sum(added) / len(checked), 2) if checked else None,
        "expert_circles_on_them": experts,
        "missed_share": round(sum(added) / (experts + sum(added)), 3) if checked else None,
    }
