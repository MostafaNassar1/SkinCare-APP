r"""Local page to type the expert acne circles of a round, one close-up at a time.

    cd ml; .venv\Scripts\activate; $env:PYTHONPATH = "."
    python scripts/label_types.py --round 1        # then open http://127.0.0.1:8765

Keys: 1 whitehead, 2 papule, 3 pustule, 4 other, 5 unclear, Backspace = back one. The keys work
only after the pictures have been shown for --min-seconds (default 2: round 1's median of 1.5 s per
answer gave 72% self-agreement; colour and a white centre need a closer look). Every answer is
appended at once to round<N>_answers.jsonl (closing the page loses nothing; reopening continues
where you stopped). Only this laptop can open the page (127.0.0.1). Photos never leave it.
"""

import argparse
import io
import json
import sys
import webbrowser
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from PIL import Image, ImageDraw

from skincare_ml import config
from skincare_ml.lesion_types import (
    INFLAMED,
    TYPES,
    crop_square,
    load_answers,
    save_answer,
    self_agreement,
)

PAGE = Path(__file__).with_name("label_types.html")
CLOSE_UP = (3.0, 64, 420)  # circle size x3 (at least 64 px), shown at 420 px
CONTEXT = (10.0, 500, 420)  # circle size x10 (at least 500 px), circles drawn
FACE_SIZE = 640  # the whole photo, longest side in px, circles drawn
KINDS = ("close", "context", "face")
CURRENT_RING = ((0, 230, 255), 3)  # the circle to type: bright cyan
OTHER_RING = ((215, 215, 215), 1)  # the photo's other expert circles: thin light grey


class Round:
    def __init__(self, number: int, min_seconds: float = 2.0):
        self.min_seconds = min_seconds
        folder = config.prepared_dir() / "lesion_types"
        queue = json.loads((folder / f"round{number}_queue.json").read_text(encoding="utf-8"))
        self.items = queue["items"]
        self.by_id = {item["id"]: item for item in self.items}
        self.answers_file = folder / f"round{number}_answers.jsonl"
        self.sources = config.data_dir() / "sources"
        manifest = json.loads(
            (config.prepared_dir() / "manifests" / "pimples.json").read_text(encoding="utf-8")
        )
        # every expert circle of each photo, to show that the face's other pimples are marked too
        self.all_boxes = {
            image["file"]: [b["box"] for b in image["boxes"]] for image in manifest["images"]
        }

    def state(self) -> dict:
        answers = load_answers(self.answers_file)
        position = next(
            (n for n, item in enumerate(self.items) if item["id"] not in answers), len(self.items)
        )
        counts = {t: 0 for t in TYPES}
        for item, label in answers.items():
            if not item.startswith("repeat:"):
                counts[label] += 1
        return {
            "position": position,
            "total": len(self.items),
            "item": self.items[position] if position < len(self.items) else None,
            "counts": counts,
            "inflamed": sum(counts[t] for t in INFLAMED),
            "agreement": self_agreement(answers),
            "min_seconds": self.min_seconds,
        }

    def take_back(self) -> None:
        """Backspace: forget the last answered item so it is shown again."""
        answers = load_answers(self.answers_file)
        answered = [item["id"] for item in self.items if item["id"] in answers]
        if answered:
            position = self.state()["position"]
            before = [i for i in answered if self.items.index(self.by_id[i]) < position]
            save_answer(self.answers_file, (before or answered)[-1], None)

    def render(self, item_id: str, kind: str) -> Image.Image:
        """close: the spot, no marks; context: the area around it; face: the whole photo.
        The last two circle the spot (bright) and the photo's other expert circles (dim)."""
        item = self.by_id[item_id]
        image = _photo(str(self.sources / item["file"]))
        if kind == "face":
            area = (0, 0, image.width, image.height)
            picture = _face(str(self.sources / item["file"])).copy()
        else:
            scale, minimum, shown = CLOSE_UP if kind == "close" else CONTEXT
            area = crop_square(tuple(item["box"]), image.width, image.height, scale, minimum)
            picture = image.crop(area).resize((shown, shown), Image.LANCZOS)
        if kind != "close":
            draw = ImageDraw.Draw(picture)
            factor = picture.width / (area[2] - area[0])
            for box in self.all_boxes.get(item["file"], []):
                if box != item["box"]:
                    _ring(draw, box, area, factor, *OTHER_RING)
            _ring(draw, item["box"], area, factor, *CURRENT_RING)  # drawn last: on top
        return picture

    def picture(self, item_id: str, kind: str) -> bytes:
        buffer = io.BytesIO()
        self.render(item_id, kind).save(buffer, "JPEG", quality=92)
        return buffer.getvalue()


def _ring(draw, box, area, factor, colour, width) -> None:
    """A circle around an expert box, in the coordinates of the shown picture."""
    x1, y1, x2, y2 = box
    if x2 < area[0] or y2 < area[1] or x1 > area[2] or y1 > area[3]:
        return  # outside the shown part of the face
    # at least 7 px across, so a small spot stays visible on the whole-face picture
    cx, cy = ((x1 + x2) / 2 - area[0]) * factor, ((y1 + y2) / 2 - area[1]) * factor
    radius = max((x2 - x1) * factor / 2 + 4, 7)
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=colour, width=width)


@lru_cache(maxsize=3)
def _photo(path: str) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGB")


@lru_cache(maxsize=3)
def _face(path: str) -> Image.Image:
    """The whole photo, shrunk once (several circles of a photo come one after another)."""
    face = _photo(path).copy()
    face.thumbnail((FACE_SIZE, FACE_SIZE), Image.LANCZOS)
    return face


def make_handler(labelling: Round):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep the terminal quiet
            pass

        def send(self, body: bytes, content_type: str, status: int = 200):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, data, status: int = 200):
            self.send(json.dumps(data).encode(), "application/json", status)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/":
                self.send(PAGE.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/state":
                self.send_json(labelling.state())
            elif path.startswith("/picture/"):
                _, _, kind, item_id = path.split("/", 3)
                item_id = unquote(item_id)
                if kind not in KINDS or item_id not in labelling.by_id:
                    self.send_json({"error": "not found"}, 404)
                    return
                self.send(labelling.picture(item_id, kind), "image/jpeg")
            else:
                self.send_json({"error": "not found"}, 404)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            path = urlparse(self.path).path
            if path == "/api/answer":
                if body.get("item") not in labelling.by_id or body.get("label") not in TYPES:
                    self.send_json({"error": "bad answer"}, 400)
                    return
                save_answer(labelling.answers_file, body["item"], body["label"])
            elif path == "/api/back":
                labelling.take_back()
            else:
                self.send_json({"error": "not found"}, 404)
                return
            self.send_json(labelling.state())

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Label the type of each acne circle.")
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--min-seconds", type=float, default=2.0,
                        help="seconds the pictures are shown before the keys work")
    args = parser.parse_args(argv)

    labelling = Round(args.round, args.min_seconds)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(labelling))
    url = f"http://127.0.0.1:{args.port}"
    print(f"Round {args.round}: {url}  (Ctrl+C to stop; answers are saved as you go)")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped. Answers are in", labelling.answers_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
