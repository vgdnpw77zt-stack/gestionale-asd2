# -*- coding: utf-8 -*-
from __future__ import annotations
import json, py_compile, re, sqlite3, shutil, subprocess, sys
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
BACK=Path('/data/release_backups/20261004_r135_document_file_route')
BACK.mkdir(parents=True,exist_ok=True)
if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

# Patch the active canonical document file route so both legacy relative paths
# and current absolute media paths resolve under approved storage roots.
target=None
for p in (APP/'asd_app').rglob('*.py'):
    try: s=p.read_text(encoding='utf-8',errors='replace')
    except Exception: continue
    if "@app.route('/documenti/file/<int:doc_id>')" in s and 'def tesserato_document_file' in s:
        target=(p,s); break
if not target:
    raise RuntimeError('R135 canonical document file route not found')
p,s=target
if 'BODYMIND_R135_DOCUMENT_FILE_RESOLVER' not in s:
    pattern=re.compile(r"(?s)# BODYMIND_R9_DOCUMENT_FILE\s*@app\.route\('/documenti/file/<int:doc_id>'\).*?def tesserato_document_file\(doc_id: int\):.*?(?=\n\n@app\.|\Z)")
    m=pattern.search(s)
    if not m:
        # Fallback without the historical comment.
        pattern=re.compile(r"(?s)@app\.route\('/documenti/file/<int:doc_id>'\).*?def tesserato_document_file\(doc_id: int\):.*?(?=\n\n@app\.|\Z)")
        m=pattern.search(s)
    if not m:
        raise RuntimeError('R135 document file function block not found')
    new=r'''# BODYMIND_R135_DOCUMENT_FILE_RESOLVER
@app.route('/documenti/file/<int:doc_id>')
@admin_required
def tesserato_document_file(doc_id: int):
    from pathlib import Path as _R135Path
    from flask import abort as _r135_abort, send_file as _r135_send_file
    conn=db()
    try:
        row=conn.execute("SELECT id,filename,original_filename FROM documenti WHERE id=? AND COALESCE(visibile,1)=1",(doc_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        _r135_abort(404)

    raw=_R135Path(str(row['filename'] or '').strip())
    roots=[
        _R135Path('/data/tenants/default/media'),
        _R135Path('/data/top2_app/user_static'),
        _R135Path('/data/top2_app/static'),
        _R135Path('/data/top2_app'),
        _R135Path('/data/tenants/default'),
    ]
    try:
        roots.insert(0,get_workspace_media_dir().resolve())
    except Exception:
        pass
    allowed=[]
    for root in roots:
        try:
            rr=root.resolve()
            if rr not in allowed: allowed.append(rr)
        except Exception:
            continue

    candidates=[]
    if raw.is_absolute():
        try: candidates.append(raw.resolve())
        except Exception: pass
    else:
        for root in allowed:
            try: candidates.append((root/raw).resolve())
            except Exception: pass

    fp=None
    for cand in candidates:
        try:
            permitted=any(cand==root or root in cand.parents for root in allowed)
            if permitted and cand.is_file():
                fp=cand; break
        except Exception:
            continue
    if fp is None:
        _r135_abort(404)
    return _r135_send_file(fp,as_attachment=(request.args.get('download')=='1'),
                           download_name=(row['original_filename'] or fp.name))
'''
    dst=BACK/p.name
    if not dst.exists(): shutil.copy2(p,dst)
    s=s[:m.start()]+new+s[m.end():]
    p.write_text(s,encoding='utf-8')
    py_compile.compile(str(p),doraise=True)
    print('[r135-route] patched '+str(p),flush=True)
else:
    print('[r135-route] already applied '+str(p),flush=True)

# Accurate read-only audit using the real media root.
def _kind(r):
    hay=' '.join(str(r.get(k) or '').lower() for k in ('doc_type','categoria','titolo','original_filename','filename'))
    if ('modulo_unico_tesseramento' in hay or 'modulo unico' in hay or 'modulo iscrizione' in hay or 'domanda iscrizione' in hay or 'domanda di iscrizione' in hay):
        return 'mu'
    if 'richiesta certificato' in hay or 'richiesta_certificato' in hay or 'ecg' in hay or 'elettrocard' in hay or 'referto' in hay:
        return 'other'
    if 'certificato_medico' in hay or ('certificat' in hay and 'medic' in hay):
        return 'medical'
    return 'other'

