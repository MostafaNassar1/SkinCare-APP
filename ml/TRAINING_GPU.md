# Training the pimple finder on the GPU laptop

The YOLO pimple finder needs an NVIDIA GPU (at least ~4 GB of GPU memory). Everything below was
checked on the development laptop with a tiny CPU run (`train_yolo.py --smoke`); only the GPU
install differs. Photos and models never go into the repository.

## 1. What to copy (USB drive)

| From the development laptop | To the GPU laptop | Size |
|---|---|---|
| `C:\SkinCareData\prepared\yolo_pimples\` | the same path | ~700 MB |
| `C:\SkinCareData\models\yolo11s.pt` | the same path | ~20 MB |

Another drive is fine too: then set `$env:SKINCARE_DATA_DIR = "D:\SkinCareData"` (for example)
before step 4. The original ACNE04 photos are **not** needed on the GPU laptop.

## 2. Install (once)

1. Install the latest **NVIDIA driver**, **Python 3.12** (python.org, "Add to PATH") and **Git**.
2. Check the GPU: open Task Manager → Performance → GPU, note its name and "Dedicated GPU memory".
3. In PowerShell:

```
git clone https://github.com/MostafaNassar1/SkinCare-APP.git
cd SkinCare-APP\ml
py -3.12 -m venv .venv
.venv\Scripts\activate
```

4. **PyTorch with CUDA** (not the CPU build): on <https://pytorch.org/get-started/locally/>
   choose Stable, Windows, Pip, Python, the newest CUDA, and run the command it shows, with the
   versions pinned as in `requirements.txt` (torch 2.15.0, torchvision 0.29.2), e.g.
   `pip install torch==2.15.0 torchvision==0.29.2 --index-url https://download.pytorch.org/whl/cuXXX`
5. The rest (Ultralytics WITHOUT its dependencies, so OpenCV stays at version 4):

```
pip install --no-deps ultralytics==8.4.201
pip install -r requirements.txt
yolo settings sync=False
```

6. Check that PyTorch sees the GPU (must print `True` and the GPU's name):

```
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

## 3. Train

```
cd SkinCare-APP\ml
.venv\Scripts\activate
$env:PYTHONPATH = "."
python scripts/train_yolo.py
```

- It picks the largest batch the GPU can hold (`batch -1`) and stops by itself after 25 epochs
  without improvement on the validation photos (at most 150 epochs). Expect several hours.
- Keep the laptop plugged in and stop it from sleeping (Settings → Power → Screen and sleep → Never).
- If it stops (power cut, closed lid), continue from the last saved epoch:
  `yolo train resume model=C:\SkinCareData\prepared\yolo_runs\pimples\weights\last.pt`

## 4. Bring back

Copy `C:\SkinCareData\prepared\yolo_runs\pimples\` (weights `best.pt` + the results and plots)
back to the same path on the development laptop. The test-set evaluation (on all 174 test photos
and on the 50 checked ones) and the ONNX export are run from there.

---

# Fine-tuning session: runs A, B and C (prepared 2026-11-06)

v1 (trained 2026-11-05, RTX 5070 Laptop 8 GB) found only **16%** of the smallest pimples (under
20 px) and got clearly worse on selfie-like photos (validation AP50 0.50 → 0.41). Three runs, each
ONE change, each starting from v1, compared afterwards on the validation photos only:

| Run | Change | Data | Expected time |
|---|---|---|---|
| A | fixed batch of 4 instead of the automatic 1 | `yolo_pimples` (already on the GPU laptop) | ~1 h |
| B | 1,024 px tiles of the full-resolution photos (pimples at their real size) | `yolo_pimples_tiles` (new) | ~2 h |
| C | as B + one phone-like copy of every training tile | `yolo_pimples_tiles` (same folder) | ~4 h |

The three runs are independent: run them one after another (e.g. overnight).

## 1. Update the repository on the GPU laptop

Its copy still has the uncommitted launcher changes of 2026-11-05; they are now in the branch, so
discard them first:

```
cd D:\Development\Projects\skincare_ai\SkinCare-APP
git checkout -- ml/scripts/train_yolo.py
git checkout mostafa/feature/phase3-step3-pimple-detector
git pull
```

## 2. Copy (USB drive, ~2.6 GB)

| From the development laptop | To the GPU laptop's data folder | Size |
|---|---|---|
| `C:\SkinCareData\prepared\yolo_pimples_tiles\` | `...\SkinCareData\prepared\yolo_pimples_tiles\` | 2.5 GB |
| `C:\SkinCareData\models\yolo_pimples_v1.pt` | `...\SkinCareData\models\yolo_pimples_v1.pt` | 19 MB |

(`yolo_pimples_v1.pt` is v1's `best.pt`, SHA-256 `666a016c…`; if the GPU laptop still has
`yolo_runs\pimples_lr0025\weights\best.pt`, copying that file to `models\yolo_pimples_v1.pt` there
is the same.) `yolo_pimples\` is already on the GPU laptop from v1.

## 3. Train (one command per run)

```
cd D:\Development\Projects\skincare_ai\SkinCare-APP\ml
conda activate hsn
$env:SKINCARE_DATA_DIR = "D:\Development\Data\Datasets\Processed\SkinCareData"
$env:PYTHONPATH = "."
python scripts/train_yolo.py --run A --epoch-confidence
python scripts/train_yolo.py --run B --epoch-confidence
python scripts/train_yolo.py --run C --epoch-confidence
```

- If a run stops with **"CUDA out of memory"**, start it again with `--batch 2` added.
- Do **not** open `results.csv` in Excel while training (that stopped the first v1 run).
- A stopped run continues with `yolo train resume model=...\yolo_runs\pimples_<run>\weights\last.pt`.

## 4. Score them on validation (optional on the GPU laptop: much faster there)

```
python scripts/compare_models.py --model v1=yolo_pimples_v1.pt:whole `
    --model A=..\prepared\yolo_runs\pimples_A\weights\best.pt:whole `
    --model B=..\prepared\yolo_runs\pimples_B\weights\best.pt:tiled `
    --model C=..\prepared\yolo_runs\pimples_C\weights\best.pt:tiled
```

(a relative path starts in the data folder's `models\`; full paths work too:
`--model A=D:\...\yolo_runs\pimples_A\weights\best.pt:whole`). The test
photos are NOT used here.

## 5. Bring back

`...\prepared\yolo_runs\pimples_A\`, `pimples_B\`, `pimples_C\` (weights + results) and, if step 4
was run, the newest `...\prepared\yolo_evaluations\compare_val_*.json`.
