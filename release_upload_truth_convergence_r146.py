# -*- coding: utf-8 -*-
from __future__ import annotations
import hashlib, json, py_compile, shutil, sqlite3, subprocess, sys
from datetime import datetime, timedelta
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
CORE=APP/'asd_app/core.py'
SYNC=APP/'asd_app/document_sync_core_r143.py'
BACK=Path('/data/release_backups/20261005_r146_upload_truth')
BACK.mkdir(parents=True,exist_ok=True)
if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

# Verified backup before any DB mutation.
stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
bak=BACK/(stamp+'_pre_r146.db')
src=sqlite3.connect(str(DB),timeout=30); out=sqlite3.connect(str(bak))
try: src.backup(out)
finally: out.close(); src.close()

sys.path.insert(0,str(APP))
if 'asd_app.document_sync_core_r143' in sys.modules:
    del sys.modules['asd_app.document_sync_core_r143']
from asd_app.document_sync_core_r143 import (
    canonical_type, resolve_file, sha256_file, sync_document, materialize_inbound,
    reconcile_all, truth, _ensure_persistent
)

def _table(conn,name):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())

def _cols(conn,name):
    return {str(x[1]) for x in conn.execute("PRAGMA table_info("+name+")").fetchall()} if _table(conn,name) else set()

def _parse_ts(v):
    raw=str(v or '').strip()
    if not raw:return None
    try:return datetime.fromisoformat(raw.replace('Z','+00:00')).replace(tzinfo=None)
    except Exception:return None

def _semantic_expiry(sems):
    for x in sorted(sems or [],key=lambda y:float(y.get('confidence') or 0),reverse=True):
        try:an=json.loads(x.get('analysis_json') or '{}')
        except Exception:an={}
        for k in ('expiry_date','valid_until','scadenza','expiration_date'):
            raw=str(an.get(k) or '').strip()
            if not raw:continue
            for fmt in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y'):
                try:return datetime.strptime(raw[:10],fmt).date().isoformat()
                except Exception:pass
    return ''

def _newer_tombstone(conn,canonical_id,path,archive_time):
    if not _table(conn,'document_deletion_tombstones'):return False
    cols=_cols(conn,'document_deletion_tombstones')
    rows=[]
    try:
        if canonical_id and 'document_id' in cols:
            rows += conn.execute("SELECT * FROM document_deletion_tombstones WHERE document_id=?",(canonical_id,)).fetchall()
    except Exception:pass
    for r in rows:
        keys=set(r.keys())
        ts=None
        for k in ('deleted_at','created_at','timestamp'):
            if k in keys and r[k]:
                ts=_parse_ts(r[k]);break
        if ts and archive_time and ts>=archive_time:
            return True
    return False

