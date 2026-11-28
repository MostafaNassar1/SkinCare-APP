import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest
import torch

from skincare_ml.unet import IGNORE, UNet, dice_counts, masked_loss
from skincare_ml.unet_data import (
    UNetDataset,
    augmented,
    encode_labels,
    place,
    placement,
    shrink,
)

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


# ---------- model and loss ----------


def test_unet_gives_two_channels_at_the_input_size():
    model = UNet(pretrained=False).eval()
    with torch.no_grad():
        out = model(torch.rand(1, 3, 64, 96))
    assert out.shape == (1, 2, 64, 96)


def test_ignored_pixels_never_change_the_loss():
    labels = torch.full((1, 2, 4, 4), IGNORE, dtype=torch.uint8)
    labels[0, 0, :2] = 1  # wrinkles known on the top half only
    labels[0, 0, 2:3] = 0
    logits = torch.zeros(1, 2, 4, 4)
    changed = logits.clone()
    changed[0, 0, 3] = 50.0  # ignored row of the wrinkle channel
    changed[0, 1] = -50.0  # the dark-spot channel is unknown everywhere

    first, second = masked_loss(logits, labels), masked_loss(changed, labels)

    assert float(first["loss"]) == pytest.approx(float(second["loss"]))
    assert first["dark_spots"] == 0.0 and first["wrinkles"] > 0


def test_a_perfect_prediction_has_a_small_loss_and_full_dice():
    labels = torch.zeros(1, 2, 8, 8, dtype=torch.uint8)
    labels[0, :, 2:4, 2:6] = 1
    logits = torch.where(labels == 1, 20.0, -20.0).float()

    assert float(masked_loss(logits, labels)["loss"]) < 0.01
    overlap, predicted, true = dice_counts(logits, labels)["wrinkles"]
    assert overlap == predicted == true == 8


# ---------- labels, shrinking, placement ----------


def test_labels_of_each_source():
    wrinkles = np.zeros((4, 4), np.uint8)
    wrinkles[1, 1] = 255
    ffhq = encode_labels((4, 4), wrinkles=wrinkles)
    assert ffhq[1, 1, 0] == 1 and ffhq[0, 0, 0] == 0 and (ffhq[..., 1] == IGNORE).all()

    dark = np.zeros((4, 4), np.uint8)
    dark[0, 0] = 1
    known = np.zeros((4, 4), np.uint8)
    known[3] = 1  # only the bottom row was checked
    memi = encode_labels((4, 4), dark_spots=dark, known_dark=known)
    assert memi[0, 0, 1] == 1  # marked = always a dark spot
    assert memi[3, 0, 1] == 0 and memi[1, 1, 1] == IGNORE
    assert (memi[..., 0] == IGNORE).all() and (memi[..., 2] == 0).all()


def test_shrink_keeps_half_marked_pixels_and_marks_partly_unknown_ones_unknown():
    labels = np.zeros((8, 8, 3), np.uint8)
    labels[0:2, :, 0] = 1  # a 2 px line: half of each 4 px block -> kept
    labels[6, 0, 1] = IGNORE  # one unknown pixel in the bottom-left block
    _, small = shrink(np.zeros((8, 8, 3), np.uint8), labels, 2)

    assert small[0, :, 0].tolist() == [1, 1]
    assert small[1, 0, 1] == IGNORE and small[1, 1, 1] == 0


def test_letterbox_shows_the_whole_crop_and_the_padding_means_nothing_there():
    image = np.full((50, 100, 3), 200, np.uint8)
    labels = np.full((50, 100, 3), IGNORE, np.uint8)  # the crop itself unknown

    photo, marks = place(image, labels, placement(100, 50, 64), 64)

    assert photo[32, 32].tolist() == [200, 200, 200] and photo[0, 32].tolist() == [0, 0, 0]
    assert (marks[0, :, :2] == 0).all()  # v2: the black border is "no" for both channels
    assert (marks[32, :, :2] == IGNORE).all()  # the crop keeps its own labels


def test_v2_labels_known_masks_for_both_channels():
    wrinkles = np.zeros((4, 4), np.uint8)
    no_dark = np.zeros((4, 4), np.uint8)
    ffhq = encode_labels((4, 4), wrinkles=wrinkles, dark_spots=no_dark)
    assert (ffhq[..., 1] == 0).all()  # v2: a normal face has no dark patches

    known = np.zeros((4, 4), np.uint8)
    known[:, 0] = 1
    partly = encode_labels((4, 4), wrinkles=wrinkles, known_wrinkles=known)
    assert (partly[:, 0, 0] == 0).all() and (partly[:, 1:, 0] == IGNORE).all()


def test_random_versions_keep_valid_labels():
    rng = np.random.default_rng(0)
    image = (np.random.default_rng(1).random((80, 60, 3)) * 255).astype(np.uint8)
    labels = encode_labels((80, 60), wrinkles=np.eye(80, 60, dtype=np.uint8))
    for _ in range(5):
        photo, marks = augmented(image, labels, rng, 64)
        assert photo.shape == (64, 64, 3)
        assert set(np.unique(marks[..., :2])) <= {0, 1, IGNORE}


# ---------- dataset and the training loop ----------


