# -*- coding: utf-8 -*-
from __future__ import annotations
import json, sqlite3
from datetime import datetime
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
BACK=Path('/data/release_backups/20261002_r95_residenza')
BACK.mkdir(parents=True,exist_ok=True)
MARKER=APP/'.BODYMIND_R95_RESIDENZA_FROM_MU'

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

def table(conn,name):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())

def cols(conn,name):
    return {str(r[1]) for r in conn.execute("PRAGMA table_info("+name+")").fetchall()} if table(conn,name) else set()

def backup_db():
    dst=BACK/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_pre_r95.db')
    src=sqlite3.connect(str(DB),timeout=30); out=sqlite3.connect(str(dst))
    try: src.backup(out)
    finally: out.close(); src.close()
    return str(dst)

def read_sem(conn,source_table,source_id):
    if not table(conn,'bodymind_document_semantics'): return {}
    r=conn.execute("""SELECT analysis_json FROM bodymind_document_semantics
      WHERE source_table=? AND source_id=? ORDER BY id DESC LIMIT 1""",(source_table,int(source_id))).fetchone()
    if not r:return {}
    try:
        a=json.loads(str(r['analysis_json'] or '{}'))
        return a if isinstance(a,dict) else {}
    except Exception:return {}

def residence(a):
    city=str((a or {}).get('city') or '').strip()
    prov=str((a or {}).get('province') or '').strip().upper()
    cap=str((a or {}).get('postal_code') or '').strip()
    if not city and not prov and not cap:return ''
    loc=' '.join(x for x in (cap,city) if x).strip()
    return (loc+' ('+prov+')').strip() if prov and loc else (prov or loc)

changed=[]; backup=''
conn=sqlite3.connect(str(DB),timeout=45); conn.row_factory=sqlite3.Row
try:
    tc=cols(conn,'tesserati')
    if 'residenza' not in tc:
        raise RuntimeError('R95 residenza column missing')
    rows=conn.execute("SELECT * FROM tesserati WHERE trim(coalesce(residenza,''))='' ORDER BY id").fetchall()
    candidates=[]
    for a in rows:
        tid=int(a['id']); sem={}
        if table(conn,'inbound_documents'):
            irs=conn.execute("""SELECT id FROM inbound_documents
              WHERE tesserato_id=? AND lower(coalesce(document_type,''))='modulo_unico_tesseramento'
              ORDER BY match_score DESC,document_confidence DESC,id DESC""",(tid,)).fetchall()
            for ir in irs:
                sem=read_sem(conn,'inbound_documents',int(ir['id']))
                if sem: break
        if not sem and table(conn,'documenti'):
            drs=conn.execute("""SELECT id FROM documenti
              WHERE tesserato_id=? AND coalesce(visibile,1)=1
                AND lower(coalesce(doc_type,''))='modulo_unico_tesseramento'
              ORDER BY id DESC""",(tid,)).fetchall()
            for dr in drs:
                sem=read_sem(conn,'documenti',int(dr['id']))
                if sem: break
        value=residence(sem)
        if value:
            candidates.append((tid,value))
    if candidates:
        backup=backup_db()
        now=datetime.now().isoformat(timespec='seconds')
        for tid,value in candidates:
            if 'updated_at' in tc:
                conn.execute("UPDATE tesserati SET residenza=?,updated_at=? WHERE id=? AND trim(coalesce(residenza,''))=''",(value,now,tid))
            else:
                conn.execute("UPDATE tesserati SET residenza=? WHERE id=? AND trim(coalesce(residenza,''))=''",(value,tid))
            if conn.total_changes:
                changed.append({'tid':tid,'residenza':value})
        conn.commit()

    audit=[]
    for surname in ('promutico','rinaldi','sartori'):
        r=conn.execute("SELECT id,nome,cognome,residenza,indirizzo,genitore,telefono_genitore,email_genitore,minorenne,onboarding_status,onboarding_blocked_reason FROM tesserati WHERE lower(trim(cognome))=? ORDER BY id DESC LIMIT 1",(surname,)).fetchone()
        if r:audit.append(dict(r))
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:
    conn.close()

print('[r95-residenza] changed='+json.dumps(changed,ensure_ascii=False)+' audit='+json.dumps(audit,ensure_ascii=False,default=str)+' backup='+backup+' integrity='+integrity+' fk='+str(fk),flush=True)
checks={
 'promutico_residenza':any(str(x.get('cognome') or '').lower()=='promutico' and str(x.get('residenza') or '').strip() for x in audit),
 'rinaldi_residenza':any(str(x.get('cognome') or '').lower()=='rinaldi' and str(x.get('residenza') or '').strip() for x in audit),
 'sartori_residenza':any(str(x.get('cognome') or '').lower()=='sartori' and str(x.get('residenza') or '').strip() for x in audit),
 'db_ok':integrity.lower()=='ok' and fk==0,
}
print('[r95-checks] '+repr(checks),flush=True)
failed=[k for k,v in checks.items() if not v]
if failed: raise RuntimeError('R95 QA failed '+repr(failed))
MARKER.write_text('BodyMind R95 residenza mapping active\n',encoding='utf-8')
print('[r95-selftest] PASS MU-residenza future-mapping empty-only-backfill db-ok',flush=True)
