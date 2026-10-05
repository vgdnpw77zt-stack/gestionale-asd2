# -*- coding: utf-8 -*-
from __future__ import annotations
import json, py_compile, re, shutil, sqlite3, subprocess, sys
from datetime import datetime
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
CORE=APP/'asd_app/core.py'
MOD=APP/'asd_app/document_sync_core_r143.py'
BACK=Path('/data/release_backups/20261005_r144_document_association')
BACK.mkdir(parents=True,exist_ok=True)
if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

# Backup before touching business data.
stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
backup=BACK/(stamp+'_pre_r144.db')
src=sqlite3.connect(str(DB),timeout=30); out=sqlite3.connect(str(backup))
try: src.backup(out)
finally: out.close(); src.close()

module=r'''from __future__ import annotations
import hashlib, json, shutil, sqlite3
from datetime import date, datetime
from pathlib import Path

APP=Path('/data/top2_app')
MEDIA=Path('/data/tenants/default/media')

TYPE_META={
 'modulo_unico_tesseramento':('Modulo iscrizione BodyMind','Modulo Unico'),
 'certificato_medico':('Certificato medico','Certificato medico'),
 'liberatoria_immagini':('Liberatoria immagini','Liberatoria immagini'),
 'altro':('Documenti ASD','Documento'),
}

def _cols(conn,table):
    try:return {str(x[1]) for x in conn.execute('PRAGMA table_info('+table+')').fetchall()}
    except Exception:return set()

def _table(conn,table):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone())

def canonical_type(row_or_value):
    if isinstance(row_or_value,str):
        hay=row_or_value.lower()
    else:
        vals=[]
        for k in ('doc_type','document_type','categoria','titolo','document_label','original_filename','filename','saved_path'):
            try:vals.append(str(row_or_value[k] or '').lower())
            except Exception:pass
        hay=' '.join(vals)
    if any(x in hay for x in ('modulo_unico_tesseramento','modulo unico','modulo iscrizione',"modulo d'iscrizione",'domanda iscrizione','domanda di iscrizione')):
        return 'modulo_unico_tesseramento'
    if any(x in hay for x in ('richiesta certificato','richiesta_certificato','ecg','elettrocard','referto')):
        return 'altro'
    if 'certificato_medico' in hay or ('certificat' in hay and 'medic' in hay):
        return 'certificato_medico'
    if 'liberatoria' in hay and ('immagin' in hay or 'foto' in hay):
        return 'liberatoria_immagini'
    return 'altro'

def resolve_file(filename):
    raw=Path(str(filename or '').strip())
    roots=[MEDIA,APP/'user_static',APP/'static',APP,Path('/data/tenants/default'),Path('/data')]
    cands=[raw] if raw.is_absolute() else [r/raw for r in roots]
    for fp in cands:
        try:
            if fp.is_file():return fp.resolve()
        except Exception:pass
    return None

def sha256_file(fp):
    if not fp:return ''
    h=hashlib.sha256()
    with open(fp,'rb') as f:
        for ch in iter(lambda:f.read(1024*1024),b''):h.update(ch)
    return h.hexdigest()

def iso_date(v):
    raw=str(v or '').strip()
    if not raw:return ''
    for fmt in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y','%Y/%m/%d','%d.%m.%Y'):
        try:return datetime.strptime(raw[:10],fmt).date().isoformat()
        except Exception:pass
    return ''

def _semantic(conn,source_table,source_id,sha=''):
    if not _table(conn,'bodymind_document_semantics'):return {}
    row=None
    try:
        row=conn.execute("""SELECT * FROM bodymind_document_semantics
          WHERE source_table=? AND source_id=? ORDER BY confidence DESC,id DESC LIMIT 1""",(source_table,int(source_id))).fetchone()
    except Exception:pass
    if not row and sha:
        try:
            row=conn.execute("""SELECT * FROM bodymind_document_semantics
              WHERE sha256=? ORDER BY confidence DESC,id DESC LIMIT 1""",(sha,)).fetchone()
        except Exception:pass
    if not row:return {}
    try:an=json.loads(row['analysis_json'] or '{}')
    except Exception:an={}
    return {'row':row,'analysis':an,'document_type':str(row['document_type'] or ''),'confidence':float(row['confidence'] or 0)}

def _expiry_from_analysis(an):
    for k in ('expiry_date','valid_until','scadenza'):
        x=iso_date((an or {}).get(k))
        if x:return x
    issue=iso_date((an or {}).get('issue_date'))
    if issue and 'validità annuale' in str((an or {}).get('content_summary') or '').lower():
        try:
            d=datetime.strptime(issue,'%Y-%m-%d').date()
            return d.replace(year=d.year+1).isoformat()
        except Exception:pass
    return ''

def _doc_expiry(conn,doc):
    vals=[]
    try:vals.append(doc['data_scadenza'])
    except Exception:pass
    fp=resolve_file(doc['filename']); sh=sha256_file(fp)
    sm=_semantic(conn,'documenti',int(doc['id']),sh)
    an=sm.get('analysis') or {}
    vals.extend([an.get('expiry_date'),an.get('valid_until'),an.get('scadenza')])
    try:iid=int(doc['inbound_id'] or 0)
    except Exception:iid=0
    if iid:
        sm2=_semantic(conn,'inbound_documents',iid,sh)
        an2=sm2.get('analysis') or {}
        vals.extend([an2.get('expiry_date'),an2.get('valid_until'),an2.get('scadenza')])
        derived=_expiry_from_analysis(an2)
        if derived:vals.append(derived)
    for v in vals:
        x=iso_date(v)
        if x:return x
    derived=_expiry_from_analysis(an)
    return derived

def _ensure_persistent(tid,fp,original=''):
    if not fp:return None
    fp=Path(fp)
    root=(MEDIA/'tesserati'/str(int(tid))).resolve()
    try:
        if root==fp.parent.resolve() or root in fp.resolve().parents:
            return fp.resolve()
    except Exception:pass
    root.mkdir(parents=True,exist_ok=True)
    safe=Path(str(original or fp.name)).name.replace('/','_').replace('\\','_')
    dest=root/(datetime.now().strftime('%Y-%m-%d_%H%M%S')+'_R144_'+safe)
    if not dest.exists():shutil.copy2(fp,dest)
    return dest.resolve()

def _hidden_exact_exists(conn,tid,dtype,sha):
    for d in conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=0",(int(tid),)).fetchall():
        if canonical_type(d)!=dtype:continue
        fp=resolve_file(d['filename'])
        if fp and sha256_file(fp)==sha:return True
    return False

def _visible_exact(conn,tid,dtype,sha):
    for d in conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1",(int(tid),)).fetchall():
        if canonical_type(d)!=dtype:continue
        fp=resolve_file(d['filename'])
        if fp and sha256_file(fp)==sha:return d
    return None

def _tombstoned(conn,canonical_id,path):
    if not _table(conn,'document_deletion_tombstones'):return False
    cc=_cols(conn,'document_deletion_tombstones')
    try:
        clauses=[]; vals=[]
        if 'source_id' in cc and canonical_id:
            clauses.append("source_id=?");vals.append(int(canonical_id))
        if 'path' in cc and path:
            clauses.append("path=?");vals.append(str(path))
        if not clauses:return False
        q="SELECT 1 FROM document_deletion_tombstones WHERE ("+" OR ".join(clauses)+")"
        if 'source_table' in cc:q+=" AND lower(coalesce(source_table,'')) IN ('documenti','document','documents')"
        q+=" LIMIT 1"
        return bool(conn.execute(q,tuple(vals)).fetchone())
    except Exception:return False

def _insert_semantic_from_archive(conn,did,sha,sem_list):
    if not _table(conn,'bodymind_document_semantics') or not sem_list:return
    try:
        best=sorted(sem_list,key=lambda x:float(x.get('confidence') or 0),reverse=True)[0]
    except Exception:return
    sc=_cols(conn,'bodymind_document_semantics')
    vals={
      'source_table':'documenti','source_id':int(did),'sha256':sha,
      'document_type':str(best.get('document_type') or ''),
      'person_name':str(best.get('person_name') or ''),
      'codice_fiscale':str(best.get('codice_fiscale') or ''),
      'semantic_key':str(best.get('semantic_key') or ''),
      'confidence':float(best.get('confidence') or 0),
      'analysis_json':str(best.get('analysis_json') or '{}'),
      'model':str(best.get('model') or ''),
      'analyzed_at':str(best.get('analyzed_at') or datetime.now().isoformat(timespec='seconds'))
    }
    ks=[k for k in vals if k in sc]
    if ks:
        conn.execute("INSERT INTO bodymind_document_semantics("+','.join(ks)+") VALUES("+','.join('?' for _ in ks)+")",[vals[k] for k in ks])

def sync_document(conn,doc_id):
    doc=conn.execute("SELECT * FROM documenti WHERE id=?",(int(doc_id),)).fetchone()
    if not doc:return {'ok':False,'reason':'missing_document'}
    if int(doc['visibile'] or 0)!=1:return {'ok':False,'reason':'not_visible'}
    tid=int(doc['tesserato_id'] or 0)
    if tid<=0:return {'ok':False,'reason':'missing_athlete'}
    fp=resolve_file(doc['filename'])
    if not fp:return {'ok':False,'reason':'missing_file','document_id':int(doc_id),'tid':tid}
    dtype=canonical_type(doc)
    if dtype=='altro':
        sm=_semantic(conn,'documenti',int(doc_id),sha256_file(fp))
        dtype=canonical_type(sm.get('document_type') or '')
    if dtype=='altro':return {'ok':False,'reason':'unsupported_type'}
    persistent=_ensure_persistent(tid,fp,doc['original_filename'] if 'original_filename' in doc.keys() else fp.name)
    dc=_cols(conn,'documenti'); sets=[]; vals=[]
    cat,label=TYPE_META[dtype]
    def add(k,v):
        if k in dc:sets.append(k+'=?');vals.append(v)
    add('filename',str(persistent));add('doc_type',dtype);add('categoria',cat);add('visibile',1)
    expiry=''
    if dtype=='certificato_medico':
        expiry=_doc_expiry(conn,doc)
        if expiry:add('data_scadenza',expiry)
    if sets:
        vals.append(int(doc_id));conn.execute("UPDATE documenti SET "+','.join(sets)+" WHERE id=?",tuple(vals))
    tc=_cols(conn,'tesserati')
    if dtype=='modulo_unico_tesseramento':
        sets=[];vals=[]
        for k in ('iscrizione_firmata','documenti_onboarding_ok'):
            if k in tc:sets.append(k+'=?');vals.append(1)
        if sets:
            vals.append(tid);conn.execute("UPDATE tesserati SET "+','.join(sets)+" WHERE id=?",tuple(vals))
    elif dtype=='certificato_medico' and 'certificato_scadenza' in tc and expiry:
        conn.execute("UPDATE tesserati SET certificato_scadenza=? WHERE id=?",(expiry,tid))
    elif dtype=='liberatoria_immagini' and 'liberatoria_immagini' in tc:
        conn.execute("UPDATE tesserati SET liberatoria_immagini=1 WHERE id=?",(tid,))
    return {'ok':True,'document_id':int(doc_id),'tid':tid,'type':dtype,'expiry':expiry,'sha':sha256_file(persistent)}

def materialize_inbound(conn,inbound_id,allow_old=False):
    if not _table(conn,'inbound_documents') or not _table(conn,'documenti'):return {'ok':False,'reason':'tables_missing'}
    r=conn.execute("SELECT * FROM inbound_documents WHERE id=?",(int(inbound_id),)).fetchone()
    if not r:return {'ok':False,'reason':'inbound_missing'}
    status=str(r['status'] or '').strip().lower()
    if status in ('deleted','archived','archived_orphan'):return {'ok':False,'reason':'inbound_archived'}
    try:conf=float(r['document_confidence'] or 0);match=float(r['match_score'] or 0)
    except Exception:conf=0;match=0
    trusted=status in ('accepted','manual_accepted','verificato','archived_to_tesserato','resolved','associato') and (status!='associato' or (conf>=80 and match>=80))
    if not trusted:return {'ok':False,'reason':'not_trusted','status':status}
    if not allow_old:
        try:
            ts=str(r['updated_at'] or r['created_at'] or '')
            d=datetime.fromisoformat(ts.replace('Z','+00:00')).replace(tzinfo=None)
            if (datetime.now()-d).total_seconds()>21600:return {'ok':False,'reason':'not_recent'}
        except Exception:
            return {'ok':False,'reason':'not_recent'}
    tid=int(r['tesserato_id'] or 0)
    if tid<=0 or not conn.execute("SELECT 1 FROM tesserati WHERE id=?",(tid,)).fetchone():return {'ok':False,'reason':'no_athlete'}
    dtype=canonical_type(r)
    if dtype=='altro':return {'ok':False,'reason':'unsupported_type'}
    linked=conn.execute("SELECT * FROM documenti WHERE inbound_id=? ORDER BY visibile DESC,id DESC",(int(inbound_id),)).fetchall()
    if linked:
        vis=[d for d in linked if int(d['visibile'] or 0)==1]
        if vis:return sync_document(conn,int(vis[0]['id']))
        return {'ok':False,'reason':'linked_document_archived'}
    fp=resolve_file(r['saved_path'] if 'saved_path' in r.keys() else '')
    if not fp:return {'ok':False,'reason':'missing_file'}
    persistent=_ensure_persistent(tid,fp,r['original_filename'] if 'original_filename' in r.keys() else fp.name)
    sh=sha256_file(persistent)
    old=_visible_exact(conn,tid,dtype,sh)
    if old:
        if 'inbound_id' in _cols(conn,'documenti') and not int(old['inbound_id'] or 0):
            conn.execute("UPDATE documenti SET inbound_id=? WHERE id=?",(int(inbound_id),int(old['id'])))
        return sync_document(conn,int(old['id']))
    # Recent trusted re-upload is explicit user intent: hidden history must not
    # block creating a new active canonical row with the same bytes.
    dc=_cols(conn,'documenti');cat,label=TYPE_META[dtype]
    values={'tesserato_id':tid,'titolo':str(r['original_filename'] or label) if 'original_filename' in r.keys() else label,
      'categoria':cat,'filename':str(persistent),'original_filename':str(r['original_filename'] or persistent.name) if 'original_filename' in r.keys() else persistent.name,
      'data_caricamento':datetime.now().strftime('%Y-%m-%d %H:%M:%S'),'data_scadenza':'','note':'R144 materializzato da associazione recente',
      'visibile':1,'tipo_template':'inbound_auto','tenant_id':'default','doc_type':dtype,'confidence':conf,'match_score':match,
      'source':'association_sync_r144','status':'salvato','inbound_id':int(inbound_id)}
    ks=[k for k in values if k in dc]
    conn.execute("INSERT INTO documenti("+','.join(ks)+") VALUES("+','.join('?' for _ in ks)+")",[values[k] for k in ks])
    did=int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    return sync_document(conn,did)

def recover_duplicate_archives(conn):
    out=[]
    if not _table(conn,'bodymind_duplicate_records_archive') or not _table(conn,'documenti'):return out
    rows=conn.execute("""SELECT * FROM bodymind_duplicate_records_archive
      WHERE source_table='inbound_documents' AND lower(reason) LIKE '%duplicate resolved%'
      ORDER BY id DESC LIMIT 300""").fetchall()
    for a in rows:
        # Never resurrect old archive history. Duplicate recovery is only for a
        # just-finished upload whose canonical row disappeared.
        try:
            ats=str(a['archived_at'] or '')
            adt=datetime.fromisoformat(ats.replace('Z','+00:00')).replace(tzinfo=None)
            if (datetime.now()-adt).total_seconds()>21600:
                continue
        except Exception:
            continue
        try:
            payload=json.loads(a['payload_json'] or '{}'); original=payload.get('row') or {}
            sems=json.loads(a['semantics_json'] or '[]')
        except Exception:
            continue
        tid=int(a['tesserato_id'] or original.get('tesserato_id') or 0)
        if tid<=0 or not conn.execute("SELECT 1 FROM tesserati WHERE id=?",(tid,)).fetchone():continue
        dtype=canonical_type(str(original.get('document_type') or ''))
        if dtype=='altro':continue
        canonical_id=int(payload.get('canonical_document_id') or 0)
        if canonical_id:
            d=conn.execute("SELECT * FROM documenti WHERE id=?",(canonical_id,)).fetchone()
            if d:
                if int(d['visibile'] or 0)==1:
                    res=sync_document(conn,canonical_id);res['archive_id']=int(a['id']);out.append(res)
                continue
        path=str(a['file_path'] or original.get('saved_path') or '')
        fp=resolve_file(path)
        if not fp:continue
        if _tombstoned(conn,canonical_id,path):continue
        sh=sha256_file(fp)
        vis=_visible_exact(conn,tid,dtype,sh)
        if vis:
            res=sync_document(conn,int(vis['id']));res['archive_id']=int(a['id']);out.append(res);continue
        if _hidden_exact_exists(conn,tid,dtype,sh):
            continue
        persistent=_ensure_persistent(tid,fp,original.get('original_filename') or fp.name)
        analysis={}
        if sems:
            try:
                best=sorted(sems,key=lambda x:float(x.get('confidence') or 0),reverse=True)[0]
                analysis=json.loads(best.get('analysis_json') or '{}')
            except Exception:analysis={}
        expiry=_expiry_from_analysis(analysis) if dtype=='certificato_medico' else ''
        dc=_cols(conn,'documenti');cat,label=TYPE_META[dtype]
        values={'tesserato_id':tid,'titolo':str(original.get('original_filename') or label),'categoria':cat,
          'filename':str(persistent),'original_filename':str(original.get('original_filename') or persistent.name),
          'data_caricamento':datetime.now().strftime('%Y-%m-%d %H:%M:%S'),'data_scadenza':expiry,
          'note':'R144 recuperato da associazione duplicato valida #'+str(int(a['source_id'])),
          'visibile':1,'tipo_template':'inbound_auto','tenant_id':'default','doc_type':dtype,
          'confidence':float(original.get('document_confidence') or 0),'match_score':float(original.get('match_score') or 0),
          'source':'duplicate_archive_recovered_r144','status':'salvato','inbound_id':None}
        ks=[k for k in values if k in dc]
        conn.execute("INSERT INTO documenti("+','.join(ks)+") VALUES("+','.join('?' for _ in ks)+")",[values[k] for k in ks])
        did=int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        _insert_semantic_from_archive(conn,did,sh,sems)
        res=sync_document(conn,did);res.update({'recovered_from_archive':int(a['id']),'source_inbound':int(a['source_id'])});out.append(res)
    return out

def _sync_profile_flags(conn):
    if not _table(conn,'tesserati') or not _table(conn,'documenti'):return
    tc=_cols(conn,'tesserati')
    for a in conn.execute("SELECT * FROM tesserati ORDER BY id").fetchall():
        tid=int(a['id']);mus=[];medexp=[]
        for d in conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1",(tid,)).fetchall():
            fp=resolve_file(d['filename'])
            if not fp:continue
            typ=canonical_type(d)
            if typ=='modulo_unico_tesseramento':mus.append(d)
            elif typ=='certificato_medico':
                x=_doc_expiry(conn,d)
                if x:medexp.append(x)
        if 'iscrizione_firmata' in tc:conn.execute("UPDATE tesserati SET iscrizione_firmata=? WHERE id=?",(1 if mus else 0,tid))
        if 'documenti_onboarding_ok' in tc:conn.execute("UPDATE tesserati SET documenti_onboarding_ok=? WHERE id=?",(1 if mus else 0,tid))
        if 'certificato_scadenza' in tc:conn.execute("UPDATE tesserati SET certificato_scadenza=? WHERE id=?",((max(medexp) if medexp else ''),tid))

def reconcile_all(conn):
    actions=[]
    actions.extend(recover_duplicate_archives(conn))
    if _table(conn,'inbound_documents'):
        for r in conn.execute("""SELECT id FROM inbound_documents
          WHERE coalesce(tesserato_id,0)>0 AND lower(coalesce(status,'')) IN ('accepted','manual_accepted','verificato','archived_to_tesserato','resolved','associato')
          ORDER BY id DESC LIMIT 300""").fetchall():
            try:
                res=materialize_inbound(conn,int(r['id']),allow_old=False)
                if res.get('ok'):actions.append(res)
            except Exception as exc:
                actions.append({'ok':False,'inbound_id':int(r['id']),'error':repr(exc)[:160]})
    if _table(conn,'documenti'):
        for r in conn.execute("SELECT id FROM documenti WHERE coalesce(visibile,1)=1 AND coalesce(tesserato_id,0)>0 ORDER BY id").fetchall():
            try:
                res=sync_document(conn,int(r['id']))
                if res.get('ok'):actions.append(res)
            except Exception:pass
    _sync_profile_flags(conn)
    conn.commit()
    return actions

def truth(conn,row):
    tid=int(row['id']);today=date.today()
    docs=conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1",(tid,)).fetchall()
    mu=any(canonical_type(d)=='modulo_unico_tesseramento' and resolve_file(d['filename']) for d in docs)
    meds=[d for d in docs if canonical_type(d)=='certificato_medico' and resolve_file(d['filename'])]
    expiries=[_doc_expiry(conn,d) for d in meds];expiries=[x for x in expiries if x]
    exp=max(expiries) if expiries else ''
    med_present=bool(meds);med_ok=False;med_state='Manca';med_detail='Certificato medico mancante'
    if med_present and exp:
        try:
            ed=datetime.strptime(exp,'%Y-%m-%d').date();med_ok=ed>=today
            med_state='OK' if med_ok else 'Scaduto'
            med_detail=('Valido fino al '+ed.strftime('%d/%m/%Y')) if med_ok else ('Scaduto il '+ed.strftime('%d/%m/%Y'))
        except Exception:
            med_state='Da verificare';med_detail='Certificato presente, scadenza da verificare'
    elif med_present:
        med_state='Da verificare';med_detail='Certificato presente, scadenza da verificare'
    pays=conn.execute("SELECT * FROM pagamenti WHERE tesserato_id=? ORDER BY id DESC",(tid,)).fetchall()
    month=today.month;year=today.year;season=year if month>=7 else year-1
    def paid(p):
        try:st=(str(p['stato'] or '')+' '+str(p['online_status'] or '')).lower()
        except Exception:st=''
        if any(x in st for x in ('pending','attesa','cancel','annull','failed','fallit','refund','rimbors')):return False
        try:amt=float(p['importo'] or 0)
        except Exception:amt=0
        try:dt=bool(p['data'])
        except Exception:dt=False
        return any(x in st for x in ('paid','pagat','saldat','complet','incassat')) or (dt and amt>0)
    monthly=False;enroll=False
    for p in pays:
        if not paid(p):continue
        try:c=str(p['causale'] or '').lower();pm=int(p['mese'] or 0);py=int(p['anno'] or 0)
        except Exception:c='';pm=0;py=0
        if (('mensil' in c) or c in ('quota','quota_mensile','mensile')) and pm==month and py==year:monthly=True
        if any(x in c for x in ('iscrizione','tesseramento')) and py in (season,season+1):enroll=True
    try:minor=bool(int(row['minorenne'] or 0))
    except Exception:minor=False
    guardian=str(row['genitore'] or '').strip() if 'genitore' in row.keys() else ''
    contact=((str(row['telefono_genitore'] or '').strip() if 'telefono_genitore' in row.keys() else '') or
             (str(row['email_genitore'] or '').strip() if 'email_genitore' in row.keys() else ''))
    consent=False
    for k in ('consenso_informato','privacy_ok','liberatoria_ok'):
        if k in row.keys():
            try:consent=consent or bool(int(row[k] or 0))
            except Exception:pass
    tutela=(not minor) or bool(mu and guardian and contact and consent)
    return {'mu':mu,'med_present':med_present,'med_ok':med_ok,'med_state':med_state,'med_detail':med_detail,'expiry':exp,
            'monthly':monthly,'enroll':enroll,'minor':minor,'tutela':tutela,'overall':bool(mu and med_ok and monthly and enroll and tutela)}
'''

