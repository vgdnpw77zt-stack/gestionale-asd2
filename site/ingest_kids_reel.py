import json, os, sys
from pathlib import Path
from yt_dlp import YoutubeDL

URL = "https://www.instagram.com/reel/DGD1bGQsSoD/?stkn=MWgxbTU3b2Z6MjFkZQ=="
DATA = Path(os.environ.get("SITE_DATA_DIR") or "/data")
UPLOADS = DATA / "uploads"
CONTENT = DATA / "site_content.json"
TARGET = UPLOADS / "kids-reel.mp4"

UPLOADS.mkdir(parents=True, exist_ok=True)

if not TARGET.exists() or TARGET.stat().st_size < 100_000:
    for old in UPLOADS.glob("kids-reel.*"):
        try:
            old.unlink()
        except OSError:
            pass
    opts = {
        "format": "best[ext=mp4]/best",
        "outtmpl": str(UPLOADS / "kids-reel.%(ext)s"),
        "noplaylist": True,
        "quiet": False,
        "no_warnings": False,
        "overwrites": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
        },
    }
    print("[kids-reel] downloading source", flush=True)
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(URL, download=True)
    candidates = sorted(UPLOADS.glob("kids-reel.*"), key=lambda p: p.stat().st_size if p.exists() else 0, reverse=True)
    if not candidates:
        raise RuntimeError("Kids Reel download produced no file")
    chosen = candidates[0]
    if chosen.suffix.lower() != ".mp4":
        raise RuntimeError("Kids Reel is not MP4: " + chosen.name)
    if chosen != TARGET:
        chosen.replace(TARGET)

if not TARGET.exists() or TARGET.stat().st_size < 100_000:
    raise RuntimeError("Kids Reel MP4 missing or too small")

try:
    content = json.loads(CONTENT.read_text(encoding="utf-8")) if CONTENT.exists() else {}
except Exception:
    content = {}
kids = content.setdefault("kids", {})
kids["reel_url"] = URL
kids["video_file"] = "/site-media/kids-reel.mp4"
tmp = CONTENT.with_suffix(".tmp")
tmp.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
tmp.replace(CONTENT)
print(f"[kids-reel] READY bytes={TARGET.stat().st_size} path={TARGET}", flush=True)
