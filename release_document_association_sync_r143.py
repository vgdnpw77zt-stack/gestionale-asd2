# -*- coding: utf-8 -*-
from __future__ import annotations
import json, py_compile, shutil, sqlite3, subprocess, sys
from pathlib import Path
from datetime import datetime

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
CORE=APP/'asd_app/core.py'
MOD=APP/'asd_app/document_sync_core_r143.py'
BACK=Path('/data/release_backups/20261004_r143_document_sync')
BACK.mkdir(parents=True,exist_ok=True)
if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

# Backup before any data mutation.
stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
backup=BACK/(stamp+'_pre_r143.db')
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
    for fmt in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y','%Y/%m/%d'):
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
    canonical_root=(MEDIA/'tesserati'/str(int(tid))).resolve()
    try:
        if canonical_root==fp.parent.resolve() or canonical_root in fp.resolve().parents:
            return fp.resolve()
    except Exception:pass
    canonical_root.mkdir(parents=True,exist_ok=True)
    safe=Path(str(original or fp.name)).name.replace('/','_').replace('\\','_')
    dest=canonical_root/(datetime.now().strftime('%Y-%m-%d_%H%M%S')+'_R143_'+safe)
    if not dest.exists(): shutil.copy2(fp,dest)
    return dest.resolve()

def _doc_expiry(conn,doc):
    fp=resolve_file(doc['filename'])
    sh=sha256_file(fp)
    candidates=[]
    try:candidates.append(doc['data_scadenza'])
    except Exception:pass
    sm=_semantic(conn,'documenti',int(doc['id']),sh)
    an=sm.get('analysis') or {}
    candidates.extend([an.get('expiry_date'),an.get('valid_until'),an.get('scadenza')])
    try:iid=int(doc['inbound_id'] or 0)
    except Exception:iid=0
    if iid:
        sm2=_semantic(conn,'inbound_documents',iid,sh)
        an2=sm2.get('analysis') or {}
        candidates.extend([an2.get('expiry_date'),an2.get('valid_until'),an2.get('scadenza')])
    for v in candidates:
        iso=iso_date(v)
        if iso:return iso
    return ''

def sync_document(conn,doc_id):
    doc=conn.execute("SELECT * FROM documenti WHERE id=?",(int(doc_id),)).fetchone()
    if not doc:return {'ok':False,'reason':'missing_document'}
    tid=int(doc['tesserato_id'] or 0)
    if tid<=0:return {'ok':False,'reason':'missing_athlete'}
    fp=resolve_file(doc['filename'])
    if not fp:return {'ok':False,'reason':'missing_file','document_id':int(doc_id),'tid':tid}
    sh=sha256_file(fp)
    sm=_semantic(conn,'documenti',int(doc_id),sh)
    dtype=canonical_type(doc)
    if dtype=='altro' and sm.get('document_type'):
        dtype=canonical_type(sm.get('document_type'))
    try:iid=int(doc['inbound_id'] or 0)
    except Exception:iid=0
    inbound=None
    if iid and _table(conn,'inbound_documents'):
        inbound=conn.execute("SELECT * FROM inbound_documents WHERE id=?",(iid,)).fetchone()
        if inbound and dtype=='altro':
            dtype=canonical_type(inbound)
    persistent=_ensure_persistent(tid,fp,doc['original_filename'] if 'original_filename' in doc.keys() else fp.name)
    dc=_cols(conn,'documenti'); sets=[]; vals=[]
    cat,label=TYPE_META.get(dtype,TYPE_META['altro'])
    def add(k,v):
        if k in dc: sets.append(k+'=?'); vals.append(v)
    add('filename',str(persistent))
    add('doc_type',dtype)
    add('categoria',cat)
    add('visibile',1)
    if 'status' in dc and str(doc['status'] or '').lower() not in ('verificato','salvato'):
        add('status','salvato')
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
        vals.append(int(doc_id)); conn.execute("UPDATE documenti SET "+','.join(sets)+" WHERE id=?",tuple(vals))
    if dtype=='modulo_unico_tesseramento':
        tc=_cols(conn,'tesserati'); up=[]; uv=[]
        for k in ('iscrizione_firmata','documenti_onboarding_ok'):
            if k in tc:up.append(k+'=?');uv.append(1)
        if up:
            uv.append(tid);conn.execute("UPDATE tesserati SET "+','.join(up)+" WHERE id=?",tuple(uv))
    elif dtype=='liberatoria_immagini':
        tc=_cols(conn,'tesserati')
        if 'liberatoria_immagini' in tc:conn.execute("UPDATE tesserati SET liberatoria_immagini=1 WHERE id=?",(tid,))
    return {'ok':True,'document_id':int(doc_id),'tid':tid,'type':dtype,'expiry':expiry,'sha':sh}

