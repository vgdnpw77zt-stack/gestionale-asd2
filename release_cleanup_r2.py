from __future__ import annotations
from pathlib import Path
import compileall, os, shutil, time, json

APP = Path(os.environ.get("BODYMIND_APP_DIR", "/data/top2_app"))
MARKER = APP / ".BODYMIND_RELEASE_20260926_R2"
BACKUPS = Path(os.environ.get("BODYMIND_RELEASE_BACKUP_DIR", "/data/release_backups/20260926_r2"))

def backup(rel: str) -> None:
    src = APP / rel
    dst = BACKUPS / rel
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

if not MARKER.exists():
    # Keep only the canonical communication delete routes; operational aliases stay available.
    rel = "asd_app/routes_a147_operational_polish.py"
    p = APP / rel
    s = p.read_text(encoding="utf-8")
    for line in (
        "@app.post('/comunicazioni-automatiche/log/<int:message_id>/elimina')\n",
        "@app.post('/admin/comunicazioni-automatiche/log/<int:message_id>/elimina')\n",
    ):
        if line in s:
            backup(rel)
            s = s.replace(line, "", 1)
    p.write_text(s, encoding="utf-8")

    # Canonical operational delete route uses the newest coherent soft-delete semantics.
    rel = "asd_app/routes_a148_product_clarity.py"
    p = APP / rel
    s = p.read_text(encoding="utf-8")
    if "_coherent_delete" not in s:
        start = s.find("@app.post('/cuore-operativo/pratiche/<kind>/<int:item_id>/elimina')")
        ret = s.find("    return redirect(next_url)", start)
        end = s.find("\n\n", ret) if ret >= 0 else -1
        if ret >= 0 and end < 0:
            end = len(s)
        if start < 0 or end < 0:
            raise RuntimeError("R2 A148 delete block not found")
        new = """@app.post('/cuore-operativo/pratiche/<kind>/<int:item_id>/elimina')
@app.post('/risolvi-automatico/pratiche/<kind>/<int:item_id>/elimina')
@admin_required
def a187_delete_operational_practice(kind: str, item_id: int):
    \"\"\"Canonical delete: use coherent soft-delete semantics when supported.\"\"\"
    next_url = request.form.get('next') or request.referrer or '/cuore-operativo'
    if not str(next_url).startswith('/'):
        next_url = '/cuore-operativo'
    from .routes_a189_coherent_ops_repair import _delete as _coherent_delete
    conn = db()
    try:
        _coherent_delete(conn, (kind or '').strip().lower(), int(item_id))
        conn.commit()
    finally:
        conn.close()
    return redirect(next_url)"""
        backup(rel)
        p.write_text(s[:start] + new + s[end:], encoding="utf-8")

    # Remove duplicate compatibility decorators; helper remains for internal compatibility.
    rel = "asd_app/routes_a189_coherent_ops_repair.py"
    p = APP / rel
    s = p.read_text(encoding="utf-8")
    for line in (
        '@app.post("/cuore-operativo/pratiche/<kind>/<int:item_id>/elimina")\n',
        '@app.post("/risolvi-automatico/pratiche/<kind>/<int:item_id>/elimina")\n',
    ):
        if line in s:
            backup(rel)
            s = s.replace(line, "", 1)
    p.write_text(s, encoding="utf-8")

    if not compileall.compile_dir(str(APP), quiet=1):
        raise SystemExit("R2 compileall failed")
    MARKER.write_text(json.dumps({"release":"2026.09.26-r2","applied_at":time.time()}, indent=2), encoding="utf-8")
    print("[release] BodyMind 2026.09.26-r2 cleanup applied", flush=True)
else:
    print("[release] BodyMind 2026.09.26-r2 cleanup already applied", flush=True)
