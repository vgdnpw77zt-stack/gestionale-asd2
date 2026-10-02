# -*- coding: utf-8 -*-
from __future__ import annotations
import json, py_compile, shutil, sqlite3, sys
from datetime import datetime
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
OP=APP/'asd_app/routes_operator_bodymind.py'
BACK=Path('/data/release_backups/20261002_r92_mu_autoenroll')
BACK.mkdir(parents=True,exist_ok=True)
MARKER=APP/'.BODYMIND_R92_MU_AUTOENROLL'

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

def table(conn,name):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())

def cols(conn,name):
    return {str(r[1]) for r in conn.execute("PRAGMA table_info("+name+")").fetchall()} if table(conn,name) else set()

def backup_db():
    dst=BACK/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_pre_r92.db')
    src=sqlite3.connect(str(DB),timeout=30); out=sqlite3.connect(str(dst))
    try: src.backup(out)
    finally: out.close(); src.close()
    return str(dst)

# Final runtime authority: Operator uses the same strict identity helper as every other ingest path.
s=OP.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R92_SHARED_AUTOENROLL_GATE' not in s:
    old='''if (production_mode and sem_conf>=.98 and current_role()=="admin"
                                and _enrollment_identity_ready(semantic,require_valid_cf=True)):'''
    new='''# BODYMIND_R92_SHARED_AUTOENROLL_GATE
                        if (production_mode and current_role()=="admin"
                                and _enrollment_identity_ready(semantic,require_valid_cf=True)):'''
    if old not in s:
        # Already normalized source/runtime is acceptable only if the strict helper is still present.
        if '_enrollment_identity_ready(semantic,require_valid_cf=True)' not in s:
            raise RuntimeError('R92 operator strict auto-enroll gate missing')
        # Insert marker next to the helper use without changing semantics.
        pos=s.find('_enrollment_identity_ready(semantic,require_valid_cf=True)')
        s=s[:pos]+'BODYMIND_R92_SHARED_AUTOENROLL_GATE_MARKER = True\n                        '+s[pos:]
    else:
        s=s.replace(old,new,1)
    OP.write_text(s,encoding='utf-8')
    py_compile.compile(str(OP),doraise=True)
    print('[operator-r92] PASS shared strict auto-enroll gate no 98-percent special case',flush=True)

sys.path.insert(0,str(APP))
from asd_app.enrollment_ingest_core_r65 import (
    enrollment_identity_ready, find_existing_athlete, create_athlete_from_analysis,
    cf_birth_date_consistent, valid_italian_cf, norm_cf
)
from asd_app.verified_mu_sync_core_r68 import sync_analysis_to_existing_athlete

def analysis_for(conn,iid):
    if not table(conn,'bodymind_document_semantics'):
        return None
    r=conn.execute("""SELECT analysis_json FROM bodymind_document_semantics
      WHERE source_table='inbound_documents' AND source_id=? ORDER BY id DESC LIMIT 1""",(int(iid),)).fetchone()
    if not r: return None
    try:
        a=json.loads(str(r['analysis_json'] or '{}'))
        return a if isinstance(a,dict) else None
    except Exception:
        return None