def _insert_from_recent_duplicate_archive(conn,a):
    try:
        payload=json.loads(a['payload_json'] or '{}')
        original=payload.get('row') or {}
        sems=json.loads(a['semantics_json'] or '[]')
    except Exception:
        return {'ok':False,'reason':'bad_archive_payload'}
    ats=_parse_ts(a['archived_at'])
    if not ats or datetime.now()-ats>timedelta(hours=24):
        return {'ok':False,'reason':'not_recent'}
    tid=int(a['tesserato_id'] or original.get('tesserato_id') or 0)
    if tid<=0 or not conn.execute("SELECT 1 FROM tesserati WHERE id=?",(tid,)).fetchone():
        return {'ok':False,'reason':'no_athlete'}
    dtype=canonical_type(str(original.get('document_type') or original.get('doc_type') or original.get('document_label') or ''))
    if dtype not in ('certificato_medico','modulo_unico_tesseramento','liberatoria_immagini'):
        return {'ok':False,'reason':'unsupported_type','type':dtype}
    try:conf=float(original.get('document_confidence') or original.get('doc_confidence') or 0)
    except Exception:conf=0
    try:match=float(original.get('match_score') or 0)
    except Exception:match=0
    # An explicit new upload must have strong recognition before it may revive
    # operational truth after an older copy was hidden/deleted.
    if conf<80 or match<80:
        return {'ok':False,'reason':'low_confidence','confidence':conf,'match':match}
    source_path=str(a['file_path'] or original.get('saved_path') or original.get('path') or original.get('filename') or '')
    fp=resolve_file(source_path)
    if not fp:
        return {'ok':False,'reason':'upload_file_missing'}
    canonical_id=int(payload.get('canonical_document_id') or 0)
    if _newer_tombstone(conn,canonical_id,source_path,ats):
        return {'ok':False,'reason':'deleted_after_reupload'}

    persistent=_ensure_persistent(tid,fp,original.get('original_filename') or fp.name)
    digest=sha256_file(persistent)

    # Never create a second active row. Same athlete + semantic type + SHA only.
    for d in conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1 ORDER BY id DESC",(tid,)).fetchall():
        if canonical_type(d)!=dtype:continue
        ef=resolve_file(d['filename'])
        if ef and sha256_file(ef)==digest:
            res=sync_document(conn,int(d['id']))
            res.update({'r146':'existing_visible','archive_id':int(a['id'])})
            return res

    dc=_cols(conn,'documenti')
    meta={
      'certificato_medico':('Certificato medico','Certificato medico'),
      'modulo_unico_tesseramento':('Modulo iscrizione BodyMind','Modulo Unico'),
      'liberatoria_immagini':('Liberatoria immagini','Liberatoria immagini'),
    }
    cat,label=meta[dtype]
    expiry=_semantic_expiry(sems) if dtype=='certificato_medico' else ''
    vals={
      'tesserato_id':tid,
      'titolo':str(original.get('original_filename') or label),
      'categoria':cat,
      'filename':str(persistent),
      'original_filename':str(original.get('original_filename') or persistent.name),
      'data_caricamento':datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
      'data_scadenza':expiry,
      'note':'R146: nuovo upload esplicito recuperato dopo precedente copia archiviata',
      'visibile':1,'tipo_template':'inbound_auto','tenant_id':'default','doc_type':dtype,
      'confidence':conf,'match_score':match,'source':'explicit_reupload_r146',
      'status':'salvato','inbound_id':None
    }
    ks=[k for k in vals if k in dc]
    conn.execute("INSERT INTO documenti("+','.join(ks)+") VALUES("+','.join('?' for _ in ks)+")",[vals[k] for k in ks])
    did=int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    res=sync_document(conn,did)
    res.update({'r146':'recovered_recent_reupload','archive_id':int(a['id'])})
    return res

