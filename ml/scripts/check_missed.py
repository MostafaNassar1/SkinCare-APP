r"""Local page for the missed-pimple check: whole test photos with every expert circle drawn.

    cd ml; .venv\Scripts\activate; $env:PYTHONPATH = "."
    python scripts/check_missed.py            # then open http://127.0.0.1:8766
    python scripts/check_missed.py --summary  # how many pimples the experts missed
    python scripts/check_missed.py --freeze   # once all photos are checked, before YOLO training

Click a CLEAR pimple that has no circle to add one (yellow); click your circle again to remove it;
"Next photo" when the photo is checked. Expert circles (cyan) cannot be changed. Every click is
appended at once to prepared/corrections/missed_pimples.jsonl. Only this laptop can open the page.
"""

import argparse
import io
import json
import sys
import webbrowser
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image

from skincare_ml import config
from skincare_ml.missed_pimples import (
    add_circle,
    choose_photos,
    default_radius,
    frozen_record,
    load_state,
    mark_done,
    remove_circle,
    summary,
)

PAGE = Path(__file__).with_name("check_missed.html")
PHOTO_COUNT = 50
SHOWN_MAX = 2400  # px, longest side sent to the page (zoom up to 3x stays sharp enough)


class Check:
    def __init__(self):
        folder = config.prepared_dir() / "corrections"
        folder.mkdir(parents=True, exist_ok=True)
        self.log = folder / "missed_pimples.jsonl"
        self.sources = config.data_dir() / "sources"
        manifest = json.loads(
            (config.prepared_dir() / "manifests" / "pimples.json").read_text(encoding="utf-8")
        )
        by_file = {image["file"]: image for image in manifest["images"]}
        chosen_file = folder / "missed_check_photos.json"
        if not chosen_file.exists():  # chosen once, so every session checks the same photos
            chosen = choose_photos(manifest["images"], PHOTO_COUNT, seed=2026)
            chosen_file.write_text(json.dumps([image["file"] for image in chosen], indent=1))
        self.photos = [by_file[f] for f in json.loads(chosen_file.read_text(encoding="utf-8"))]

    def state(self) -> dict:
        state = load_state(self.log)
        index = next(
            (n for n, p in enumerate(self.photos) if p["file"] not in state.done), len(self.photos)
        )
        photo = None
        if index < len(self.photos):
            image = self.photos[index]
            photo = {
                "index": index,
                "file": image["file"],
                "width": image["width"],
                "height": image["height"],
                "grade": image["expert_grade"],
                "experts": [b["box"] for b in image["boxes"]],
                "added": [{"id": k, **v} for k, v in state.added.get(image["file"], {}).items()],
                "radius": default_radius(image),
            }
        return {"total": len(self.photos), "index": index, "photo": photo,
                "summary": summary(self.photos, state)}  # fmt: skip

    def back(self) -> None:
        """Reopen the last checked photo."""
        state = load_state(self.log)
        done = [p["file"] for p in self.photos if p["file"] in state.done]
        if done:
            mark_done(self.log, done[-1], done=False)

    def picture(self, index: int) -> bytes:
        return _shown(str(self.sources / self.photos[index]["file"]))


@lru_cache(maxsize=4)
def _shown(path: str) -> bytes:
    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((SHOWN_MAX, SHOWN_MAX), Image.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=90)
        return buffer.getvalue()


def make_handler(check: Check):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
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
                self.send_json(check.state())
            elif path.startswith("/photo/") and path[7:].isdigit() and int(path[7:]) < len(
                check.photos
            ):
                self.send(check.picture(int(path[7:])), "image/jpeg")
            else:
                self.send_json({"error": "not found"}, 404)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            current = check.state()["photo"]
            path = urlparse(self.path).path
            if path == "/api/back":
                check.back()
            elif current is None:
                self.send_json({"error": "all photos are checked"}, 400)
                return
            elif path == "/api/add":
                x, y = float(body["x"]), float(body["y"])
                if not (0 <= x <= current["width"] and 0 <= y <= current["height"]):
                    self.send_json({"error": "outside the photo"}, 400)
                    return
                add_circle(check.log, current["file"], x, y, current["radius"])
            elif path == "/api/remove":
                remove_circle(check.log, current["file"], str(body["id"]))
            elif path == "/api/done":
                mark_done(check.log, current["file"])
            else:
                self.send_json({"error": "not found"}, 404)
                return
            self.send_json(check.state())

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check test photos for pimples without a circle.")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--summary", action="store_true", help="print the result and stop")
    parser.add_argument("--freeze", action="store_true", help="freeze the checked corrections")
    args = parser.parse_args(argv)

    check = Check()
    if args.summary:
        print(json.dumps(check.state()["summary"], indent=1))
        return 0
    if args.freeze:
        target = check.log.with_name("missed_pimples_frozen.json")
        state = check.state()
        if target.exists():
            print(f"{target} already exists: frozen once", file=sys.stderr)
            return 1
        if state["photo"] is not None:
            print("Not every photo is checked yet", file=sys.stderr)
            return 1
        record = {**frozen_record(check.photos, load_state(check.log)),
                  "summary": state["summary"]}  # fmt: skip
        target.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
        print(f"Frozen {state['summary']['missed_added']} added circles on "
              f"{state['summary']['photos_checked']} photos, fingerprint {record['sha256']}")
        return 0
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(check))
    url = f"http://127.0.0.1:{args.port}"
    print(f"Missed-pimple check: {url}  (Ctrl+C to stop; every click is saved)")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped. Additions are in", check.log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
