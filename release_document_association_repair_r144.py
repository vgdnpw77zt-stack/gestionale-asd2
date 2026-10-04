# -*- coding: utf-8 -*-
from __future__ import annotations
import json, py_compile, shutil, sqlite3, subprocess, sys
from pathlib import Path
from datetime import datetime

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
CORE=APP/'asd_app/core.py'
OP=APP/'asd_app/routes_operator_bodymind.py'
MOD=APP/'asd_app/document_sync_core_r143.py'
BACK=Path('/data/release_backups/20261005_r144_document_association')
BACK.mkdir(parents=True,exist_ok=True)
if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

# Backup before any DB mutation.
stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
backup=BACK/(stamp+'_pre_r144.db')
src=sqlite3.connect(str(DB),timeout=30); out=sqlite3.connect(str(backup))
try: src.backup(out)
finally: out.close(); src.close()

# Replace the failed R143 prototype with a conservative, idempotent sync core.
# It NEVER rematerializes arbitrary historical inbound rows. It only:
# - syncs current visible documents;
# - materializes very recent trusted inbound associations;
# - recovers a recent R78 "duplicate resolved" upload when its canonical row
#   has disappeared, using the archived file + semantic evidence.
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
            try: vals.append(str(row_or_value[k] or '').lower())
            except Exception: pass
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
            if fp.is_file(): return fp.resolve()
        except Exception: pass
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
    if not dest.exists(): shutil.copy2(fp,dest)
    return dest.resolve()

def _analysis_expiry(an):
    for k in ('expiry_date','valid_until','scadenza'):
        iso=iso_date((an or {}).get(k))
        if iso:return iso
    issue=iso_date((an or {}).get('issue_date'))
    if issue:
        try:
            d=datetime.strptime(issue,'%Y-%m-%d').date()
            # Certificates in this workflow are annual when semantic analysis
            # explicitly states annual validity but omits expiry.
            txt=(' '+str((an or {}).get('content_summary') or '')+' '+str((an or {}).get('notes') or '')+' ').lower()
            if 'validità annuale' in txt or 'validita annuale' in txt or 'validità di un anno' in txt or 'validita di un anno' in txt:
                try:return d.replace(year=d.year+1).isoformat()
                except Exception:return d.replace(year=d.year+1,day=28).isoformat()
        except Exception:pass
    return ''

def _doc_expiry(conn,doc):
    try:
        iso=iso_date(doc['data_scadenza'])
        if iso:return iso
    except Exception:pass
    fp=resolve_file(doc['filename']); sh=sha256_file(fp)
    sm=_semantic(conn,'documenti',int(doc['id']),sh); exp=_analysis_expiry(sm.get('analysis') or {})
    if exp:return exp
    try:iid=int(doc['inbound_id'] or 0)
    except Exception:iid=0
    if iid:
        sm2=_semantic(conn,'inbound_documents',iid,sh); exp=_analysis_expiry(sm2.get('analysis') or {})
        if exp:return exp
    return ''

def _advance_profile_expiry(conn,tid,expiry):
    expiry=iso_date(expiry)
    if not expiry:return
    tc=_cols(conn,'tesserati')
    if 'certificato_scadenza' not in tc:return
    row=conn.execute("SELECT certificato_scadenza FROM tesserati WHERE id=?",(int(tid),)).fetchone()
    old=iso_date(row[0] if row else '')
    if not old or expiry>old:
        conn.execute("UPDATE tesserati SET certificato_scadenza=? WHERE id=?",(expiry,int(tid)))

def _sync_flags(conn,tid,dtype):
    tc=_cols(conn,'tesserati')
    if dtype=='modulo_unico_tesseramento':
        sets=[]; vals=[]
        for k in ('iscrizione_firmata','documenti_onboarding_ok'):
            if k in tc:sets.append(k+'=?');vals.append(1)
        if sets:
            vals.append(int(tid));conn.execute("UPDATE tesserati SET "+','.join(sets)+" WHERE id=?",tuple(vals))
    elif dtype=='liberatoria_immagini' and 'liberatoria_immagini' in tc:
        conn.execute("UPDATE tesserati SET liberatoria_immagini=1 WHERE id=?",(int(tid),))