MOD.write_text(module,encoding='utf-8')
py_compile.compile(str(MOD),doraise=True)

# Reconcile existing current truth, including safe recovery of an operator
# duplicate whose former canonical row disappeared without a deletion tombstone.
sys.path.insert(0,str(APP))
from asd_app.document_sync_core_r143 import reconcile_all,truth
conn=sqlite3.connect(str(DB),timeout=60);conn.row_factory=sqlite3.Row
try:
    actions=reconcile_all(conn)
    giulia=conn.execute("SELECT * FROM tesserati WHERE lower(cognome)='di francia' AND lower(nome)='giulia' LIMIT 1").fetchone()
    giulia_truth=truth(conn,giulia) if giulia else {}
    giulia_docs=[dict(x) for x in conn.execute("""SELECT id,doc_type,categoria,titolo,filename,data_scadenza,visibile,status,source,inbound_id
      FROM documenti WHERE tesserato_id=? ORDER BY id""",(int(giulia['id']),)).fetchall()] if giulia else []
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0]);fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:conn.close()
print('[r144-reconcile] backup='+str(backup)+' actions='+str(len(actions))+' giulia_truth='+json.dumps(giulia_truth,ensure_ascii=False)+' giulia_docs='+json.dumps(giulia_docs,ensure_ascii=False),flush=True)
if integrity.lower()!='ok' or fk:raise RuntimeError('R144 DB integrity failed')