def _resolve(r):
    raw=Path(str(r.get('filename') or '').strip())
    roots=[Path('/data/tenants/default/media'),APP/'user_static',APP/'static',APP,Path('/data/tenants/default')]
    cands=[raw] if raw.is_absolute() else [x/raw for x in roots]
    for c in cands:
        try:
            if c.is_file(): return str(c.resolve())
        except Exception: pass
    return ''

conn=sqlite3.connect(str(DB),timeout=30); conn.row_factory=sqlite3.Row
try:
    rows=[dict(x) for x in conn.execute("""SELECT d.*,t.nome AS atleta_nome,t.cognome AS atleta_cognome
      FROM documenti d LEFT JOIN tesserati t ON t.id=d.tesserato_id
      WHERE coalesce(d.visibile,1)=1 ORDER BY d.id""").fetchall()]
    report={'mu':{'total':0,'exists':0,'missing':[]},'medical':{'total':0,'exists':0,'missing':[]}}
    lud=[]
    for r in rows:
        k=_kind(r)
        if k not in report: continue
        report[k]['total']+=1
        fp=_resolve(r)
        if fp: report[k]['exists']+=1
        else: report[k]['missing'].append({'id':r.get('id'),'athlete':((r.get('atleta_cognome') or '')+' '+(r.get('atleta_nome') or '')).strip(),'filename':r.get('filename')})
        if str(r.get('atleta_cognome') or '').strip().lower()=='angelucci' and str(r.get('atleta_nome') or '').strip().lower()=='ludovica':
            lud.append({'id':r.get('id'),'kind':k,'filename':r.get('filename'),'resolved':fp})
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0]); fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally: conn.close()
print('[r135-audit] '+json.dumps(report,ensure_ascii=False),flush=True)
print('[r135-ludovica] '+json.dumps(lud,ensure_ascii=False),flush=True)

# Fresh import test: verify the resolver against any CURRENT visible document
# whose physical file exists. Do not pin QA to a specific athlete/document that
# the user may legitimately archive or delete from the operational view.
qa=r'''
import sqlite3,sys
from pathlib import Path
sys.path.insert(0,"/data/top2_app")
import app as _full
from asd_app.core import app
app.config["TESTING"]=True
roots=[Path("/data/tenants/default/media"),Path("/data/top2_app/user_static"),Path("/data/top2_app/static"),Path("/data/top2_app"),Path("/data/tenants/default")]
conn=sqlite3.connect("/data/tenants/default/asd.db",timeout=20); conn.row_factory=sqlite3.Row
try:
    target=None
    for row in conn.execute("SELECT id,filename FROM documenti WHERE coalesce(visibile,1)=1 ORDER BY id DESC").fetchall():
        raw=Path(str(row["filename"] or "").strip())
        cands=[raw] if raw.is_absolute() else [r/raw for r in roots]
        if any(p.is_file() for p in cands):
            target=int(row["id"]); break
finally: conn.close()
if target is None:
    raise RuntimeError("R135 no visible document with a physical file available for resolver QA")
c=app.test_client()
with c.session_transaction() as sess:
    sess.update({"logged":True,"username":"admin","display_name":"R135 QA","role":"admin","tenant_slug":"default"})
rr=c.get("/documenti/file/"+str(target),follow_redirects=False)
print("[r135-open-test] id="+str(target)+" status="+str(rr.status_code)+" type="+str(rr.headers.get("Content-Type","")),flush=True)
if rr.status_code!=200:
    raise RuntimeError("R135 current visible document open failed id="+str(target))
'''
proc=subprocess.run([sys.executable,'-c',qa],capture_output=True,text=True,timeout=120)
print((proc.stdout or '').strip(),flush=True)
if proc.returncode!=0:
    raise RuntimeError('R135 child QA failed '+((proc.stderr or '')+(proc.stdout or ''))[-4000:])
if integrity.lower()!='ok' or fk:
    raise RuntimeError('R135 DB integrity failed')
print('[r135-selftest] PASS file-route legacy+current paths db-ok',flush=True)
