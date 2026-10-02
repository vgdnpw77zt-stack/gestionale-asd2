# -*- coding: utf-8 -*-
from __future__ import annotations
import json, sqlite3
from datetime import datetime
from pathlib import Path

DB=Path('/data/tenants/default/asd.db')
BACK=Path('/data/release_backups/20261002_r108_mu_canonical')
BACK.mkdir(parents=True,exist_ok=True)

def table(c,n):
    return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(n,)).fetchone())
def cols(c,n):
    return {str(r[1]) for r in c.execute("PRAGMA table_info("+n+")").fetchall()} if table(c,n) else set()
def is_mu(r):
    ks=set(r.keys())
    hay=' '.join(str(r[k] or '').lower() for k in ('doc_type','categoria','titolo','original_filename','filename') if k in ks)
    return ('modulo_unico_tesseramento' in hay or 'modulo unico' in hay or 'modulo_unico' in hay
            or 'modulo iscrizione' in hay or 'domanda iscrizione' in hay or 'iscrizione manleva' in hay)
def sem(c,did):
    if not table(c,'bodymind_document_semantics'): return {}
    r=c.execute("""SELECT document_type,confidence,analysis_json FROM bodymind_document_semantics
      WHERE source_table='documenti' AND source_id=? ORDER BY id DESC LIMIT 1""",(did,)).fetchone()
    if not r:return {}
    a={}
    try:a=json.loads(str(r['analysis_json'] or '{}'))
    except Exception:pass
    return {'type':str(r['document_type'] or a.get('document_type') or ''),'confidence':float(r['confidence'] or a.get('confidence') or 0)}
def inbound_mu(c,r):
    if 'inbound_id' not in r.keys() or int(r['inbound_id'] or 0)<=0 or not table(c,'inbound_documents'): return False
    q=c.execute("SELECT document_type FROM inbound_documents WHERE id=?",(int(r['inbound_id']),)).fetchone()
    return bool(q and str(q[0] or '').lower()=='modulo_unico_tesseramento')
def backup_db():
    dst=BACK/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_pre_r108.db')
    s=sqlite3.connect(str(DB),timeout=30); d=sqlite3.connect(str(dst))
    try:s.backup(d)
    finally:d.close();s.close()
    return str(dst)