# Patch the canonical mobile profile source directly. Do not rely on after_request
# ordering: the route itself now reads the same central truth used after upload.
matches=[]
for p in (APP/'asd_app').rglob('*.py'):
    try:s=p.read_text(encoding='utf-8',errors='replace')
    except Exception:continue
    if 'BODYMIND_R110_SIMPLE_MOBILE' in s and 'def fix12_mobile_atleta' in s:
        matches.append((p,s))
if len(matches)!=1:
    raise RuntimeError('R144 expected one canonical mobile profile source, found '+repr([str(x[0]) for x in matches]))
MOB,ms=matches[0]
start=ms.find('def fix12_mobile_atleta')
end=ms.find('\n@app.',start)
if end<0:end=len(ms)
block=ms[start:end]
if 'BODYMIND_R144_CANONICAL_PROFILE_TRUTH' not in block:
    a=block.find("        if request.method=='GET' and request.args.get('advanced')!='1':")
    b=block.find("        if request.method=='POST':",a)
    if a<0 or b<0:raise RuntimeError('R144 mobile GET/POST anchors missing')
    new_get=r'''        # BODYMIND_R144_CANONICAL_PROFILE_TRUTH
        if request.method=='GET' and request.args.get('advanced')!='1':
            from .document_sync_core_r143 import truth as _r144_truth
            tr=_r144_truth(conn,row)
            items=[
              ('Modulo Unico',tr['mu'],'Presente e apribile' if tr['mu'] else 'Modulo Unico mancante','OK' if tr['mu'] else 'Manca'),
              ('Certificato',tr['med_ok'],tr['med_detail'],tr['med_state']),
              ('Mensile',tr['monthly'],'Pagamento mese corrente','OK' if tr['monthly'] else 'Manca'),
              ('Tesseramento',tr['enroll'],'Quota stagione corrente','OK' if tr['enroll'] else 'Manca'),
            ]
            if tr['minor']:
                items.append(('Tutela',tr['tutela'],'Completa' if tr['tutela'] else ('Non valida senza MU' if not tr['mu'] else 'Genitore/contatto/consenso incompleto'),'OK' if tr['tutela'] else 'Manca'))
            name=(str(row['cognome'] or '')+' '+str(row['nome'] or '')).strip()
            tpl="""<!doctype html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'><title>BodyMind · {{name}}</title>
            <style>body{margin:0;background:#071426;color:#eaf2ff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}.r144{max-width:700px;margin:auto;padding:16px 14px 40px}.head{padding:18px;border-radius:20px;background:#0d2036;border:1px solid #203b57}.head h1{margin:4px 0}.head p{margin:0;color:#9fb3ca}.overall{display:inline-block;margin-top:10px;padding:8px 11px;border-radius:999px;background:{{'#14532d' if overall else '#7f1d1d'}};font-weight:950}.state{display:grid;grid-template-columns:16px 1fr auto;gap:9px;align-items:center;padding:14px;margin-top:9px;border-radius:15px;background:#0b1b2e;border:1px solid #1d3651}.dot{width:12px;height:12px;border-radius:50%}.state small{display:block;color:#91a6bd;margin-top:3px}.actions{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}.actions a{padding:12px;border-radius:13px;background:#163b5f;color:white;text-decoration:none;text-align:center;font-weight:900}.actions a.upload{background:#166534}.ok{color:#86efac}.bad{color:#fca5a5}.warn{color:#fde68a}</style></head><body><main class='r144'><section class='head'><small>ATLETA</small><h1>{{name}}</h1><p>{{course or 'Corso non indicato'}}</p><span class='overall'>{{'REGOLARE' if overall else 'DA COMPLETARE'}}</span></section>{% for label,ok,detail,state in items %}<div class='state'><span class='dot' style='background:{{"#16a34a" if ok else ("#f59e0b" if state=="Da verificare" else "#dc2626")}}'></span><div><b>{{label}}</b><small>{{detail}}</small></div><strong class='{{"ok" if ok else ("warn" if state=="Da verificare" else "bad")}}'>{{state}}</strong></div>{% endfor %}<div class='actions'><a href='/mobile/atleta/{{tid}}?advanced=1'>Modifica dati</a><a href='/mobile/atleta/{{tid}}/documenti'>Documenti</a><a class='upload' href='/mobile/atleta/{{tid}}/documenti/carica'>＋ Carica documento</a><a href='/pagamenti?tesserato_id={{tid}}'>Pagamenti</a><a href='/mobile/atlete'>Atlete</a><a href='/mobile'>Home</a></div></main></body></html>"""
            return render_template_string(tpl,name=name,course=(row['corso'] or ''),items=items,tid=tid,overall=tr['overall'])

'''
    block=block[:a]+new_get+block[b:]
    ms=ms[:start]+block+ms[end:]
    shutil.copy2(MOB,BACK/('mobile_'+MOB.name))
    MOB.write_text(ms,encoding='utf-8');py_compile.compile(str(MOB),doraise=True)
    print('[r144-mobile-profile] PASS canonical route truth + direct upload action',flush=True)
