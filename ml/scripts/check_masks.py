r"""Part 4.1: the student's visual check of the U-Net masks (decided 2026-11-22).

    cd ml; .venv\Scripts\activate; $env:PYTHONPATH = "."
    python scripts/check_masks.py      # then open the printed index.html in a browser

Draws, on the U-Net's face crop (segmentation_data.CROP_MARGINS):
- every MEMI-DS photo with a face: the melasma (yellow) and the area training will IGNORE (red,
  segmentation_data.known_dark_spots), to confirm the automatic cheek zones;
- 50 random FFHQ-Wrinkle photos (seed 2026): the wrinkle lines (yellow), to check the manual masks
  for missing wrinkles (correction rule 6: fix only if the gaps are systematic).
Writes the pictures and index.html to prepared/reports/mask_check/ (never committed: faces), plus
zone_coverage.json: on side views, how much of the marked cheek lies inside the known cheek zone;
on front views, how much of the marked forehead / nose / chin falls in an ignored cheek zone
(still learned, as marked pixels are always known).
"""

import html
import json
import sys

import cv2
import numpy as np

from skincare_ml import config
from skincare_ml.faces import FaceDetector
from skincare_ml.segmentation_data import known_dark_spots, load_sample, unet_crop_box

YUNET = "face_detection_yunet_2023mar.onnx"
WRINKLE_SAMPLE = 50
SHOWN = 900  # px, longest side of each picture


def picture(image, mask, ignored, box) -> np.ndarray:
    left, top, right, bottom = box
    crop = image[top:bottom, left:right]
    scale = SHOWN / max(crop.shape[:2])
    small = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    size = (small.shape[1], small.shape[0])
    marked = cv2.resize(mask[top:bottom, left:right], size, interpolation=cv2.INTER_NEAREST) > 0
    painted = small.copy()
    if ignored is not None:
        off = cv2.resize(ignored[top:bottom, left:right], size, interpolation=cv2.INTER_NEAREST) > 0
        painted[off] = (0.5 * painted[off] + (0, 0, 120)).clip(0, 255).astype(np.uint8)
    painted[marked] = (0.4 * painted[marked] + (0, 150, 150)).clip(0, 255).astype(np.uint8)
    return painted


