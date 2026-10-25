# ml/ — AI models of SkinCare-APP (Phase 3)

Two models are trained on public datasets and run on the server as ONNX files:

| Model | Finds | Draws on the photo | Severity from |
|---|---|---|---|
| YOLO pimple detector | whiteheads, pustules, other acne lesions | circles | number of lesions (Hayashi grade for acne) |
| U-Net segmentation | wrinkles, dark spots | lines / patches | % of the face covered |

The face is found first with YuNet (pretrained, MIT licence, not trained by us). Oiliness, dryness
and redness come from the skin quiz, not from the photo. Datasets and licences: [DATASETS.md](DATASETS.md).

## Where things live

| What | Where | In Git? |
|---|---|---|
| Our code, tests, docs | `ml/` | yes |
| Downloaded datasets, labelling app, its database | `C:\SkinCareData\starter_kit\` (copy of the research kit) | **never** |
| Our prepared data (face crops, YOLO / U-Net formats, splits) | `C:\SkinCareData\prepared\` | **never** |

The data folder is outside OneDrive so face photos are not synced to the cloud. Set the environment
variable `SKINCARE_DATA_DIR` to use another folder (e.g. on the GPU laptop); a folder inside the
repository is refused.

## Setup (development laptop, Windows)

```powershell
cd ml
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
pytest
```

Training packages (PyTorch, Ultralytics) are added in Step 3, mainly on the GPU laptop.

## Face detection rule (YuNet)

YuNet finds faces on a **~640 px copy** of the photo; the crop is then taken from the **full-resolution
original** (small lesions need the detail). On full-size 3,000-5,000 px photos YuNet finds no face, and
with OpenCV 5.0 it found none at all, so OpenCV 4 is pinned (tested 2026-10-25).