def materialize_inbound(conn,inbound_id):
    if not _table(conn,'inbound_documents') or not _table(conn,'documenti'):return {'ok':False,'reason':'tables_missing'}
    r=conn.execute("SELECT * FROM inbound_documents WHERE id=?",(int(inbound_id),)).fetchone()
    if not r:return {'ok':False,'reason':'inbound_missing'}
    status=str(r['status'] or '').strip().lower()
    try:conf=float(r['document_confidence'] or 0)
    except Exception:conf=0
    try:match=float(r['match_score'] or 0)
    except Exception:match=0
    trusted=status in ('accepted','manual_accepted','verificato','archived_to_tesserato','resolved','associato','duplicato_risolto') and (status!='associato' or (conf>=80 and match>=80))
    if not trusted:return {'ok':False,'reason':'not_trusted','status':status}
    tid=int(r['tesserato_id'] or 0)
    if tid<=0:return {'ok':False,'reason':'no_athlete'}
    dtype=canonical_type(r)
    if dtype=='altro':return {'ok':False,'reason':'unsupported_type'}
    fp=resolve_file(r['saved_path'] if 'saved_path' in r.keys() else '')
    if not fp:return {'ok':False,'reason':'missing_file'}
    persistent=_ensure_persistent(tid,fp,r['original_filename'] if 'original_filename' in r.keys() else fp.name)
    sh=sha256_file(persistent)

    # Exact duplicate only within same athlete + same semantic type.
    existing=[]
    for d in conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1 ORDER BY id",(tid,)).fetchall():
        if canonical_type(d)!=dtype:continue
        ef=resolve_file(d['filename'])
        if ef and sha256_file(ef)==sh:
            existing.append(d)
    if existing:
        d=existing[0]; dc=_cols(conn,'documenti')
        if 'inbound_id' in dc and not int(d['inbound_id'] or 0):
            conn.execute("UPDATE documenti SET inbound_id=? WHERE id=?",(int(inbound_id),int(d['id'])))
        result=sync_document(conn,int(d['id']))
        result.update({'duplicate':True,'inbound_id':int(inbound_id)})
        return result

    dc=_cols(conn,'documenti')
    cat,label=TYPE_META.get(dtype,TYPE_META['altro'])
    values={
      'tesserato_id':tid,'titolo':str(r['original_filename'] or label) if 'original_filename' in r.keys() else label,
      'categoria':cat,'filename':str(persistent),
      'original_filename':str(r['original_filename'] or persistent.name) if 'original_filename' in r.keys() else persistent.name,
      'data_caricamento':datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
      'data_scadenza':'','note':'R143 materializzato da inbound associato','visibile':1,
      'tipo_template':'inbound_auto','tenant_id':'default','doc_type':dtype,
      'confidence':conf,'match_score':match,'source':'association_sync_r143','status':'salvato','inbound_id':int(inbound_id)
    }
    ks=[k for k in values if k in dc]
    conn.execute("INSERT INTO documenti("+','.join(ks)+") VALUES("+','.join('?' for _ in ks)+")",[values[k] for k in ks])
    did=int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    result=sync_document(conn,did)
    result.update({'created':True,'inbound_id':int(inbound_id)})
    return result