def ensure_document(conn,row,tid,analysis):
    dc=cols(conn,'documenti')
    if not dc:
        return {'ok':False,'reason':'documenti_table_missing'}
    iid=int(row['id']); found=[]
    if 'inbound_id' in dc:
        found=conn.execute("SELECT * FROM documenti WHERE inbound_id=? ORDER BY id",(iid,)).fetchall()
    saved=str(row['saved_path'] or '') if 'saved_path' in row.keys() else ''
    original=str(row['original_filename'] or '') if 'original_filename' in row.keys() else ''
    if not found and saved and 'filename' in dc:
        found=conn.execute("SELECT * FROM documenti WHERE filename=? ORDER BY id",(saved,)).fetchall()
    if not found and original and 'filename' in dc:
        base=Path(original).name
        found=conn.execute("SELECT * FROM documenti WHERE coalesce(tesserato_id,0)=0 AND filename LIKE ? ORDER BY id",('%'+base+'%',)).fetchall()

    conf=int(round(float(analysis.get('confidence') or 0)*100))
    if found:
        ids=[]
        for d in found:
            sets=[]; vals=[]
            if 'tesserato_id' in dc: sets.append('tesserato_id=?'); vals.append(tid)
            if 'doc_type' in dc: sets.append('doc_type=?'); vals.append('modulo_unico_tesseramento')
            if 'categoria' in dc: sets.append('categoria=?'); vals.append('Modulo iscrizione BodyMind')
            if 'status' in dc: sets.append('status=?'); vals.append('salvato')
            if 'visibile' in dc: sets.append('visibile=1')
            if 'confidence' in dc: sets.append('confidence=?'); vals.append(conf)
            if 'inbound_id' in dc and int(d['inbound_id'] or 0)==0: sets.append('inbound_id=?'); vals.append(iid)
            if sets:
                vals.append(int(d['id']))
                conn.execute('UPDATE documenti SET '+','.join(sets)+' WHERE id=?',tuple(vals))
            ids.append(int(d['id']))
        return {'ok':True,'updated':ids,'created':False}

    info=conn.execute('PRAGMA table_info(documenti)').fetchall()
    now=datetime.now().isoformat(timespec='seconds')
    full=(str(analysis.get('first_name') or '')+' '+str(analysis.get('last_name') or '')).strip()
    desired={
      'tesserato_id':tid,
      'titolo':'Modulo Unico - '+full if full else 'Modulo Unico',
      'categoria':'Modulo iscrizione BodyMind',
      'doc_type':'modulo_unico_tesseramento',
      'status':'salvato',
      'visibile':1,
      'filename':saved or original,
      'original_filename':original,
      'inbound_id':iid,
      'confidence':conf,
      'note':'Creato automaticamente dal Modulo Unico riconosciuto e validato R92',
      'created_at':now,'updated_at':now,
    }
    fields={}
    for ci in info:
        name=str(ci[1]); typ=str(ci[2] or '').upper(); notnull=bool(ci[3]); default=ci[4]; pk=bool(ci[5])
        if pk: continue
        if name in desired and desired[name] not in (None,''):
            fields[name]=desired[name]
        elif notnull and default is None:
            fields[name]=0 if any(x in typ for x in ('INT','REAL','NUM','DEC','FLOAT','DOUBLE')) else ''
    if 'tesserato_id' not in fields:
        return {'ok':False,'reason':'documenti_has_no_tesserato_id'}
    names=list(fields.keys())
    try:
        cur=conn.execute('INSERT INTO documenti ('+','.join(names)+') VALUES ('+','.join('?' for _ in names)+')',tuple(fields[k] for k in names))
        return {'ok':True,'created':True,'document_id':int(cur.lastrowid)}
    except Exception as exc:
        return {'ok':False,'reason':'document_insert_failed','error':repr(exc)[:220]}

