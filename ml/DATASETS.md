# Datasets, licences and citations

Status: **Part 1.1 skeleton** — licences marked "to verify" are checked on the official sources in
Step 1 Part 1.2. Images are never committed; they live in `C:\SkinCareData` (see README.md).

## Used

| Dataset | Used for | Size | Licence | Status |
|---|---|---|---|---|
| ACNE04 (Wu et al., ICCV 2019) | Expert acne grades (`levle0-3` in the filename) to evaluate our lesion counts | 1,457 photos | to verify | to verify |
| ACNE04-v2 (Gazeau et al., MICCAI 2024) | Pimple circles → YOLO training (types labelled by us) | 1,204 entries = 1,168 unique photos; 32,443 circles | to verify | to verify |
| FFHQ-Wrinkle + FFHQ originals | Wrinkle masks → U-Net | 1,000 manual masks | CC BY-NC-SA 4.0 (photos: CC BY / BY-NC / public domain, per image) | licence text kept in the kit |
| MEMI-DS public release | Dark spot (melasma) masks → U-Net | 131 photos + masks | CC BY 4.0 | licence text kept in the kit |
| YuNet (OpenCV Zoo) | Face detection, used as it is | — | MIT | licence text kept in the kit |

## Not used, and why

| Source | Reason |
|---|---|
| DermNet | Its licence forbids AI training / testing with its images |
| ISIC | Dermoscopy close-ups of single lesions, not face selfies |
| Fitzpatrick17k, SD-198, SCIN | Disease datasets (the app does not diagnose diseases) |
| Nexdata facial skin dataset | Paid |
| Redness / oily-dry photo sets | Redness, oiliness and dryness come from the skin quiz (no reliable licensed photo data) |
| Unverified Kaggle re-uploads | Unknown origin and quality (duplicates, rotations, processed images) |
