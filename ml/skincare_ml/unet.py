"""The U-Net for wrinkles and dark spots (Phase 3 Step 4, designed 2026-11-23).

Encoder = torchvision's ResNet34 (BSD), pretrained on ImageNet (the general "edges and textures"
head start); decoder = the classic U-Net path: upsample, join the encoder's feature map of the same
size (skip connection, keeps thin lines sharp), two 3x3 convolutions. Output: 2 channels of logits
at the input size, channel 0 = wrinkles, channel 1 = dark spots (sigmoid -> probability).

Loss (masked): each pixel of each channel is 0 (no), 1 (yes) or IGNORE (unknown: the other
dataset's channel, MEMI's unchecked regions, padding). Ignored pixels add nothing to the loss.
BCE (every pixel right or wrong) + soft Dice (overlap, robust to rare pixels: wrinkles are ~1.3%
of the face).
"""

import torch
import torch.nn.functional as F
from torch import nn
from torchvision.models import ResNet34_Weights, resnet34

CHANNELS = ("wrinkles", "dark_spots")
IGNORE = 255


class _Up(nn.Module):
    def __init__(self, in_channels: int, skip_channels: int, out_channels: int):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_channels + skip_channels, out_channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x, skip=None):
        x = F.interpolate(x, scale_factor=2, mode="nearest")
        if skip is not None:
            x = torch.cat([x, skip], dim=1)
        return self.block(x)


class UNet(nn.Module):
    def __init__(self, pretrained: bool = True, out_channels: int = len(CHANNELS)):
        super().__init__()
        encoder = resnet34(weights=ResNet34_Weights.IMAGENET1K_V1 if pretrained else None)
        self.stem = nn.Sequential(encoder.conv1, encoder.bn1, encoder.relu)  # 1/2, 64
        self.pool = encoder.maxpool  # 1/4
        self.layer1, self.layer2 = encoder.layer1, encoder.layer2  # 1/4 64, 1/8 128
        self.layer3, self.layer4 = encoder.layer3, encoder.layer4  # 1/16 256, 1/32 512
        self.up4 = _Up(512, 256, 256)  # -> 1/16
        self.up3 = _Up(256, 128, 128)  # -> 1/8
        self.up2 = _Up(128, 64, 64)  # -> 1/4
        self.up1 = _Up(64, 64, 32)  # -> 1/2
        self.up0 = _Up(32, 0, 16)  # -> full size
        self.head = nn.Conv2d(16, out_channels, 1)
        # ImageNet colour normalisation inside the model, so the server only sends RGB 0-1
        self.register_buffer("mean", torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1))
        self.register_buffer("std", torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1))

    def forward(self, x):
        """x: N x 3 x H x W, RGB 0-1, H and W multiples of 32 -> N x 2 x H x W logits."""
        x = (x - self.mean) / self.std
        s1 = self.stem(x)
        s2 = self.layer1(self.pool(s1))
        s3 = self.layer2(s2)
        s4 = self.layer3(s3)
        x = self.layer4(s4)
        x = self.up4(x, s4)
        x = self.up3(x, s3)
        x = self.up2(x, s2)
        x = self.up1(x, s1)
        return self.head(self.up0(x))


def masked_loss(logits: torch.Tensor, labels: torch.Tensor, dice_weight: float = 1.0) -> dict:
    """BCE + soft Dice per channel over the known pixels only.

    labels: N x C x H x W uint8 (0, 1 or IGNORE). A channel with no known pixel in the batch adds
    nothing. Returns {"loss": total, "<channel>": its part (float)}.
    """
    total = logits.new_zeros(())
    parts = {}
    for c, name in enumerate(CHANNELS):
        known = labels[:, c] != IGNORE
        if not known.any():
            parts[name] = 0.0
            continue
        target = (labels[:, c] == 1).float()[known]
        logit = logits[:, c][known].float()
        bce = F.binary_cross_entropy_with_logits(logit, target)
        prob = torch.sigmoid(logit)
        dice = 1 - (2 * (prob * target).sum() + 1) / (prob.sum() + target.sum() + 1)
        part = bce + dice_weight * dice
        total = total + part
        parts[name] = float(part.detach())
    return {"loss": total, **parts}


def dice_counts(logits: torch.Tensor, labels: torch.Tensor, cutoff: float = 0.5) -> dict:
    """Per channel: overlap, predicted and true pixel counts over the known pixels (summed over a
    whole validation set they give Dice = 2 x overlap / (predicted + true))."""
    out = {}
    for c, name in enumerate(CHANNELS):
        known = labels[:, c] != IGNORE
        predicted = (torch.sigmoid(logits[:, c].float()) >= cutoff) & known
        true = (labels[:, c] == 1) & known
        out[name] = (int((predicted & true).sum()), int(predicted.sum()), int(true.sum()))
    return out