else:
    print('[r144-mobile-profile] already current',flush=True)

# Ensure a direct upload route exists even on a clean runtime.
core=CORE.read_text(encoding='utf-8',errors='replace')
if "def bodymind_r144_direct_document_upload" not in core:
    shutil.copy2(CORE,BACK/'core.py')
    core += r'''

# BODYMIND_R144_DIRECT_ATHLETE_UPLOAD
@app.route('/mobile/atleta/<int:tid>/documenti/carica',methods=['GET','POST'])
@admin_required
def bodymind_r144_direct_document_upload(tid):
    from pathlib import Path as _P
    from datetime import datetime as _DT
    from werkzeug.utils import secure_filename as _secure
    from .document_sync_core_r143 import canonical_type as _ctype,sha256_file as _sha,resolve_file as _resolve,sync_document as _syncdoc
    conn=db();conn.row_factory=sqlite3.Row
    try:
        athlete=conn.execute("SELECT * FROM tesserati WHERE id=?",(tid,)).fetchone()
        if not athlete:abort(404)
        if request.method=='POST':
            up=request.files.get('file');dtype=str(request.form.get('tipo') or '').strip().lower()
            allowed={'modulo_unico_tesseramento','certificato_medico','liberatoria_immagini','altro'}
            if dtype not in allowed:return redirect('/mobile/atleta/'+str(tid)+'/documenti/carica?error=tipo')
            if not up or not getattr(up,'filename',''):return redirect('/mobile/atleta/'+str(tid)+'/documenti/carica?error=file')
            ext=_P(up.filename).suffix.lower()
            if ext not in ('.pdf','.png','.jpg','.jpeg','.webp','.docx'):return redirect('/mobile/atleta/'+str(tid)+'/documenti/carica?error=formato')
            ddir=_P('/data/tenants/default/media/tesserati')/str(tid);ddir.mkdir(parents=True,exist_ok=True)
            name=_secure(up.filename) or ('documento'+ext);dest=ddir/(_DT.now().strftime('%Y-%m-%d_%H%M%S')+'_manual_'+name);up.save(str(dest))
            digest=_sha(dest)
            for old in conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1",(tid,)).fetchall():
                if _ctype(old)!=dtype:continue
                fp=_resolve(old['filename'])
                if fp and _sha(fp)==digest:
                    try:dest.unlink()
                    except Exception:pass
                    return redirect('/mobile/atleta/'+str(tid)+'/documenti?duplicate=1')
            meta={'modulo_unico_tesseramento':('Modulo iscrizione BodyMind','Modulo Unico'),'certificato_medico':('Certificato medico','Certificato medico'),'liberatoria_immagini':('Liberatoria immagini','Liberatoria immagini'),'altro':('Documenti ASD','Documento')}
            cat,label=meta[dtype]
            scad_raw=str(request.form.get('scadenza') or '').strip() if dtype=='certificato_medico' else ''
            scad=''
            if dtype=='certificato_medico' and scad_raw:
                _digits=''.join(ch for ch in scad_raw if ch.isdigit())
                _candidates=[('%d/%m/%Y',scad_raw),('%d-%m-%Y',scad_raw),('%Y-%m-%d',scad_raw),('%Y/%m/%d',scad_raw)]
                if len(_digits)==8:_candidates.append(('%d%m%Y',_digits))
                for _fmt,_val in _candidates:
                    try:scad=_DT.strptime(_val,_fmt).date().isoformat();break
                    except Exception:pass
                if not scad:return redirect('/mobile/atleta/'+str(tid)+'/documenti/carica?error=scadenza')
            dc={str(x[1]) for x in conn.execute('PRAGMA table_info(documenti)').fetchall()}
            vals={'tesserato_id':tid,'titolo':name,'categoria':cat,'filename':str(dest),'original_filename':name,'data_caricamento':_DT.now().strftime('%Y-%m-%d %H:%M:%S'),'data_scadenza':scad,'note':'Caricamento manuale dalla scheda atleta','visibile':1,'tipo_template':'manuale_atleta','tenant_id':'default','doc_type':dtype,'confidence':100,'match_score':100,'source':'manuale_atleta','status':'salvato','inbound_id':None}
            ks=[k for k in vals if k in dc];conn.execute("INSERT INTO documenti("+','.join(ks)+") VALUES("+','.join('?' for _ in ks)+")",[vals[k] for k in ks]);did=int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            _syncdoc(conn,did);conn.commit()
            return redirect('/mobile/atleta/'+str(tid)+'/documenti?uploaded=1')
    finally:
        if request.method=='POST':
            try:conn.close()
            except Exception:pass
    name=(str(athlete['cognome'] or '')+' '+str(athlete['nome'] or '')).strip()
    msg={'tipo':'Seleziona il tipo documento.','file':'Seleziona un file.','formato':'Formato non supportato.','scadenza':'Data non valida. Usa GG/MM/AAAA oppure 8 cifre, ad esempio 14112026.'}.get(request.args.get('error') or '','')
    return f"""<!doctype html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'><title>Carica documento</title><style>body{{margin:0;background:#071426;color:#eef6ff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}}main{{max-width:620px;margin:auto;padding:18px}}.box{{background:#0b1d33;border:1px solid #27445f;border-radius:20px;padding:18px}}label{{display:block;margin-top:13px;font-weight:900}}select,input{{width:100%;min-height:48px;margin-top:6px;border-radius:12px;border:1px solid #315475;background:#081727;color:#fff;padding:10px}}button,.back{{display:block;width:100%;margin-top:14px;padding:13px;border:0;border-radius:12px;background:#166534;color:#fff;text-align:center;text-decoration:none;font-weight:950}}.back{{background:#163b5f}}</style></head><body><main><div class='box'><small>DOCUMENTO ATLETA</small><h1>{e(name)}</h1>{("<p>"+e(msg)+"</p>" if msg else "")}<form method='post' enctype='multipart/form-data'>{csrf_input()}<label>Tipo documento<select name='tipo' required><option value=''>Seleziona…</option><option value='certificato_medico'>Certificato medico</option><option value='modulo_unico_tesseramento'>Modulo Unico</option><option value='liberatoria_immagini'>Liberatoria immagini</option><option value='altro'>Altro documento</option></select></label><label>File<input type='file' name='file' accept='.pdf,.png,.jpg,.jpeg,.webp,.docx' required></label><label>Scadenza certificato (se nota) · GG/MM/AAAA oppure 8 cifre<input type='text' name='scadenza' inputmode='text' autocomplete='off' placeholder='es. 14/11/2026 o 14112026'></label><button type='submit'>Carica e associa a {e(name)}</button></form><a class='back' href='/mobile/atleta/{tid}'>Annulla</a></div></main></body></html>"""
'''
    CORE.write_text(core,encoding='utf-8');py_compile.compile(str(CORE),doraise=True)
    print('[r144-upload-route] installed',flush=True)