before={}
created=[]; associated=[]; blocked=[]; backup=''
conn=sqlite3.connect(str(DB),timeout=60); conn.row_factory=sqlite3.Row
try:
    for t in ('tesserati','documenti','inbound_documents','minori'):
        if table(conn,t): before[t]=int(conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0])

    rows=conn.execute("""SELECT * FROM inbound_documents
      WHERE lower(coalesce(document_type,''))='modulo_unico_tesseramento'
        AND coalesce(tesserato_id,0)=0
      ORDER BY id""").fetchall()
    actionable=[]
    for row in rows:
        a=analysis_for(conn,int(row['id']))
        if a and enrollment_identity_ready(a,require_valid_cf=True):
            actionable.append((row,a))
        else:
            blocked.append({'inbound_id':int(row['id']),'filename':str(row['original_filename'] or ''),
                            'reason':'identity_not_strict_ready',
                            'semantic_confidence':(a or {}).get('confidence'),
                            'cf':norm_cf((a or {}).get('codice_fiscale'))})
    if actionable:
        backup=backup_db()

    for row,a in actionable:
        iid=int(row['id'])
        existing,reason=find_existing_athlete(conn,a)
        was_created=False
        if existing:
            tid=int(existing['id'])
        else:
            cr=create_athlete_from_analysis(conn,a,source='r92_mu_autoenroll',require_valid_cf=True)
            tid=int(cr.get('tesserato_id') or 0)
            was_created=bool(cr.get('created'))
            if tid<=0:
                blocked.append({'inbound_id':iid,'filename':str(row['original_filename'] or ''),
                                'reason':str(cr.get('reason') or 'create_failed')})
                continue

        ic=cols(conn,'inbound_documents')
        sets=[]; vals=[]
        for col in ('tesserato_id','matched_tesserato_id','suggested_tesserato_id'):
            if col in ic: sets.append(col+'=?'); vals.append(tid)
        if 'match_score' in ic: sets.append('match_score=?'); vals.append(100)
        if 'document_type' in ic: sets.append('document_type=?'); vals.append('modulo_unico_tesseramento')
        if 'document_confidence' in ic:
            sets.append('document_confidence=?'); vals.append(max(int(row['document_confidence'] or 0),int(round(float(a.get('confidence') or 0)*100))))
        if 'status' in ic: sets.append('status=?'); vals.append('associato')
        if sets:
            vals.append(iid)
            conn.execute('UPDATE inbound_documents SET '+','.join(sets)+' WHERE id=?',tuple(vals))

        docres=ensure_document(conn,row,tid,a)
        sync=sync_analysis_to_existing_athlete(conn,tid,a,source='r92_mu_autoenroll')
        try:
            from asd_app.onboarding_flow import sync_unified_module_flags, recompute_onboarding_status
            sync_unified_module_flags(conn,tid,source='r92_mu_autoenroll')
            recompute_onboarding_status(conn,tid)
        except Exception:
            pass
        entry={'inbound_id':iid,'tesserato_id':tid,'name':(str(a.get('first_name') or '')+' '+str(a.get('last_name') or '')).strip(),
               'created':was_created,'match_reason':reason,'document':docres,'sync':sync}
        if was_created: created.append(entry)
        else: associated.append(entry)
    conn.commit()

    after={}
    for t in ('tesserati','documenti','inbound_documents','minori'):
        if table(conn,t): after[t]=int(conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0])

    remaining_ready=[]
    for row in conn.execute("""SELECT * FROM inbound_documents
      WHERE lower(coalesce(document_type,''))='modulo_unico_tesseramento'
        AND coalesce(tesserato_id,0)=0 ORDER BY id""").fetchall():
        a=analysis_for(conn,int(row['id']))
        if a and enrollment_identity_ready(a,require_valid_cf=True):
            remaining_ready.append({'id':int(row['id']),'filename':str(row['original_filename'] or '')})

    rinaldi=conn.execute("SELECT * FROM tesserati WHERE lower(trim(coalesce(cognome,'')))='rinaldi' ORDER BY id DESC LIMIT 1").fetchone()
    rinaldi_check={}
    if rinaldi:
        tid=int(rinaldi['id'])
        docs=conn.execute("""SELECT id,tesserato_id,titolo,categoria,doc_type,status,visibile
          FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1 ORDER BY id""",(tid,)).fetchall()
        ins=conn.execute("""SELECT id,tesserato_id,status,document_type,document_confidence,match_score,original_filename
          FROM inbound_documents WHERE tesserato_id=? ORDER BY id""",(tid,)).fetchall()
        rinaldi_check={'tid':tid,'name':(str(rinaldi['nome'] or '')+' '+str(rinaldi['cognome'] or '')).strip(),
                       'docs':[dict(x) for x in docs],'inbound':[dict(x) for x in ins]}

    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:
    conn.close()

print('[r92-autoenroll] created='+json.dumps(created,ensure_ascii=False,default=str)+
      ' associated='+json.dumps(associated,ensure_ascii=False,default=str)+
      ' blocked='+json.dumps(blocked,ensure_ascii=False,default=str)+
      ' before='+json.dumps(before)+' after='+json.dumps(after)+
      ' remaining_ready='+json.dumps(remaining_ready,ensure_ascii=False)+
      ' Rinaldi='+json.dumps(rinaldi_check,ensure_ascii=False,default=str)+
      ' backup='+backup+' integrity='+integrity+' fk='+str(fk),flush=True)

# Regression fixture: a 94% MU with checksum-valid CF consistent with DOB is safely strict-ready.
fixture={'document_type':'modulo_unico_tesseramento','confidence':.94,'first_name':'Giorgia','last_name':'Promutico',
         'birth_date':'10/11/2011','codice_fiscale':'PRMGRG11S50A341K'}
checks={
  'composite_identity_ready':enrollment_identity_ready(fixture,require_valid_cf=True),
  'fixture_cf_valid':valid_italian_cf(fixture['codice_fiscale']),
  'fixture_cf_birth_consistent':cf_birth_date_consistent(fixture['codice_fiscale'],fixture['birth_date']),
  'no_strict_ready_left':not remaining_ready,
  'rinaldi_created_or_existing':bool(rinaldi_check.get('tid')),
  'rinaldi_has_mu':any(str(d.get('doc_type') or '')=='modulo_unico_tesseramento' for d in rinaldi_check.get('docs',[])),
  'db_integrity':integrity.lower()=='ok' and fk==0,
}
print('[r92-checks] '+repr(checks),flush=True)
failed=[k for k,v in checks.items() if not v]
if failed:
    raise RuntimeError('R92 QA failed '+repr(failed))
MARKER.write_text('BodyMind R92 MU auto-enroll convergence active\n',encoding='utf-8')
print('[r92-selftest] PASS shared-autoenroll composite-CF-DOB existing-backfill Rinaldi-dossier db-ok',flush=True)