conn=sqlite3.connect(str(DB),timeout=60);conn.row_factory=sqlite3.Row
actions=[];before_caruso={};after_caruso={}
try:
    car=conn.execute("SELECT * FROM tesserati WHERE lower(cognome)='caruso' AND lower(nome)='vincenza' LIMIT 1").fetchone()
    if car:
        tid=int(car['id'])
        before_caruso={
          'athlete':dict(car),
          'truth':truth(conn,car),
          'documents':[dict(x) for x in conn.execute("SELECT id,tesserato_id,titolo,categoria,filename,original_filename,data_scadenza,visibile,doc_type,confidence,match_score,source,status,inbound_id FROM documenti WHERE tesserato_id=? ORDER BY id DESC LIMIT 30",(tid,)).fetchall()],
          'inbound':[dict(x) for x in conn.execute("SELECT * FROM inbound_documents WHERE coalesce(tesserato_id,0)=? OR coalesce(matched_tesserato_id,0)=? OR coalesce(suggested_tesserato_id,0)=? ORDER BY id DESC LIMIT 30",(tid,tid,tid)).fetchall()] if _table(conn,'inbound_documents') else []
        }

    # 1) First run existing conservative convergence.
    actions.extend(reconcile_all(conn))

    # 2) Recover CURRENT explicit re-uploads that were deduped against an older
    # hidden/deleted canonical row. This is the gap that made "recognized and
    # associated" still display as missing.
    if _table(conn,'bodymind_duplicate_records_archive'):
        archives=conn.execute("""SELECT * FROM bodymind_duplicate_records_archive
          WHERE source_table='inbound_documents'
            AND datetime(archived_at)>=datetime('now','-24 hours')
          ORDER BY id DESC""").fetchall()
        for a in archives:
            res=_insert_from_recent_duplicate_archive(conn,a)
            if res.get('ok'):actions.append(res)

    # 3) Positive recent inbound associations are materialized even if an
    # earlier response path forgot to invoke the sync hook.
    if _table(conn,'inbound_documents'):
        positive=('accepted','manual_accepted','verificato','archived_to_tesserato','resolved','associato')
        rows=conn.execute("""SELECT * FROM inbound_documents
          WHERE coalesce(tesserato_id,0)>0
            AND datetime(coalesce(updated_at,created_at))>=datetime('now','-24 hours')
          ORDER BY id DESC LIMIT 500""").fetchall()
        for r in rows:
            st=str(r['status'] or '').strip().lower()
            if st not in positive:continue
            try:
                res=materialize_inbound(conn,int(r['id']),allow_old=False)
                if res.get('ok'):actions.append(res)
            except Exception as exc:
                actions.append({'ok':False,'inbound_id':int(r['id']),'error':repr(exc)[:180]})

    actions.extend(reconcile_all(conn))
    conn.commit()

    if car:
        car2=conn.execute("SELECT * FROM tesserati WHERE id=?",(int(car['id']),)).fetchone()
        after_caruso={
          'athlete':dict(car2),
          'truth':truth(conn,car2),
          'documents':[dict(x) for x in conn.execute("SELECT id,tesserato_id,titolo,categoria,filename,original_filename,data_scadenza,visibile,doc_type,confidence,match_score,source,status,inbound_id FROM documenti WHERE tesserato_id=? ORDER BY id DESC LIMIT 30",(int(car['id']),)).fetchall()]
        }

    # Global invariant: any visible physical canonical document must be seen by
    # truth. Medical with no expiry may be orange/Da verificare, but never Manca.
    contradictions=[]
    for a in conn.execute("SELECT * FROM tesserati ORDER BY id").fetchall():
        tid=int(a['id'])
        tr=truth(conn,a)
        docs=conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1",(tid,)).fetchall()
        has_mu=any(canonical_type(d)=='modulo_unico_tesseramento' and resolve_file(d['filename']) for d in docs)
        has_med=any(canonical_type(d)=='certificato_medico' and resolve_file(d['filename']) for d in docs)
        if has_mu and not tr.get('mu'): contradictions.append({'tid':tid,'kind':'mu'})
        if has_med and not tr.get('med_present'): contradictions.append({'tid':tid,'kind':'medical'})
        if has_med and tr.get('med_state')=='Manca': contradictions.append({'tid':tid,'kind':'medical_state_manca'})

    integrity=str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    fk=len(conn.execute("PRAGMA foreign_key_check").fetchall())
finally:
    conn.close()

print('[r146-before-caruso] '+json.dumps(before_caruso,ensure_ascii=False,default=str),flush=True)
print('[r146-after-caruso] '+json.dumps(after_caruso,ensure_ascii=False,default=str),flush=True)
print('[r146-actions] '+json.dumps(actions[-120:],ensure_ascii=False,default=str),flush=True)
print('[r146-invariants] contradictions='+json.dumps(contradictions,ensure_ascii=False)+' integrity='+integrity+' fk='+str(fk)+' backup='+str(bak),flush=True)
if contradictions or integrity.lower()!='ok' or fk:
    raise RuntimeError('R146 document truth invariant failed')

