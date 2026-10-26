from collections import Counter

import numpy as np
import pytest

from skincare_ml.splits import connected_groups, difference_hash, near_identical, split_groups


def test_a_resized_copy_is_near_identical_and_another_image_is_not():
    rng = np.random.default_rng(0)
    image = (rng.random((160, 170)) * 255).astype(np.uint8)
    bigger = np.kron(image, np.ones((4, 4), dtype=np.uint8))  # same picture, 4x the size
    other = (rng.random((160, 170)) * 255).astype(np.uint8)

    assert near_identical(difference_hash(image), difference_hash(bigger))
    assert not near_identical(difference_hash(image), difference_hash(other))


def test_linked_items_are_grouped_through_chains():
    links = {("a", "b"), ("b", "c")}

    groups = connected_groups(["d", "c", "b", "a"], lambda x, y: (x, y) in links)

    # a-b and b-c: one group even though a and c are not linked directly
    assert groups == {"a": "a", "b": "a", "c": "a", "d": "d"}


def test_split_keeps_every_group_together_and_respects_the_ratios():
    groups = {f"photo{i}": f"person{i // 3}" for i in range(300)}  # 100 people, 3 photos each

    splits = split_groups(groups)

    by_group = {}
    for item, split in splits.items():
        assert by_group.setdefault(groups[item], split) == split
    sizes = Counter(splits.values())
    assert sizes["train"] == pytest.approx(210, abs=3)
    assert sizes["val"] == pytest.approx(45, abs=3)
    assert sizes["test"] == pytest.approx(45, abs=3)


def test_split_is_reproducible_and_depends_on_the_seed():
    groups = {f"photo{i}": f"photo{i}" for i in range(200)}

    assert split_groups(groups) == split_groups(groups)
    assert split_groups(groups, seed=1) != split_groups(groups, seed=2)


def test_stratified_split_puts_a_rare_class_in_every_split():
    groups = {f"photo{i}": f"photo{i}" for i in range(220)}
    strata = {f"photo{i}": "rare" if i < 20 else "common" for i in range(220)}

    splits = split_groups(groups, strata)

    rare = Counter(splits[f"photo{i}"] for i in range(20))
    assert rare == {"train": 14, "val": 3, "test": 3}
