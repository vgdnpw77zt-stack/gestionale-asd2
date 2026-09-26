from __future__ import annotations
from pathlib import Path
import compileall, shutil

APP=Path('/data/top2_app')
MARKER=APP/'.BODYMIND_DOCUMENT_UX_R10'
BACKUPS=Path('/data/release_backups/20260926_document_ux_r10')

def backup(rel):
    src=APP/rel; dst=BACKUPS/rel
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dst)

def patch_file(rel, transform):
    p=APP/rel
    if not p.exists():
        raise RuntimeError('R10 target missing: '+rel)
    old=p.read_text(encoding='utf-8')
    new=transform(old)
    if new != old:
        backup(rel)
        p.write_text(new,encoding='utf-8')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

if not MARKER.exists():
    # Recover any partial R10 write from the pre-R10 backups before retrying.
    for rel in ('asd_app/core.py','asd_app/routes_documenti.py','asd_app/routes_a159_total_audit_fix.py'):
        p=APP/rel; b=BACKUPS/rel
        if p.exists() and b.exists():
            cur=p.read_text(encoding='utf-8',errors='replace')
            if 'BODYMIND_R10_' in cur or 'bodymind-r10-document-ux' in cur:
                shutil.copy2(b,p)
                print('[document-ux-r10] restored partial '+rel,flush=True)
    def patch_core(s):
        if 'BODYMIND_R10_ABSOLUTE_DOCUMENT_PATHS' in s:
            return s
        start=s.find('def delete_media_file(relative_path: str) -> None:')
        end=s.find('def document_status_info(data_scadenza: str)', start)
        if start < 0 or end < 0:
            raise RuntimeError('R10 core document path anchors missing')
        block='''# BODYMIND_R10_ABSOLUTE_DOCUMENT_PATHS
def _resolve_workspace_document_path(stored_path: str) -> Path:
    media_root = get_workspace_media_dir().resolve()
    raw_text = str(stored_path or '').replace("\\\\", "/").strip()
    if not raw_text:
        return (media_root / "__missing_document__").resolve()
    raw = Path(raw_text)
    if raw.is_absolute():
        resolved = raw.resolve()
        if resolved == media_root or media_root in resolved.parents:
            return resolved
        return (media_root / "__invalid_absolute_document__").resolve()
    return (media_root / raw.as_posix().lstrip("/")).resolve()


def delete_media_file(relative_path: str) -> None:
    if not relative_path:
        return
    try:
        abs_path = _resolve_workspace_document_path(relative_path)
        media_root = get_workspace_media_dir().resolve()
        if (abs_path == media_root or media_root in abs_path.parents) and abs_path.exists() and abs_path.is_file():
            abs_path.unlink(missing_ok=True)
    except Exception:
        pass


def document_abs_path(relative_path: str) -> Path:
    return _resolve_workspace_document_path(relative_path)


'''
        return s[:start]+block+s[end:]

    patch_file('asd_app/core.py', patch_core)

    def patch_documenti(s):
        if 'BODYMIND_R10_VERIFY_DOCUMENT' in s:
            return s

        route_anchor='@app.route("/documenti/modelli/download/<path:filename>")'
        if route_anchor not in s:
            raise RuntimeError('R10 route anchor missing')
        verify_route='''# BODYMIND_R10_VERIFY_DOCUMENT
@app.post("/documenti/verify/<int:doc_id>")
@login_required
def documenti_verify(doc_id: int):
    tesserato_id = parse_int(request.form.get("tesserato_id"), 0)
    conn = db(); c = conn.cursor()
    try:
        row = c.execute("SELECT * FROM documenti WHERE id=?", (int(doc_id),)).fetchone()
        if not row or (tesserato_id > 0 and int(row["tesserato_id"] or 0) != tesserato_id):
            conn.close()
            return redirect_with_message("/documenti", "Documento non trovato nel dossier del tesserato.", "error", tesserato_id=tesserato_id)
        tesserato_id = int(row["tesserato_id"] or tesserato_id or 0)
        cols = {str(x[1]) for x in c.execute("PRAGMA table_info(documenti)").fetchall()}
        updates=[]; values=[]
        if "status" in cols:
            updates.append("status=?"); values.append("verificato")
        if "confidence" in cols:
            updates.append("confidence=?"); values.append(100)
        if "source" in cols and not (row["source"] if "source" in row.keys() else ""):
            updates.append("source=?"); values.append("manual_verify")
        if updates:
            values.append(int(doc_id))
            c.execute("UPDATE documenti SET "+",".join(updates)+" WHERE id=?", values)
        inbound_id = int((row["inbound_id"] if "inbound_id" in row.keys() else 0) or 0)
        if inbound_id:
            try:
                icols={str(x[1]) for x in c.execute("PRAGMA table_info(inbound_documents)").fetchall()}
                iupdates=["status='associato'","document_confidence=100"]
                if "updated_at" in icols:
                    iupdates.append("updated_at=datetime('now')")
                c.execute("UPDATE inbound_documents SET "+",".join(iupdates)+" WHERE id=?", (inbound_id,))
            except Exception:
                pass
        conn.commit()
    finally:
        try: conn.close()
        except Exception: pass
    return redirect_with_message("/documenti", "Documento verificato.", "success", tesserato_id=tesserato_id)


'''
        s=s.replace(route_anchor,verify_route+route_anchor,1)

        doc_lines=s.splitlines(True)
        preview_idx=next((i for i,line in enumerate(doc_lines) if "/documenti/preview/{d['id']}" in line and "Anteprima" in line),None)
        if preview_idx is None:
            raise RuntimeError('R10 preview action anchor missing')
        pfx=doc_lines[preview_idx][:len(doc_lines[preview_idx])-len(doc_lines[preview_idx].lstrip())]
        ok_line_raw='''{f"<form method='POST' action='/documenti/verify/{int(d['id'])}' class='inline-form bm-r10-ok-form'>{csrf_input()}<input type='hidden' name='tesserato_id' value='{tesserato_id}'><button class='pro-cta slim bm-r10-ok' type='submit'>✓ OK</button></form>" if ((int(d['inbound_id'] or 0) if 'inbound_id' in d.keys() else 0) and ((int(d['confidence'] or 0) if 'confidence' in d.keys() else 0) < 100 or str((d['status'] if 'status' in d.keys() else '') or '').lower() in ('da_verificare','needs_review','richiede_conferma','associato_tipo_da_verificare'))) else ''}\n'''
        doc_lines.insert(preview_idx,pfx+ok_line_raw)
        s=''.join(doc_lines)

        style_anchor='''       html body #archivio-doc .doc-archive-actions .pro-cta *,html body #archivio-asd-bulk .actions .pro-cta *{{color:#fff!important;-webkit-text-fill-color:#fff!important;pointer-events:none!important}}
'''
        style_extra=style_anchor+'''       html body #archivio-doc .bm-r10-ok-form{{display:inline-flex!important;margin:0!important}}
       html body #archivio-doc .bm-r10-ok{{background:#15803d!important;background-image:linear-gradient(180deg,#22c55e,#166534)!important;border-color:#86efac!important;color:#fff!important;-webkit-text-fill-color:#fff!important;font-weight:950!important}}
'''
        if style_anchor not in s:
            raise RuntimeError('R10 archive style anchor missing')
        s=s.replace(style_anchor,style_extra,1)

        close_anchor='''   </div>
   """)
'''
        route_pos=s.find(route_anchor)
        close_pos=s.rfind(close_anchor,0,route_pos)
        if close_pos < 0:
            raise RuntimeError('R10 document page close anchor missing')
        script='''   <script id="bodymind-r10-document-ux">
   document.addEventListener('DOMContentLoaded',function(){{
     const archive=document.getElementById('archivio-doc');
     const dossier=document.getElementById('dossier-onboarding');
     if(archive&&dossier&&dossier.parentNode){{dossier.parentNode.insertBefore(archive,dossier);}}
     const quick=[...document.querySelectorAll('.card')].find(x=>x.querySelector('.kicker')&&x.querySelector('.kicker').textContent.trim()==='Azioni rapide');
     if(quick)quick.remove();
     const models=document.getElementById('modelli-doc');
     if(models)models.remove();
     const upload=document.getElementById('upload-doc');
     if(upload){{
       const grid=upload.parentElement;
       const metrics=[...document.querySelectorAll('.metric-strip')][0];
       const anchor=(metrics&&metrics.nextSibling)?metrics.nextSibling:null;
       if(grid&&grid.classList.contains('grid-2')){{
         grid.parentNode.insertBefore(upload,anchor||grid);
         grid.remove();
       }}
       const kicker=upload.querySelector('.kicker'); if(kicker)kicker.textContent='Aggiungi documento';
       const h=upload.querySelector('.section-title'); if(h)h.textContent='Carica documento';
       const desc=upload.querySelector('.small-muted'); if(desc)desc.textContent='Un solo punto di caricamento. Il file comparirà subito nell’elenco documenti qui sopra.';
     }}
     const note=document.querySelector('#archivio-doc .small-muted');
     if(note)note.textContent='Prima controlla ciò che è già presente. Se un documento richiede conferma compare il pulsante ✓ OK.';
   }});
   </script>
'''
        s=s[:close_pos]+script+s[close_pos:]
        return s

    patch_file('asd_app/routes_documenti.py', patch_documenti)

    def patch_a159(s):
        if 'BODYMIND_R10_DOCUMENT_HUB_SIMPLIFY' in s:
            return s
        old="<button class='a159-btn ghost' type='button' data-a159-link='{did}'>Collega</button>"
        s=s.replace(old,'',1)
        marker="<main class='a159-page'>"
        if marker not in s:
            raise RuntimeError('R10 a159 marker missing')
        css="""<style id='BODYMIND_R10_DOCUMENT_HUB_SIMPLIFY'>
html body .a159-doc-actions .a159-btn,html body .a159-doc-actions a.a159-btn{background:#17324d!important;color:#fff!important;-webkit-text-fill-color:#fff!important;border:1px solid #6ea8d8!important;opacity:1!important;text-decoration:none!important;font-weight:850!important}
html body .a159-doc-actions .a159-btn.ghost,html body .a159-doc-actions a.a159-btn.ghost{background:#102a43!important;color:#fff!important;-webkit-text-fill-color:#fff!important;border-color:#7dd3fc!important}
html body .a159-doc-actions .a159-btn.danger{background:#991b1b!important;color:#fff!important;-webkit-text-fill-color:#fff!important;border-color:#fca5a5!important}
</style>"""
        return s.replace(marker,css+marker,1)

    patch_file('asd_app/routes_a159_total_audit_fix.py', patch_a159)

    if not compileall.compile_dir(str(APP/'asd_app'),quiet=1):
        raise RuntimeError('R10 compile failed')

    core=(APP/'asd_app/core.py').read_text(encoding='utf-8')
    docs=(APP/'asd_app/routes_documenti.py').read_text(encoding='utf-8')
    hub=(APP/'asd_app/routes_a159_total_audit_fix.py').read_text(encoding='utf-8')
    checks={
        'absolute-paths':'BODYMIND_R10_ABSOLUTE_DOCUMENT_PATHS' in core,
        'verify-route':'BODYMIND_R10_VERIFY_DOCUMENT' in docs and '/documenti/verify/' in docs,
        'reorder-script':'bodymind-r10-document-ux' in docs,
        'hub-no-collega':"data-a159-link" not in hub,
        'hub-contrast':'BODYMIND_R10_DOCUMENT_HUB_SIMPLIFY' in hub,
    }
    failed=[k for k,v in checks.items() if not v]
    if failed:
        raise RuntimeError('R10 selftest failed: '+repr(failed))
    MARKER.write_text('BodyMind document UX R10 applied\n',encoding='utf-8')
    print('[document-ux-r10] applied',flush=True)
    print('[document-ux-r10-selftest] PASS absolute-path-preview verify-ok archive-first single-upload hub-no-collega hub-contrast',flush=True)
else:
    print('[document-ux-r10] already applied',flush=True)