else:
    print('[r144-upload-route] existing direct route retained',flush=True)

# Canonical date-input migration for an already-persisted R144 route.
# Scope every rewrite to bodymind_r144_direct_document_upload so historical
# variants elsewhere cannot be touched accidentally.
_r144_core=CORE.read_text(encoding='utf-8',errors='replace')
_r144_before=_r144_core
_r144_start=_r144_core.find('def bodymind_r144_direct_document_upload')
if _r144_start<0:
    _r144_deco=_r144_core.find("@app.route('/mobile/atleta/<int:tid>/documenti/carica'")
    if _r144_deco<0:
        _r144_deco=_r144_core.find('@app.route("/mobile/atleta/<int:tid>/documenti/carica')
    if _r144_deco<0:
        raise RuntimeError('R144 direct upload route decorator missing from persistent core')
    _r144_start=_r144_deco
_r144_end=_r144_core.find('\n# BODYMIND_',_r144_start+1)
if _r144_end<0:
    _r144_end=_r144_core.find('\n@app.route(',_r144_start+1)
if _r144_end<0:_r144_end=len(_r144_core)
_r144_seg=_r144_core[_r144_start:_r144_end]

_old_parser="            cat,label=meta[dtype];scad=str(request.form.get('scadenza') or '').strip() if dtype=='certificato_medico' else ''"
_new_parser="""            cat,label=meta[dtype]
            scad_raw=str(request.form.get('scadenza') or '').strip() if dtype=='certificato_medico' else ''
            scad=''
            if dtype=='certificato_medico' and scad_raw:
                _digits=''.join(ch for ch in scad_raw if ch.isdigit())
                _candidates=[('%d/%m/%Y',scad_raw),('%d-%m-%Y',scad_raw),('%Y-%m-%d',scad_raw),('%Y/%m/%d',scad_raw)]
                if len(_digits)==8:_candidates.append(('%d%m%Y',_digits))
                for _fmt,_val in _candidates:
                    try:scad=_DT.strptime(_val,_fmt).date().isoformat();break
                    except Exception:pass
                if not scad:return redirect('/mobile/atleta/'+str(tid)+'/documenti/carica?error=scadenza')"""
