from __future__ import annotations
from pathlib import Path
import compileall, json, re, shutil, time

APP = Path("/data/top2_app")
MARKER = APP / ".BODYMIND_RELEASE_20260926_R1"
BACKUPS = Path("/data/release_backups/20260926_r1")
PACKAGES = Path("/data/release_packages")

def backup(rel: str) -> None:
    src = APP / rel
    dst = BACKUPS / rel
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

def mutate(rel: str, fn) -> None:
    p = APP / rel
    if not p.exists():
        raise RuntimeError(f"missing release target: {rel}")
    old = p.read_text(encoding="utf-8")
    new = fn(old)
    if new != old:
        backup(rel)
        p.write_text(new, encoding="utf-8")

def req(s: str, old: str, new: str, label: str) -> str:
    if new in s:
        return s
    if old not in s:
        raise RuntimeError(f"release anchor missing: {label}")
    return s.replace(old, new, 1)

if not APP.joinpath(".TOP2_OFFICIAL").exists():
    raise SystemExit("TOP2_OFFICIAL marker missing; release refused")

if not MARKER.exists():
    BACKUPS.mkdir(parents=True, exist_ok=True)

    def patch_matcher(s: str) -> str:
        if "nome e cognome esatti e univoci nel documento" in s:
            return s
        old = '''    scored.sort(key=lambda x: x["score"], reverse=True)
    best = scored[0] if scored else {"row": None, "score": 0, "reasons": []}
'''
        new = '''    # RELEASE 2026-09: nome+cognome completi ed univoci nel TESTO sono
    # un segnale identitario forte. Gli omonimi restano protetti.
    hay_norm = _norm(text or "")
    exact_indexes: list[int] = []
    for idx, item in enumerate(scored):
        row = item.get("row")
        nome = _val(row, "nome")
        cognome = _val(row, "cognome")
        full = _norm(f"{nome} {cognome}")
        rev = _norm(f"{cognome} {nome}")
        if nome and cognome and ((full and full in hay_norm) or (rev and rev in hay_norm)):
            exact_indexes.append(idx)
    if len(exact_indexes) == 1:
        item = scored[exact_indexes[0]]
        if int(item.get("score") or 0) < 92:
            item["score"] = 92
            item.setdefault("reasons", []).append("nome e cognome esatti e univoci nel documento")

    # Layout a colonne/OCR: se i due nomi sono presenti come token separati,
    # chiedi conferma ma non auto-associare.
    words = set(hay_norm.split())
    for item in scored:
        row = item.get("row")
        n = set(_norm(_val(row, "nome")).split())
        c = set(_norm(_val(row, "cognome")).split())
        if n and c and n.issubset(words) and c.issubset(words) and int(item.get("score") or 0) < 78:
            item["score"] = 78
            item.setdefault("reasons", []).append("nome e cognome presenti nel testo")

    scored.sort(key=lambda x: x["score"], reverse=True)
    best = scored[0] if scored else {"row": None, "score": 0, "reasons": []}
'''
        return req(s, old, new, "athlete matcher")
    mutate("asd_app/athlete_matcher.py", patch_matcher)

    def patch_classifier(s: str) -> str:
        s=s.replace('"confidence": 20, "scores": {}, "hits": {}}','"confidence": 20, "confidence_label": "Tipo non riconosciuto", "scores": {}, "hits": {}}')
        s=s.replace('"confidence": 25, "scores": scores, "hits": hits}','"confidence": 25, "confidence_label": "Tipo non riconosciuto", "scores": scores, "hits": hits}')
        s=s.replace('"confidence": 45, "scores": scores, "hits": hits, "ambiguous": True}','"confidence": 45, "confidence_label": "Tipo ambiguo: verifica richiesta", "scores": scores, "hits": hits, "ambiguous": True}')
        if '"confidence_label": "Tipo riconosciuto" if confidence >= 80 else "Tipo probabile"' not in s:
            s=req(s,'        "confidence": confidence,\n        "scores": scores,','        "confidence": confidence,\n        "confidence_label": "Tipo riconosciuto" if confidence >= 80 else "Tipo probabile",\n        "scores": scores,',"classifier label")
        return s
    mutate("asd_app/document_classifier.py", patch_classifier)

    mutate("asd_app/medical_certificate_dates.py", lambda s: s.replace("def _ocr_pdf(payload: bytes, max_pages: int = 1) -> str:","def _ocr_pdf(payload: bytes, max_pages: int = 3) -> str:"))

    def patch_email(s: str) -> str:
        s=s.replace("ALLOWED_INBOUND_DOCS = {'.pdf', '.png', '.jpg', '.jpeg', '.webp', '.doc', '.docx'}","ALLOWED_INBOUND_DOCS = {'.pdf', '.png', '.jpg', '.jpeg', '.webp', '.docx'}")
        if "'document_confidence_label':" not in s:
            s=s.replace("'document_confidence': int(classification.get('confidence') or 0),","'document_confidence': int(classification.get('confidence') or 0),\n                'document_confidence_label': classification.get('confidence_label') or '',")
        if "current_tenant_slug, csrf_input," not in s:
            s=s.replace("db, get_workspace_media_dir, now_iso_dt, load_config, current_tenant_slug,\n)","db, get_workspace_media_dir, now_iso_dt, load_config, current_tenant_slug, csrf_input,\n)")
        if "<form method='post' class='a16-form-grid'>{csrf_input()}" not in s:
            s=s.replace("<form method='post' class='a16-form-grid'>","<form method='post' class='a16-form-grid'>{csrf_input()}")
        return s
    mutate("asd_app/routes_email_documents.py", patch_email)

    def patch_mobile(s: str) -> str:
        s=s.replace("from .core import app, admin_required, csrf_input","from .core import app, admin_required, csrf_input, MAX_UPLOAD_MB")
        s=s.replace("PDF, foto, DOC/DOCX. L'OCR usa lo stesso motore della versione desktop.","PDF, foto e DOCX. Prima leggiamo il testo digitale; OCR solo quando serve.")
        s=s.replace('accept=".pdf,.png,.jpg,.jpeg,.webp,.doc,.docx"','accept=".pdf,.png,.jpg,.jpeg,.webp,.docx"')
        s=s.replace("if(d.document_label||d.document_type) html+=badge((d.document_label||d.document_type)+(d.document_confidence?' · '+d.document_confidence+'%':''));","if(d.document_label||d.document_type) html+=badge('Tipo documento: '+(d.document_label||d.document_type)+(d.document_confidence?' · '+d.document_confidence+'%':'')+(d.document_confidence_label?' · '+d.document_confidence_label:''), d.document_confidence>=60?'':'warn');")
        s=s.replace("html+='<div class=\"kv\"><span>Match</span><b>'+esc(d.match_score?d.match_score+'%':'—')+'</b></div>';","html+='<div class=\"kv\"><span>Identità atleta</span><b>'+esc(d.match_score?d.match_score+'%':'—')+'</b></div>';")
        s=s.replace("const max=50*1024*1024, over=files.find(f=>f.size>max); if(over){msg('File troppo grande: '+over.name+'. Limite 50 MB.','err');return;}","const max={{max_upload_mb|int}}*1024*1024, over=files.find(f=>f.size>max); if(over){msg('File troppo grande: '+over.name+'. Limite {{max_upload_mb|int}} MB.','err');return;}")
        s=s.replace("return render_template_string(MOBILE_AUTOPILOT, csrf=csrf_input())","return render_template_string(MOBILE_AUTOPILOT, csrf=csrf_input(), max_upload_mb=MAX_UPLOAD_MB)")
        return s
    mutate("asd_app/routes_bodymind_fix49.py", patch_mobile)

    def patch_final(s: str) -> str:
        s=s.replace("/static/pwa/icons/icon-192.svg","/static/pwa/icon-192.svg").replace("/static/pwa/icons/icon-512.svg","/static/pwa/icon-512.svg")
        if '<form method="post">{{csrf|safe}}<div class="field">' not in s:
            s=s.replace('<form method="post"><div class="field">','<form method="post">{{csrf|safe}}<div class="field">')
        s=s.replace("return render_template_string(FAMILY_LANDING, error=error)","return render_template_string(FAMILY_LANDING, error=error, csrf=csrf_input())")
        return s
    mutate("asd_app/routes_bodymind_final.py", patch_final)

    def patch_core(s: str) -> str:
        s=s.replace('MAX_UPLOAD_MB = max(1, min(200, int(os.environ.get("ASD_MAX_UPLOAD_MB", "50"))))','MAX_UPLOAD_MB = max(1, min(500, int(os.environ.get("ASD_MAX_UPLOAD_MB", "50"))))')
        if 'PRAGMA busy_timeout = 15000' not in s:
            old='''def db():
   ensure_workspace_ready(current_tenant_slug())
   conn = sqlite3.connect(get_workspace_db_path(), timeout=10)
   conn.row_factory = sqlite3.Row
   conn.execute("PRAGMA foreign_keys = ON")
   return conn
'''
            new='''def db():
   ensure_workspace_ready(current_tenant_slug())
   conn = sqlite3.connect(get_workspace_db_path(), timeout=15)
   conn.row_factory = sqlite3.Row
   conn.execute("PRAGMA foreign_keys = ON")
   conn.execute("PRAGMA busy_timeout = 15000")
   try:
       conn.execute("PRAGMA journal_mode = WAL")
       conn.execute("PRAGMA synchronous = NORMAL")
   except Exception:
       pass
   return conn
'''
            s=req(s,old,new,"sqlite db")
        s=s.replace("<script src='/static/demo/demo_wow.js?v=a82-hardening-build'></script>","")
        s=s.replace("<div id=\\'a241-runtime-stamp\\'>A241 ACTIVE · HARD SURFACE</div>","")
        return s
    mutate("asd_app/core.py", patch_core)

    # Consolidate the historical CSS/JS references in core into two real files.
    corep=APP/"asd_app/core.py"; core=corep.read_text(encoding="utf-8")
    dist=APP/"static/dist"; dist.mkdir(parents=True, exist_ok=True)
    if "/static/dist/bodymind-ui-20260926.css" not in core:
        refs=re.findall(r"<link rel='stylesheet' href='(/static/[^']+\.css[^']*)'>",core)
        seen=set(); refs=[x for x in refs if not (x in seen or seen.add(x))]
        parts=[]
        for ref in refs:
            rel=ref.split("?",1)[0].removeprefix("/static/")
            fp=APP/"static"/rel
            if not fp.exists(): raise RuntimeError(f"missing CSS asset {rel}")
            parts.append(f"/* ---- {rel} ---- */\n"+fp.read_text(encoding="utf-8",errors="ignore"))
        (dist/"bodymind-ui-20260926.css").write_text("\n\n".join(parts),encoding="utf-8")
        if refs:
            core=core.replace(f"<link rel='stylesheet' href='{refs[0]}'>","<link rel='stylesheet' href='/static/dist/bodymind-ui-20260926.css?v=1'>",1)
            for ref in refs[1:]: core=core.replace(f"<link rel='stylesheet' href='{ref}'>","")
    if "/static/dist/bodymind-ui-20260926.js" not in core:
        refs=[]
        for m in re.finditer(r"<script src=\\?'(/static/[^'\\]+\.js[^'\\]*)\\?'></script>",core):
            ref=m.group(1)
            if "safari_fallback.js" not in ref and "demo_wow.js" not in ref and ref not in refs: refs.append(ref)
        parts=[]
        for ref in refs:
            rel=ref.split("?",1)[0].removeprefix("/static/")
            fp=APP/"static"/rel
            if not fp.exists(): raise RuntimeError(f"missing JS asset {rel}")
            parts.append(f"/* ---- {rel} ---- */\n;(function(){{\n"+fp.read_text(encoding="utf-8",errors="ignore")+"\n})();")
        (dist/"bodymind-ui-20260926.js").write_text("\n\n".join(parts),encoding="utf-8")
        if refs:
            token=f"<script src=\\'{refs[0]}\\'></script>"
            core=core.replace(token,"<script src=\\'/static/dist/bodymind-ui-20260926.js?v=1\\'></script>",1)
            for ref in refs[1:]: core=core.replace(f"<script src=\\'{ref}\\'></script>","")
    backup("asd_app/core.py"); corep.write_text(core,encoding="utf-8")

    # Make A241 a harmless compatibility hook; the bundled UI already contains its CSS.
    def patch_a241(s: str) -> str:
        start=s.index("def a241_hard_runtime_surface")
        end=s.index("\n\n# Register as FIRST",start)
        new='''def a241_hard_runtime_surface(response: Response) -> Response:
    """Legacy diagnostic hook kept inert in the consolidated release."""
    try:
        if "text/html" in (response.headers.get("Content-Type") or "").lower():
            response.headers["X-ASD-A241"] = "consolidated"
    except Exception:
        pass
    return response
'''
        s=s[:start]+new+s[end:]
        s=s.replace("STAMP = \"<div id='a241-runtime-stamp'>A241 ACTIVE · HARD SURFACE</div>\"","STAMP = \"\"")
        s=s.replace("'visible_stamp': 'A241 ACTIVE · HARD SURFACE',","'visible_stamp': None,")
        return s
    mutate("asd_app/routes_a241_hard_runtime_surface.py", patch_a241)

    release_module = '''# -*- coding: utf-8 -*-
from __future__ import annotations
import re
from flask import request, Response, jsonify
from .core import app, MAX_UPLOAD_MB
_RELEASE="2026.09.26-r1"
_SW={"/static/pwa/service-worker.js","/static/pwa/sw.js","/static/pwa/manifest.json"}
def release_response_policy(response: Response) -> Response:
    try:
        path=request.path or ""; ctype=(response.headers.get("Content-Type") or "").lower()
        if path in _SW or path.endswith("/manifest.json"):
            response.headers["Cache-Control"]="no-cache, max-age=0, must-revalidate"; response.headers["Pragma"]="no-cache"; response.headers["Expires"]="0"
        elif path.startswith("/static/"):
            response.headers["Cache-Control"]="public, max-age=31536000, immutable"; response.headers.pop("Pragma",None); response.headers.pop("Expires",None)
        elif path.startswith("/user-static/") or path.startswith("/bodymind-media/"):
            response.headers["Cache-Control"]="private, max-age=300"; response.headers.pop("Pragma",None); response.headers.pop("Expires",None)
        else:
            response.headers["Cache-Control"]="no-store"
        response.headers.setdefault("X-Content-Type-Options","nosniff")
        response.headers.setdefault("Referrer-Policy","strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options","SAMEORIGIN")
        response.headers.setdefault("Permissions-Policy","geolocation=(), microphone=(), camera=(self)")
        response.headers["X-BodyMind-Release"]=_RELEASE
        if "text/html" in ctype:
            original=response.get_data(as_text=True)
            fixed=re.sub(r"<div\\s+id=['\\\"]a241-runtime-stamp['\\\"]>.*?</div>","",original,flags=re.I|re.S)
            if fixed!=original: response.set_data(fixed); response.headers.pop("Content-Length",None)
    except Exception: pass
    return response
_funcs=app.after_request_funcs.setdefault(None,[])
_funcs[:]=[f for f in _funcs if getattr(f,"__name__","")!="release_response_policy"]
_funcs.insert(0,release_response_policy)
@app.get("/__release_20260926")
def release_probe():
    return jsonify({"ok":True,"release":_RELEASE,"max_upload_mb":MAX_UPLOAD_MB,"static_bundle":True,"response_policy":True})
'''
    p=APP/"asd_app/routes_release_20260926.py"; p.write_text(release_module,encoding="utf-8")

    def patch_app(s: str) -> str:
        s=s.replace("import asd_app.routes_bodymind_fix33  # BODYMIND FIX33 preventive audit hardening\nimport asd_app.routes_bodymind_fix33\n","import asd_app.routes_bodymind_fix33  # BODYMIND FIX33 preventive audit hardening\n")
        marker="import asd_app.routes_bodymind_fix47  # BODYMIND FIX47 diagnostics\n"
        if "import asd_app.routes_release_20260926" not in s:
            s=req(s,marker,marker+"import asd_app.routes_release_20260926  # consolidated release policy MUST remain last\n","final release import")
        return s
    mutate("app.py", patch_app)

    if not compileall.compile_dir(str(APP), quiet=1):
        raise SystemExit("release compileall failed")

    PACKAGES.mkdir(parents=True,exist_ok=True)
    pkg=PACKAGES/"bodymind_app_release_20260926_r1"
    if not pkg.with_suffix(".zip").exists():
        shutil.make_archive(str(pkg),"zip",root_dir=str(APP))

    MARKER.write_text(json.dumps({"release":"2026.09.26-r1","applied_at":time.time()},indent=2),encoding="utf-8")
    print("[release] BodyMind 2026.09.26-r1 applied",flush=True)
else:
    print("[release] BodyMind 2026.09.26-r1 already applied",flush=True)