def sync_document(conn,doc_id):
    doc=conn.execute("SELECT * FROM documenti WHERE id=?",(int(doc_id),)).fetchone()
    if not doc:return {'ok':False,'reason':'missing_document'}
    if int(doc['visibile'] or 0)!=1:return {'ok':False,'reason':'not_visible'}
    tid=int(doc['tesserato_id'] or 0)
    if tid<=0:return {'ok':False,'reason':'missing_athlete'}
    fp=resolve_file(doc['filename'])
    if not fp:return {'ok':False,'reason':'missing_file','document_id':int(doc_id),'tid':tid}
    sh=sha256_file(fp)
    sm=_semantic(conn,'documenti',int(doc_id),sh)
    dtype=canonical_type(doc)
    if dtype=='altro' and sm.get('document_type'):dtype=canonical_type(sm.get('document_type'))
    try:iid=int(doc['inbound_id'] or 0)
    except Exception:iid=0
    inbound=None
    if iid and _table(conn,'inbound_documents'):
        inbound=conn.execute("SELECT * FROM inbound_documents WHERE id=?",(iid,)).fetchone()
        if inbound and dtype=='altro':dtype=canonical_type(inbound)
    persistent=_ensure_persistent(tid,fp,doc['original_filename'] if 'original_filename' in doc.keys() else fp.name)
    dc=_cols(conn,'documenti'); sets=[]; vals=[]
    cat,_=TYPE_META.get(dtype,TYPE_META['altro'])
    def add(k,v):
        if k in dc:sets.append(k+'=?');vals.append(v)
    add('filename',str(persistent));add('doc_type',dtype);add('categoria',cat);add('visibile',1)
    if 'status' in dc and str(doc['status'] or '').lower() not in ('verificato','salvato'):add('status','salvato')
    if inbound:
        try:
            if 'confidence' in dc and float(doc['confidence'] or 0)<=0:add('confidence',float(inbound['document_confidence'] or 0))
        except Exception:pass
        try:
            if 'match_score' in dc and float(doc['match_score'] or 0)<=0:add('match_score',float(inbound['match_score'] or 0))
        except Exception:pass
    expiry=''
    if dtype=='certificato_medico':
        expiry=_doc_expiry(conn,doc)
        if expiry:add('data_scadenza',expiry)
    if sets:
        vals.append(int(doc_id));conn.execute("UPDATE documenti SET "+','.join(sets)+" WHERE id=?",tuple(vals))
    _sync_flags(conn,tid,dtype)
    if dtype=='certificato_medico' and expiry:_advance_profile_expiry(conn,tid,expiry)
    return {'ok':True,'document_id':int(doc_id),'tid':tid,'type':dtype,'expiry':expiry,'sha':sh}