if _old_parser in _r144_seg:
    _r144_seg=_r144_seg.replace(_old_parser,_new_parser,1)

_canonical_field="<label>Scadenza certificato (se nota) · GG/MM/AAAA oppure 8 cifre<input type='text' name='scadenza' inputmode='text' autocomplete='off' placeholder='es. 14/11/2026 o 14112026'></label>"
_r144_seg,n_field=re.subn(
    r"<label>Scadenza certificato[^<\n]*<input\b[^>]*\bname=['\"]scadenza['\"][^>]*></label>",
    lambda m:_canonical_field,
    _r144_seg,count=1,flags=re.I
)
if n_field!=1:
    raise RuntimeError('R144 persistent expiry field migration matched '+str(n_field)+' fields; refusing blind write')
if "%d%m%Y" not in _r144_seg:
    raise RuntimeError('R144 persistent expiry parser is not compact-date capable')

_r144_core=_r144_core[:_r144_start]+_r144_seg+_r144_core[_r144_end:]
if _r144_core!=_r144_before:
    compile(_r144_core,str(CORE),'exec')
    shutil.copy2(CORE,BACK/'core_pre_canonical_date.py')
    CORE.write_text(_r144_core,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r144-date-canonical] PASS route-scoped persistent migration field=1 parser=compact+slash',flush=True)
