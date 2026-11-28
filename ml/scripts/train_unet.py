r"""Part 4.2: train the U-Net (wrinkles + dark spots).

    cd ml; $env:PYTHONPATH = "."
    python scripts/train_unet.py                 # run "v1" (GPU laptop, 2026-11-26)
    python scripts/train_unet.py --run v2 --data unet_data_v2 --init unet_v1_state.pt `
        --epochs 10 --patience 4 --lr 1e-4       # v2: continues from v1 (CPU overnight)
    python scripts/train_unet.py --run v2 --resume   # continue a run after a stop
    python scripts/train_unet.py --smoke         # 1-minute CPU check of the whole loop

Reads prepared/<--data>/ (scripts/export_unet_data.py). Each epoch: every training wrinkle photo
once + every training MEMI photo --memi-repeat times, with random changes; then the validation
photos without changes. The best epoch = the highest mean of the two channels' validation Dice
(cutoff 0.5); it stops after --patience epochs without a better one. Every epoch also reports
`val_dark_on_normal_pct`: the share of the normal (FFHQ) validation pictures painted as dark
patches (v1 painted ~49%; it should be near 0). The TEST photos are never read here. --init starts
from saved weights (a file in <data folder>/models or a full path) instead of ImageNet.
Output: prepared/unet_runs/<run>/ best.pt, last.pt (every epoch, for --resume), results.csv (one
line per epoch: do NOT open it in Excel while training), settings.json.
Loader workers stay 0 (Step 3 lesson: Windows worker processes filled the GPU laptop's 16 GB RAM).
"""

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import torch

from skincare_ml import config
from skincare_ml.ram_guard import PROCESS_LIMIT, RamGuard, RamLimitReached
from skincare_ml.unet import CHANNELS, UNet, dice_counts, masked_loss
from skincare_ml.unet_data import SIZE, UNetDataset

FIELDS = ["epoch", "seconds", "lr", "train_loss", "val_loss",
          *[f"val_dice_{c}" for c in CHANNELS], "val_dice_mean", "val_dark_on_normal_pct", "best",
          "ram_peak_gb", "ram_peak_share"]  # fmt: skip
SOURCES = ("ffhq_wrinkle", "memi_ds")
RAM_CHECK_EVERY = 20  # batches


def parse(argv):
    p = argparse.ArgumentParser(description="Train the U-Net for wrinkles and dark spots.")
    p.add_argument("--run", default="v1")
    p.add_argument("--data", default="unet_data", help="folder in prepared/ (unet_data_v2 for v2)")
    p.add_argument("--init", default=None, help="start from these weights instead of ImageNet")
    p.add_argument("--epochs", type=int, default=60)
    p.add_argument("--patience", type=int, default=15)
    p.add_argument("--batch", type=int, default=8)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--memi-repeat", type=int, default=4)
    p.add_argument("--size", type=int, default=SIZE)
    p.add_argument("--device", default=None, help="cuda, cpu (default: cuda if available)")
    p.add_argument("--ram-limit", type=float, default=PROCESS_LIMIT,
                   help="stop cleanly above this share of the RAM (default 0.60)")
    p.add_argument("--resume", action="store_true", help="continue this run from its last.pt")
    p.add_argument("--smoke", action="store_true", help="tiny CPU run to check the code")
    return p.parse_args(argv)


