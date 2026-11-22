# Datasets, licences and citations

Licences checked on the official sources on **2026-10-25** (Step 1 Part 1.2). Images are never
committed; they live in `C:\SkinCareData` (see README.md). This project is academic and
non-commercial; the trained models inherit these restrictions (see "Consequences" below).

## Used

| Dataset | Used for | Size | Licence (official source) |
|---|---|---|---|
| **ACNE04** | Expert severity grades (`levle0-3` in the filename) to evaluate our lesion counts; its own lesion boxes are the fallback for ACNE04-v2 | 1,457 photos, 18,983 lesion boxes | "This work is free for academic usage"; other uses: contact the author ([xpwu95/LDL](https://github.com/xpwu95/LDL)) |
| **ACNE04-v2** | Lesion circles → YOLO training (types whitehead / pustule / other labelled by us) | 1,204 entries = 1,168 unique photos (36 exact duplicates), 32,443 circles (49 invalid on `levle2_130.jpg`) | **No licence stated** ([AIpourlapeau/acne04v2](https://github.com/AIpourlapeau/acne04v2)): asks to cite AcneAI; academic use only (see below) |
| **FFHQ-Wrinkle** + FFHQ originals | Wrinkle masks → U-Net | 1,000 manual masks (1024×1024, 8-bit grayscale) + 50,000 weak masks | CC BY-NC-SA 4.0 ([labhai/ffhq-wrinkle-dataset](https://github.com/labhai/ffhq-wrinkle-dataset)); each FFHQ photo CC BY 2.0 / BY-NC 2.0 / public domain (author per image in the metadata) |
| **MEMI-DS** public release | Dark spot (melasma) masks → U-Net | 131 photo / mask pairs in two folders, *Flaky* and *Punctate* (melasma patterns) | CC BY 4.0 ([figshare 10.6084/m9.figshare.29209229.v1](https://doi.org/10.6084/m9.figshare.29209229.v1)) |
| **YuNet** (OpenCV Zoo) | Face detection, used as it is | — | MIT |
| **SFace** (OpenCV Zoo, `face_recognition_sface_2021dec.onnx`) | Face fingerprints, only to keep photos of the same person in one split (never in the app) | — | Apache 2.0 |

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
- **MEMI-DS mask colours are not documented** by the source: inspected in Part 1.3 (below).

## Inspection results (Part 1.3, 2026-10-26)

Downloaded with the kit's script (every file size + checksum verified, 0 failures); ACNE04-v2 also
downloaded from its official repository (commit `5930801`): identical SHA-256 to the kit's copy.
Full report: `C:\SkinCareData\prepared\reports\inspection.json`, produced by
`ml/scripts/inspect_datasets.py`.

**ACNE04 (1,457 photos, 18,983 original lesions)**
- The real grade is the one in the **split files** (`NNEW_*.txt`: file, grade, lesion count), not the
  file name: they agree with the Hayashi grade of the original count on **100%** of photos. **42**
  file names carry a different grade (17 "moderate" → mild, 14 "severe" → moderate, 8 "very severe" →
  severe, 2 moderate → severe, 1 mild → moderate). The 5 folds give the same grades.
- **38 groups of byte-identical photos** (36 inside the v2 subset): removed before splitting, so the
  same photo can never be in training and test.
- The archive has no lesion boxes (only photos + split files); the original 18,983 boxes would be a
  separate download (only needed if ACNE04-v2 cannot be used).

**ACNE04-v2 (1,204 entries)**
- All photos present; 32,394 valid circles; 49 invalid on `levle2_130.jpg`.
- v2 marks **more lesions than the original count on 90%** of photos (1,084; equal 19; fewer 101), so
  the Hayashi grade of *all* v2 circles agrees with the expert grade on only **31%** of photos (it
  over-grades). Likely reason: Hayashi counts inflammatory lesions only. → In Step 3, severity uses
  only inflamed lesions (our type labels) or count thresholds calibrated on the expert grades.

**FFHQ-Wrinkle (1,000)**: every mask paired, binary (0 / 255), none empty; wrinkles cover only
**0.67%** of the pixels on average (thin lines → a loss suited to rare pixels, e.g. Dice, in Step 4).
Every photo has wrinkles: wrinkle-free regions inside the photos are the negatives.

**MEMI-DS (131 pairs, 63 people; 62 front, 37 left, 32 right views)**: mask colours are **face regions**,
every coloured pixel is melasma: red = forehead, green = nose, purple = chin / jaw (front views),
yellow = left cheek (left views), cyan = right cheek (right views). **Cheeks are only annotated in
the side views**, so unmarked cheeks in front views are *unknown*, not "no dark spot": the U-Net loss
must ignore them (region-wise masking, Step 4). Annotations are coarse patches (limitation). Splits by
person (the number before `_`).

**YuNet (exactly one face?)**
| Source | 1 face | 0 faces | 2-3 faces |
|---|---|---|---|
| ACNE04 (1,457) | 1,156 | 295 | 6 |
| ↳ inside v2 (1,204) | 1,038 | 160 (13%) | 6 |
| ↳ removed by v2 (253) | 118 | 135 (53%) | 0 |
| FFHQ (1,000) | 979 | 0 | 21 (people in the background) |
| MEMI-DS (131) | 126 | 5 | 0 |

Photos without a detected face are extreme side profiles, close-ups of a cheek, or watermarked web
images. → The YOLO detector trains on the **whole ACNE04 photos** (already skin close-ups), not on
YuNet crops; YuNet stays in the app to check that a user photo shows exactly one face (the largest /
best face is used when a training photo has several).

## Consequences for the project

- ACNE04 and the share-alike FFHQ data allow **academic, non-commercial use only**; models trained on
  them must not be used commercially (stated as a limitation in the report).
- **ShareAlike (FFHQ-Wrinkle):** if we publish the U-Net weights, they must carry CC BY-NC-SA 4.0.
  Whether model files go into the public repository is decided in Step 5.
- **ACNE04-v2 has no licence:** strictly, no permission is granted beyond the public release and the
  citation request. We use it for academic research only, never redistribute it and cite it. Asking
  the authors for written permission was suggested; the student decided not to (2026-10-26: local,
  academic use only, nothing published online). If the use is ever questioned, the original ACNE04
  boxes (clearly licensed for academic use; 18,983 instead of 32,443) are the fallback.
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

## Manifests and splits (Part 1.4, 2026-10-26)

`ml/scripts/build_manifests.py` writes one manifest per model to `C:\SkinCareData\prepared\manifests\`
(every photo, its labels, its group and its split; training formats are produced in Steps 3-4).
Splits: **70% train / 15% validation / 15% test by group**, so photos of one person are never on both
sides (otherwise the test would measure memory instead of skill); fixed seed 2026 (reproducible).

**`pimples.json` (YOLO): 1,167 photos, 31,676 boxes** (circle → surrounding square). 1,204 v2 entries
− 36 byte-identical duplicates (the copy with most circles kept) − `levle2_130.jpg` (invalid
circles, until relabelled). Grade = split-file expert grade; every box has type "lesion" until the
whitehead / pustule / other labelling of Step 3. Stratified by grade:

| Expert grade | train | val | test |
|---|---|---|---|
| mild | 334 | 67 | 75 |
| moderate | 387 | 90 | 79 |
| severe | 85 | 15 | 16 |
| very severe | 12 | 3 | 4 |

Only 19 very-severe photos remain in v2: results for that grade will be uncertain (limitation).

**Grouping ACNE04 by person** (it has no person ids):
- A perceptual hash (dHash) was tried first and **rejected for identity**: same-person photos
  differed by 36-42 / 256 bits, different people in the same clinic setup by 43+, so one threshold
  cannot separate them; at 64 bits, chains merged 136 different people into one group. The hash is
  kept only for near-identical copies (≤ 20 / 256 bits).
- Same person = **SFace fingerprints** (YuNet face found on 1,017 of 1,167 photos), cosine ≥ **0.65**.
  OpenCV's default 0.363 is meant for frontal faces: on these angled clinical photos 7% of all pairs
  passed it and chaining merged 1,008 photos into one group. At 0.65 the largest group (15) is one
  patient photographed at several visits with grades 0, 1 and 2 (proof that grouping was needed);
  borderline pairs (0.65-0.68) were checked by eye: almost all the same person.
- Result: 615 groups (394 single photos, 221 people with 2-15 photos). Limitations: photos without a
  detected face (150) can only be linked as copies; the threshold was calibrated by eye.

**`segmentation.json` (U-Net): 1,131 photos.** FFHQ-Wrinkle 1,000 (known channel: wrinkles; no person
ids, each photo its own group) → 700 / 150 / 150. MEMI-DS 131 (known channel: dark spots, only the
regions of its view; grouped by person) → 91 / 21 / 19. Every MEMI region colour appears only in its
expected view (0 exceptions on 131 masks), which confirms the region mapping.

## Rules for manual corrections (agreed 2026-10-26)

1. **Add only clear misses** (a visible pimple without a circle, an obvious missing wrinkle line);
   never delete or move expert labels unless obviously wrong (e.g. on the background), and say why.
2. **Never change expert grades**: they are the reference our model is evaluated against.
3. **Every change is logged** (photo, what, why, who, date) in `C:\SkinCareData\prepared\corrections\`,
   apart from the original files, which stay untouched.
4. **Test-set labels are frozen before training** and never edited after seeing model results.
5. Labels follow written definitions (American Academy of Dermatology); the report states that
   corrections and lesion types were labelled by non-experts.
6. Wrinkle masks: check a sample (~50) first; fix only if systematic gaps are found (brush tool, e.g.
   Label Studio, decided in Step 4). MEMI front-view cheeks may optionally be annotated the same way.

## Lesion types (Phase 3 Step 3, labelled by the student)

**Design (decided 2026-11-01):** two stages. YOLO learns to FIND pimples from all the expert circles
of `pimples.json` (1,167 photos, no new labels); a small classifier learns the TYPE of each found
pimple from close-ups labelled by the student (`skincare_ml/lesion_types.py`, page
`scripts/label_types.py`, local only). Answers: whitehead, papule, pustule, other, unclear.
Papule + pustule = inflamed lesions, counted for the Hayashi grade (Step 1: counting every circle
agreed with the expert grade on 31% of photos). Labelled by a non-expert (stated in the report).

**Round 1 (2026-11-01):** 600 close-ups (89 test, 91 val, 420 train; max 3 circles per photo,
circles < 10 px skipped) + 60 hidden repeats, answered in 39 minutes (median 1.5 s per answer).
whitehead 299 (50%), papule 206 (34%), pustule 68 (11%), other 12, unclear 15. Papules dominate on
severe / very severe photos, as expected. **Self-agreement on the 60 repeats: 71.7%, Cohen's kappa
0.54 (moderate)**; most changes were whitehead <-> papule (8) and pustule -> papule / whitehead (6:
pustules kept their answer 5 times out of 11).

**Test labels frozen** (`prepared/lesion_types/test_labels_frozen.json`, the student's choice:
as labelled once, no second pass): 89 labels (whitehead 34, papule 34, pustule 12, other 2,
unclear 7), SHA-256 `70d4051325ec8697f68fb65717f1cb49e91faade82a394a0e6140cfb32a29db5`;
`python scripts/freeze_test_labels.py --check` proves they never changed. Later rounds refuse test
close-ups.

**Round 2:** 600 training close-ups only, moderate / severe photos favoured (weights 1 / 2 / 4 / 4)
to find more pustules (mild 143, moderate 323, severe 120, very severe 14) + 60 repeats. A 2-second
wait before answering was proposed (round 1's median was 1.5 s per answer) and declined by the
student; the page keeps it as an option (`--min-seconds`), off by default.

**Round 2 results (2026-11-01):** 600 + 60 repeats in 17 minutes (median 1.2 s): whitehead 314,
papule 207, pustule 74, other 4, unclear 1. **Self-agreement 90.0%, kappa 0.82** (up from 0.54:
the student's consistency improved with practice, not with a slower pace).

**Scout for round 3 (active learning, 2026-11-02):** pustules stayed ~12% of answers, so a quick
type model (`skincare_ml/type_model.py`, `scripts/train_scout.py`; MobileNetV3-small,
ImageNet-pretrained, CPU, 6 minutes) learned from rounds 1-2 (984 training close-ups: whitehead 531,
papule 344, pustule 109; circles answered differently on their repeat left out) and was checked on
84 validation close-ups: **balanced accuracy 0.62** (chance 0.33); recall whitehead 0.77, papule
0.63, pustule 0.45 (5 of 11). Of the validation spots it called "pustule", 38% were (vs ~12% at
random): about 3x enrichment, which is its only job. It scored the 21,228 untyped training circles;
round 3 = 400 of them (70% likeliest pustules, 30% least sure, shuffled, max 3 per photo; the scout
called 306 of them pustules) + 40 repeats. The scout is thrown away; the frozen test labels were
never used. Training data chosen this way over-represents pustule-looking spots (fine for training;
the test set keeps the real mix).

**Round 3 results (2026-11-02):** 400 scout-chosen close-ups + 40 repeats in 13 minutes:
pustule 161 (40%), papule 127, whitehead 99, other 13. Of the 306 the scout called pustules, the
student said pustule for 152 (50%, ~4x random). Self-agreement 75.0%, kappa 0.60: lower than
round 2 as expected, since round 3 is made of deliberately ambiguous spots (30% least-sure +
papule/pustule boundary cases).

**Round 4 (validation, random, 2026-11-03):** 300 close-ups from 161 validation photos + 30
repeats in 9 minutes: whitehead 142, papule 89, pustule 63 (21%), other 6. Self-agreement 86.7%,
kappa 0.78.

**Drift check (round 5, 2026-11-03):** round 4's 21% pustules (random) against 11-13% in round 1
(random) raised the question of a looser "pustule" standard after the pustule-heavy round 3. 60
round-1 training close-ups (20 per type) were shown again blind: pustules 20 then, **18 now**; only
2 of 20 round-1 papules became pustules. No drift towards pustules (a slight move of 10 inflamed
spots to "whitehead", within the usual red / not-red uncertainty; same answer 73%). Recheck
answers are never used for training. Conclusion: labels final.

**Final labels (rounds 1-4, 1,900 answers, ~80 minutes):** self-agreement over all 190 hidden
repeats 80.5%, kappa 0.70. Usable for learning (circles answered differently on their repeat left
out): **train** whitehead 626, papule 468, pustule 267 (1,361); **validation** whitehead 184,
papule 118, pustule 72 (374); **test (frozen)** 89 (whitehead 34, papule 34, pustule 12, other 2,
unclear 7).

## Missed-pimple check (Phase 3 Step 3, 2026-11-03)

YOLO learns to find pimples from the expert circles, so a visible pimple without a circle teaches
it "this is skin" and, on test photos, turns a correct find into a counted mistake. The student
checked **50 test photos** (chosen once, spread like the test grades: 22 mild, 22 moderate, 5
severe, 1 very severe) with every expert circle drawn (`scripts/check_missed.py`, local page) and
added a circle on each clear miss (rule 1: only clear misses; expert circles never changed).
11 minutes; 46 circles added, 5 taken back.

**Result: 41 missed pimples on 50 photos (0.82 per photo, 19 photos with at least one) against
1,290 expert circles: the experts missed about 3.1% of the pimples** (mild 6 / 257, moderate
26 / 599, severe 9 / 379, very severe 0 / 55). The expert circles are reliable, so the 818
training photos are not checked (3% missing labels is a small noise for YOLO). The 41 additions
are frozen (`prepared/corrections/missed_pimples_frozen.json`, SHA-256
`730c4cd7f683553761d15122921855d5b098e8bf197de0084df047c9420f81d3`) and join the expert circles of
those 50 photos for YOLO's test; results are reported on the 50 checked photos and on all 174 test
photos.

## Type model, first final version (2026-11-03)

`scripts/train_type_model.py` (same code as the scout; CPU, 7.4 minutes): MobileNetV3-small,
ImageNet-pretrained, 96 px close-ups, 20 epochs, trained on 1,361 close-ups (whitehead 626, papule
468, pustule 267), best epoch chosen on 374 validation close-ups (184 / 118 / 72); weights in
`C:\SkinCareData\models\lesion_type_model.pt` (never committed). **Best epoch 9: balanced accuracy
0.628, accuracy 0.68; recall whitehead 0.815, papule 0.610, pustule 0.458.** Confusion (rows =
student, columns = model): whitehead 150 / 20 / 14, papule 29 / 72 / 17, pustule 10 / 29 / 33.
Inflamed vs not inflamed works well (151 of 190 inflamed spots called papule or pustule: 79%;
whiteheads 82%); papule vs pustule is the hard boundary (29 of 72 pustules called papules), the
same boundary where the student's own repeat answers changed most. Validation stopped improving
after epoch 9 (overfitting afterwards). The frozen test labels were NOT used. Planned (the
student's decision: later, when they say so): two variants only, 160 px close-ups and
MobileNetV3-large, the better one on validation kept.

**Two variants (2026-11-04, as agreed: only two, chosen on validation).** Same labels, seed, 20
epochs; validation = the 374 close-ups:

| | base (small, 96 px) | 160px (small, 160 px) | **large (MobileNetV3-large, 96 px)** |
|---|---|---|---|
| best balanced accuracy (epoch) | 0.628 (9) | 0.649 (19) | **0.681 (3)** |
| recall whitehead / papule / pustule | 0.82 / 0.61 / 0.46 | 0.90 / 0.62 / 0.43 | 0.84 / **0.72** / **0.49** |
| inflamed spots called inflamed | 79% | 78% | **85%** |
| CPU training time | 7.4 min | 9.6 min | 12.2 min |

**Chosen: large** (`C:\SkinCareData\models\lesion_type_model.pt`, a copy of
`lesion_type_model_large.pt`; the others are kept). Honest caveat: validation scores move by
±0.03-0.05 between epochs and "large" peaked at epoch 3 (later epochs ~0.60-0.63), so taking the
best of 20 epochs is optimistic; the frozen test set, used once at the end, gives the real
number. Papule vs pustule stays the hardest boundary for every variant (31 of 72 pustules called
papules by "large"), matching the labeller's own repeat changes.

**Final test (2026-11-22, once, `scripts/test_type_model.py`):** 80 frozen test close-ups (34
whiteheads, 34 papules, 12 pustules; "other" / "unclear" not scored): **balanced accuracy 0.655
(95% range 0.53-0.77)**, accuracy 0.675, recall whitehead 0.68 / papule 0.71 / pustule 0.58;
87% of inflamed spots called inflamed. Confusion (rows = student): whitehead 23 / 11 / 0, papule
3 / 24 / 7, pustule 3 / 2 / 7. Close to validation (0.681); the small test set gives a wide range.

## Pimple finder (YOLO11s): runs, choice and final test (2026-11-05 → 2026-11-22)

**v1** (GPU laptop, 2026-11-05): yolo11s from COCO weights, whole photos at 1,280 px, 150 epochs.
Validation mAP50 0.506, test 0.497 (recall 0.45). On the student's selfie it marked skin shine
beside the nose and gave the real pimple only 0.32: half of the pimples are under 16 px at 1,280,
and selfies are softer than ACNE04's clinical photos.

**Fine-tuning runs** (GPU laptop, 2026-11-15/16, each from v1, batch 4, AdamW; RAM fix workers=0;
A resumed after the RAM incident, C after a Windows Update restart; details in the handoff folder
`Final Year Project\SkinCare_FineTuning_Handoff`): **A** whole photos (56 epochs, best 36),
**B** 1,024 px full-resolution tiles (20 epochs), **C** tiles + one phone-like copy of every
training tile (20 epochs, best 17). Training-time scores of tiles and whole photos are not
comparable, so every model was rescored the same way (`scripts/compare_models.py`, own metrics
in `skincare_ml/detection_metrics.py`, whole photos in photo pixels, each at its best-F1 cutoff).

**Validation comparison 1** (175 photos, whole photo, 2026-11-21), AP50 original / phone-like x0.4:
v1 0.496 / 0.405, A 0.526 / 0.433, B 0.535 / 0.314, C 0.541 / 0.383. A looked best on selfies,
but the student's real selfie showed the opposite (A missed the pimple and marked the shine; B / C
found it, their only false marks were wall stickers that the app's face crop removes).

**Validation comparison 2** (as the app will run: YuNet face crop + 20% margin, 152 faces, 23
photos without a face left out; bootstrap 95% ranges, 1,000 paired draws of the photos):

| AP50 (95% range) | original | phone x0.6 (sharp selfie) | phone x0.4 (blurry) |
|---|---|---|---|
| v1 | 0.530 (0.50-0.56) | 0.497 | 0.443 |
| A | 0.546 (0.52-0.57) | 0.525 | **0.463** |
| **C (tiled)** | **0.568 (0.54-0.59)** | 0.522 | 0.403 |
| C on whole photos | 0.413 | 0.376 | 0.332 |

C beats A on original faces in 100% of the draws (recall 0.58 vs 0.51 at equal precision, count
bias -0.7 vs -4.0 pimples per face); tie at x0.6 (C better in 64%); A better on blurry x0.4. C
must run on tiles. **Chosen: C**, with capture rules in the app (close, sharp, well-lit photos;
blurry ones refused: Step 5). Not tried (future work): YOLO11m, real consented selfies.

**Two cutoffs and grade calibration** (fitted on validation, frozen with the weights' SHA-256 in
`C:\SkinCareData\models\pimple_detector_settings.json` by `scripts/freeze_detector_settings.py`):
display 0.20 (dots drawn: ~80% on real pimples), count 0.13 (best F1, the most complete count).
A "dot on the pimple" rule (centre of the box inside the expert box) is reported next to the
standard box rule (IoU >= 0.5), which punishes a box shifted by a few pixels on a 15 px pimple.
The Hayashi table on our raw count agreed with the dermatologists' grade on only 23% of validation
faces (the v2 circles mark many more lesions than they counted), so the count limits are learned
(`skincare_ml/grading.py`, three app levels, very severe = severe): **mild <= 14 counted pimples,
moderate <= 69, severe above**.

**Final test** (once, `scripts/final_test.py`, 150 test faces, 3,603 expert pimples incl. the
student's 41 additions; refuses to run again; `prepared/yolo_evaluations/final_test_20261121_190102.json`):

| C, test | original | phone x0.6 |
|---|---|---|
| dots on real pimples, display 0.20 | **80% (78-82%)** | **88% (86-90%)** |
| pimples with a dot, display 0.20 | 49% (45-52%) | 42% (38-45%) |
| dots right / pimples found, count 0.13 | 67% / 61% | 76% / 53% |
| grade agreement with dermatologists | **65% (57-73%)** | 65% (58-73%) |
| AP50 box rule / dot rule | 0.538 / 0.677 | 0.496 / 0.654 |

Grade mistakes are one level off (no mild called severe, no severe called mild on originals);
moderate is often called mild (25 / 70). **On selfie-quality photos severe acne is mostly called
moderate (12 / 14)**: the dermatologist referral must not rely on the photo alone (Step 5: the
skin quiz adds a referral question; capture rules keep photos sharp). The student's selfie with C
(face crop, frozen settings): one dot, on the real pimple (0.34), no false dot, grade mild.

**ONNX** (`scripts/export_onnx.py`, 2026-11-22): `C:\SkinCareData\models\yolo_pimples_final.onnx`
(1 x 3 x 1,024 x 1,024 = one tile, opset 17); on 20 validation faces ONNX and PyTorch counted the
same 286 pimples (confidence difference < 0.0001).