def _insert_document(conn,tid,dtype,fp,original='',confidence=100,match=100,source='association_sync_r144',note='',expiry='',semantic=None):
    persistent=_ensure_persistent(tid,fp,original or Path(fp).name)
    sh=sha256_file(persistent)
    # exact duplicate only for same athlete + same semantic type
    for d in conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1 ORDER BY id",(int(tid),)).fetchall():
        if canonical_type(d)!=dtype:continue
        ef=resolve_file(d['filename'])
        if ef and sha256_file(ef)==sh:
            return sync_document(conn,int(d['id']))
    dc=_cols(conn,'documenti');cat,label=TYPE_META.get(dtype,TYPE_META['altro'])
    values={'tesserato_id':int(tid),'titolo':str(original or label),'categoria':cat,'filename':str(persistent),
      'original_filename':str(original or persistent.name),'data_caricamento':datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
      'data_scadenza':iso_date(expiry),'note':note,'visibile':1,'tipo_template':'inbound_auto','tenant_id':'default',
      'doc_type':dtype,'confidence':confidence,'match_score':match,'source':source,'status':'salvato','inbound_id':None}
    ks=[k for k in values if k in dc]
    conn.execute("INSERT INTO documenti("+','.join(ks)+") VALUES("+','.join('?' for _ in ks)+")",[values[k] for k in ks])
    did=int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    if semantic and _table(conn,'bodymind_document_semantics'):
        sc=_cols(conn,'bodymind_document_semantics')
        sv={
          'source_table':'documenti','source_id':did,'sha256':sh,
          'document_type':dtype,'person_name':semantic.get('person_name') or '',
          'codice_fiscale':semantic.get('codice_fiscale') or '',
          'semantic_key':semantic.get('semantic_key') or '',
          'confidence':semantic.get('confidence') or 0,
          'analysis_json':semantic.get('analysis_json') or '{}',
          'model':semantic.get('model') or '',
          'analyzed_at':semantic.get('analyzed_at') or datetime.now().isoformat(timespec='seconds')
        }
        ks2=[k for k in sv if k in sc]
        try:
            conn.execute("INSERT INTO bodymind_document_semantics("+','.join(ks2)+") VALUES("+','.join('?' for _ in ks2)+")",[sv[k] for k in ks2])
        except Exception:pass
    res=sync_document(conn,did);res['created']=True
    return res

def materialize_inbound(conn,inbound_id):
    if not _table(conn,'inbound_documents') or not _table(conn,'documenti'):return {'ok':False,'reason':'tables_missing'}
    r=conn.execute("SELECT * FROM inbound_documents WHERE id=?",(int(inbound_id),)).fetchone()
    if not r:return {'ok':False,'reason':'inbound_missing'}
    status=str(r['status'] or '').strip().lower()
    try:conf=float(r['document_confidence'] or 0)
    except Exception:conf=0
    try:match=float(r['match_score'] or 0)
    except Exception:match=0
    trusted=status in ('accepted','manual_accepted','verificato','archived_to_tesserato','resolved','associato') and (status!='associato' or (conf>=80 and match>=80))
    if not trusted:return {'ok':False,'reason':'not_trusted','status':status}
    tid=int(r['tesserato_id'] or 0)
    if tid<=0:return {'ok':False,'reason':'no_athlete'}
    dtype=canonical_type(r)
    if dtype=='altro':return {'ok':False,'reason':'unsupported_type'}

    linked=conn.execute("SELECT * FROM documenti WHERE inbound_id=? ORDER BY visibile DESC,id DESC",(int(inbound_id),)).fetchall()
    if linked:
        visible=[d for d in linked if int(d['visibile'] or 0)==1 and resolve_file(d['filename'])]
        if visible:return sync_document(conn,int(visible[0]['id']))
        # A user-hidden linked document must not be resurrected merely because
        # its historical inbound remains.
        return {'ok':False,'reason':'linked_document_archived'}

    fp=resolve_file(r['saved_path'] if 'saved_path' in r.keys() else '')
    if not fp:return {'ok':False,'reason':'missing_file'}
    sm=_semantic(conn,'inbound_documents',int(inbound_id),sha256_file(fp));an=sm.get('analysis') or {}
    expiry=_analysis_expiry(an) if dtype=='certificato_medico' else ''
    semantic=None
    if sm.get('row'):
        sr=sm['row'];semantic={
          'person_name':sr['person_name'] if 'person_name' in sr.keys() else '',
          'codice_fiscale':sr['codice_fiscale'] if 'codice_fiscale' in sr.keys() else '',
          'semantic_key':sr['semantic_key'] if 'semantic_key' in sr.keys() else '',
          'confidence':sr['confidence'] if 'confidence' in sr.keys() else 0,
          'analysis_json':sr['analysis_json'] if 'analysis_json' in sr.keys() else '{}',
          'model':sr['model'] if 'model' in sr.keys() else '',
          'analyzed_at':sr['analyzed_at'] if 'analyzed_at' in sr.keys() else ''
        }
    res=_insert_document(conn,tid,dtype,fp,r['original_filename'] if 'original_filename' in r.keys() else fp.name,
        conf,match,'association_sync_r144','R144 materializzato da associazione recente',expiry,semantic)
    res['inbound_id']=int(inbound_id)
    if res.get('created') and 'inbound_id' in _cols(conn,'documenti'):
        conn.execute("UPDATE documenti SET inbound_id=? WHERE id=?",(int(inbound_id),int(res['document_id'])))
    return res