def evaluate(model, loaders: dict, device, amp, guard: RamGuard | None = None) -> dict:
    """Dice over all validation photos; plus the share of the normal (FFHQ) pictures predicted as
    dark patches, whatever their labels say (the v1 false-alarm check)."""
    model.eval()
    losses, counts = [], {c: np.zeros(3) for c in CHANNELS}
    dark_pixels = all_pixels = 0
    dark = CHANNELS.index("dark_spots")
    with torch.no_grad():
        for source, loader in loaders.items():
            for step, (photos, labels) in enumerate(loader):
                if guard and step % RAM_CHECK_EVERY == 0:
                    guard.check()
                photos, labels = photos.to(device), labels.to(device)
                with torch.autocast(device.type, enabled=amp):
                    logits = model(photos)
                losses.append(float(masked_loss(logits, labels)["loss"]))
                for name, value in dice_counts(logits, labels).items():
                    counts[name] += value
                if source == "ffhq_wrinkle":
                    dark_pixels += int((logits[:, dark] >= 0).sum())  # logit 0 = probability 0.5
                    all_pixels += logits[:, dark].numel()
    dice = {c: (2 * n[0] / (n[1] + n[2]) if n[1] + n[2] else 0.0) for c, n in counts.items()}
    return {"loss": float(np.mean(losses)), "dice": dice, "mean": float(np.mean(list(dice.values()))),
            "dark_on_normal_pct": 100 * dark_pixels / all_pixels if all_pixels else 0.0}  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    run_dir = config.prepared_dir() / "unet_runs" / (f"{args.run}_smoke" if args.smoke else args.run)
    checkpoint = None
    if args.resume:
        if not (run_dir / "last.pt").exists():
            print(f"{run_dir / 'last.pt'} is missing: nothing to resume", file=sys.stderr)
            return 1
        checkpoint = torch.load(run_dir / "last.pt", map_location="cpu", weights_only=False)
        saved = checkpoint["settings"]
        for key in ("epochs", "patience", "batch", "lr", "memi_repeat", "size", "data", "init"):
            if key in saved:
                setattr(args, key, saved[key])
        print(f"resuming {args.run} after epoch {checkpoint['epoch']}")
    elif (run_dir / "last.pt").exists():
        print(f"{run_dir} already has a run: use --resume, or another --run name", file=sys.stderr)
        return 1
    data = config.prepared_dir() / args.data
    if not (data / "index.json").exists():
        print(f"{data} is missing: export or copy it first", file=sys.stderr)
        return 1
    if args.smoke:
        args.device, args.epochs, args.batch, args.size = "cpu", 1, 2, 128
    device = torch.device(args.device or ("cuda" if torch.cuda.is_available() else "cpu"))
    amp = device.type == "cuda"
    torch.manual_seed(2026)
    run_dir.mkdir(parents=True, exist_ok=True)

    limit = 2 if args.smoke else None
    train = UNetDataset(data, "train", True, args.size, args.memi_repeat, limit=limit)
    val = {s: UNetDataset(data, "val", False, args.size, limit=limit, sources=(s,)) for s in SOURCES}
    train_loader = torch.utils.data.DataLoader(train, batch_size=args.batch, shuffle=True,
                                               num_workers=0, drop_last=True)  # fmt: skip
    val_loaders = {s: torch.utils.data.DataLoader(v, batch_size=args.batch, num_workers=0)
                   for s, v in val.items()}  # fmt: skip

    model = UNet(pretrained=not args.smoke and checkpoint is None and args.init is None).to(device)
    if args.init and checkpoint is None:
        init = config.data_dir() / "models" / args.init
        init = init if init.exists() else Path(args.init)
        model.load_state_dict(torch.load(init, map_location="cpu", weights_only=True)["state_dict"])
        print(f"starting from {init}")
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    scaler = torch.amp.GradScaler(device.type, enabled=amp)
    start, best, best_epoch = 1, -1.0, 0
    if checkpoint:
        model.load_state_dict(checkpoint["state_dict"])
        optimizer.load_state_dict(checkpoint["optimizer"])
        scheduler.load_state_dict(checkpoint["scheduler"])
        scaler.load_state_dict(checkpoint["scaler"])
        start, best, best_epoch = checkpoint["epoch"] + 1, checkpoint["best"], checkpoint["best_epoch"]
        torch.set_rng_state(checkpoint["torch_rng"])
    settings = {k: getattr(args, k) for k in ("run", "epochs", "patience", "batch", "lr",
                                              "memi_repeat", "size", "ram_limit", "data",
                                              "init")}  # fmt: skip
    settings |= {"device": str(device), "gpu": torch.cuda.get_device_name(0) if amp else None,
                 "torch": torch.__version__, "train_items": len(train),
                 "val_items": sum(len(v) for v in val.values()),
                 "data_index_sha256": hashlib.sha256((data / "index.json").read_bytes()).hexdigest(),
                 "started" if not checkpoint else "resumed": datetime.now().isoformat()}  # fmt: skip
    (run_dir / ("settings.json" if not checkpoint else f"resumed_{start}.json")).write_text(
        json.dumps(settings, indent=1) + "\n", encoding="utf-8")
    results = run_dir / "results.csv"
    if not results.exists():
        results.write_text(",".join(FIELDS) + "\n", encoding="utf-8")
    print(f"{len(train)} training items, {settings['val_items']} validation photos, "
          f"device {device}, batch {args.batch}, {args.size} px")  # fmt: skip

    guard = RamGuard(process_limit=args.ram_limit)
    try:
        if args.init and checkpoint is None:  # the starting point, scored on the same labels
            began = time.time()
            result = evaluate(model, val_loaders, device, amp, guard)
            best = result["mean"]
            write_row(results, epoch_row(0, began, args.lr, float("nan"), result, False, guard))
            print(f"before training (epoch 0 = {args.init}): " + describe(result), flush=True)
        best, best_epoch = train_epochs(args, model, optimizer, scheduler, scaler, train_loader,
                                        val_loaders, device, amp, guard, run_dir, results, settings,
                                        start, best, best_epoch)  # fmt: skip
    except RamLimitReached as reason:
        print(f"\nSTOPPED SAFELY: {reason}.\nNothing is lost: every finished epoch is saved. "
              f"Continue with: python scripts/train_unet.py --run {args.run} --resume", flush=True)
        return 2
    if best_epoch == 0:
        print(f"no epoch beat the starting weights (mean Dice {best:.3f}): no best.pt written")
    else:
        print(f"best epoch {best_epoch}: mean validation Dice {best:.3f} -> {run_dir / 'best.pt'}")
    return 0


