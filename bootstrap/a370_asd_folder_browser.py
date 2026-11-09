"""A370 - secure, read-only BodyMind ASD document folder browser.

The filesystem is the source of truth: no database migration, no reindex,
no folder move, no document deletion. The upload system remains unchanged.
"""

from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import quote, urlencode
import re

from flask import abort, make_response, request


def safe_folder(base: Path, raw: str = "") -> Path:
    base = Path(base).resolve()
    raw = (raw or "").strip()
    if not raw:
        return base
    if (len(raw) > 400 or "\x00" in raw or "\\" in raw
            or raw.startswith("/") or "//" in raw
            or any(p in (".", "..") or p.startswith(".") for p in raw.split("/"))):
        raise ValueError("Percorso cartella non valido")
    candidate = (base / raw).resolve()
    if candidate == base or base not in candidate.parents:
        raise ValueError("Percorso fuori dall'archivio ASD")
    if not candidate.is_dir():
        raise FileNotFoundError("Cartella non trovata")
    return candidate


def list_folder(base: Path, raw: str = "") -> tuple[Path, list[dict], list[dict]]:
    """Read one folder level; preserve empty directories and original filenames."""
    base = Path(base).resolve()
    target = safe_folder(base, raw)
    folders, files = [], []
    for p in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.casefold())):
        if p.name.startswith(".") or p.is_symlink():
            continue
        rel = p.relative_to(base).as_posix()
        if p.is_dir():
            num = sum(1 for sub in p.rglob("*") if sub.is_file() and not sub.is_symlink())
            folders.append({"name": p.name, "rel": rel, "count": num})
        elif p.is_file():
            stat = p.stat()
            files.append({"name": p.name, "rel": rel, "bytes": stat.st_size,
                          "changed": datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y")})
    return target, folders, files


CSS = """<style id="bm370-styles">
#bm370{max-width:1120px;margin:24px auto 90px;padding:12px 14px;color:#e8f1ff;font-family:system-ui,-apple-system,Arial,sans-serif}
#bm370 *{box-sizing:border-box}#bm370 h1{font-size:clamp(26px,5vw,39px);margin:7px 0 8px;color:#fff}
#bm370 p{color:#adc9e5;line-height:1.5}#bm370 a{color:#d3f1ff;text-decoration:none}
#bm370 a:hover{text-decoration:underline}
#bm370 .crumb{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-weight:650;margin-bottom:17px}
#bm370 .crumb a,#bm370 .back{padding:8px 11px;border:1px solid #517da3;border-radius:10px;background:#103455}
#bm370 .note{padding:15px;border-radius:15px;border:1px solid #486d8a;background:#0e293f;margin:16px 0}
#bm370 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:13px;margin:18px 0}
#bm370 .folder{display:block;background:linear-gradient(135deg,#153b58,#17304b);border:1px solid #507ca1;border-radius:16px;padding:18px;min-height:109px}
#bm370 .folder b{font-size:16px;color:#fff;display:block;margin:10px 0 4px;word-break:break-word}#bm370 small{color:#b7d5ee}
#bm370 .file{display:flex;justify-content:space-between;align-items:center;gap:18px;padding:17px 14px;border-bottom:1px solid #3c5771;background:#112a42}
#bm370 .file:first-child{border-radius:14px 14px 0 0}#bm370 .file:last-child{border-radius:0 0 14px 14px}
#bm370 .file b{display:block;color:#fff;overflow-wrap:anywhere;font-size:15px}
#bm370 .actions{display:flex;gap:8px;flex-wrap:wrap;flex-shrink:0}#bm370 .actions a{padding:10px 12px;border-radius:11px;border:1px solid #6c9ac1;background:#174a70;font-weight:700}
#bm370 .empty{padding:22px;border:1px dashed #5b7fa1;border-radius:14px;color:#d3e8f8}
#bm370 .head{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap}
#bm370 .safe{font-size:13px;color:#b9d7e7}
.bm370-quick{margin:16px auto!important;padding:15px!important;border:1px solid #69b5da!important;background:#133852!important;border-radius:16px!important;max-width:1120px;color:#fff!important}
.bm370-quick a{display:inline-block!important;margin:8px 8px 0 0!important;padding:10px 13px!important;color:#fff!important;background:#215f84!important;border-radius:11px!important;text-decoration:none!important;font-weight:750!important;border:1px solid #8acaec!important}
.bm370-quick strong{color:#fff!important}
@media(max-width:640px){#bm370 .file{align-items:flex-start;flex-direction:column}#bm370 .actions{width:100%}#bm370 .actions a{flex:1;text-align:center}#bm370 .grid{grid-template-columns:1fr 1fr;gap:9px}#bm370 .folder{padding:12px}}
</style>"""


def render_archive(base: Path, raw: str = "") -> str:
    target, folders, files = list_folder(base, raw)
    home = "/documenti/asd/cartelle"
    parent = target.parent.relative_to(base).as_posix() if target != base else ""
    crumbs = f'<a href="{home}">Archivio ASD</a>'
    if target != base:
        path = []
        for part in target.relative_to(base).parts:
            path.append(part)
            url = home + "?" + urlencode({"cartella": "/".join(path)})
            crumbs += f' <span aria-hidden="true">/</span> <a href="{escape(url, quote=True)}">{escape(part.replace("_"," "))}</a>'
    tiles = "".join(
        f'<a class="folder" href="{home}?{urlencode({"cartella": d["rel"]})}">'
        f'<span aria-hidden="true">📁</span><b>{escape(d["name"].replace("_"," "))}</b>'
        f'<small>{d["count"]} file (anche nelle sottocartelle)</small></a>'
        for d in folders
    )
    documents = []
    for item in files:
        rel = quote(item["rel"], safe="/")
        preview = f"/documenti/asd/preview/{rel}"
        download = f"/documenti/asd/download/{rel}"
        documents.append(
            '<article class="file">'
            f'<div><b>{escape(item["name"])}</b><small>{item["changed"]} · {max(1,round(item["bytes"]/1024))} KB</small></div>'
            f'<div class="actions"><a href="{escape(preview,quote=True)}" target="_blank" rel="noopener noreferrer">Apri</a>'
            f'<a href="{escape(download,quote=True)}">Scarica</a></div></article>'
        )
    total = sum(x["count"] for x in folders) + len(files)
    return (
      CSS+'<main id="bm370">'
      f'<nav class="crumb" aria-label="Posizione cartella">{crumbs}</nav>'
      '<div class="head"><div><small>BODYMIND AERIAL STUDIO ASD</small>'
      f'<h1>{escape("Documenti ASD" if target == base else target.name.replace("_"," "))}</h1>'
      f'<p>{len(folders)} cartelle · {total} documenti complessivi in questa posizione</p></div>'
      '<a class="back" href="/documenti">← Torna a Documenti</a></div>'
      '<p class="note">Qui sono visibili le cartelle originali e i file conservati sul volume dell’associazione. '
      'Puoi aprire e scaricare i documenti senza modificarli. Le cartelle vuote sono mostrate normalmente.</p>'
      + ('<h2>Cartelle</h2><section class="grid">'+tiles+'</section>' if folders else '')
      + ('<h2>File della cartella</h2><section aria-label="Documenti presenti">'
         +''.join(documents)+'</section>' if files else
         '<div class="empty">Nessun file direttamente in questa cartella. Se ci sono sottocartelle, aprine una.</div>')
      + '<p class="safe">Sola consultazione: nessun file viene spostato, cancellato o reimportato.</p>'
      '</main>'
    )


def install(app):
    from asd_app.core import admin_required, get_asd_media_dir, layout
    if any(r.rule == "/documenti/asd/cartelle" for r in app.url_map.iter_rules()):
        raise RuntimeError("A370 duplicate archive browser route")

    @app.get("/documenti/asd/cartelle", endpoint="bm370_asd_folders")
    @admin_required
    def browse():
        folder = request.args.get("cartella", "")
        try:
            page = render_archive(get_asd_media_dir(), folder)
        except (ValueError, FileNotFoundError):
            abort(404)
        response = make_response(layout(page))
        response.headers["Cache-Control"] = "private, no-store, max-age=0"
        response.headers["X-BodyMind-Document-Archive"] = "A370"
        return response

    def quick_link(response):
        if (request.method != "GET" or request.path.rstrip("/") not in
                ("/documenti", "/documenti/asd", "/document-hub")
                or response.status_code != 200 or response.direct_passthrough
                or response.mimetype != "text/html"):
            return response
        page = response.get_data(as_text=True)
        if 'bm370-quick' in page:
            return response
        # The old index page does not include the physical ASD archive hierarchy.
        try:
            _,folders,_ = list_folder(get_asd_media_dir())
            chips = "".join(
                f'<a href="/documenti/asd/cartelle?{urlencode({"cartella": f["rel"]})}">📁 {escape(f["name"].replace("_"," "))}</a>'
                for f in folders
            )
        except (OSError, ValueError):
            chips = ""
        block = ('<div class="bm370-quick" role="region" aria-label="Cartelle documenti ASD">'
                 '<strong>📂 Documenti ASD · Cartelle originali</strong><div>'
                 '<a href="/documenti/asd/cartelle">Apri tutto l’archivio →</a>'+chips+'</div></div>')
        match = re.search(r"<main\b[^>]*>", page, flags=re.I)
        if not match:
            match = re.search(r"<body\b[^>]*>", page, flags=re.I)
        if not match:
            return response
        page = page[:match.end()] + CSS + block + page[match.end():]
        response.set_data(page)
        response.headers.pop("ETag", None)
        response.headers["Cache-Control"] = "private, no-store, max-age=0"
        return response

    app.after_request_funcs.setdefault(None, []).insert(0,quick_link)
    print("BODYMIND A370 DOCUMENT FOLDERS READY — read-only original tenant media", flush=True)