def reconcile_all(conn):
    actions=[]
    if _table(conn,'inbound_documents'):
        for r in conn.execute("SELECT id FROM inbound_documents WHERE coalesce(tesserato_id,0)>0 ORDER BY id").fetchall():
            try:
                res=materialize_inbound(conn,int(r['id']))
                if res.get('ok'):actions.append(res)
            except Exception as exc:
                actions.append({'ok':False,'inbound_id':int(r['id']),'error':repr(exc)[:180]})
    if _table(conn,'documenti'):
        for r in conn.execute("SELECT id FROM documenti WHERE coalesce(visibile,1)=1 AND coalesce(tesserato_id,0)>0 ORDER BY id").fetchall():
            try:
                res=sync_document(conn,int(r['id']))
                if res.get('ok'):actions.append(res)
            except Exception as exc:
                actions.append({'ok':False,'document_id':int(r['id']),'error':repr(exc)[:180]})

    # Profile certificate expiry must come from CURRENT visible physical medical evidence.
    if _table(conn,'tesserati') and _table(conn,'documenti'):
        for a in conn.execute("SELECT id FROM tesserati ORDER BY id").fetchall():
            tid=int(a['id']); expiries=[]
            for d in conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1",(tid,)).fetchall():
                if canonical_type(d)!='certificato_medico' or not resolve_file(d['filename']):continue
                exp=_doc_expiry(conn,d)
                if exp:expiries.append(exp)
            wanted=max(expiries) if expiries else ''
            tc=_cols(conn,'tesserati')
            if 'certificato_scadenza' in tc:
                conn.execute("UPDATE tesserati SET certificato_scadenza=? WHERE id=?",(wanted,tid))
    conn.commit()
    return actions

def truth(conn,row):
    tid=int(row['id']); today=date.today()
    docs=conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1",(tid,)).fetchall()
    mu=any(canonical_type(d)=='modulo_unico_tesseramento' and resolve_file(d['filename']) for d in docs)
    meds=[d for d in docs if canonical_type(d)=='certificato_medico' and resolve_file(d['filename'])]
    expiries=[_doc_expiry(conn,d) for d in meds]; expiries=[x for x in expiries if x]
    exp=max(expiries) if expiries else ''
    med_present=bool(meds); med_ok=False; med_state='Manca'; med_detail='Certificato medico mancante'
    if med_present and exp:
        try:
            ed=datetime.strptime(exp,'%Y-%m-%d').date()
            med_ok=ed>=today
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

# Reconcile all existing associations now.
sys.path.insert(0,str(APP))
from asd_app.document_sync_core_r143 import reconcile_all,truth
conn=sqlite3.connect(str(DB),timeout=60);conn.row_factory=sqlite3.Row
try:
    actions=reconcile_all(conn)
    giulia=conn.execute("SELECT * FROM tesserati WHERE lower(cognome)='di francia' AND lower(nome)='giulia' LIMIT 1").fetchone()
    giulia_truth=truth(conn,giulia) if giulia else {}
    giulia_docs=[dict(x) for x in conn.execute("SELECT id,doc_type,categoria,titolo,filename,data_scadenza,visibile,status,inbound_id FROM documenti WHERE tesserato_id=? ORDER BY id",(int(giulia['id']),)).fetchall()] if giulia else []
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0]);fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:conn.close()
print('[r143-reconcile] backup='+str(backup)+' actions='+str(len(actions))+' giulia_truth='+json.dumps(giulia_truth,ensure_ascii=False)+' giulia_docs='+json.dumps(giulia_docs,ensure_ascii=False),flush=True)
if integrity.lower()!='ok' or fk:raise RuntimeError('R143 DB integrity failed')