# High-contrast iPhone/Safari upload and sub-screen controls.
core=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R146_MOBILE_CONTROL_CONTRAST' not in core:
    shutil.copy2(CORE,BACK/'core.py')
    core += r'''

# BODYMIND_R146_MOBILE_CONTROL_CONTRAST
@app.after_request
def _bodymind_r146_mobile_control_contrast(resp):
    try:
        import re as _r146_re
        p=request.path or ''
        if request.method!='GET' or not p.startswith('/mobile/') or int(getattr(resp,'status_code',200) or 200)!=200:
            return resp
        if 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp
        html=resp.get_data(as_text=True)
        css="""<style id='bodymind-r146-contrast'>
        html{color-scheme:dark}
        body{color:#eef6ff!important}
        h1,h2,h3,label{color:#eef6ff!important;-webkit-text-fill-color:#eef6ff!important}
        button,input[type=submit],input[type=button],.back,.r138-back,.r137-back,
        a.upload,.actions a,.r138-actions button,.r137-actions button{
          opacity:1!important;visibility:visible!important;
          color:#fff!important;-webkit-text-fill-color:#fff!important;
          text-shadow:none!important;font-weight:900!important;
        }
        input,select,textarea{
          color:#fff!important;-webkit-text-fill-color:#fff!important;
          background:#081727!important;border-color:#315475!important;
          opacity:1!important;
        }
        select option{background:#081727!important;color:#fff!important}
        input[type=file]{color:#eef6ff!important;-webkit-text-fill-color:#eef6ff!important}
        input[type=file]::file-selector-button{
          appearance:none!important;-webkit-appearance:none!important;
          background:#eef6ff!important;color:#071426!important;
          -webkit-text-fill-color:#071426!important;
          border:1px solid #fff!important;border-radius:10px!important;
          padding:9px 13px!important;margin-right:10px!important;
          font-weight:900!important;opacity:1!important;
        }
        input[type=file]::-webkit-file-upload-button{
          -webkit-appearance:none!important;
          background:#eef6ff!important;color:#071426!important;
          -webkit-text-fill-color:#071426!important;
          border:1px solid #fff!important;border-radius:10px!important;
          padding:9px 13px!important;margin-right:10px!important;
          font-weight:900!important;opacity:1!important;
        }
        </style>"""
        if "id='bodymind-r146-contrast'" not in html:
            html=html.replace('</head>',css+'</head>',1) if '</head>' in html else css+html
            resp.set_data(html)
    except Exception as exc:
        print('[r146-contrast-warning] '+repr(exc),flush=True)
    return resp
'''
    CORE.write_text(core,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r146-contrast] installed',flush=True)
else:
    print('[r146-contrast] already installed',flush=True)

# Fresh-process UI + truth QA. No POST mutation.
qa=r'''
import sqlite3,sys
sys.path.insert(0,"/data/top2_app")
import app as _full
from asd_app.core import app
from asd_app.document_sync_core_r143 import truth,canonical_type,resolve_file
app.config["TESTING"]=True
c=app.test_client()
with c.session_transaction() as s:
    s.update({"logged":True,"logged_in":True,"username":"admin","display_name":"R146 QA","role":"admin","tenant_slug":"default","user_id":1,"is_admin":True,"admin":True,"_csrf_token":"r146"})
conn=sqlite3.connect("/data/tenants/default/asd.db");conn.row_factory=sqlite3.Row
try:
    car=conn.execute("SELECT * FROM tesserati WHERE lower(cognome)='caruso' AND lower(nome)='vincenza' LIMIT 1").fetchone()
    ctr=truth(conn,car) if car else {}
    bad=[]
    for a in conn.execute("SELECT * FROM tesserati ORDER BY id").fetchall():
        tr=truth(conn,a)
        docs=conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1",(int(a['id']),)).fetchall()
        hm=any(canonical_type(d)=='certificato_medico' and resolve_file(d['filename']) for d in docs)
        if hm and (not tr.get('med_present') or tr.get('med_state')=='Manca'):bad.append(int(a['id']))
    integ=str(conn.execute("PRAGMA integrity_check").fetchone()[0]);fk=len(conn.execute("PRAGMA foreign_key_check").fetchall())
finally:conn.close()
up=c.get("/mobile/atleta/21/documenti/carica")
uh=up.get_data(as_text=True)
checks={
  "upload_200":up.status_code==200,
  "contrast":"bodymind-r146-contrast" in uh and "file-selector-button" in uh,
  "global_med_truth":not bad,
  "db":integ.lower()=="ok" and fk==0,
}
print("[r146-selftest] "+repr(checks)+" caruso_truth="+repr(ctr)+" bad="+repr(bad),flush=True)
if not all(checks.values()):raise RuntimeError("R146 QA failed "+repr(checks))
'''
proc=subprocess.run([sys.executable,'-c',qa],capture_output=True,text=True,timeout=120)
print((proc.stdout or '').strip(),flush=True)
if proc.returncode!=0:
    raise RuntimeError('R146 child QA failed '+((proc.stderr or '')+(proc.stdout or ''))[-6000:])
print('[r146-selftest-main] PASS upload->association->truth convergence + mobile control contrast',flush=True)