def recover_orphan_duplicate_archives(conn):
    out=[]
    if not _table(conn,'bodymind_duplicate_records_archive') or not _table(conn,'documenti'):return out
    rows=conn.execute("""SELECT * FROM bodymind_duplicate_records_archive
      WHERE source_table='inbound_documents' AND lower(coalesce(status,''))='associato'
        AND reason LIKE 'R78 duplicate resolved to canonical document %'
      ORDER BY archived_at DESC,id DESC""").fetchall()
    seen=set()
    for a in rows:
        tid=int(a['tesserato_id'] or 0)
        if tid<=0:continue
        try:payload=json.loads(a['payload_json'] or '{}')
        except Exception:payload={}
        row=payload.get('row') or {}
        dtype=canonical_type(str(row.get('document_type') or '')+' '+str(row.get('original_filename') or ''))
        if dtype=='altro':continue
        fp=resolve_file(a['file_path'])
        if not fp:continue
        sh=sha256_file(fp)
        key=(tid,dtype,sh)
        if key in seen:continue
        seen.add(key)
        canonical_id=int(payload.get('canonical_document_id') or 0)
        canonical=conn.execute("SELECT * FROM documenti WHERE id=?",(canonical_id,)).fetchone() if canonical_id else None
        if canonical and int(canonical['tesserato_id'] or 0)==tid and int(canonical['visibile'] or 0)==1 and resolve_file(canonical['filename']):
            continue
        # If a current visible exact document already exists, just synchronize it.
        current=None
        for d in conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1",(tid,)).fetchall():
            if canonical_type(d)!=dtype:continue
            ef=resolve_file(d['filename'])
            if ef and sha256_file(ef)==sh:
                current=d;break
        if current:
            out.append(sync_document(conn,int(current['id'])));continue

        semantic=None;expiry=''
        try:sems=json.loads(a['semantics_json'] or '[]')
        except Exception:sems=[]
        if sems:
            sr=sems[0]
            try:an=json.loads(sr.get('analysis_json') or '{}')
            except Exception:an={}
            expiry=_analysis_expiry(an) if dtype=='certificato_medico' else ''
            semantic={
              'person_name':sr.get('person_name') or an.get('person_name') or '',
              'codice_fiscale':sr.get('codice_fiscale') or an.get('codice_fiscale') or '',
              'semantic_key':sr.get('semantic_key') or an.get('semantic_key') or '',
              'confidence':sr.get('confidence') or an.get('confidence') or 0,
              'analysis_json':sr.get('analysis_json') or json.dumps(an,ensure_ascii=False),
              'model':sr.get('model') or an.get('model') or '',
              'analyzed_at':sr.get('analyzed_at') or ''
            }
        res=_insert_document(conn,tid,dtype,fp,row.get('original_filename') or fp.name,
          row.get('document_confidence') or 100,row.get('match_score') or 100,
          'association_recovered_r144','R144 recuperato da upload riconosciuto: canonical precedente non più disponibile',
          expiry,semantic)
        res['recovered_archive_id']=int(a['id']);res['source_inbound_id']=int(a['source_id'])
        out.append(res)
    return out

