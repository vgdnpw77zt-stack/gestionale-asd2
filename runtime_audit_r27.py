from __future__ import annotations
from pathlib import Path
import ast, os, re, sqlite3, sys
from collections import Counter, defaultdict

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MEDIA=Path('/data/tenants/default/media')
MARKER=APP/'.BODYMIND_AUDIT_R27_DONE'

def emit(tag,val):
    print('[audit-r27-'+tag+'] '+repr(val), flush=True)

def table_exists(conn,name):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())

def cols(conn,name):
    return {str(r[1]) for r in conn.execute('PRAGMA table_info('+name+')').fetchall()} if table_exists(conn,name) else set()

def file_exists(raw):
    s=str(raw or '').strip()
    if not s:
        return False
    p=Path(s)
    candidates=[p] if p.is_absolute() else [MEDIA/p,APP/p,Path('/data')/p]
    for q in candidates:
        try:
            if q.exists() and q.is_file():
                return True
        except Exception:
            pass
    try:
        hits=[x for x in MEDIA.rglob(p.name) if x.is_file()] if p.name else []
        return len(hits)==1
    except Exception:
        return False

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')
if MARKER.exists():
    emit('skip','already completed')
    raise SystemExit(0)

py_files=list((APP/'asd_app').rglob('*.py'))
syntax=[]
for p in py_files:
    try:
        ast.parse(p.read_text(encoding='utf-8',errors='replace'),filename=str(p))
    except Exception as exc:
        syntax.append((str(p.relative_to(APP)),str(exc)))
emit('syntax',{'files':len(py_files),'errors':syntax[:20]})

missing=Counter()
srcs=defaultdict(list)
pattern=re.compile(r"(?:src|href)=[\"'](/static/[^\"'?#< >]+)")
for p in list(APP.rglob('*.py'))+list(APP.rglob('*.html'))+list(APP.rglob('*.jinja'))+list(APP.rglob('*.js')):
    try:
        txt=p.read_text(encoding='utf-8',errors='ignore')
    except Exception:
        continue
    for m in pattern.finditer(txt):
        ref=m.group(1)
        if '{{' in ref or '{%' in ref:
            continue
        if not (APP/ref.lstrip('/')).exists():
            missing[ref]+=1
            if len(srcs[ref])<4:
                srcs[ref].append(str(p.relative_to(APP))+':'+str(txt[:m.start()].count('\n')+1))
emit('static-missing',[{'ref':k,'count':v,'sources':srcs[k]} for k,v in missing.most_common(30)])
emit('static-known',{
    'demo_wow':(APP/'static/demo/demo_wow.js').exists(),
    'favicon':(APP/'static/favicon.ico').exists(),
    'manifest':any((APP/'static').glob('*manifest*')) if (APP/'static').exists() else False,
    'sw_root':(APP/'service-worker.js').exists(),
    'sw_static':(APP/'static/service-worker.js').exists()
})

