"""The lesion-type model: whitehead / papule / pustule from a close-up of one found pimple.

Used twice (decided 2026-11-02): now as a quick "scout" trained on this laptop's CPU, only to choose
the close-ups of labelling round 3 (active learning: likely pustules first) and thrown away; later
as the real second stage, trained on the GPU laptop with every label. Same code both times.

- Input: the same close-up the labeller saw (circle size x3, at least 64 px), shrunk to 96 px.
- Model: MobileNetV3-small pretrained on ImageNet (torchvision, BSD; small and fast on a CPU), its
  last layer replaced by 3 outputs, every layer fine-tuned.
- Augmentation: flips and small rotations only, NEVER colour changes: redness and a white / yellow
  centre are exactly what separates the types.
- Classes are unbalanced (pustules ~12%): the loss weights each class by 1 / its frequency, and the
  best epoch is chosen on the validation photos' balanced accuracy (the mean recall of the three
  types), so the rare pustules count as much as the common whiteheads.
"""

import random
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import torchvision
from PIL import Image
from torch import nn
from torchvision import transforms

from skincare_ml.lesion_types import LEARNED, crop_square

CLOSE_UP = (3.0, 64)  # as on the labelling page
SIZE = 96  # the close-up is shrunk to SIZE x SIZE px (variant "160px" tries a sharper 160)
# the network: MobileNetV3-small by default (variant "large" tries MobileNetV3-large)
ARCHITECTURES = {
    "small": (torchvision.models.mobilenet_v3_small,
              torchvision.models.MobileNet_V3_Small_Weights.IMAGENET1K_V1),
    "large": (torchvision.models.mobilenet_v3_large,
              torchvision.models.MobileNet_V3_Large_Weights.IMAGENET1K_V2),
}  # fmt: skip
IMAGENET_MEAN, IMAGENET_STD = (0.485, 0.456, 0.406), (0.229, 0.224, 0.225)

TRAIN_TRANSFORM = transforms.Compose([
    transforms.RandomHorizontalFlip(),
    transforms.RandomVerticalFlip(),
    transforms.RandomRotation(15),
    transforms.ToTensor(),
    transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
])  # fmt: skip
EVAL_TRANSFORM = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
])  # fmt: skip


def close_up(photo: Image.Image, box, size: int = SIZE) -> Image.Image:
    area = crop_square(tuple(box), photo.width, photo.height, *CLOSE_UP)
    return photo.crop(area).resize((size, size), Image.LANCZOS)


def load_close_ups(
    items: list[dict], sources: Path, progress=None, size: int = SIZE
) -> list[Image.Image]:
    """The close-up of every item, opening each photo only once (photos are 3-5,000 px)."""
    by_file: dict[str, list[int]] = defaultdict(list)
    for index, item in enumerate(items):
        by_file[item["file"]].append(index)
    crops: list[Image.Image | None] = [None] * len(items)
    for done, (file, indexes) in enumerate(by_file.items(), start=1):
        with Image.open(sources / file) as photo:
            photo = photo.convert("RGB")
            for index in indexes:
                crops[index] = close_up(photo, items[index]["box"], size)
        if progress and done % 100 == 0:
            progress(f"  {done} / {len(by_file)} photos")
    return crops


def build_model(pretrained: bool = True, architecture: str = "small") -> nn.Module:
    make, weights = ARCHITECTURES[architecture]
    model = make(weights=weights if pretrained else None)
    model.classifier[3] = nn.Linear(model.classifier[3].in_features, len(LEARNED))
    return model


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def train(
    model: nn.Module,
    train_images: list[Image.Image],
    train_labels: list[int],
    val_images: list[Image.Image],
    val_labels: list[int],
    epochs: int = 12,
    lr: float = 3e-4,
    batch_size: int = 32,
    progress=None,
) -> list[dict]:
    """Fine-tune; keeps the weights of the epoch with the best validation balanced accuracy."""
    counts = np.bincount(train_labels, minlength=len(LEARNED)).astype(float)
    weights = torch.tensor(counts.sum() / (len(LEARNED) * np.maximum(counts, 1)), dtype=torch.float)
    loss_fn = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    history, best, best_state = [], -1.0, None
    order = list(range(len(train_images)))
    for epoch in range(1, epochs + 1):
        model.train()
        random.shuffle(order)
        total = 0.0
        for start in range(0, len(order), batch_size):
            batch = order[start : start + batch_size]
            x = torch.stack([TRAIN_TRANSFORM(train_images[i]) for i in batch])
            y = torch.tensor([train_labels[i] for i in batch])
            optimizer.zero_grad()
            loss = loss_fn(model(x), y)
            loss.backward()
            optimizer.step()
            total += loss.item() * len(batch)
        scores = evaluate(val_labels, predict(model, val_images))
        history.append({"epoch": epoch, "loss": round(total / len(order), 4), **scores})
        if progress:
            progress(f"  epoch {epoch}: loss {history[-1]['loss']:.3f}, validation balanced "
                     f"accuracy {scores['balanced_accuracy']:.3f}")  # fmt: skip
        if scores["balanced_accuracy"] > best:
            best = scores["balanced_accuracy"]
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)
    return history


@torch.no_grad()
def predict(model: nn.Module, images: list[Image.Image], batch_size: int = 128) -> np.ndarray:
    """Probabilities (one row per image, columns in LEARNED order)."""
    model.eval()
    rows = []
    for start in range(0, len(images), batch_size):
        x = torch.stack([EVAL_TRANSFORM(image) for image in images[start : start + batch_size]])
        rows.append(torch.softmax(model(x), dim=1).numpy())
    return np.concatenate(rows) if rows else np.zeros((0, len(LEARNED)))


def evaluate(labels: list[int], probabilities: np.ndarray) -> dict:
    """Accuracy, balanced accuracy (mean recall per type), recall per type, confusion matrix."""
    predicted = probabilities.argmax(axis=1)
    labels = np.asarray(labels)
    confusion = np.zeros((len(LEARNED), len(LEARNED)), dtype=int)
    for truth, guess in zip(labels, predicted, strict=True):
        confusion[truth, guess] += 1
    recall = {
        name: round(float(confusion[i, i] / confusion[i].sum()), 3) if confusion[i].sum() else None
        for i, name in enumerate(LEARNED)
    }
    present = [r for r in recall.values() if r is not None]
    return {
        "accuracy": round(float((predicted == labels).mean()), 3) if len(labels) else None,
        "balanced_accuracy": round(float(np.mean(present)), 3) if present else 0.0,
        "recall": recall,
        "confusion": confusion.tolist(),  # rows = the labeller's answer, columns = the model's
    }
