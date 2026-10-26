"""Train / validation / test splits that never separate photos of the same person.

If the same face (or the same photo twice) were in training and in test, the test score would
measure memory instead of skill. Photos are therefore split by GROUP: a person (when the dataset
gives an id, or recognised with face fingerprints when it does not) plus near-identical copies.
"""

import random
from collections import Counter, defaultdict
from collections.abc import Callable

import cv2
import numpy as np

SPLITS = ("train", "val", "test")
RATIOS = (0.70, 0.15, 0.15)
SEED = 2026
# 256-bit hash: re-saved / resized copies differ by a few bits. A perceptual hash can NOT recognise
# people: on ACNE04, two photos of the same person differed by 36-42 bits and different people in
# the same clinic setup by 43+ (checked 2026-10-26), so it is used only for near-identical copies.
NEAR_IDENTICAL_DISTANCE = 20


def difference_hash(gray: np.ndarray, size: int = 16) -> int:
    """dHash of size x size bits: is each pixel brighter than its right neighbour on a thumbnail."""
    small = cv2.resize(gray, (size + 1, size), interpolation=cv2.INTER_AREA)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    return int("".join("1" if bit else "0" for bit in bits), 2)


def near_identical(a: int, b: int, max_distance: int = NEAR_IDENTICAL_DISTANCE) -> bool:
    return (a ^ b).bit_count() <= max_distance


def connected_groups(names: list[str], linked: Callable[[str, str], bool]) -> dict[str, str]:
    """Item -> group id (smallest name of its group): linked items, directly or through a chain,
    share a group."""
    parent = {name: name for name in names}

    def root(name: str) -> str:
        while parent[name] != name:
            parent[name] = parent[parent[name]]
            name = parent[name]
        return name

    ordered = sorted(names)
    for i, first in enumerate(ordered):
        for second in ordered[i + 1 :]:
            if linked(first, second):
                a, b = root(first), root(second)
                parent[max(a, b)] = min(a, b)
    return {name: root(name) for name in ordered}


def split_groups(
    groups: dict[str, str],
    strata: dict[str, str] | None = None,
    ratios: tuple[float, float, float] = RATIOS,
    seed: int = SEED,
) -> dict[str, str]:
    """Item -> "train" / "val" / "test"; all items of a group get the same split.

    Within each stratum (e.g. each acne grade, so rare grades appear in every split) the groups are
    shuffled with a fixed seed, then each goes to the split furthest below its target size.
    Same input + same seed = same splits.
    """
    members = defaultdict(list)
    for item, group in groups.items():
        members[group].append(item)
    by_stratum = defaultdict(list)
    for group, items in members.items():
        stratum = Counter(strata[item] for item in items).most_common(1)[0][0] if strata else ""
        by_stratum[stratum].append(group)

    result = {}
    for stratum in sorted(by_stratum):
        chosen = sorted(by_stratum[stratum])
        random.Random(f"{seed}:{stratum}").shuffle(chosen)
        total = sum(len(members[group]) for group in chosen)
        filled = dict.fromkeys(SPLITS, 0)
        for group in chosen:
            split = max(SPLITS, key=lambda s: ratios[SPLITS.index(s)] * total - filled[s])
            filled[split] += len(members[group])
            for item in members[group]:
                result[item] = split
    return result