conn=sqlite3.connect(str(DB),timeout=20)
conn.row_factory=sqlite3.Row
try:
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=conn.execute('PRAGMA foreign_key_check').fetchall()
    tables=[str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
    key=['tesserati','minori','documenti','inbound_documents','onboarding_document_requests','pagamenti','ricevute','users','firme','document_hub']
    counts={t:(int(conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]) if table_exists(conn,t) else None) for t in key}
    emit('db',{'integrity':integrity,'fk_issues':len(fk),'tables':len(tables),'counts':counts})

    zero=[]
    for t in tables:
        try:
            if int(conn.execute('SELECT COUNT(*) FROM "'+t+'"').fetchone()[0])==0:
                zero.append(t)
        except Exception:
            pass
    emit('zero-tables',zero)

    if table_exists(conn,'inbound_documents'):
        ic=cols(conn,'inbound_documents')
        st=conn.execute("SELECT lower(coalesce(status,'')) s,COUNT(*) n FROM inbound_documents GROUP BY 1 ORDER BY n DESC").fetchall()
        emit('inbound-status',{str(r['s']):int(r['n']) for r in st})
        vals=('needs_manual_match','associato_tipo_da_verificare','richiede_conferma','needs_review','da_verificare','pending')
        ph=','.join('?' for _ in vals)
        extra=" AND coalesce(deleted_at,'')=''" if 'deleted_at' in ic else ''
        rows=conn.execute("SELECT * FROM inbound_documents WHERE lower(coalesce(status,'')) IN ("+ph+")"+extra+" ORDER BY id",vals).fetchall()
        pending=[]
        for r in rows:
            raw=r['saved_path'] if 'saved_path' in r.keys() else ''
            pending.append({
                'id':int(r['id']),
                'status':str(r['status'] or ''),
                'type':str(r['document_type'] or '') if 'document_type' in r.keys() else '',
                'tid':int(r['tesserato_id'] or 0) if 'tesserato_id' in r.keys() else 0,
                'file_ok':file_exists(raw),
                'name':str(r['original_filename'] or '') if 'original_filename' in r.keys() else ''
            })
        emit('pending',pending)
        if 'sha256' in ic:
            rows=conn.execute("SELECT sha256,COUNT(*) n,GROUP_CONCAT(id) ids FROM inbound_documents WHERE coalesce(sha256,'')<>'' GROUP BY sha256 HAVING COUNT(*)>1 ORDER BY n DESC").fetchall()
            emit('inbound-sha-dups',[{'sha':str(r['sha256'])[:16],'n':int(r['n']),'ids':str(r['ids'])} for r in rows[:30]])

    if table_exists(conn,'documenti'):
        dc=cols(conn,'documenti')
        clause="coalesce(visibile,1)=1" if 'visibile' in dc else '1=1'
        docs=conn.execute('SELECT * FROM documenti WHERE '+clause+' ORDER BY id').fetchall()
        missing_docs=[]
        for r in docs:
            raw=r['filename'] if 'filename' in r.keys() else ''
            if raw and not file_exists(raw):
                missing_docs.append(int(r['id']))
        emit('document-paths',{'visible':len(docs),'missing_after_resolver':missing_docs})

        mu_parts=[]
        if 'doc_type' in dc:
            mu_parts.append("lower(coalesce(doc_type,''))='modulo_unico_tesseramento'")
        if 'categoria' in dc:
            mu_parts.append("lower(coalesce(categoria,'')) like '%modulo unico%'")
        if 'titolo' in dc:
            mu_parts.append("lower(coalesce(titolo,'')) like '%modulo unico%'")
        if mu_parts and 'tesserato_id' in dc and table_exists(conn,'tesserati'):
            sc="lower(coalesce(status,'')) in ('verificato','salvato','associato')" if 'status' in dc else '1=1'
            mu=conn.execute("SELECT * FROM documenti WHERE ("+' OR '.join(mu_parts)+") AND "+sc+" AND coalesce(tesserato_id,0)>0").fetchall()
            tc=cols(conn,'tesserati')
            coverage=['consenso_informato','manleva_firmata','iscrizione_firmata','documenti_onboarding_ok','privacy_ok','liberatoria_ok','regolamento_ok']
            bad=[]
            for r in mu:
                tid=int(r['tesserato_id'])
                tr=conn.execute('SELECT * FROM tesserati WHERE id=?',(tid,)).fetchone()
                miss=[f for f in coverage if f in tc and (not tr or int(tr[f] or 0)!=1)]
                if miss:
                    bad.append({'doc':int(r['id']),'tid':tid,'flags':miss})
            emit('mu-coverage',{'docs':len(mu),'inconsistent':bad})

    if table_exists(conn,'onboarding_document_requests'):
        oc=cols(conn,'onboarding_document_requests')
        if {'status','accepted_by','document_type'}.issubset(oc):
            rows=conn.execute("SELECT lower(coalesce(status,'')) status,lower(coalesce(accepted_by,'')) accepted_by,lower(coalesce(document_type,'')) dtype,COUNT(*) n FROM onboarding_document_requests GROUP BY 1,2,3 ORDER BY n DESC").fetchall()
            emit('onboarding-status',[dict(r) for r in rows])
            auto=int(conn.execute("SELECT COUNT(*) FROM onboarding_document_requests WHERE lower(coalesce(document_type,''))='modulo_unico_tesseramento' AND lower(coalesce(accepted_by,''))='autopilot' AND lower(coalesce(status,'')) IN ('accepted','manual_accepted')").fetchone()[0])
            emit('unsafe-auto-mu',auto)

    if table_exists(conn,'minori'):
        mc=cols(conn,'minori')
        wanted=[x for x in ('tesserato_id','consenso_firmato','autorizzazioni_ok','delega_ritiro_ok','uscita_autonoma_ok','data_consenso') if x in mc]
        if wanted:
            rows=conn.execute('SELECT '+','.join(wanted)+' FROM minori ORDER BY id').fetchall()
            emit('minori-flags',[{k:r[k] for k in wanted} for r in rows])

    if table_exists(conn,'tesserati'):
        tc=cols(conn,'tesserati')
        emit('tesserati-cert-cols',sorted([x for x in tc if 'cert' in x.lower() or 'medic' in x.lower()]))
        fields=[x for x in ('nome','cognome','codice_fiscale','email','telefono','data_nascita','genitore','telefono_genitore','email_genitore') if x in tc]
        empties={f:int(conn.execute("SELECT COUNT(*) FROM tesserati WHERE trim(coalesce(CAST("+f+" AS TEXT),''))=''").fetchone()[0]) for f in fields}
        emit('tesserati-empty-fields',empties)
