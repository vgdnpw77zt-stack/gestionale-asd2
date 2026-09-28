# R24 read-only production audit trigger
from __future__ import annotations
from pathlib import Path
import ast, json, re, sqlite3, unicodedata

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MEDIA=Path('/data/tenants/default/media')
ACTIVE=('needs_manual_match','associato_tipo_da_verificare','richiede_conferma','needs_review','da_verificare','pending')

def emit(tag, value):
    if not isinstance(value,str):
        value=json.dumps(value,ensure_ascii=False,sort_keys=True,default=str)
    print(f'[audit-r24-{tag}] {value}',flush=True)

def has_table(conn,name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() is not None

def cols_full(conn,name):
    return [
        {'name':r[1],'type':r[2],'notnull':r[3],'default':r[4],'pk':r[5]}
        for r in conn.execute(f'PRAGMA table_info({name})').fetchall()
    ]

def dist(conn,table,col):
    rows=conn.execute(f"SELECT CASE WHEN {col} IS NULL THEN 'NULL' ELSE CAST({col} AS TEXT) END v,COUNT(*) n FROM {table} GROUP BY CASE WHEN {col} IS NULL THEN 'NULL' ELSE CAST({col} AS TEXT) END ORDER BY v").fetchall()
    return {str(r[0]):int(r[1]) for r in rows}

def resolve_doc(raw):
    txt=str(raw or '').replace('\\','/').strip()
    if not txt:
        return None
    p=Path(txt)
    if p.is_absolute():
        try:
            rp=p.resolve()
            mr=MEDIA.resolve()
            if rp==mr or mr in rp.parents:
                return rp
            return None
        except Exception:
            return None
    try:
        return (MEDIA / p.as_posix().lstrip('/')).resolve()
    except Exception:
        return None

def norm(v):
    s=unicodedata.normalize('NFKD',str(v or ''))
    s=''.join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return ''.join(ch for ch in s if ch.isalnum())

emit('begin',{'app':str(APP),'db':str(DB),'media':str(MEDIA)})
emit('markers',sorted(p.name for p in APP.glob('.BODYMIND*') if p.is_file()))

# Syntax-only source audit: ast.parse does not write pyc files.
syntax_bad=[]
pyfiles=list((APP/'asd_app').rglob('*.py'))
for p in pyfiles:
    try:
        ast.parse(p.read_text(encoding='utf-8',errors='replace'),filename=str(p))
    except Exception as exc:
        syntax_bad.append({'file':str(p.relative_to(APP)),'error':f'{type(exc).__name__}:{exc}'})
emit('syntax',{'files':len(pyfiles),'errors':syntax_bad})

uri='file:'+str(DB)+'?mode=ro'
conn=sqlite3.connect(uri,uri=True,timeout=30); conn.row_factory=sqlite3.Row
try:
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=conn.execute('PRAGMA foreign_key_check').fetchall()
    tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
    emit('db',{'integrity':integrity,'foreign_key_issues':len(fk),'tables':len(tables)})

    counts={}
    for t in ('tesserati','documenti','inbound_documents','pagamenti','ricevute','onboarding_document_requests','minori','users'):
        if has_table(conn,t):
            counts[t]=int(conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0])
    emit('counts',counts)

    for t in ('tesserati','minori','documenti','inbound_documents','onboarding_document_requests'):
        if has_table(conn,t):
            emit('schema-'+t,cols_full(conn,t))

    # Discover every potentially relevant persistence field, rather than assuming names.
    kw=re.compile(r'(consens|privacy|liberat|immag|foto|guardian|tutor|genitor|delega|uscita|autoriz|minor|medical|medic|certif|onboard|regol)',re.I)
    relevant={}
    for t in tables:
        names=[x['name'] for x in cols_full(conn,t)]
        hit=[c for c in names if kw.search(c)]
        if hit:
            relevant[t]=hit
    emit('relevant-columns',relevant)

    if has_table(conn,'tesserati'):
        tc={x['name'] for x in cols_full(conn,'tesserati')}
        flag_names=['consenso_informato','liberatoria_immagini','manleva_firmata','iscrizione_firmata','documenti_onboarding_ok','privacy_ok','liberatoria_ok','regolamento_ok']
        emit('tesserati-flag-dist',{c:dist(conn,'tesserati',c) for c in flag_names if c in tc})

    if has_table(conn,'minori'):
        mc={x['name'] for x in cols_full(conn,'minori')}
        flag_names=['consenso_firmato','autorizzazioni_ok','delega_ritiro_ok','uscita_autonoma_ok','data_consenso','note_consenso']
        emit('minori-flag-dist',{c:dist(conn,'minori',c) for c in flag_names if c in mc})
        sel=[c for c in ['id','tesserato_id','consenso_firmato','autorizzazioni_ok','delega_ritiro_ok','uscita_autonoma_ok','data_consenso','note_consenso'] if c in mc]
        emit('minori-rows',[dict(r) for r in conn.execute('SELECT '+','.join(sel)+' FROM minori ORDER BY id').fetchall()])

    # Exact state of the operational document queue and the two known physical files.
    if has_table(conn,'inbound_documents'):
        ic={x['name'] for x in cols_full(conn,'inbound_documents')}
        vals=','.join('?' for _ in ACTIVE)
        pending=[dict(r) for r in conn.execute(f"SELECT * FROM inbound_documents WHERE LOWER(COALESCE(status,'')) IN ({vals}) AND COALESCE(deleted_at,'')='' ORDER BY id",ACTIVE).fetchall()]
        slim=[]
        keep=['id','status','original_filename','saved_path','document_type','document_confidence','tesserato_id','matched_tesserato_id','suggested_tesserato_id','match_score','match_action','deleted_at']
        for r in pending:
            slim.append({k:r.get(k) for k in keep if k in r})
        emit('pending',slim)
        for did in (33,38):
            r=conn.execute('SELECT * FROM inbound_documents WHERE id=?',(did,)).fetchone()
            if not r: continue
            d=dict(r)
            raw=str(d.get('saved_path') or '')
            rp=resolve_doc(raw)
            emit('inbound-'+str(did),{
                'status':d.get('status'),'file':d.get('original_filename'),'saved_path':raw,
                'raw_exists':Path(raw).is_file() if raw else False,
                'resolved':str(rp) if rp else None,'resolved_exists':bool(rp and rp.is_file()),
                'document_type':d.get('document_type'),'document_confidence':d.get('document_confidence'),
                'tesserato_id':d.get('tesserato_id'),'matched_tesserato_id':d.get('matched_tesserato_id'),
                'suggested_tesserato_id':d.get('suggested_tesserato_id'),'match_score':d.get('match_score'),
                'match_action':d.get('match_action')
            })

    # Candidate uniqueness evidence for Ferlan/Pimpinelli.
    if has_table(conn,'tesserati'):
        rows=conn.execute("SELECT id,nome,cognome FROM tesserati ORDER BY id").fetchall()
        for surname in ('Ferlan','Pimpinelli'):
            key=norm(surname)
            matches=[{'id':int(r['id']),'nome':str(r['nome'] or ''),'cognome':str(r['cognome'] or '')} for r in rows if norm(r['cognome'])==key]
            emit('surname-'+surname.lower(),matches)

    # Resolve historical dossier paths using the actual media-root semantics.
    if has_table(conn,'documenti'):
        dc={x['name'] for x in cols_full(conn,'documenti')}
        where="WHERE COALESCE(visibile,1)=1" if 'visibile' in dc else ''
        rows=conn.execute(f"SELECT * FROM documenti {where} ORDER BY id").fetchall()
        raw_missing=[]; resolved_missing=[]; resolved_ok=[]
        for r in rows:
            d=dict(r); raw=str(d.get('filename') or '')
            if raw and not Path(raw).is_file():
                raw_missing.append(int(d['id']))
            rp=resolve_doc(raw)
            if raw and rp and rp.is_file():
                if not Path(raw).is_file():
                    resolved_ok.append(int(d['id']))
            elif raw:
                resolved_missing.append(int(d['id']))
        emit('document-paths',{'visible':len(rows),'raw_missing':raw_missing,'resolved_ok_from_relative':resolved_ok,'truly_missing_after_resolver':resolved_missing})

    # Onboarding request status summary.
    if has_table(conn,'onboarding_document_requests'):
        oc={x['name'] for x in cols_full(conn,'onboarding_document_requests')}
        if 'status' in oc:
            emit('onboarding-status',dict((str(r[0]),int(r[1])) for r in conn.execute("SELECT COALESCE(status,'NULL'),COUNT(*) FROM onboarding_document_requests GROUP BY COALESCE(status,'NULL')").fetchall()))