def reconcile_all(conn):
    actions=[]
    # First recover high-confidence uploads that were incorrectly discarded as
    # duplicates of a canonical document that no longer exists.
    actions.extend(recover_orphan_duplicate_archives(conn))

    # Only recent inbound associations may auto-materialize. Historical inbound
    # rows are never replayed globally because the user may have deleted them.
    if _table(conn,'inbound_documents'):
        rows=conn.execute("""SELECT id FROM inbound_documents
          WHERE coalesce(tesserato_id,0)>0
            AND lower(coalesce(status,'')) IN ('accepted','manual_accepted','verificato','archived_to_tesserato','resolved','associato')
            AND datetime(created_at)>=datetime('now','-12 hours')
          ORDER BY id""").fetchall()
        for r in rows:
            try:
                res=materialize_inbound(conn,int(r['id']))
                if res.get('ok'):actions.append(res)
            except Exception as exc:
                actions.append({'ok':False,'inbound_id':int(r['id']),'error':repr(exc)[:180]})

    # Normalize only currently visible documents. Never resurrect hidden rows.
    if _table(conn,'documenti'):
        for r in conn.execute("SELECT id FROM documenti WHERE coalesce(visibile,1)=1 AND coalesce(tesserato_id,0)>0 ORDER BY id").fetchall():
            try:
                res=sync_document(conn,int(r['id']))
                if res.get('ok'):actions.append(res)
            except Exception as exc:
                actions.append({'ok':False,'document_id':int(r['id']),'error':repr(exc)[:180]})

    # Certificate profile expiry is derived only from CURRENT visible physical
    # medical evidence. A stale profile date cannot create a green certificate.
    if _table(conn,'tesserati') and _table(conn,'documenti') and 'certificato_scadenza' in _cols(conn,'tesserati'):
        for a in conn.execute("SELECT id FROM tesserati ORDER BY id").fetchall():
            tid=int(a['id']);expiries=[]
            for d in conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1",(tid,)).fetchall():
                if canonical_type(d)!='certificato_medico' or not resolve_file(d['filename']):continue
                exp=_doc_expiry(conn,d)
                if exp:expiries.append(exp)
            wanted=max(expiries) if expiries else ''
            conn.execute("UPDATE tesserati SET certificato_scadenza=? WHERE id=?",(wanted,tid))
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
        try:c=str(p['causale'] or '').lower()
        except Exception:c=''
        try:pm=int(p['mese'] or 0);py=int(p['anno'] or 0)
        except Exception:pm=0;py=0
        if (('mensil' in c) or c in ('quota','quota_mensile','mensile')) and pm==month and py==year:monthly=True
        if any(x in c for x in ('iscrizione','tesseramento')) and py in (season,season+1):enroll=True

    minor=False
    try:minor=bool(int(row['minorenne'] or 0))
    except Exception:pass
    guardian=str(row['genitore'] or '').strip() if 'genitore' in row.keys() else ''
    contact=((str(row['telefono_genitore'] or '').strip() if 'telefono_genitore' in row.keys() else '') or (str(row['email_genitore'] or '').strip() if 'email_genitore' in row.keys() else ''))
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
print('[r144-module] PASS conservative document sync core installed',flush=True)

# Patch future Operator duplicate resolution: a stale/missing/hidden canonical
# duplicate is NOT grounds to discard the new upload. Materialize it instead.
opsrc=OP.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R144_STALE_DUPLICATE_RECOVERY' not in opsrc:
    old='''    canonical=conn.execute("SELECT * FROM documenti WHERE id=?",(canonical_id,)).fetchone() if _table(conn,"documenti") else None
    if not canonical or int(canonical["tesserato_id"] or 0)!=tid:
        return {"ok":False,"reason":"canonical_athlete_mismatch"}
'''
    new='''    canonical=conn.execute("SELECT * FROM documenti WHERE id=?",(canonical_id,)).fetchone() if _table(conn,"documenti") else None
    # BODYMIND_R144_STALE_DUPLICATE_RECOVERY
    _canonical_usable=False
    if canonical and int(canonical["tesserato_id"] or 0)==tid:
        try:
            from .document_sync_core_r143 import resolve_file as _r144_resolve
            _canonical_usable=(int(canonical["visibile"] or 0)==1 and bool(_r144_resolve(canonical["filename"])))
        except Exception:
            _canonical_usable=(int(canonical["visibile"] or 0)==1)
    if not _canonical_usable:
        try:
            from .document_sync_core_r143 import materialize_inbound as _r144_materialize
            _rec=_r144_materialize(conn,int(inbound_id))
            conn.commit()
            if _rec.get("ok"):
                return {"ok":True,"tesserato_id":tid,"canonical_document_id":int(_rec.get("document_id") or 0),
                        "canonical_recovered":True,"staging":{"archived":False,"deleted":False,"reason":"materialized_missing_canonical"}}
        except Exception as _exc:
            return {"ok":False,"reason":"stale_canonical_recovery_error","error":repr(_exc)[:180]}
        return {"ok":False,"reason":"canonical_missing_hidden_or_file_missing"}
'''
    if old not in opsrc:
        raise RuntimeError('R144 operator duplicate anchor missing')
    shutil.copy2(OP,BACK/'routes_operator_bodymind.py')
    opsrc=opsrc.replace(old,new,1)
    OP.write_text(opsrc,encoding='utf-8')
    py_compile.compile(str(OP),doraise=True)
    print('[r144-operator] PASS stale duplicate canonical now materializes current upload',flush=True)
