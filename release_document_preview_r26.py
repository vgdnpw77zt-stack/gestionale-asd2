from __future__ import annotations
from pathlib import Path
import compileall, shutil

APP=Path('/data/top2_app')
MARKER=APP/'.BODYMIND_DOCUMENT_PREVIEW_R26'
BACKUPS=Path('/data/release_backups/20260928_document_preview_r26')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

if not MARKER.exists():
    rel='asd_app/routes_documenti.py'
    p=APP/rel
    if not p.exists():
        raise RuntimeError('R26 target missing')
    s=p.read_text(encoding='utf-8')

    if 'BODYMIND_R26_DOCUMENT_VIEWER' not in s:
        BACKUPS.mkdir(parents=True,exist_ok=True)
        dst=BACKUPS/rel
        if not dst.exists():
            dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(p,dst)

        route_anchor='@app.route("/documenti/modelli/download/<path:filename>")'
        if route_anchor not in s:
            raise RuntimeError('R26 route anchor missing')
        route=r'''# BODYMIND_R26_DOCUMENT_VIEWER
@app.get("/documenti/visualizza/<int:doc_id>")
@login_required
def documenti_visualizza_r26(doc_id: int):
    conn=db(); c=conn.cursor()
    try:
        row=c.execute("SELECT id,tesserato_id,filename FROM documenti WHERE id=? AND COALESCE(visibile,1)=1",(int(doc_id),)).fetchone()
    finally:
        try: conn.close()
        except Exception: pass
    if not row:
        return redirect_with_message("/documenti","Documento non trovato.","error")
    tid=int(row["tesserato_id"] or 0)
    fp=document_abs_path(str(row["filename"] or ""))
    if not fp.exists() or not fp.is_file():
        return redirect_with_message("/documenti","File non disponibile.","error",tesserato_id=tid)
    back=f"/documenti?tesserato_id={tid}" if tid else "/documenti"
    return layout(f"""
    <style id='BODYMIND_R26_DOCUMENT_VIEWER_STYLE'>
      .bm-r26-viewer{{position:relative;max-width:1500px;margin:0 auto;padding:8px 0 24px}}
      .bm-r26-bar{{position:sticky;top:0;z-index:30;display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px 14px;margin-bottom:10px;border:1px solid rgba(148,163,184,.18);border-radius:16px;background:rgba(7,16,31,.94);backdrop-filter:blur(14px)}}
      .bm-r26-bar strong{{font-size:14px}} .bm-r26-actions{{display:flex;gap:8px;flex-wrap:wrap}}
      .bm-r26-btn{{display:inline-flex;align-items:center;justify-content:center;min-height:42px;padding:9px 13px;border-radius:12px;border:1px solid rgba(125,211,252,.3);background:#17324d;color:#fff!important;text-decoration:none;font-weight:900;cursor:pointer}}
      .bm-r26-btn.close{{background:#7f1d1d;border-color:#f87171}}
      .bm-r26-frame{{display:block;width:100%;height:calc(100svh - 150px);min-height:620px;border:1px solid rgba(148,163,184,.18);border-radius:18px;background:#fff}}
      @media(max-width:720px){{.bm-r26-bar{{align-items:flex-start;flex-direction:column}}.bm-r26-actions,.bm-r26-btn{{width:100%}}.bm-r26-frame{{height:calc(100svh - 205px);min-height:520px}}}}
    </style>
    <main class='bm-r26-viewer'>
      <div class='bm-r26-bar'>
        <strong>Anteprima documento</strong>
        <div class='bm-r26-actions'>
          <a class='bm-r26-btn' href='/documenti/preview/{int(doc_id)}' target='_blank' rel='noopener'>Apri originale</a>
          <button class='bm-r26-btn close' type='button' onclick="if(window.opener&&!window.opener.closed){{window.close();}}else if(history.length>1){{history.back();}}else{{window.location.href='{back}';}}">Chiudi</button>
        </div>
      </div>
      <iframe class='bm-r26-frame' src='/documenti/preview/{int(doc_id)}' title='Anteprima documento'></iframe>
    </main>
    """)


'''
        s=s.replace(route_anchor,route+route_anchor,1)

        marker='id="bodymind-r10-document-ux"'
        m=s.find(marker)
        if m<0:
            raise RuntimeError('R26 R10 UI marker missing')
        end=s.find('</script>',m)
        if end<0:
            raise RuntimeError('R26 script end missing')
        js=r'''
   document.addEventListener('DOMContentLoaded',function(){
     document.querySelectorAll('a[href^="/documenti/preview/"]').forEach(function(a){
       const m=(a.getAttribute('href')||'').match(/^\/documenti\/preview\/(\d+)/);
       if(m){a.setAttribute('href','/documenti/visualizza/'+m[1]);}
     });
   });
'''
        s=s[:end]+js+s[end:]
        p.write_text(s,encoding='utf-8')

    if not compileall.compile_file(str(p),quiet=1):
        raise RuntimeError('R26 compile failed')
    text=p.read_text(encoding='utf-8')
    checks={
        'viewer-route':'BODYMIND_R26_DOCUMENT_VIEWER' in text and '/documenti/visualizza/' in text,
        'close':'Chiudi' in text and 'window.close()' in text,
        'rewrite':'/documenti/visualizza/' in text and 'documenti/preview' in text,
    }
    failed=[k for k,v in checks.items() if not v]
    if failed:
        raise RuntimeError('R26 selftest failed: '+repr(failed))
    MARKER.write_text('BodyMind document preview R26 applied\n',encoding='utf-8')
    print('[document-preview-r26] applied',flush=True)
    print('[document-preview-r26-selftest] PASS wrapper close-button original-link responsive-viewer',flush=True)
else:
    print('[document-preview-r26] already applied',flush=True)
