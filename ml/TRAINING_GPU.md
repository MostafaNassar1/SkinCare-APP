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
