# Datasets, licences and citations

Licences checked on the official sources on **2026-10-25** (Step 1 Part 1.2). Images are never
committed; they live in `C:\SkinCareData` (see README.md). This project is academic and
non-commercial; the trained models inherit these restrictions (see "Consequences" below).

## Used

| Dataset | Used for | Size | Licence (official source) |
|---|---|---|---|
| **ACNE04** | Expert severity grades (`levle0-3` in the filename) to evaluate our lesion counts; its own lesion boxes are the fallback for ACNE04-v2 | 1,457 photos, 18,983 lesion boxes | "This work is free for academic usage"; other uses: contact the author ([xpwu95/LDL](https://github.com/xpwu95/LDL)) |
| **ACNE04-v2** | Lesion circles → YOLO training (types whitehead / pustule / other labelled by us) | 1,204 entries = 1,168 unique photos (36 exact duplicates), 32,443 circles (49 invalid on `levle2_130.jpg`) | **No licence stated** ([AIpourlapeau/acne04v2](https://github.com/AIpourlapeau/acne04v2)): asks to cite AcneAI; permission requested from the authors (see below) |
| **FFHQ-Wrinkle** + FFHQ originals | Wrinkle masks → U-Net | 1,000 manual masks (1024×1024, 8-bit grayscale) + 50,000 weak masks | CC BY-NC-SA 4.0 ([labhai/ffhq-wrinkle-dataset](https://github.com/labhai/ffhq-wrinkle-dataset)); each FFHQ photo CC BY 2.0 / BY-NC 2.0 / public domain (author per image in the metadata) |
| **MEMI-DS** public release | Dark spot (melasma) masks → U-Net | 131 photo / mask pairs in two folders, *Flaky* and *Punctate* (melasma patterns) | CC BY 4.0 ([figshare 10.6084/m9.figshare.29209229.v1](https://doi.org/10.6084/m9.figshare.29209229.v1)) |
| **YuNet** (OpenCV Zoo) | Face detection, used as it is | — | MIT |

## Facts checked for the design

- **Hayashi grading** (used for the ACNE04 grades): 1-5 lesions **mild**, 6-20 **moderate**, 21-50
  **severe**, more than 50 **very severe**, counted on **half of the face**. ACNE04 has no "clear skin"
  level: grade 0 (`levle0`) is *mild*. Source: Prokhorov & Kalinin, "Improving Acne Image Grading with
  Label Distribution Smoothing", arXiv 2403.00268 (2024), describing ACNE04 and Hayashi et al.,
  J Dermatol 35(5):255-260 (2008).
- **ACNE04 photos are side views** (about 45°, one half of the face, chin rest), not frontal selfies.
  MEMI-DS photos are clinical photos with the eyes hidden, in front / left / right views (`_F`,
  `_L`, `_R` in the filename). Both differ from app selfies;
  the photo-capture design (frontal and/or side views) is decided in Step 5.
- **YuNet** found the face in samples of all three sources (including MEMI's hidden eyes and a side
  view) on a ~640 px copy; on the full-size photos it found none (see README.md).
- **MEMI-DS mask colours are not documented** by the source: inspected in Part 1.3 before use.

## Consequences for the project

- ACNE04 and the share-alike FFHQ data allow **academic, non-commercial use only**; models trained on
  them must not be used commercially (stated as a limitation in the report).
- **ShareAlike (FFHQ-Wrinkle):** if we publish the U-Net weights, they must carry CC BY-NC-SA 4.0.
  Whether model files go into the public repository is decided in Step 5.
- **ACNE04-v2 has no licence:** strictly, no permission is granted beyond the public release and the
  citation request. We use it for academic research only, never redistribute it, cite it, and ask the
  authors for written permission. If refused, we switch to the original ACNE04 boxes (clearly licensed
  for academic use; 18,983 boxes instead of 32,443).
- Attribution in the report and the app's "About" page: ACNE04, ACNE04-v2 (AcneAI), FFHQ-Wrinkle,
  FFHQ (NVIDIA), MEMI-DS, YuNet.

## Citations

- Wu X. et al., "Joint Acne Image Grading and Counting via Label Distribution Learning", ICCV 2019,
  pp. 10642-10651, doi:10.1109/ICCV.2019.01074 (ACNE04).
- Gazeau et al., "AcneAI: A New Acne Severity Assessment Method Using Digital Images and Deep
  Learning", MICCAI 2024 (ACNE04-v2).
- Moon J., Chung H., Jang I., "Facial Wrinkle Segmentation for Cosmetic Dermatology: Pretraining with
  Texture Map-Based Weak Supervision", ICPR 2024, pp. 319-334 (FFHQ-Wrinkle).
- Karras T., Laine S., Aila T., "A Style-Based Generator Architecture for Generative Adversarial
  Networks", CVPR 2019 (FFHQ).
- Zhai Z., "MEMI-DS: A Benchmark Melasma Image Dataset for Image Segmentation", figshare, 2025,
  doi:10.6084/m9.figshare.29209229.v1.
- Hayashi N., Akamatsu H., Kawashima M., "Establishment of grading criteria for acne severity",
  J Dermatol 35(5):255-260, 2008.
- Yu S. et al., YuNet face detector, OpenCV Zoo (MIT).

## Not used, and why

| Source | Reason |
|---|---|
| DermNet | Its licence forbids AI training / testing with its images |
| ISIC | Dermoscopy close-ups of single lesions, not face selfies |
| Fitzpatrick17k, SD-198, SCIN | Disease datasets (the app does not diagnose diseases) |
| Nexdata facial skin dataset | Paid |
| Redness / oily-dry photo sets | Redness, oiliness and dryness come from the skin quiz (no reliable licensed photo data) |
| Unique Data / TrainingDataPro selfies | CC BY-NC-ND (no derivatives): at most local testing, never training or publishing |
| Unverified Kaggle re-uploads | Unknown origin and quality (duplicates, rotations, processed images) |