c=sqlite3.connect(str(DB),timeout=60); c.row_factory=sqlite3.Row
changed=[]; archived=[]; backup=''
try:
    visible=c.execute("SELECT * FROM documenti WHERE coalesce(visibile,1)=1 ORDER BY tesserato_id,id").fetchall()
    groups={}
    for r in visible:
        if is_mu(r):
            groups.setdefault(int(r['tesserato_id'] or 0),[]).append(r)
    actionable=[]
    for tid,rows in groups.items():
        if tid<=0: continue
        scored=[]
        for r in rows:
            sm=sem(c,int(r['id']))
            score=(100 if sm.get('type')=='modulo_unico_tesseramento' else 0)+(50 if inbound_mu(c,r) else 0)+int(round(float(sm.get('confidence') or 0)*10))+int(r['id'])/100000.0
            scored.append((score,r,sm))
        scored.sort(key=lambda x:x[0],reverse=True)
        winner=scored[0]
        losers=scored[1:]
        wr=winner[1]
        dtype=str(wr['doc_type'] or '').lower() if 'doc_type' in wr.keys() else ''
        cat=str(wr['categoria'] or '').lower() if 'categoria' in wr.keys() else ''
        if dtype!='modulo_unico_tesseramento' or 'modulo iscrizione' not in cat or losers:
            actionable.append((tid,winner,losers))
    if actionable:
        backup=backup_db()
    dc=cols(c,'documenti')
    if table(c,'bodymind_duplicate_records_archive'):
        ac=cols(c,'bodymind_duplicate_records_archive')
    else:
        c.execute("""CREATE TABLE IF NOT EXISTS bodymind_duplicate_records_archive(
          id INTEGER PRIMARY KEY AUTOINCREMENT,source_table TEXT NOT NULL,source_id INTEGER NOT NULL,tesserato_id INTEGER,
          status TEXT,reason TEXT NOT NULL,payload_json TEXT NOT NULL,semantics_json TEXT,file_path TEXT,archived_at TEXT NOT NULL,
          UNIQUE(source_table,source_id))""")
        ac=cols(c,'bodymind_duplicate_records_archive')
    for tid,(score,wr,wsm),losers in actionable:
        wid=int(wr['id'])
        sets=[]; vals=[]
        if 'doc_type' in dc: sets.append('doc_type=?'); vals.append('modulo_unico_tesseramento')
        if 'categoria' in dc: sets.append('categoria=?'); vals.append('Modulo iscrizione BodyMind')
        if 'visibile' in dc: sets.append('visibile=1')
        if 'status' in dc and str(wr['status'] or '').lower() in ('','da_verificare','needs_review','associato_tipo_da_verificare'):
            sets.append('status=?'); vals.append('salvato')
        if sets:
            vals.append(wid); c.execute("UPDATE documenti SET "+",".join(sets)+" WHERE id=?",tuple(vals))
            changed.append({'tid':tid,'document_id':wid})
        for _,lr,lsm in losers:
            lid=int(lr['id'])
            payload=json.dumps(dict(lr),ensure_ascii=False,default=str)
            semjson=json.dumps(lsm,ensure_ascii=False,default=str)
            fpath=str(lr['filename'] or '') if 'filename' in lr.keys() else ''
            c.execute("""INSERT OR IGNORE INTO bodymind_duplicate_records_archive
              (source_table,source_id,tesserato_id,status,reason,payload_json,semantics_json,file_path,archived_at)
              VALUES(?,?,?,?,?,?,?,?,?)""",
              ('documenti',lid,tid,str(lr['status'] or ''),'R108 non-canonical visible MU',payload,semjson,fpath,datetime.now().isoformat(timespec='seconds')))
            sets=[]; vals=[]
            if 'visibile' in dc: sets.append('visibile=0')
            if 'status' in dc: sets.append('status=?'); vals.append('mu_duplicate_archived_r108')
            if sets:
                vals.append(lid); c.execute("UPDATE documenti SET "+",".join(sets)+" WHERE id=?",tuple(vals))
            archived.append({'tid':tid,'document_id':lid,'canonical_document_id':wid})
    c.commit()
    # Final invariants use the same lexical definition as R80.
    rows=c.execute("SELECT * FROM documenti WHERE coalesce(visibile,1)=1 ORDER BY tesserato_id,id").fetchall()
    groups={}
    wrong=[]
    for r in rows:
        if not is_mu(r):continue
        tid=int(r['tesserato_id'] or 0); groups.setdefault(tid,[]).append(int(r['id']))
        dtype=str(r['doc_type'] or '').strip().lower() if 'doc_type' in r.keys() else ''
        cat=str(r['categoria'] or '').strip().lower() if 'categoria' in r.keys() else ''
        if dtype!='modulo_unico_tesseramento' or 'modulo iscrizione' not in cat:
            wrong.append({'id':int(r['id']),'tid':tid,'doc_type':dtype,'categoria':cat})
    dup=[{'tid':k,'ids':v} for k,v in groups.items() if k>0 and len(v)>1]
    integrity=str(c.execute('PRAGMA integrity_check').fetchone()[0]); fk=len(c.execute('PRAGMA foreign_key_check').fetchall())
finally:c.close()

print('[r108-mu] changed='+json.dumps(changed)+' archived='+json.dumps(archived)+' duplicates='+json.dumps(dup)+' wrong_meta='+json.dumps(wrong)+' backup='+backup+' integrity='+integrity+' fk='+str(fk),flush=True)
if dup or wrong or integrity.lower()!='ok' or fk:
    raise RuntimeError('R108 MU canonicalization failed')
print('[r108-selftest] PASS one-visible-MU-per-athlete canonical-metadata audit-preserved db-ok',flush=True)