else:
    print('[r144-operator] already applied',flush=True)

# Remove ONLY technical documents created by the failed R143 candidate. They
# never reached a successful release. Do not touch user-created/pre-existing rows.
conn=sqlite3.connect(str(DB),timeout=60);conn.row_factory=sqlite3.Row
cleanup=[]
try:
    dcols={str(x[1]) for x in conn.execute("PRAGMA table_info(documenti)").fetchall()}
    if 'source' in dcols:
        bad=conn.execute("SELECT id,filename FROM documenti WHERE source='association_sync_r143' ORDER BY id").fetchall()
        for b in bad:
            did=int(b['id']);path=str(b['filename'] or '')
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bodymind_document_semantics'").fetchone():
                conn.execute("DELETE FROM bodymind_document_semantics WHERE source_table='documenti' AND source_id=?",(did,))
            conn.execute("DELETE FROM documenti WHERE id=?",(did,))
            cleanup.append({'id':did,'path':path})
        conn.commit()
        for item in cleanup:
            fp=Path(item['path'])
            if '_R143_' not in fp.name:continue
            refs=int(conn.execute("SELECT COUNT(*) FROM documenti WHERE filename=?",(str(fp),)).fetchone()[0])
            if refs==0:
                try:
                    if fp.is_file():fp.unlink()
                except Exception:pass

    sys.path.insert(0,str(APP))
    if 'asd_app.document_sync_core_r143' in sys.modules:
        del sys.modules['asd_app.document_sync_core_r143']
    from asd_app.document_sync_core_r143 import reconcile_all,truth
    actions=reconcile_all(conn)
    giulia=conn.execute("SELECT * FROM tesserati WHERE lower(cognome)='di francia' AND lower(nome)='giulia' LIMIT 1").fetchone()
    giulia_truth=truth(conn,giulia) if giulia else {}
    giulia_docs=[dict(x) for x in conn.execute("""SELECT id,doc_type,categoria,titolo,filename,data_scadenza,visibile,status,source,inbound_id
      FROM documenti WHERE tesserato_id=? ORDER BY id""",(int(giulia['id']),)).fetchall()] if giulia else []
    integ=str(conn.execute('PRAGMA integrity_check').fetchone()[0]);fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:conn.close()

print('[r144-reconcile] backup='+str(backup)+' cleanup='+json.dumps(cleanup,ensure_ascii=False)+
      ' actions='+json.dumps(actions[-40:],ensure_ascii=False,default=str)+
      ' giulia_truth='+json.dumps(giulia_truth,ensure_ascii=False)+
      ' giulia_docs='+json.dumps(giulia_docs,ensure_ascii=False),flush=True)
if integ.lower()!='ok' or fk:raise RuntimeError('R144 DB integrity failed')