def page(sections: list[tuple[str, str, list[str]]]) -> str:
    parts = []
    for title, note, names in sections:
        cards = "".join(
            f'<figure><a href="{html.escape(n)}" target="_blank"><img src="{html.escape(n)}" '
            f'loading="lazy" alt="{html.escape(n)}"></a><figcaption><label><input type="checkbox" '
            f'data-name="{html.escape(n)}"> problem</label> {html.escape(n[:-4])}</figcaption></figure>'
            for n in names
        )
        parts.append(f"<h2>{html.escape(title)}</h2><p>{note}</p><div class=grid>{cards}</div>")
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1"><title>Mask Check</title>
<style>
 body {{ margin: 0; padding: 12px 16px; background: #6e6e6e; color: #f2f2f2;
        font: 15px/1.4 "Segoe UI", Arial, sans-serif; }}
 .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px; }}
 figure {{ margin: 0; background: #5f5f5f; border-radius: 6px; padding: 6px; }}
 img {{ width: 100%; display: block; border-radius: 4px; }}
 figcaption {{ font-size: 13px; padding-top: 4px; }}
 #bar {{ position: sticky; top: 0; background: #6e6e6e; padding: 6px 0; }}
 button {{ font: inherit; padding: 4px 10px; }}
</style></head><body>
<h1>Mask check</h1>
<div id=bar>Tick "problem" on any picture that looks wrong, then
 <button id=copy>Copy the list of problems</button> and paste it to Claude. <span id=n></span></div>
{''.join(parts)}
<script>
 const boxes = [...document.querySelectorAll("input[data-name]")];
 const key = "mask-check";
 let saved = [];
 try {{ saved = JSON.parse(localStorage.getItem(key) || "[]"); }} catch (e) {{}}
 boxes.forEach(b => {{ b.checked = saved.includes(b.dataset.name); }});
 const update = () => {{
   const list = boxes.filter(b => b.checked).map(b => b.dataset.name);
   document.getElementById("n").textContent = list.length + " ticked";
   try {{ localStorage.setItem(key, JSON.stringify(list)); }} catch (e) {{}}
   return list;
 }};
 boxes.forEach(b => b.addEventListener("change", update));
 update();
 document.getElementById("copy").addEventListener("click", async () => {{
   const text = update().join(", ") || "no problems";
   try {{ await navigator.clipboard.writeText(text); alert("Copied: " + text); }}
   catch (e) {{ prompt("Copy this:", text); }}
 }});
</script></body></html>"""


def main() -> int:
    data_dir = config.data_dir()
    manifest = json.loads((config.prepared_dir() / "manifests" / "segmentation.json")
                          .read_text(encoding="utf-8"))  # fmt: skip
    detector = FaceDetector(config.kit_dir() / "models" / YUNET)
    out = config.prepared_dir() / "reports" / "mask_check"
    out.mkdir(parents=True, exist_ok=True)

    memi_names, coverage = {"F": [], "L": [], "R": []}, []
    for entry in (e for e in manifest["images"] if e["source"] == "memi_ds"):
        sample = load_sample(entry, data_dir)
        faces = detector.detect(sample.image)
        if not faces:
            continue
        face, view = faces[0], entry["view"]
        known = known_dark_spots(face, view, sample.dark_spots)
        zones_only = known_dark_spots(face, view, np.zeros_like(sample.dark_spots))
        marked = int(sample.dark_spots.sum())
        inside = int((sample.dark_spots & zones_only).sum())
        coverage.append({"file": entry["file"], "view": view, "split": entry["split"],
                         # side: marked cheek inside the known zone; front: marked pixels NOT in
                         # an ignored cheek zone
                         "marked_in_known_zone": round(inside / marked, 4),
                         "ignored_share_of_photo": round(1 - float(known.mean()), 3)})  # fmt: skip
        height, width = sample.image.shape[:2]
        name = f"memi_{entry['file'].rsplit('/', 1)[1].rsplit('.', 1)[0]}.jpg"
        box = unet_crop_box(face, width, height)
        cv2.imwrite(str(out / name), picture(sample.image, sample.dark_spots, 1 - known, box))
        memi_names[view].append(name)

    ffhq = [e for e in manifest["images"] if e["source"] == "ffhq_wrinkle"]
    chosen = np.random.default_rng(2026).choice(len(ffhq), WRINKLE_SAMPLE, replace=False)
    wrinkle_names = []
    for index in sorted(chosen.tolist()):
        entry = ffhq[index]
        sample = load_sample(entry, data_dir)
        faces = detector.detect(sample.image)
        height, width = sample.image.shape[:2]
        box = unet_crop_box(faces[0], width, height) if faces else (0, 0, width, height)
        name = f"ffhq_{entry['file'].rsplit('/', 1)[1].rsplit('.', 1)[0]}.jpg"
        cv2.imwrite(str(out / name), picture(sample.image, sample.wrinkles, None, box))
        wrinkle_names.append(name)

    red = '<b style="color:#ff8a8a">red</b> = ignored in training'
    sections = [
        ("1. Dark spots, front views", f"Yellow = melasma marked by the dataset; {red}. "
         "Check that the red boxes cover BOTH cheeks (they were never marked on front views).",
         memi_names["F"]),
        ("2. Dark spots, side views", f"Yellow = the marked cheek; {red}. Check that the cheek "
         "is NOT red (it is the part we learn from) and the rest of the face is red.",
         memi_names["L"] + memi_names["R"]),
        ("3. Wrinkles (50 random photos)", "Yellow = wrinkle lines drawn by the dataset's "
         "annotators. Tick a photo only if CLEAR wrinkles have no line, or a line is on "
         "something that is not a wrinkle.", wrinkle_names),
    ]
    (out / "index.html").write_text(page(sections), encoding="utf-8")
    side = [c["marked_in_known_zone"] for c in coverage if c["view"] != "F"]
    front = [c["marked_in_known_zone"] for c in coverage if c["view"] == "F"]
    summary = {"memi_photos": len(coverage),
               "side_views_marked_cheek_inside_zone_min_median": [min(side), float(np.median(side))],
               "front_views_marked_outside_cheek_zones_min_median": [min(front), float(np.median(front))],
               "wrinkle_photos": len(wrinkle_names)}  # fmt: skip
    (out / "zone_coverage.json").write_text(
        json.dumps({"summary": summary, "photos": coverage}, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1))
    print(f"-> open {out / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