# Append canonical manual upload + immediate post-association reconcile + authoritative mobile profile.
core=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R143_DOCUMENT_ASSOCIATION_SYNC' not in core:
    shutil.copy2(CORE,BACK/'core.py')
    core += r'''

# BODYMIND_R143_DOCUMENT_ASSOCIATION_SYNC
def _r143_sync_now():
    try:
        from .document_sync_core_r143 import reconcile_all as _sync
        conn=db();conn.row_factory=sqlite3.Row
        try:return _sync(conn)
        finally:conn.close()
    except Exception as exc:
        print('[r143-sync-warning] '+repr(exc),flush=True)
        return []

@app.after_request
def _bodymind_r143_post_association_sync(resp):
    try:
        p=(request.path or '').lower()
        if request.method=='POST' and any(k in p for k in ('operatore-bodymind','autopilot','inbound','documenti','documento')):
            _r143_sync_now()
    except Exception as exc:
        print('[r143-after-upload-warning] '+repr(exc),flush=True)
    return resp

@app.route('/mobile/atleta/<int:tid>/documenti/carica',methods=['GET','POST'])
@admin_required
def bodymind_r143_direct_document_upload(tid):
    from pathlib import Path as _P
    from datetime import datetime as _DT
    from werkzeug.utils import secure_filename as _secure
    from .document_sync_core_r143 import canonical_type as _ctype,sha256_file as _sha,resolve_file as _resolve,sync_document as _syncdoc
    conn=db();conn.row_factory=sqlite3.Row
    try:
        athlete=conn.execute("SELECT * FROM tesserati WHERE id=?",(tid,)).fetchone()
        if not athlete:abort(404)
        if request.method=='POST':
            up=request.files.get('file')
            dtype=str(request.form.get('tipo') or '').strip().lower()
            allowed={'modulo_unico_tesseramento','certificato_medico','liberatoria_immagini','altro'}
            if dtype not in allowed:return redirect('/mobile/atleta/'+str(tid)+'/documenti/carica?error=tipo')
            if not up or not getattr(up,'filename',''):return redirect('/mobile/atleta/'+str(tid)+'/documenti/carica?error=file')
            ext=_P(up.filename).suffix.lower()
            if ext not in ('.pdf','.png','.jpg','.jpeg','.webp','.docx'):
                return redirect('/mobile/atleta/'+str(tid)+'/documenti/carica?error=formato')
            ddir=_P('/data/tenants/default/media/tesserati')/str(tid);ddir.mkdir(parents=True,exist_ok=True)
            name=_secure(up.filename) or ('documento'+ext)
            dest=ddir/(_DT.now().strftime('%Y-%m-%d_%H%M%S')+'_manual_'+name)
            up.save(str(dest))
            digest=_sha(dest)
            # Exact duplicate only within same athlete + same semantic type.
            for old in conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1",(tid,)).fetchall():
                if _ctype(old)!=dtype:continue
                fp=_resolve(old['filename'])
                if fp and _sha(fp)==digest:
                    try:dest.unlink()
                    except Exception:pass
                    return redirect('/mobile/atleta/'+str(tid)+'/documenti?duplicate=1')
            meta={
              'modulo_unico_tesseramento':('Modulo iscrizione BodyMind','Modulo Unico'),
              'certificato_medico':('Certificato medico','Certificato medico'),
              'liberatoria_immagini':('Liberatoria immagini','Liberatoria immagini'),
              'altro':('Documenti ASD','Documento')
            }
            cat,label=meta[dtype]
            scad=str(request.form.get('scadenza') or '').strip() if dtype=='certificato_medico' else ''
            dc={str(x[1]) for x in conn.execute('PRAGMA table_info(documenti)').fetchall()}
            values={'tesserato_id':tid,'titolo':name,'categoria':cat,'filename':str(dest),'original_filename':name,
                    'data_caricamento':_DT.now().strftime('%Y-%m-%d %H:%M:%S'),'data_scadenza':scad,'note':'Caricamento manuale dalla scheda atleta',
                    'visibile':1,'tipo_template':'manuale_atleta','tenant_id':'default','doc_type':dtype,
                    'confidence':100,'match_score':100,'source':'manuale_atleta','status':'salvato','inbound_id':None}
            ks=[k for k in values if k in dc]
            conn.execute("INSERT INTO documenti("+','.join(ks)+") VALUES("+','.join('?' for _ in ks)+")",[values[k] for k in ks])
            did=int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            _syncdoc(conn,did);conn.commit()
            _r143_sync_now()
            return redirect('/mobile/atleta/'+str(tid)+'/documenti?uploaded=1')
    finally:
        if request.method!='POST':
            conn.close()
        else:
            try:conn.close()
            except Exception:pass
    name=(str(athlete['cognome'] or '')+' '+str(athlete['nome'] or '')).strip()
    err=request.args.get('error') or ''
    msg={'tipo':'Seleziona il tipo documento.','file':'Seleziona un file.','formato':'Formato non supportato.'}.get(err,'')
    return f"""<!doctype html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'><title>Carica documento</title>
    <style>body{{margin:0;background:#071426;color:#eef6ff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}}main{{max-width:620px;margin:auto;padding:18px}}.box{{background:#0b1d33;border:1px solid #27445f;border-radius:20px;padding:18px}}h1{{margin:0 0 5px}}p{{color:#a9b9cb}}label{{display:block;margin-top:13px;font-weight:900}}select,input{{width:100%;min-height:48px;margin-top:6px;border-radius:12px;border:1px solid #315475;background:#081727;color:#fff;padding:10px}}button,.back{{display:block;width:100%;margin-top:14px;padding:13px;border:0;border-radius:12px;background:#166534;color:#fff;text-align:center;text-decoration:none;font-weight:950}}.back{{background:#163b5f}}.err{{background:#7f1d1d;padding:10px;border-radius:10px}}</style></head><body><main><div class='box'><small>DOCUMENTO ATLETA</small><h1>{e(name)}</h1>{("<div class='err'>"+e(msg)+"</div>" if msg else "")}
    <form method='post' enctype='multipart/form-data'>{csrf_input()}<label>Tipo documento<select name='tipo' required><option value=''>Seleziona…</option><option value='certificato_medico'>Certificato medico</option><option value='modulo_unico_tesseramento'>Modulo Unico</option><option value='liberatoria_immagini'>Liberatoria immagini</option><option value='altro'>Altro documento</option></select></label><label>File<input type='file' name='file' accept='.pdf,.png,.jpg,.jpeg,.webp,.docx' required></label><label>Scadenza certificato (solo se nota)<input type='date' name='scadenza'></label><button type='submit'>Carica e associa a {e(name)}</button></form><a class='back' href='/mobile/atleta/{tid}'>Annulla</a></div></main></body></html>"""

@app.after_request
def _bodymind_r143_mobile_profile_truth(resp):
    try:
        import re as _re
        from html import escape as _e
        from .document_sync_core_r143 import truth as _truth
        m=_re.fullmatch(r'/mobile/atleta/(\d+)/?',request.path or '')
        if request.method!='GET' or not m or request.args.get('advanced')=='1' or int(getattr(resp,'status_code',200) or 200)!=200:
            return resp
        tid=int(m.group(1));conn=db();conn.row_factory=sqlite3.Row
        try:
            row=conn.execute("SELECT * FROM tesserati WHERE id=?",(tid,)).fetchone()
            if not row:return resp
            tr=_truth(conn,row)
        finally:conn.close()
        nm=(str(row['cognome'] or '')+' '+str(row['nome'] or '')).strip()
        course=str(row['corso'] or 'Corso non indicato')
        states=[
          ('Modulo Unico','OK' if tr['mu'] else 'Manca','Presente e apribile' if tr['mu'] else 'Modulo Unico mancante','ok' if tr['mu'] else 'bad'),
          ('Certificato',tr['med_state'],tr['med_detail'],'ok' if tr['med_ok'] else ('warn' if tr['med_present'] else 'bad')),
          ('Mensile','OK' if tr['monthly'] else 'Manca','Pagamento mese corrente','ok' if tr['monthly'] else 'bad'),
          ('Tesseramento','OK' if tr['enroll'] else 'Manca','Quota stagione corrente','ok' if tr['enroll'] else 'bad'),
        ]
        if tr['minor']:
            states.append(('Tutela','OK' if tr['tutela'] else 'Manca','Completa' if tr['tutela'] else ('Non valida senza MU' if not tr['mu'] else 'Genitore/contatto/consenso incompleto'),'ok' if tr['tutela'] else 'bad'))
        cards=''.join("<div class='st "+tone+"'><i></i><div><b>"+_e(label)+"</b><small>"+_e(detail)+"</small></div><strong>"+_e(state)+"</strong></div>" for label,state,detail,tone in states)
        overall='REGOLARE' if tr['overall'] else 'DA COMPLETARE'
        html=f"""<!doctype html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'><title>{_e(nm)}</title><style>body{{margin:0;background:#071426;color:#eef6ff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}}main{{max-width:650px;margin:auto;padding:16px 14px 95px}}.head{{padding:18px;border-radius:20px;background:#0d2036;border:1px solid #203b57}}.head h1{{margin:4px 0}}.head p{{margin:0;color:#9fb3ca}}.overall{{display:inline-block;margin-top:10px;padding:8px 11px;border-radius:999px;background:{'#14532d' if tr['overall'] else '#7f1d1d'};font-weight:950}}.st{{display:grid;grid-template-columns:12px 1fr auto;gap:10px;align-items:center;padding:14px;margin-top:9px;border-radius:15px;background:#0b1b2e;border:1px solid #1d3651}}.st i{{width:11px;height:11px;border-radius:50%;background:#dc2626}}.st.ok i{{background:#16a34a}}.st.warn i{{background:#f59e0b}}.st small{{display:block;color:#91a6bd;margin-top:3px}}.st strong{{color:#fca5a5}}.st.ok strong{{color:#86efac}}.st.warn strong{{color:#fde68a}}.actions{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}}.actions a{{padding:12px;border-radius:13px;background:#163b5f;color:white;text-decoration:none;text-align:center;font-weight:900}}</style></head><body><main><section class='head'><small>ATLETA</small><h1>{_e(nm)}</h1><p>{_e(course)}</p><span class='overall'>{overall}</span></section>{cards}<div class='actions'><a href='/mobile/atleta/{tid}?advanced=1'>Modifica dati</a><a href='/mobile/atleta/{tid}/documenti'>Documenti</a><a href='/mobile/atleta/{tid}/documenti/carica'>Carica documento</a><a href='/pagamenti?tesserato_id={tid}'>Pagamenti</a><a href='/mobile/atlete'>Atlete</a><a href='/mobile'>Home</a></div></main></body></html>"""
        resp.set_data(html);resp.headers['Content-Type']='text/html; charset=utf-8'
    except Exception as exc:
        print('[r143-profile-warning] '+repr(exc),flush=True)
    return resp
'''
    CORE.write_text(core,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r143-core] installed association sync + direct athlete upload + truthful profile',flush=True)
