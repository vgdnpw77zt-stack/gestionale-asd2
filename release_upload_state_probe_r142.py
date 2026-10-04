from __future__ import annotations
import json, sqlite3
from pathlib import Path
DB=Path('/data/tenants/default/asd.db')
c=sqlite3.connect(str(DB),timeout=30); c.row_factory=sqlite3.Row
try:
    tables=[str(x[0]) for x in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
    print('[r142-tables] '+json.dumps([t for t in tables if any(k in t.lower() for k in ('inbound','operator','upload','job','document','semantic','audit','event'))],ensure_ascii=False),flush=True)

    ath=[dict(x) for x in c.execute("SELECT id,nome,cognome,certificato_scadenza,iscrizione_firmata,documenti_onboarding_ok FROM tesserati WHERE lower(cognome) LIKE '%francia%' OR lower(nome) LIKE '%giulia%' ORDER BY id").fetchall()]
    print('[r142-athletes] '+json.dumps(ath,ensure_ascii=False,default=str),flush=True)
    tids=[int(a['id']) for a in ath]

    if 'documenti' in tables:
        cols=[x[1] for x in c.execute("PRAGMA table_info(documenti)").fetchall()]
        print('[r142-documenti-cols] '+json.dumps(cols),flush=True)
        if tids:
            qs=','.join('?' for _ in tids)
            rows=[dict(x) for x in c.execute(f"SELECT * FROM documenti WHERE tesserato_id IN ({qs}) ORDER BY id DESC LIMIT 50",tids).fetchall()]
            print('[r142-documenti-francia] '+json.dumps(rows,ensure_ascii=False,default=str),flush=True)
        recent=[dict(x) for x in c.execute("SELECT * FROM documenti ORDER BY id DESC LIMIT 35").fetchall()]
        print('[r142-documenti-recent] '+json.dumps(recent,ensure_ascii=False,default=str),flush=True)

    if 'inbound_documents' in tables:
        cols=[x[1] for x in c.execute("PRAGMA table_info(inbound_documents)").fetchall()]
        print('[r142-inbound-cols] '+json.dumps(cols),flush=True)
        if tids and 'tesserato_id' in cols:
            qs=','.join('?' for _ in tids)
            rows=[dict(x) for x in c.execute(f"SELECT * FROM inbound_documents WHERE coalesce(tesserato_id,0) IN ({qs}) ORDER BY id DESC LIMIT 50",tids).fetchall()]
            print('[r142-inbound-francia] '+json.dumps(rows,ensure_ascii=False,default=str),flush=True)
        recent=[dict(x) for x in c.execute("SELECT * FROM inbound_documents ORDER BY id DESC LIMIT 40").fetchall()]
        print('[r142-inbound-recent] '+json.dumps(recent,ensure_ascii=False,default=str),flush=True)

    if 'bodymind_document_semantics' in tables:
        cols=[x[1] for x in c.execute("PRAGMA table_info(bodymind_document_semantics)").fetchall()]
        print('[r142-sem-cols] '+json.dumps(cols),flush=True)
        recent=[dict(x) for x in c.execute("SELECT * FROM bodymind_document_semantics ORDER BY id DESC LIMIT 50").fetchall()]
        print('[r142-sem-recent] '+json.dumps(recent,ensure_ascii=False,default=str),flush=True)

    for t in tables:
        if any(k in t.lower() for k in ('operator','upload_job','jobs','task')):
            try:
                cols=[x[1] for x in c.execute("PRAGMA table_info("+t+")").fetchall()]
                rows=[dict(x) for x in c.execute("SELECT * FROM "+t+" ORDER BY rowid DESC LIMIT 25").fetchall()]
                print('[r142-table-'+t+'] '+json.dumps({'cols':cols,'rows':rows},ensure_ascii=False,default=str),flush=True)
            except Exception as exc:
                print('[r142-table-error] '+t+' '+repr(exc),flush=True)
    print('[r142-db] integrity='+str(c.execute('PRAGMA integrity_check').fetchone()[0])+' fk='+str(len(c.execute('PRAGMA foreign_key_check').fetchall())),flush=True)
finally:
    c.close()


# Compact targeted current-state summary for latest operator/autopilot activity.
c=sqlite3.connect(str(DB),timeout=30); c.row_factory=sqlite3.Row
try:
    out={}
    if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documenti'").fetchone():
        out['docs_168_233']=[dict(x) for x in c.execute("SELECT * FROM documenti WHERE id IN (168,233) ORDER BY id").fetchall()]
    if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inbound_documents'").fetchone():
        out['inbound_143']=[dict(x) for x in c.execute("SELECT * FROM inbound_documents WHERE id=143").fetchall()]
        out['inbound_recent']=[dict(x) for x in c.execute("""SELECT id,tesserato_id,original_filename,saved_path,document_type,document_confidence,match_score,status,created_at,updated_at
          FROM inbound_documents WHERE created_at>='2026-10-04 18:00:00' ORDER BY id DESC LIMIT 50""").fetchall()]
    if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bodymind_operator_upload_jobs'").fetchone():
        jobs=[]
        for r in c.execute("SELECT * FROM bodymind_operator_upload_jobs ORDER BY created_at DESC LIMIT 15").fetchall():
            d=dict(r)
            try:
                rr=json.loads(d.get('result_json') or '{}')
                d['result_summary']={'status':d.get('status'),'text':rr.get('text'),'summary':rr.get('summary'),'results':rr.get('results')}
            except Exception: pass
            for k in list(d):
                if k not in ('id','conversation_id','status','created_at','updated_at','document_type_hint','result_summary','error'):
                    d.pop(k,None)
            jobs.append(d)
        out['recent_jobs']=jobs
    if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bodymind_document_semantics'").fetchone():
        out['sem_143_168_233']=[dict(x) for x in c.execute("""SELECT * FROM bodymind_document_semantics
          WHERE (source_table='inbound_documents' AND source_id=143)
             OR (source_table='documenti' AND source_id IN (168,233))
          ORDER BY id DESC""").fetchall()]
    print('[r142-targeted-current] '+json.dumps(out,ensure_ascii=False,default=str),flush=True)
finally:
    c.close()


c=sqlite3.connect(str(DB),timeout=30); c.row_factory=sqlite3.Row
try:
    out={}
    if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bodymind_duplicate_records_archive'").fetchone():
        rr=[dict(x) for x in c.execute("SELECT * FROM bodymind_duplicate_records_archive WHERE source_table='inbound_documents' AND source_id IN (143,204) ORDER BY id DESC").fetchall()]
        for x in rr:
            fp=str(x.get('file_path') or '')
            x['file_exists']=Path(fp).is_file() if fp else False
        out['archive']=rr
    jobdir=Path('/data/operator_upload_jobs/6e50bff771b64fac86f2db1654e0dcab')
    out['job_files']=[{'path':str(p),'exists':p.is_file(),'size':p.stat().st_size if p.is_file() else 0} for p in jobdir.glob('*')] if jobdir.exists() else []
    print('[r142-duplicate-204] '+json.dumps(out,ensure_ascii=False,default=str),flush=True)
finally:c.close()


c=sqlite3.connect(str(DB),timeout=30); c.row_factory=sqlite3.Row
try:
    out={}
    out['docs_by_name']=[dict(x) for x in c.execute("""SELECT * FROM documenti
      WHERE lower(coalesce(filename,'')) LIKE '%di_francia%' OR lower(coalesce(original_filename,'')) LIKE '%di francia%' OR lower(coalesce(titolo,'')) LIKE '%di francia%'
      ORDER BY id""").fetchall()]
    for tn in ('document_deletion_tombstones','audit_log','system_logs','operational_events'):
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(tn,)).fetchone():
            cols=[str(x[1]) for x in c.execute("PRAGMA table_info("+tn+")").fetchall()]
            rows=[]
            try:
                if tn=='document_deletion_tombstones':
                    rows=[dict(x) for x in c.execute("SELECT * FROM "+tn+" WHERE document_id IN (233,148) OR lower(coalesce(payload_json,'')) LIKE '%di francia%' ORDER BY rowid DESC LIMIT 30").fetchall()]
                else:
                    expr=" || ' ' || ".join(["coalesce(cast("+k+" as text),'')" for k in cols])
                    rows=[dict(x) for x in c.execute("SELECT * FROM "+tn+" WHERE lower("+expr+") LIKE '%di francia%' OR "+expr+" LIKE '%233%' ORDER BY rowid DESC LIMIT 30").fetchall()]
            except Exception as exc:
                rows=[{'error':repr(exc),'cols':cols}]
            out[tn]=rows
    print('[r142-giulia-certificate-forensics] '+json.dumps(out,ensure_ascii=False,default=str),flush=True)
finally:c.close()
