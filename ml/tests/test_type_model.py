"""The lesion-type model code (scout now, real model later); skipped without PyTorch."""

import numpy as np
import pytest
from PIL import Image

torch = pytest.importorskip("torch")

from skincare_ml import type_model  # noqa: E402
from skincare_ml.lesion_types import LEARNED  # noqa: E402


def test_close_up_is_the_labelling_crop_at_96_px():
    photo = Image.new("RGB", (800, 600), (200, 150, 130))

    crop = type_model.close_up(photo, [100, 100, 150, 150])

    assert crop.size == (96, 96)


def test_model_gives_one_probability_per_type():
    model = type_model.build_model(pretrained=False)  # no download in tests
    images = [Image.new("RGB", (96, 96), (n * 40, 120, 110)) for n in range(4)]

    probabilities = type_model.predict(model, images)

    assert probabilities.shape == (4, len(LEARNED))
    assert np.allclose(probabilities.sum(axis=1), 1, atol=1e-5)


def test_training_keeps_the_best_validation_epoch():
    type_model.seed_everything(0)
    model = type_model.build_model(pretrained=False)
    colours = [(240, 230, 220), (200, 60, 60), (230, 220, 60)]  # one plain colour per type
    images = [Image.new("RGB", (96, 96), colours[n % 3]) for n in range(12)]
    labels = [n % 3 for n in range(12)]

    history = type_model.train(model, images, labels, images, labels, epochs=2, batch_size=6)

    assert [h["epoch"] for h in history] == [1, 2]
    assert all(0 <= h["balanced_accuracy"] <= 1 for h in history)


def test_evaluate_counts_recall_per_type():
    probabilities = np.array([[0.8, 0.1, 0.1], [0.2, 0.7, 0.1], [0.6, 0.3, 0.1], [0.1, 0.1, 0.8]])

    scores = type_model.evaluate([0, 1, 1, 2], probabilities)

    assert scores["recall"] == {"whitehead": 1.0, "papule": 0.5, "pustule": 1.0}
    assert scores["balanced_accuracy"] == pytest.approx(0.833, abs=0.001)
    assert scores["confusion"] == [[1, 0, 0], [1, 1, 0], [0, 0, 1]]


@pytest.mark.parametrize("architecture", ["small", "large"])
def test_both_networks_give_three_outputs(architecture):
    model = type_model.build_model(pretrained=False, architecture=architecture)

    probabilities = type_model.predict(model, [Image.new("RGB", (160, 160), (200, 90, 90))])

    assert probabilities.shape == (1, len(LEARNED))


def test_close_up_size_can_change():
    photo = Image.new("RGB", (800, 600), (200, 150, 130))

    assert type_model.close_up(photo, [100, 100, 150, 150], size=160).size == (160, 160)
