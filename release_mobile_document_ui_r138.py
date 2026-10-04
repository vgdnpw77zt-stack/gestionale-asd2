from __future__ import annotations
import py_compile, shutil
from pathlib import Path

APP=Path('/data/top2_app')
BACK=Path('/data/release_backups/20261004_r138_mobile_docs')
BACK.mkdir(parents=True,exist_ok=True)
if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

# Tie minor tutela truth to MU presence on both desktop and mobile status cards.
patched=[]
for p in (APP/'asd_app').rglob('*.py'):
    try: s=p.read_text(encoding='utf-8',errors='replace')
    except Exception: continue
    before=s
    s=s.replace("_tutela_ok=(not _minor) or bool(_guardian and _guardian_contact and _consent)",
                "_tutela_ok=(not _minor) or bool(_mu and _guardian and _guardian_contact and _consent)")
    s=s.replace("_tut=(not _minor) or _guard",
                "_tut=(not _minor) or bool(_mu and _guard)")
    if s!=before:
        shutil.copy2(p,BACK/p.name)
        p.write_text(s,encoding='utf-8')
        py_compile.compile(str(p),doraise=True)
        patched.append(str(p))
print('[r138-truth] patched='+repr(patched),flush=True)

CORE=APP/'asd_app/core.py'
s=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R138_MOBILE_DOCUMENTS' not in s:
    shutil.copy2(CORE,BACK/'core.py')
    s += r'''

# BODYMIND_R138_MOBILE_DOCUMENTS
def _r138_doc_exists(filename):
    from pathlib import Path as _P
    raw=_P(str(filename or '').strip())
    roots=[_P('/data/tenants/default/media'),_P('/data/top2_app/user_static'),_P('/data/top2_app/static'),_P('/data/top2_app'),_P('/data/tenants/default')]
    cands=[raw] if raw.is_absolute() else [root/raw for root in roots]
    for fp in cands:
        try:
            if fp.is_file(): return True
        except Exception: pass
    return False

def _r138_doc_family(row):
    def v(k):
        try:return str(row[k] or '').lower()
        except Exception:return ''
    hay=' '.join(v(k) for k in ('doc_type','categoria','titolo','original_filename','filename'))
    if any(x in hay for x in ('modulo_unico_tesseramento','modulo unico','modulo iscrizione',"modulo d'iscrizione",'domanda iscrizione')):
        return 'Modulo Unico'
    if 'richiesta certificato' in hay or 'richiesta_certificato' in hay:
        return 'Richiesta certificato'
    if 'certificato_medico' in hay or ('certificat' in hay and 'medic' in hay):
        return 'Certificato medico'
    if 'liberatoria' in hay and ('immagin' in hay or 'foto' in hay):
        return 'Liberatoria immagini'
    return 'Documento'

@app.post('/mobile/documenti/<int:doc_id>/archivia')
@login_required
def bodymind_r138_mobile_document_archive(doc_id):
    conn=db(); conn.row_factory=sqlite3.Row
    try:
        row=conn.execute("SELECT * FROM documenti WHERE id=?",(doc_id,)).fetchone()
        if not row:
            return redirect_with_message('/mobile/atlete','Documento non trovato.','error')
        tid=int(row['tesserato_id'] or 0)
        conn.execute("UPDATE documenti SET visibile=0,status='archived_mobile_r138',updated_at=datetime('now') WHERE id=?",(doc_id,))
        remaining=conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1",(tid,)).fetchall()
        has_mu=any(_r138_doc_family(rr)=='Modulo Unico' and _r138_doc_exists(rr['filename']) for rr in remaining)
        try:
            conn.execute("UPDATE tesserati SET iscrizione_firmata=?,documenti_onboarding_ok=? WHERE id=?",
                         (1 if has_mu else 0,1 if has_mu else 0,tid))
        except Exception:
            pass
        conn.commit()
    finally:
        conn.close()
    return redirect('/mobile/atleta/'+str(tid)+'/documenti?updated=1')

@app.after_request
def bodymind_r138_mobile_document_page(resp):
    try:
        import re as _re
        m=_re.fullmatch(r'/mobile/atleta/(\d+)/documenti/?',request.path or '')
        if request.method!='GET' or not m or int(getattr(resp,'status_code',200) or 200)!=200:
            return resp
        tid=int(m.group(1))
        conn=db(); conn.row_factory=sqlite3.Row
        try:
            athlete=conn.execute("SELECT * FROM tesserati WHERE id=?",(tid,)).fetchone()
            rows=conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1 ORDER BY id DESC",(tid,)).fetchall()
        finally:
            conn.close()
        if not athlete: return resp
        name=(str(athlete['cognome'] or '')+' '+str(athlete['nome'] or '')).strip()
        cards=[]
        for r in rows:
            did=int(r['id']); family=_r138_doc_family(r); exists=_r138_doc_exists(r['filename'])
            title=str(r['titolo'] or r['original_filename'] or ('Documento #'+str(did)))
            open_btn=("<a class='r138-open' target='_blank' href='/documenti/file/"+str(did)+"'>Apri</a>" if exists else "")
            cards.append(f"""<article class='r138-doc'><div class='r138-main'><span>{e(family)}</span><b>{e(title)}</b><small class='{'ok' if exists else 'bad'}'>{'Disponibile' if exists else 'File non disponibile'}</small></div><div class='r138-actions'>{open_btn}<form method='post' action='/mobile/documenti/{did}/archivia' onsubmit="return confirm('Rimuovere questo documento dalla vista operativa? Il file fisico resterà conservato.');">{csrf_input()}<button type='submit'>Elimina</button></form></div></article>""")
        html=f"""<!doctype html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'><title>Documenti · {e(name)}</title><style>body{{margin:0;background:#071426;color:#eaf2ff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}}.r138{{max-width:720px;margin:auto;padding:16px 14px 90px}}.r138-head{{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;padding:17px;border-radius:18px;background:#0d2036;border:1px solid #203b57}}.r138-head h1{{margin:4px 0;font-size:25px}}.r138-head p{{margin:0;color:#9fb3ca}}.r138-back{{padding:10px 12px;background:#163b5f;border-radius:12px;color:#fff;text-decoration:none;font-weight:900}}.r138-list{{display:grid;gap:9px;margin-top:12px}}.r138-doc{{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center;padding:14px;border-radius:16px;background:#0b1b2e;border:1px solid #1d3651}}.r138-main{{display:grid;gap:4px;min-width:0}}.r138-main span{{font-size:10px;letter-spacing:.09em;text-transform:uppercase;color:#7dd3fc;font-weight:950}}.r138-main b{{font-size:15px;overflow-wrap:anywhere}}.r138-main small.ok{{color:#86efac}}.r138-main small.bad{{color:#fca5a5}}.r138-actions{{display:grid;gap:6px}}.r138-actions form{{margin:0}}.r138-open,.r138-actions button{{display:block;min-width:82px;padding:10px 12px;border:0;border-radius:11px;text-align:center;font-weight:900;text-decoration:none}}.r138-open{{background:#1d4ed8;color:white}}.r138-actions button{{width:100%;background:#7f1d1d;color:white}}.r138-empty{{padding:18px;border-radius:16px;background:#0b1b2e;color:#94a3b8;text-align:center}}@media(max-width:520px){{.r138-doc{{grid-template-columns:1fr}}.r138-actions{{grid-template-columns:1fr 1fr}}}}</style></head><body><main class='r138'><section class='r138-head'><div><small>DOCUMENTI ATLETA</small><h1>{e(name)}</h1><p>Archivio operativo. “Elimina” nasconde il record ma conserva il file fisico.</p></div><a class='r138-back' href='/mobile/atleta/{tid}'>Scheda</a></section>{("<div style='margin-top:10px;padding:10px;border-radius:12px;background:#14532d;color:#dcfce7;font-weight:900'>Documento archiviato.</div>" if request.args.get('updated') else '')}<section class='r138-list'>{''.join(cards) if cards else "<div class='r138-empty'>Nessun documento operativo presente.</div>"}</section></main></body></html>"""
        resp.set_data(html)
        resp.headers['Content-Type']='text/html; charset=utf-8'
    except Exception as exc:
        print('[r138-mobile-doc-warning] '+repr(exc),flush=True)
    return resp
'''
    CORE.write_text(s,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r138-mobile-docs] installed',flush=True)
else:
    print('[r138-mobile-docs] already present',flush=True)
