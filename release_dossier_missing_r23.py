from pathlib import Path
import compileall, shutil

APP=Path('/data/top2_app')
MARKER=APP/'.BODYMIND_DOSSIER_MISSING_R23'
BACKUPS=Path('/data/release_backups/20260928_dossier_missing_r23')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

def backup(rel):
    src=APP/rel; dst=BACKUPS/rel
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dst)

if not MARKER.exists():
    rel='asd_app/routes_documenti.py'
    p=APP/rel
    if not p.exists():
        raise RuntimeError('R23 target missing: '+rel)
    s=p.read_text(encoding='utf-8')

    if 'BODYMIND_R23_REMOVE_MISSING_DOSSIER_REF' not in s:
        backup(rel)

        route_anchor='@app.route("/documenti/modelli/download/<path:filename>")'
        route_code=r'''# BODYMIND_R23_REMOVE_MISSING_DOSSIER_REF
@app.post("/documenti/riferimento-mancante/<int:doc_id>/rimuovi")
@login_required
def documenti_remove_missing_reference(doc_id: int):
    tesserato_id = parse_int(request.form.get("tesserato_id"), 0)
    conn = db(); c = conn.cursor()
    try:
        row = c.execute("SELECT * FROM documenti WHERE id=? AND COALESCE(visibile,1)=1", (int(doc_id),)).fetchone()
        if not row:
            return redirect_with_message("/documenti", "Riferimento già rimosso o non trovato.", "error", tesserato_id=tesserato_id)
        tesserato_id = int(row["tesserato_id"] or tesserato_id or 0)
        fp = document_abs_path(str(row["filename"] or ""))
        if fp.exists() and fp.is_file():
            return redirect_with_message("/documenti", "Il file esiste: il riferimento non è stato rimosso.", "error", tesserato_id=tesserato_id)
        cols = {str(x[1]) for x in c.execute("PRAGMA table_info(documenti)").fetchall()}
        sets=[]
        if "visibile" in cols:
            sets.append("visibile=0")
        if "status" in cols:
            sets.append("status='riferimento_file_mancante_rimosso'")
        if sets:
            c.execute("UPDATE documenti SET "+",".join(sets)+" WHERE id=?", (int(doc_id),))
        conn.commit()
    finally:
        try: conn.close()
        except Exception: pass
    return redirect_with_message("/documenti", "Riferimento senza file rimosso dal dossier. Nessun file fisico è stato cancellato.", "success", tesserato_id=tesserato_id)


'''
        if route_anchor not in s:
            raise RuntimeError('R23 route anchor missing')
        s=s.replace(route_anchor,route_code+route_anchor,1)

        lines=s.splitlines(True)
        preview_idx=next((i for i,line in enumerate(lines) if "/documenti/preview/{d['id']}" in line and "Anteprima" in line),None)
        if preview_idx is None:
            raise RuntimeError('R23 preview action anchor missing')
        pfx=lines[preview_idx][:len(lines[preview_idx])-len(lines[preview_idx].lstrip())]
        missing_line=r'''{f"<span class='bm-r23-missing-badge'>File non disponibile</span><form method='POST' action='/documenti/riferimento-mancante/{int(d['id'])}/rimuovi' class='inline-form bm-r23-missing-form' onsubmit=\"return confirm('Rimuovere solo questo riferimento senza file dal dossier?')\">{csrf_input()}<input type='hidden' name='tesserato_id' value='{tesserato_id}'><button class='pro-cta slim bm-r23-remove-ref' type='submit'>Rimuovi riferimento</button></form>" if not document_abs_path(str(d['filename'] or '')).is_file() else ''}
'''
        lines.insert(preview_idx,pfx+missing_line)
        s=''.join(lines)

        style_anchor="html body #archivio-doc .bm-r10-ok{{background:#15803d!important;background-image:linear-gradient(180deg,#22c55e,#166534)!important;border-color:#86efac!important;color:#fff!important;-webkit-text-fill-color:#fff!important;font-weight:950!important}}"
        style_extra=style_anchor+"""
       html body #archivio-doc .bm-r23-missing-badge{{display:inline-flex!important;align-items:center!important;padding:7px 10px!important;border-radius:999px!important;background:rgba(127,29,29,.18)!important;border:1px solid rgba(248,113,113,.35)!important;color:#fecaca!important;-webkit-text-fill-color:#fecaca!important;font-size:10px!important;font-weight:900!important}}
       html body #archivio-doc .bm-r23-missing-form{{display:inline-flex!important;margin:0!important}}
       html body #archivio-doc .bm-r23-remove-ref{{background:#3b1620!important;background-image:none!important;border-color:#7f1d1d!important;color:#fecaca!important;-webkit-text-fill-color:#fecaca!important}}
"""
        if style_anchor not in s:
            raise RuntimeError('R23 style anchor missing')
        s=s.replace(style_anchor,style_extra,1)

        p.write_text(s,encoding='utf-8')

    if not compileall.compile_file(str(p),quiet=1):
        raise RuntimeError('R23 compile failed')

    text=p.read_text(encoding='utf-8')
    checks={
        'route':'BODYMIND_R23_REMOVE_MISSING_DOSSIER_REF' in text,
        'missing-badge':'bm-r23-missing-badge' in text,
        'remove-button':'Rimuovi riferimento' in text,
        'physical-guard':'if fp.exists() and fp.is_file():' in text,
    }
    failed=[k for k,v in checks.items() if not v]
    if failed:
        raise RuntimeError('R23 selftest failed: '+repr(failed))

    MARKER.write_text('BodyMind dossier missing reference R23 applied\n',encoding='utf-8')
    print('[dossier-r23] applied',flush=True)
    print('[dossier-r23-selftest] PASS missing-only-ui physical-file-guard soft-hide no-file-delete',flush=True)
else:
    print('[dossier-r23] already applied',flush=True)
