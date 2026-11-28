"""Training data for the U-Net (Phase 3 Step 4, 2026-11-23; label rules v2 on 2026-11-28).

Each photo is stored ONCE (scripts/export_unet_data.py) as its U-Net face crop shrunk to
STORED_SIDE px + a label picture (PNG, OpenCV channel 0 = wrinkles, 1 = dark spots, 2 unused) whose
pixels are 0 (no), 1 (yes) or IGNORE (unknown). Training places each crop on a SIZE x SIZE canvas
(whole crop visible) with random changes; validation and the app use the same placement without
the random part ("letterbox").

v2 (after v1 painted ~49% of every normal face as dark patches: the dark channel had only ever seen
MEMI photos and never a "no" outside them): the padding is "no" for both channels (it was unknown,
and v1 marked the black border) and FFHQ faces are "no dark patches" (export_unet_data.py).
"""

import json
from pathlib import Path

import cv2
import numpy as np
import torch

from skincare_ml.unet import IGNORE

SIZE = 512  # model input (Part 4.1: 512 keeps 90% of the wrinkle pixels, 768 only 1 point more)
STORED_SIDE = 640  # longest side of the stored crops: room for zooming in during training


def encode_labels(shape, wrinkles=None, dark_spots=None, known_dark=None,
                  known_wrinkles=None) -> np.ndarray:  # fmt: skip
    """H x W x 3 uint8 label picture: channel 0 wrinkles, 1 dark spots (0 / 1 / IGNORE), 2 zero.

    A channel given as None is unknown everywhere; a channel given as a mask is known where its
    `known_*` picture is 1 (everywhere when that is None). A marked pixel is always known."""
    labels = np.full((*shape[:2], 3), IGNORE, np.uint8)
    labels[..., 2] = 0
    for c, (mask, known) in enumerate(((wrinkles, known_wrinkles), (dark_spots, known_dark))):
        if mask is None:
            continue
        marked = (mask > 0).astype(np.uint8)
        trusted = np.ones(shape[:2], bool) if known is None else known > 0
        labels[..., c] = np.where(trusted | (marked > 0), marked, IGNORE)
    return labels


def shrink(image: np.ndarray, labels: np.ndarray, longest: int) -> tuple[np.ndarray, np.ndarray]:
    """Shrink a crop and its labels so the longest side is `longest` (never enlarges).

    A small label pixel is "yes" when at least half of it was "yes" (thin lines survive as in the
    Part 4.1 measure), otherwise IGNORE when any part of it was unknown, otherwise "no"."""
    height, width = image.shape[:2]
    scale = min(1.0, longest / max(height, width))
    if scale == 1.0:
        return image, labels
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    small = cv2.resize(image, size, interpolation=cv2.INTER_AREA)
    out = np.zeros((size[1], size[0], 3), np.uint8)
    for c in (0, 1):
        yes = cv2.resize((labels[..., c] == 1).astype(np.float32), size, interpolation=cv2.INTER_AREA)
        unknown = cv2.resize((labels[..., c] == IGNORE).astype(np.float32), size,
                             interpolation=cv2.INTER_AREA)  # fmt: skip
        out[..., c] = np.where(yes >= 0.5, 1, np.where(unknown > 0, IGNORE, 0))
    return small, out


def placement(width: int, height: int, size: int = SIZE, zoom: float = 1.0, angle: float = 0.0,
              shift: tuple[float, float] = (0.0, 0.0)) -> np.ndarray:  # fmt: skip
    """2 x 3 affine matrix putting a width x height crop on a size x size canvas: the whole crop
    fits (letterbox) at zoom 1, centred, then zoomed / turned (degrees) / shifted (canvas share)."""
    scale = size / max(width, height) * zoom
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, scale)
    matrix[0, 2] += size / 2 - width / 2 + shift[0] * size
    matrix[1, 2] += size / 2 - height / 2 + shift[1] * size
    return matrix


def place(image: np.ndarray, labels: np.ndarray, matrix: np.ndarray, size: int = SIZE):
    """Apply a placement: photo smoothly, labels without blending. The padding is black and
    labelled "no" for both channels (v2: v1 left it unknown and then marked the black border)."""
    photo = cv2.warpAffine(image, matrix, (size, size), flags=cv2.INTER_LINEAR,
                           borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))  # fmt: skip
    marks = cv2.warpAffine(labels, matrix, (size, size), flags=cv2.INTER_NEAREST,
                           borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))  # fmt: skip
    return photo, marks