def _tiny_data(root: Path) -> Path:
    folder = root / "prepared" / "unet_data"
    (folder / "images").mkdir(parents=True)
    (folder / "labels").mkdir()
    rng = np.random.default_rng(0)
    items = []
    for n, (source, split) in enumerate([("ffhq_wrinkle", "train"), ("ffhq_wrinkle", "train"),
                                         ("memi_ds", "train"), ("memi_ds", "train"),
                                         ("ffhq_wrinkle", "val"), ("memi_ds", "val")]):  # fmt: skip
        image = (rng.random((160, 120, 3)) * 255).astype(np.uint8)
        mask = np.zeros((160, 120), np.uint8)
        mask[60:64, 20:100] = 1
        labels = (encode_labels((160, 120), wrinkles=mask) if source == "ffhq_wrinkle"
                  else encode_labels((160, 120), dark_spots=mask))  # fmt: skip
        cv2.imwrite(str(folder / "images" / f"{n}.jpg"), image)
        cv2.imwrite(str(folder / "labels" / f"{n}.png"), labels)
        items.append({"source": source, "split": split, "image": f"images/{n}.jpg",
                      "labels": f"labels/{n}.png"})  # fmt: skip
    (folder / "index.json").write_text(json.dumps({"items": items}), encoding="utf-8")
    return folder


def test_dataset_repeats_memi_photos_and_limits_per_source(tmp_path):
    folder = _tiny_data(tmp_path)

    train = UNetDataset(folder, "train", True, 64, memi_repeat=3)
    assert len(train) == 2 + 2 * 3
    assert len(UNetDataset(folder, "train", True, 64, limit=1)) == 2  # one of each source
    photo, labels = UNetDataset(folder, "val", False, 64)[0]
    assert photo.shape == (3, 64, 64) and labels.shape == (2, 64, 64)
    assert photo.dtype == torch.float32 and labels.dtype == torch.uint8


def test_smoke_training_writes_a_run_and_refuses_to_overwrite_it(monkeypatch, tmp_path):
    _tiny_data(tmp_path)
    monkeypatch.setenv("SKINCARE_DATA_DIR", str(tmp_path))
    monkeypatch.syspath_prepend(str(SCRIPTS))
    sys.modules.pop("train_unet", None)
    import train_unet

    assert train_unet.main(["--smoke"]) == 0
    run = tmp_path / "prepared" / "unet_runs" / "v1_smoke"
    lines = (run / "results.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("epoch,") and len(lines) == 2
    assert (run / "best.pt").exists() and (run / "last.pt").exists()
    assert train_unet.main(["--smoke"]) == 1  # a second start needs --resume
    assert train_unet.main(["--smoke", "--resume"]) == 0  # already at its last epoch: nothing to do
    header = lines[0].split(",")
    row = dict(zip(header, lines[1].split(","), strict=True))
    assert 0 < float(row["ram_peak_share"]) < 0.6  # the peak RAM of the epoch is recorded
    assert 0 <= float(row["val_dark_on_normal_pct"]) <= 100  # the false-alarm check


def test_a_run_can_start_from_saved_weights_and_scores_them_first(monkeypatch, tmp_path, capsys):
    _tiny_data(tmp_path)
    monkeypatch.setenv("SKINCARE_DATA_DIR", str(tmp_path))
    monkeypatch.syspath_prepend(str(SCRIPTS))
    sys.modules.pop("train_unet", None)
    import train_unet

    (tmp_path / "models").mkdir()
    torch.save({"state_dict": UNet(pretrained=False).state_dict()}, tmp_path / "models" / "start.pt")

    assert train_unet.main(["--smoke", "--run", "v2", "--init", "start.pt"]) == 0
    lines = (tmp_path / "prepared" / "unet_runs" / "v2_smoke" / "results.csv").read_text(
        encoding="utf-8").splitlines()
    assert [line.split(",")[0] for line in lines[1:]] == ["0", "1"]  # epoch 0 = the start weights
    out = capsys.readouterr().out
    assert "before training (epoch 0 = start.pt)" in out and "dark on normal faces" in out
    settings = json.loads((tmp_path / "prepared" / "unet_runs" / "v2_smoke" / "settings.json")
                          .read_text(encoding="utf-8"))  # fmt: skip
    assert settings["init"] == "start.pt" and settings["data"] == "unet_data"


def test_training_stops_safely_when_the_ram_limit_is_crossed(monkeypatch, tmp_path, capsys):
    _tiny_data(tmp_path)
    monkeypatch.setenv("SKINCARE_DATA_DIR", str(tmp_path))
    monkeypatch.syspath_prepend(str(SCRIPTS))
    sys.modules.pop("train_unet", None)
    import train_unet

    assert train_unet.main(["--smoke", "--ram-limit", "0.0001"]) == 2
    assert "STOPPED SAFELY" in capsys.readouterr().out


def test_ram_guard_limits(monkeypatch):
    from skincare_ml import ram_guard

    guard = ram_guard.RamGuard(process_limit=0.6, system_limit=0.9)
    guard.total = 100
    monkeypatch.setattr(guard, "used_by_training", lambda: 50)
    monkeypatch.setattr(ram_guard.psutil, "virtual_memory",
                        lambda: type("M", (), {"percent": 70.0})())  # fmt: skip
    guard.check()  # 50% of the RAM, laptop at 70%: fine
    assert guard.take_peak() == (round(50 / 2**30, 2), 0.5)

    monkeypatch.setattr(guard, "used_by_training", lambda: 61)
    with pytest.raises(ram_guard.RamLimitReached, match="limit 60%"):
        guard.check()
    monkeypatch.setattr(guard, "used_by_training", lambda: 10)
    monkeypatch.setattr(ram_guard.psutil, "virtual_memory",
                        lambda: type("M", (), {"percent": 95.0})())  # fmt: skip
    with pytest.raises(ram_guard.RamLimitReached, match="close other programs"):
        guard.check()