else:
    py_compile.compile(str(CORE),doraise=True)
    print('[r144-date-canonical] already canonical',flush=True)

# If the older post-association hook is absent, add one. It calls the safe,
# recent-only reconciler above, so Autopilot/Operatore immediately update truth.
core=CORE.read_text(encoding='utf-8',errors='replace')
if '_bodymind_r143_post_association_sync' not in core and '_bodymind_r144_post_association_sync' not in core:
    core += r'''

# BODYMIND_R144_POST_ASSOCIATION_SYNC
@app.after_request
def _bodymind_r144_post_association_sync(resp):
    try:
        p=(request.path or '').lower()
        if request.method=='POST' and any(k in p for k in ('operatore-bodymind','autopilot','inbound','documenti','documento')):
            from .document_sync_core_r143 import reconcile_all as _sync
            conn=db();conn.row_factory=sqlite3.Row
            try:_sync(conn)
            finally:conn.close()
    except Exception as exc:
        print('[r144-post-sync-warning] '+repr(exc),flush=True)
    return resp
'''
    CORE.write_text(core,encoding='utf-8');py_compile.compile(str(CORE),doraise=True)
    print('[r144-post-sync] installed',flush=True)

# BODYMIND_R145_UPLOAD_LINK_SURFACE
# Make direct per-athlete upload reachable from the actual mobile profile and
# document page, regardless of which historical route renderer serves them.
core=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R145_UPLOAD_LINK_SURFACE' not in core:
    core += r'''

# BODYMIND_R145_UPLOAD_LINK_SURFACE
@app.after_request
def _bodymind_r145_upload_link_surface(resp):
    try:
        import re as _r145_re
        if request.method!='GET' or int(getattr(resp,'status_code',200) or 200)!=200:
            return resp
        if 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp
        m=_r145_re.fullmatch(r'/mobile/atleta/(\d+)(?:/documenti)?/?',request.path or '')
        if not m:
            return resp
        tid=int(m.group(1));html=resp.get_data(as_text=True)
        if '/documenti/carica' in html:
            return resp
        btn="<div style='margin:12px 14px'><a href='/mobile/atleta/"+str(tid)+"/documenti/carica' style='display:block;padding:13px;border-radius:13px;background:#166534;color:#fff;text-align:center;text-decoration:none;font-weight:950'>＋ Carica documento</a></div>"
        if '</main>' in html:
            html=html.replace('</main>',btn+'</main>',1)
        elif '</body>' in html:
            html=html.replace('</body>',btn+'</body>',1)
        else:
            html+=btn
        resp.set_data(html)
    except Exception as exc:
        print('[r145-upload-link-warning] '+repr(exc),flush=True)
    return resp
'''
    CORE.write_text(core,encoding='utf-8');py_compile.compile(str(CORE),doraise=True)
    print('[r145-upload-link] installed',flush=True)