def phone_like(image: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """A softer, compressed copy, like an ordinary selfie (the Step 3 lesson: model C)."""
    height, width = image.shape[:2]
    factor = rng.uniform(0.4, 0.75)
    small = cv2.resize(image, (max(1, int(width * factor)), max(1, int(height * factor))),
                       interpolation=cv2.INTER_AREA)  # fmt: skip
    _, jpeg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, int(rng.integers(55, 90))])
    return cv2.resize(cv2.imdecode(jpeg, cv2.IMREAD_COLOR), (width, height),
                      interpolation=cv2.INTER_LINEAR)  # fmt: skip


def colour_jitter(image: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Random brightness, contrast and saturation (each +-20%)."""
    out = image.astype(np.float32)
    out = (out - out.mean()) * rng.uniform(0.8, 1.2) + out.mean() * rng.uniform(0.8, 1.2)
    grey = out.mean(axis=2, keepdims=True)
    out = grey + (out - grey) * rng.uniform(0.8, 1.2)
    return out.clip(0, 255).astype(np.uint8)


def augmented(image, labels, rng: np.random.Generator, size: int = SIZE, phone_share: float = 0.3):
    """One random training version of a stored crop."""
    if rng.random() < 0.5:  # a mirrored face is still a face (labels move with it)
        image, labels = image[:, ::-1].copy(), labels[:, ::-1].copy()
    height, width = image.shape[:2]
    matrix = placement(width, height, size, zoom=rng.uniform(0.85, 1.2),
                       angle=rng.uniform(-10, 10),
                       shift=(rng.uniform(-0.05, 0.05), rng.uniform(-0.05, 0.05)))  # fmt: skip
    photo, marks = place(image, labels, matrix, size)
    photo = colour_jitter(photo, rng)
    if rng.random() < phone_share:
        photo = phone_like(photo, rng)
    return photo, marks


def to_tensors(photo_bgr: np.ndarray, marks: np.ndarray) -> tuple[torch.Tensor, torch.Tensor]:
    """BGR uint8 -> 3 x H x W RGB float 0-1; labels -> 2 x H x W uint8."""
    rgb = np.ascontiguousarray(photo_bgr[..., ::-1]).astype(np.float32) / 255
    return (torch.from_numpy(rgb).permute(2, 0, 1),
            torch.from_numpy(np.ascontiguousarray(marks[..., :2])).permute(2, 0, 1))  # fmt: skip


def load_index(folder: Path) -> list[dict]:
    return json.loads((folder / "index.json").read_text(encoding="utf-8"))["items"]


class UNetDataset(torch.utils.data.Dataset):
    """Items of one split. `repeat` = how many times each MEMI photo appears per epoch (balances 91
    melasma photos against 700 wrinkle photos); training adds random changes, validation not."""

    def __init__(self, folder: Path, split: str, train: bool, size: int = SIZE,
                 memi_repeat: int = 1, seed: int = 2026, limit: int | None = None,
                 sources: tuple[str, ...] = ("ffhq_wrinkle", "memi_ds")):  # fmt: skip
        items = [i for i in load_index(folder) if i["split"] == split and i["source"] in sources]
        if limit:  # quick checks: the first `limit` photos of each source
            items = [i for s in ("ffhq_wrinkle", "memi_ds")
                     for i in [j for j in items if j["source"] == s][:limit]]  # fmt: skip
        self.items = [i for i in items for _ in range(memi_repeat if i["source"] == "memi_ds" else 1)]
        self.folder, self.train, self.size = folder, train, size
        self.rng = np.random.default_rng(seed)

    def __len__(self):
        return len(self.items)

    def read(self, index: int) -> tuple[np.ndarray, np.ndarray]:
        item = self.items[index]
        image = cv2.imread(str(self.folder / item["image"]))
        labels = cv2.imread(str(self.folder / item["labels"]), cv2.IMREAD_UNCHANGED)
        if image is None or labels is None:
            raise FileNotFoundError(item["image"])
        return image, labels

    def __getitem__(self, index: int):
        image, labels = self.read(index)
        if self.train:
            photo, marks = augmented(image, labels, self.rng, self.size)
        else:
            height, width = image.shape[:2]
            photo, marks = place(image, labels, placement(width, height, self.size), self.size)
        return to_tensors(photo, marks)