finally:
    conn.close()

# Source-of-truth warning and flag logic from the current persistent runtime.
targets=[
    'asd_app/onboarding_flow.py',
    'asd_app/routes_a151_final_ops.py',
    'asd_app/routes_a202_operational_integrity.py',
    'asd_app/routes_documenti.py',
    'asd_app/routes_inbound_documents.py',
    'asd_app/athlete_matcher.py',
    'asd_app/document_classifier.py',
    'asd_app/medical_certificate_dates.py',
    'asd_app/routes_bodymind_final.py',
    'asd_app/routes_bodymind_fix49.py',
]
patterns=re.compile(r'(BODYMIND_R1[34678]|sync_unified_module_flags|recompute_onboarding_status|consenso_firmato|autorizzazioni_ok|delega_ritiro_ok|uscita_autonoma_ok|liberatoria_immagini|documenti_onboarding_ok|privacy_ok|regolamento_ok|issues\.append|mancant|warning|document_abs_path|match_action|auto_save|richiede_conferma|92|78|service-worker|manifest)',re.I)
for rel in targets:
    p=APP/rel
    if not p.is_file():
        emit('source-missing',rel)
        continue
    lines=p.read_text(encoding='utf-8',errors='replace').splitlines()
    hits=[]
    for i,line in enumerate(lines,1):
        if patterns.search(line):
            hits.append(f'{i}:{line.strip()}')
    emit('source-'+p.name, hits[:220])

# Static/PWA files relevant to iPhone/Safari.
static_checks={}
for rel in ('static/pwa/service-worker.js','static/pwa/sw.js','static/pwa/manifest.json','static/pwa/icon-192.svg','static/pwa/icon-512.svg'):
    q=APP/rel
    static_checks[rel]={'exists':q.is_file(),'size':q.stat().st_size if q.is_file() else 0}
emit('pwa-files',static_checks)
emit('end','OK')