else:
    print('[r145-upload-link] already present',flush=True)

# Final rendered QA against current production data.
qa=r'''
import sqlite3,sys
from pathlib import Path
sys.path.insert(0,"/data/top2_app")
import app as _full
from asd_app.core import app
from asd_app.document_sync_core_r143 import truth,resolve_file,canonical_type
app.config["TESTING"]=True
c=app.test_client()
with c.session_transaction() as s:
    s.update({"logged":True,"logged_in":True,"username":"admin","display_name":"R144 QA","role":"admin","tenant_slug":"default","user_id":1,"is_admin":True,"admin":True,"_csrf_token":"r144"})
conn=sqlite3.connect("/data/tenants/default/asd.db",timeout=20);conn.row_factory=sqlite3.Row
try:
    g=conn.execute("SELECT * FROM tesserati WHERE lower(cognome)='di francia' AND lower(nome)='giulia' LIMIT 1").fetchone()
    checks={"giulia_exists":bool(g)}
    if g:
        docs=conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1",(int(g["id"]),)).fetchall()
        med=[d for d in docs if canonical_type(d)=='certificato_medico' and resolve_file(d["filename"])]
        tr=truth(conn,g)
        checks["giulia_medical_visible"]=bool(med)
        checks["giulia_medical_truth"]=bool(tr["med_present"])
        p=c.get("/mobile/atleta/"+str(int(g["id"])),follow_redirects=False);ph=p.get_data(as_text=True)
        u=c.get("/mobile/atleta/"+str(int(g["id"]))+"/documenti/carica",follow_redirects=False);uh=u.get_data(as_text=True)
        checks["profile"]=p.status_code==200 and "Modulo Unico" in ph and "Certificato" in ph and "Carica documento" in ph and "Certificato medico mancante" not in ph
        if not checks["profile"]:
            try:
                rules=[(str(r.rule),r.endpoint,sorted(r.methods or [])) for r in app.url_map.iter_rules() if str(r.rule).startswith("/mobile/atleta/")]
            except Exception:
                rules=[]
            print("[r144-profile-diag] status="+str(p.status_code)+" location="+str(p.headers.get("Location",""))+" body="+repr(ph[:2500])+" rules="+repr(rules),flush=True)
        checks["upload"]=u.status_code==200 and "Certificato medico" in uh and "Modulo Unico" in uh
        # Final keyboard/input rendering is intentionally verified after R147,
        # because legacy after_request handlers are removed there. R144 owns
        # document truth + route availability, not final response decoration.
    checks["db"]=str(conn.execute("PRAGMA integrity_check").fetchone()[0]).lower()=="ok" and len(conn.execute("PRAGMA foreign_key_check").fetchall())==0
finally:conn.close()
print("[r144-selftest] "+repr(checks),flush=True)
if not all(checks.values()):raise RuntimeError("R144 QA failed "+repr(checks))
'''
proc=subprocess.run([sys.executable,'-c',qa],capture_output=True,text=True,timeout=120)
print((proc.stdout or '').strip(),flush=True)
if proc.returncode!=0:
    raise RuntimeError('R144 child QA failed '+((proc.stderr or '')+(proc.stdout or ''))[-5000:])
print('[r144-selftest-main] PASS association->canonical document->truth + direct athlete upload db-ok',flush=True)