else:
    print('[r143-core] already present',flush=True)

# Patch the R138 document page to expose upload directly from Documents as well.
core=CORE.read_text(encoding='utf-8',errors='replace')
if "r143-upload-from-docs" not in core:
    old="<p>Archivio operativo. “Elimina” nasconde il record ma conserva il file fisico.</p></div><a class='r138-back' href='/mobile/atleta/{tid}'>Scheda</a>"
    new="<p>Archivio operativo.</p><a id='r143-upload-from-docs' style='display:inline-block;margin-top:9px;padding:9px 11px;border-radius:10px;background:#166534;color:#fff;text-decoration:none;font-weight:900' href='/mobile/atleta/{tid}/documenti/carica'>＋ Carica documento</a></div><a class='r138-back' href='/mobile/atleta/{tid}'>Scheda</a>"
    if old in core:
        core=core.replace(old,new,1)
        CORE.write_text(core,encoding='utf-8');py_compile.compile(str(CORE),doraise=True)
        print('[r143-doc-page] upload button installed',flush=True)
    else:
        print('[r143-doc-page] R138 anchor not found; profile upload route remains available',flush=True)

# Fresh-process smoke on current data, no POST mutation.
qa=r'''
import sqlite3,sys
sys.path.insert(0,"/data/top2_app")
import app as _full
from asd_app.core import app
app.config["TESTING"]=True
c=app.test_client()
with c.session_transaction() as s:
    s.update({"logged":True,"logged_in":True,"username":"admin","display_name":"R143 QA","role":"admin","tenant_slug":"default","user_id":1,"is_admin":True,"admin":True,"_csrf_token":"r143"})
p=c.get("/mobile/atleta/19")
u=c.get("/mobile/atleta/19/documenti/carica")
ph=p.get_data(as_text=True);uh=u.get_data(as_text=True)
checks={"profile":p.status_code==200 and "Modulo Unico" in ph and "Certificato" in ph and "Carica documento" in ph,
        "upload":u.status_code==200 and "Certificato medico" in uh and "Modulo Unico" in uh}
conn=sqlite3.connect("/data/tenants/default/asd.db");conn.row_factory=sqlite3.Row
try:
    d=conn.execute("SELECT * FROM documenti WHERE id=233").fetchone()
    checks["giulia_doc"]=bool(d and int(d["visibile"] or 0)==1 and str(d["doc_type"] or "")=="certificato_medico")
    checks["db"]=str(conn.execute("PRAGMA integrity_check").fetchone()[0]).lower()=="ok" and len(conn.execute("PRAGMA foreign_key_check").fetchall())==0
finally:conn.close()
print("[r143-selftest] "+repr(checks),flush=True)
if not all(checks.values()):raise RuntimeError("R143 QA failed "+repr(checks))
'''
proc=subprocess.run([sys.executable,'-c',qa],capture_output=True,text=True,timeout=120)
print((proc.stdout or '').strip(),flush=True)
if proc.returncode!=0:
    raise RuntimeError('R143 child QA failed '+((proc.stderr or '')+(proc.stdout or ''))[-5000:])
print('[r143-selftest-main] PASS canonical association sync manual upload truthful mobile profile db-ok',flush=True)