finally:
    conn.close()

os.chdir(APP)
sys.path.insert(0,str(APP))
try:
    import app as app_module
    flask_app=app_module.app
    exact=defaultdict(list)
    groups=Counter()
    for rule in flask_app.url_map.iter_rules():
        methods=tuple(sorted(m for m in rule.methods if m not in ('HEAD','OPTIONS')))
        exact[(str(rule.rule),methods)].append(str(rule.endpoint))
        first=(str(rule.rule).strip('/').split('/',1)[0] or '/')
        groups[first]+=1
    dup=[{'rule':k[0],'methods':k[1],'endpoints':v} for k,v in exact.items() if len(v)>1]
    emit('routes',{'total':sum(groups.values()),'groups':groups.most_common(40),'exact_duplicates':dup[:50]})
    cfg=flask_app.config
    emit('security',{
        'secret_key_present':bool(cfg.get('SECRET_KEY')),
        'session_cookie_secure':cfg.get('SESSION_COOKIE_SECURE'),
        'session_cookie_httponly':cfg.get('SESSION_COOKIE_HTTPONLY'),
        'session_cookie_samesite':cfg.get('SESSION_COOKIE_SAMESITE'),
        'csrf_enabled':cfg.get('WTF_CSRF_ENABLED','unset'),
        'extensions':sorted(list(getattr(flask_app,'extensions',{}).keys()))
    })
except Exception as exc:
    emit('route-import-error',repr(exc))

for rel in ('asd_app/core.py','asd_app/routes_a202_operational_integrity.py','asd_app/routes_bodymind_fix22.py','asd_app/routes_documenti.py'):
    p=APP/rel
    if not p.exists():
        continue
    lines=p.read_text(encoding='utf-8',errors='replace').splitlines()
    hits=[]
    for i,line in enumerate(lines,1):
        if any(tok in line for tok in ('nav_link(','nav_dropdown(','/documenti-automatici','/document-hub','/generatore-documenti','/firma-smart','/cuore-operativo','/risolvi-automatico','demo_wow.js')):
            hits.append(str(i)+':'+line.strip()[:240])
    emit('source-'+rel.replace('/','-').replace('.','-'),hits[:120])

MARKER.write_text('BodyMind audit R27 completed\n',encoding='utf-8')
emit('done','PASS')