# Existing failed R143 candidate already installed the safe direct per-athlete
# upload route and documents-page entry point. Require them; do not add a second
# route with the same URL.
core=CORE.read_text(encoding='utf-8',errors='replace')
if "BODYMIND_R143_DOCUMENT_ASSOCIATION_SYNC" not in core or "/mobile/atleta/<int:tid>/documenti/carica" not in core:
    raise RuntimeError('R144 direct athlete upload route missing from runtime core')
if "r143-upload-from-docs" not in core:
    old="<p>Archivio operativo. “Elimina” nasconde il record ma conserva il file fisico.</p></div><a class='r138-back' href='/mobile/atleta/{tid}'>Scheda</a>"
    new="<p>Archivio operativo.</p><a id='r143-upload-from-docs' style='display:inline-block;margin-top:9px;padding:9px 11px;border-radius:10px;background:#166534;color:#fff;text-decoration:none;font-weight:900' href='/mobile/atleta/{tid}/documenti/carica'>＋ Carica documento</a></div><a class='r138-back' href='/mobile/atleta/{tid}'>Scheda</a>"
    if old in core:
        shutil.copy2(CORE,BACK/'core.py')
        core=core.replace(old,new,1)
        CORE.write_text(core,encoding='utf-8');py_compile.compile(str(CORE),doraise=True)

# Fresh-process QA, read-only HTTP.
qa=r'''
import sqlite3,sys
sys.path.insert(0,"/data/top2_app")
import app as _full
from asd_app.core import app
from asd_app.document_sync_core_r143 import truth
app.config["TESTING"]=True
c=app.test_client()
with c.session_transaction() as s:
    s.update({"logged":True,"logged_in":True,"username":"admin","display_name":"R144 QA","role":"admin","tenant_slug":"default","user_id":1,"is_admin":True,"admin":True,"_csrf_token":"r144"})
conn=sqlite3.connect("/data/tenants/default/asd.db");conn.row_factory=sqlite3.Row
try:
    g=conn.execute("SELECT * FROM tesserati WHERE lower(cognome)='di francia' AND lower(nome)='giulia' LIMIT 1").fetchone()
    tr=truth(conn,g) if g else {}
    visible_med=conn.execute("""SELECT id,filename,data_scadenza FROM documenti
      WHERE tesserato_id=? AND coalesce(visibile,1)=1 AND lower(coalesce(doc_type,''))='certificato_medico' ORDER BY id DESC""",(int(g['id']),)).fetchall() if g else []
    integ=str(conn.execute("PRAGMA integrity_check").fetchone()[0]);fk=len(conn.execute("PRAGMA foreign_key_check").fetchall())
finally:conn.close()
u=c.get("/mobile/atleta/"+str(int(g['id']))+"/documenti/carica") if g else None
docs=c.get("/mobile/atleta/"+str(int(g['id']))+"/documenti") if g else None
checks={
 "giulia_recovered":bool(g and visible_med and tr.get("med_present")),
 "giulia_expiry":bool(tr.get("expiry")=="2027-03-27"),
 "upload_route":bool(u and u.status_code==200 and "Certificato medico" in u.get_data(as_text=True) and "Modulo Unico" in u.get_data(as_text=True)),
 "documents_upload_link":bool(docs and docs.status_code==200 and "Carica documento" in docs.get_data(as_text=True)),
 "db":integ.lower()=="ok" and fk==0,
}
print("[r144-selftest] "+repr(checks)+" truth="+repr(tr)+" visible_med="+repr([dict(x) for x in visible_med]),flush=True)
if not all(checks.values()):raise RuntimeError("R144 QA failed "+repr(checks))
'''
proc=subprocess.run([sys.executable,'-c',qa],capture_output=True,text=True,timeout=120)
print((proc.stdout or '').strip(),flush=True)
if proc.returncode!=0:
    raise RuntimeError('R144 child QA failed '+((proc.stderr or '')+(proc.stdout or ''))[-5000:])
print('[r144-selftest-main] PASS operator/autopilot association recovery direct-upload current-truth db-ok',flush=True)