def describe(result: dict) -> str:
    return ("dice " + "  ".join(f"{c} {result['dice'][c]:.3f}" for c in CHANNELS)
            + f"  dark on normal faces {result['dark_on_normal_pct']:.1f}%")  # fmt: skip


def epoch_row(epoch, began, lr, train_loss, result, improved, guard) -> list:
    return [epoch, round(time.time() - began, 1), f"{lr:.2e}", round(train_loss, 4),
            round(result["loss"], 4), *[round(result["dice"][c], 4) for c in CHANNELS],
            round(result["mean"], 4), round(result["dark_on_normal_pct"], 2), int(improved),
            *guard.take_peak()]  # fmt: skip


def write_row(results, row) -> None:
    with open(results, "a", encoding="utf-8") as file:  # opened and closed every epoch
        file.write(",".join(map(str, row)) + "\n")


def train_epochs(args, model, optimizer, scheduler, scaler, train_loader, val_loaders, device, amp,
                 guard, run_dir, results, settings, start, best, best_epoch):  # fmt: skip
    for epoch in range(start, args.epochs + 1):
        began = time.time()
        model.train()
        train_losses = []
        for step, (photos, labels) in enumerate(train_loader):
            if step % RAM_CHECK_EVERY == 0:
                guard.check()
            photos, labels = photos.to(device), labels.to(device)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device.type, enabled=amp):
                logits = model(photos)
            loss = masked_loss(logits, labels)["loss"]
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            train_losses.append(float(loss.detach()))
        lr = scheduler.get_last_lr()[0]
        scheduler.step()
        result = evaluate(model, val_loaders, device, amp, guard)
        guard.check()
        improved = result["mean"] > best
        if improved:
            best, best_epoch = result["mean"], epoch
        state = {"state_dict": model.state_dict(), "epoch": epoch, "best": best,
                 "best_epoch": best_epoch, "settings": settings, "channels": CHANNELS,
                 "val": result}  # fmt: skip
        if improved:
            torch.save(state, run_dir / "best.pt")
        torch.save(state | {"optimizer": optimizer.state_dict(), "scheduler": scheduler.state_dict(),
                            "scaler": scaler.state_dict(), "torch_rng": torch.get_rng_state()},
                   run_dir / "last.pt")  # fmt: skip
        row = epoch_row(epoch, began, lr, float(np.mean(train_losses)), result, improved, guard)
        write_row(results, row)
        print(f"epoch {epoch}/{args.epochs}  {row[1]:.0f}s  train {row[3]}  val {row[4]}  "
              + describe(result) + f"  RAM {row[-2]} GB ({row[-1]:.0%})"
              + ("  * best" if improved else ""), flush=True)  # fmt: skip
        if epoch - best_epoch >= args.patience:
            print(f"no better epoch for {args.patience} epochs: stopping")
            break
    return best, best_epoch


if __name__ == "__main__":
    sys.exit(main())
