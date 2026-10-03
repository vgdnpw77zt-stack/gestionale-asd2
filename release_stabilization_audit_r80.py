# -*- coding: utf-8 -*-
from __future__ import annotations
import hashlib, json, os, re, shutil, sqlite3, tempfile
from datetime import date, datetime
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

def table(conn,name):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())

def cols(conn,name):
    return {str(r[1]) for r in conn.execute("PRAGMA table_info("+name+")").fetchall()} if table(conn,name) else set()

def norm(v):
    s=str(v or '').strip().lower()
    s=s.replace('à','a').replace('è','e').replace('é','e').replace('ì','i').replace('ò','o').replace('ù','u')
    return re.sub(r'[^a-z0-9]+','',s)

def iso(v):
    raw=str(v or '').strip()[:10]
    for fmt in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y','%d.%m.%Y'):
        try: return datetime.strptime(raw,fmt).date().isoformat()
        except Exception: pass
    return ''

def age(v):
    d=iso(v)
    if not d: return None
    born=date.fromisoformat(d); today=date.today()
    return today.year-born.year-((today.month,today.day)<(born.month,born.day))

def is_mu_row(r):
    ks=set(r.keys())
    hay=' '.join(str(r[k] or '').lower() for k in ('doc_type','categoria','titolo','original_filename','filename') if k in ks)
    return (
      'modulo_unico_tesseramento' in hay or 'modulo unico' in hay or 'modulo_unico' in hay
      or 'modulo iscrizione' in hay or 'domanda iscrizione' in hay or 'iscrizione manleva' in hay
    )

def canonical_kind(r):
    ks=set(r.keys())
    hay=' '.join(str(r[k] or '').lower() for k in ('doc_type','categoria','titolo','original_filename','filename') if k in ks)
    if is_mu_row(r): return 'modulo_unico_tesseramento'
    if 'certificato_medico' in hay or 'certificato medico' in hay: return 'certificato_medico'
    return str(r['doc_type'] or r['categoria'] or 'altro').strip().lower() if ('doc_type' in ks or 'categoria' in ks) else 'altro'

def read_analysis(conn,source_table,source_id):
    if not table(conn,'bodymind_document_semantics'): return None
    row=conn.execute("""SELECT analysis_json FROM bodymind_document_semantics
      WHERE source_table=? AND source_id=? ORDER BY id DESC LIMIT 1""",(source_table,int(source_id))).fetchone()
    if not row: return None
    try:
        a=json.loads(str(row['analysis_json'] or '{}'))
        return a if isinstance(a,dict) else None
    except Exception:
        return None

report={}
conn=sqlite3.connect(str(DB),timeout=45); conn.row_factory=sqlite3.Row
try:
    tables=[str(x[0]) for x in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
    report['tables']=tables
    counts={}
    for tn in ('tesserati','documenti','inbound_documents','minori','bodymind_document_semantics',
               'bodymind_duplicate_records_archive','bodymind_operator_tasks','bodymind_operator_actions',
               'pagamenti','payments','ricevute','receipts','quote_mensili','payment_requests','payment_notifications'):
        if table(conn,tn):
            counts[tn]=int(conn.execute('SELECT COUNT(*) FROM '+tn).fetchone()[0])
    report['counts']=counts

    # Anagrafiche: duplicates by CF and by exact identity tuple.
    tcols=cols(conn,'tesserati')
    duplicate_cf=[]
    if 'codice_fiscale' in tcols:
        rows=conn.execute("""SELECT upper(replace(replace(trim(codice_fiscale),' ',''),'-','')) cf,
             COUNT(*) n, group_concat(id) ids
             FROM tesserati
             WHERE trim(coalesce(codice_fiscale,''))<>''
             GROUP BY upper(replace(replace(trim(codice_fiscale),' ',''),'-',''))
             HAVING COUNT(*)>1""").fetchall()
        duplicate_cf=[dict(x) for x in rows]
    report['duplicate_cf']=duplicate_cf

    identity={}
    for r in conn.execute('SELECT * FROM tesserati ORDER BY id').fetchall():
        key=(norm(r['nome'] if 'nome' in r.keys() else ''),norm(r['cognome'] if 'cognome' in r.keys() else ''),iso(r['data_nascita'] if 'data_nascita' in r.keys() else ''))
        if key[0] and key[1] and key[2]:
            identity.setdefault(key,[]).append(int(r['id']))
    report['duplicate_identity']=[{'key':list(k),'ids':v} for k,v in identity.items() if len(v)>1]

    # Minor/guardian coherence.
    minor_issues=[]; multiple_minor=[]; orphan_minor=[]
    if table(conn,'minori'):
        mcols=cols(conn,'minori')
        if 'tesserato_id' in mcols:
            rows=conn.execute("""SELECT tesserato_id,COUNT(*) n,group_concat(id) ids
              FROM minori GROUP BY tesserato_id HAVING COUNT(*)>1""").fetchall()
            multiple_minor=[dict(x) for x in rows]
            rows=conn.execute("""SELECT m.id,m.tesserato_id FROM minori m
              LEFT JOIN tesserati t ON t.id=m.tesserato_id WHERE t.id IS NULL""").fetchall()
            orphan_minor=[dict(x) for x in rows]
    report['multiple_minor_rows']=multiple_minor
    report['orphan_minor_rows']=orphan_minor

    athletes=conn.execute('SELECT * FROM tesserati ORDER BY id').fetchall()
    for a in athletes:
        ks=set(a.keys()); tid=int(a['id'])
        a_age=age(a['data_nascita'] if 'data_nascita' in ks else '')
        flagged=bool(int(a['minorenne'] or 0)) if 'minorenne' in ks else False
        should_minor=(a_age is not None and a_age<18)
        guardian=''
        for k in ('genitore','nome_genitore'):
            if k in ks and a[k]:
                guardian=str(a[k]).strip()
                if guardian: break
        gphone=''
        for k in ('telefono_genitore','guardian_phone'):
            if k in ks and a[k]:
                gphone=str(a[k]).strip()
                if gphone: break
        if should_minor!=flagged and a_age is not None:
            minor_issues.append({'tid':tid,'name':(str(a['nome'] or '')+' '+str(a['cognome'] or '')).strip(),'issue':'minor_flag_mismatch','age':a_age,'flag':flagged})
        if (should_minor or flagged) and (not guardian or not gphone):
            minor_issues.append({'tid':tid,'name':(str(a['nome'] or '')+' '+str(a['cognome'] or '')).strip(),'issue':'guardian_or_phone_missing','guardian':guardian,'phone':gphone})
    report['minor_guardian_issues']=minor_issues

    # Documents and MU invariants.
    visible_docs=[]
    if table(conn,'documenti'):
        dcols=cols(conn,'documenti')
        vis=' WHERE coalesce(visibile,1)=1' if 'visibile' in dcols else ''
        visible_docs=conn.execute('SELECT * FROM documenti'+vis+' ORDER BY tesserato_id,id').fetchall()
    mu_by_tid={}; doc_orphans=[]; wrong_mu_meta=[]; inbound_ref_orphans=[]; visible_hash_dupes=[]
    for d in visible_docs:
        tid=int(d['tesserato_id'] or 0) if 'tesserato_id' in d.keys() else 0
        if tid<=0 or not conn.execute('SELECT 1 FROM tesserati WHERE id=?',(tid,)).fetchone():
            doc_orphans.append({'id':int(d['id']),'tid':tid,'title':str(d['titolo'] or '') if 'titolo' in d.keys() else ''})
        if is_mu_row(d):
            mu_by_tid.setdefault(tid,[]).append(int(d['id']))
            dtype=str(d['doc_type'] or '').strip().lower() if 'doc_type' in d.keys() else ''
            cat=str(d['categoria'] or '').strip().lower() if 'categoria' in d.keys() else ''
            if dtype!='modulo_unico_tesseramento' or 'modulo iscrizione' not in cat:
                wrong_mu_meta.append({'id':int(d['id']),'tid':tid,'doc_type':dtype,'categoria':cat})
        if 'inbound_id' in d.keys() and int(d['inbound_id'] or 0)>0:
            iid=int(d['inbound_id'])
            if not conn.execute('SELECT 1 FROM inbound_documents WHERE id=?',(iid,)).fetchone():
                inbound_ref_orphans.append({'document_id':int(d['id']),'inbound_id':iid})

    report['visible_mu_duplicates']=[{'tid':tid,'document_ids':ids} for tid,ids in mu_by_tid.items() if tid>0 and len(ids)>1]
    report['visible_mu_metadata_incoherent']=wrong_mu_meta
    report['orphan_documents']=doc_orphans
    report['document_inbound_orphans']=inbound_ref_orphans

    # File-level duplicate check among active same-athlete/same-type docs.
    hash_groups={}
    for d in visible_docs:
        tid=int(d['tesserato_id'] or 0) if 'tesserato_id' in d.keys() else 0
        path=''
        for k in ('filename','saved_path'):
            if k in d.keys() and d[k]:
                path=str(d[k]); break
        p=Path(path)
        if not p.is_file():
            continue
        try:
            h=hashlib.sha256(p.read_bytes()).hexdigest()
        except Exception:
            continue
        key=(tid,canonical_kind(d),h)
        hash_groups.setdefault(key,[]).append(int(d['id']))
    report['visible_exact_file_duplicates']=[
      {'tid':k[0],'type':k[1],'sha256':k[2],'document_ids':v}
      for k,v in hash_groups.items() if len(v)>1
    ]

    # Inbound integrity and duplicate residue.
    inbound_issues=[]; duplicate_status_rows=[]; inbound_orphans=[]
    if table(conn,'inbound_documents'):
        ic=cols(conn,'inbound_documents')
        rows=conn.execute('SELECT * FROM inbound_documents ORDER BY id').fetchall()
        dupstates={'duplicate_exact','duplicato_confermato','duplicato_non_importato','duplicate_confirmed','semantic_duplicate_archived','duplicate_archived'}
        for r in rows:
            iid=int(r['id']); tid=int(r['tesserato_id'] or 0) if 'tesserato_id' in r.keys() else 0
            st=str(r['status'] or '').strip().lower() if 'status' in r.keys() else ''
            if tid>0 and not conn.execute('SELECT 1 FROM tesserati WHERE id=?',(tid,)).fetchone():
                inbound_orphans.append({'id':iid,'tid':tid,'status':st})
            if st in dupstates:
                duplicate_status_rows.append({'id':iid,'tid':tid,'status':st,'type':str(r['document_type'] or '') if 'document_type' in r.keys() else ''})
            dtype=str(r['document_type'] or '').strip().lower() if 'document_type' in r.keys() else ''
            conf=int(r['document_confidence'] or 0) if 'document_confidence' in r.keys() else 0
            match=int(r['match_score'] or 0) if 'match_score' in r.keys() else 0
            if dtype=='modulo_unico_tesseramento' and tid>0 and conf>=95 and match>=95:
                if not mu_by_tid.get(tid):
                    inbound_issues.append({'id':iid,'tid':tid,'issue':'trusted_mu_inbound_without_visible_mu','confidence':conf,'match':match})
        report['inbound_orphans']=inbound_orphans
        report['duplicate_status_remaining']=duplicate_status_rows
        report['trusted_inbound_without_visible_mu']=inbound_issues

    # Onboarding vs dossier truth.
    onboarding_issues=[]
    for a in athletes:
        tid=int(a['id']); ks=set(a.keys()); has_mu=bool(mu_by_tid.get(tid))
        if 'iscrizione_firmata' in ks:
            flag=bool(int(a['iscrizione_firmata'] or 0))
            if has_mu and not flag:
                onboarding_issues.append({'tid':tid,'issue':'mu_present_but_iscrizione_firmata_0'})
            if flag and not has_mu:
                onboarding_issues.append({'tid':tid,'issue':'iscrizione_firmata_1_but_no_visible_mu'})
        if 'documenti_onboarding_ok' in ks and has_mu and not bool(int(a['documenti_onboarding_ok'] or 0)):
            onboarding_issues.append({'tid':tid,'issue':'mu_present_but_documenti_onboarding_ok_0'})
    report['onboarding_consistency']=onboarding_issues

    # Operator task/action residue.
    stale_tasks=[]
    if table(conn,'bodymind_operator_tasks'):
        rows=conn.execute("""SELECT id,status,task_type,created_at,updated_at FROM bodymind_operator_tasks
          WHERE status IN ('active','awaiting_confirmation') ORDER BY id""").fetchall()
        stale_tasks=[dict(x) for x in rows]
    stale_actions=[]
    if table(conn,'bodymind_operator_actions'):
        ac=cols(conn,'bodymind_operator_actions')
        if 'status' in ac:
            rows=conn.execute("""SELECT id,status,action_type,created_at FROM bodymind_operator_actions
              WHERE status IN ('pending','awaiting_confirmation') ORDER BY id""").fetchall()
            stale_actions=[dict(x) for x in rows]
    report['open_operator_tasks']=stale_tasks
    report['open_operator_actions']=stale_actions
    stale_active_batch=[]
    if table(conn,'bodymind_operator_tasks'):
        try:
            clauses=["t.task_type='batch_upload'","t.status='active'","julianday(t.updated_at) < julianday('now','-6 hours')"]
            if table(conn,'bodymind_operator_upload_jobs'):
                clauses.append("NOT EXISTS (SELECT 1 FROM bodymind_operator_upload_jobs j WHERE j.conversation_id=t.conversation_id AND j.status IN ('queued','processing'))")
            if table(conn,'bodymind_operator_actions'):
                clauses.append("NOT EXISTS (SELECT 1 FROM bodymind_operator_actions a WHERE a.conversation_id=t.conversation_id AND a.status IN ('proposed','pending','awaiting_confirmation'))")
            rows=conn.execute("""SELECT t.id,t.conversation_id,t.task_type,t.status,t.created_at,t.updated_at
              FROM bodymind_operator_tasks t WHERE """+" AND ".join(clauses)+" ORDER BY t.id").fetchall()
            stale_active_batch=[dict(x) for x in rows]
        except Exception:
            stale_active_batch=[]
    report['stale_active_batch_uploads']=stale_active_batch

    # Payments/receipts/competence tables basic referential checks.
    finance={}
    for tn in ('pagamenti','payments','ricevute','receipts','quote_mensili','payment_requests','payment_notifications'):
        if not table(conn,tn): continue
        tc=cols(conn,tn)
        entry={'count':int(conn.execute('SELECT COUNT(*) FROM '+tn).fetchone()[0])}
        if 'tesserato_id' in tc:
            entry['orphan_tesserato_ids']=[dict(x) for x in conn.execute(
              'SELECT x.id,x.tesserato_id FROM '+tn+' x LEFT JOIN tesserati t ON t.id=x.tesserato_id WHERE x.tesserato_id IS NOT NULL AND t.id IS NULL'
            ).fetchall()]
        finance[tn]=entry
    report['finance']=finance

    # Replay simulation using cached canonical MU semantics.
    from asd_app import enrollment_ingest_core_r65 as ingest
    replay_cases=[]
    for tid,docids in sorted(mu_by_tid.items()):
        if tid<=0: continue
        analysis=None; source=''
        for did in reversed(docids):
            analysis=read_analysis(conn,'documenti',did)
            if analysis:
                source='documenti:'+str(did); break
        if not analysis and table(conn,'inbound_documents'):
            ir=conn.execute("""SELECT id FROM inbound_documents
              WHERE tesserato_id=? AND lower(coalesce(document_type,''))='modulo_unico_tesseramento'
              ORDER BY match_score DESC,document_confidence DESC,id DESC""",(tid,)).fetchall()
            for rr in ir:
                analysis=read_analysis(conn,'inbound_documents',int(rr['id']))
                if analysis:
                    source='inbound_documents:'+str(rr['id']); break
        if analysis:
            found,reason=ingest.find_existing_athlete(conn,analysis)
            replay_cases.append({
              'expected_tid':tid,'resolved_tid':int(found['id']) if found else None,'reason':reason,
              'source':source,'valid_cf_ready':bool(ingest.enrollment_identity_ready(analysis,require_valid_cf=True))
            })
    replay30=[]
    if replay_cases:
        for i in range(30):
            c=replay_cases[i%len(replay_cases)]
            replay30.append({'n':i+1,**c})
    report['mu_replay_cases']=replay_cases
    report['mu_replay_30_failures']=[x for x in replay30 if x['resolved_tid']!=x['expected_tid']]

    # New-athlete creation idempotency on a temporary copy only.
    tmp='/tmp/bodymind_r80_sim.db'
    try:
        if os.path.exists(tmp): os.unlink(tmp)
        src=sqlite3.connect(str(DB),timeout=30); dst=sqlite3.connect(tmp)
        try: src.backup(dst)
        finally: dst.close(); src.close()
        tc=sqlite3.connect(tmp); tc.row_factory=sqlite3.Row
        try:
            base15='ZZZYYY00A01H501'
            total=0
            for idx,ch in enumerate(base15,start=1):
                total += ingest._ODD[ch] if idx%2==1 else ingest._EVEN[ch]
            cf=base15+chr(ord('A')+(total%26))
            fake={
              'document_type':'modulo_unico_tesseramento','confidence':.99,
              'first_name':'QAUTO','last_name':'BODYMIND','birth_date':'2000-01-01',
              'codice_fiscale':cf,'email':'qa-auto@example.invalid'
            }
            first=ingest.create_athlete_from_analysis(tc,fake,source='r80_sim',require_valid_cf=True)
            tc.commit()
            second=ingest.create_athlete_from_analysis(tc,fake,source='r80_sim_repeat',require_valid_cf=True)
            tc.commit()
            sim_count=int(tc.execute("SELECT COUNT(*) FROM tesserati WHERE codice_fiscale=?",(cf,)).fetchone()[0]) if 'codice_fiscale' in cols(tc,'tesserati') else 0
            report['new_athlete_temp_simulation']={'cf':cf,'first':first,'second':second,'rows_with_cf':sim_count}
        finally:
            tc.close()
    finally:
        try: os.unlink(tmp)
        except Exception: pass

    report['integrity']=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    report['foreign_keys']=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:
    conn.close()

# Static/runtime architecture markers.
markers={}
files={
 'operator':APP/'asd_app/routes_operator_bodymind.py',
 'coherence':APP/'asd_app/routes_document_coherence_r41.py',
 'documents':APP/'asd_app/routes_documenti.py',
 'mu_core':APP/'asd_app/verified_mu_sync_core_r68.py',
}
for name,p in files.items():
    txt=p.read_text(encoding='utf-8',errors='replace') if p.exists() else ''
    markers[name]={
      'exists':p.exists(),
      'r74_autocreate':'BODYMIND_R74_AUTOCREATE_STRICT_CF' in txt,
      'r78_autonomous':'BODYMIND_R78_AUTONOMOUS_SAFE_DOCUMENT_PRODUCTION' in txt,
      'r79_self_canonical':'BODYMIND_R79_SELF_CANONICAL' in txt,
      'r74_iphone_composer':'BODYMIND_R74_IPHONE_COMPOSER' in txt,
      'r74_tutela':'BODYMIND_R74_TUTELA_FROM_MU' in txt,
      'r75_hide_archived':'BODYMIND_R75_HIDE_ARCHIVED_DOCS' in txt,
      'r81_visible_docs':'BODYMIND_R81_VISIBLE_DOCS_ONLY' in txt,
      'r73_cf_gate':'BODYMIND_R73_HARD_CF_CONFLICT_GATE' in txt,
      'r82_guardian_convergence':'BODYMIND_R82_GUARDIAN_CONVERGENCE' in txt,
    }
report['runtime_markers']=markers

severity={
 'duplicate_cf':len(report.get('duplicate_cf') or []),
 'duplicate_identity':len(report.get('duplicate_identity') or []),
 'multiple_minor_rows':len(report.get('multiple_minor_rows') or []),
 'orphan_minor_rows':len(report.get('orphan_minor_rows') or []),
 'visible_mu_duplicates':len(report.get('visible_mu_duplicates') or []),
 'visible_exact_file_duplicates':len(report.get('visible_exact_file_duplicates') or []),
 'visible_mu_metadata_incoherent':len(report.get('visible_mu_metadata_incoherent') or []),
 'orphan_documents':len(report.get('orphan_documents') or []),
 'document_inbound_orphans':len(report.get('document_inbound_orphans') or []),
 'inbound_orphans':len(report.get('inbound_orphans') or []),
 'duplicate_status_remaining':len(report.get('duplicate_status_remaining') or []),
 'onboarding_consistency':len(report.get('onboarding_consistency') or []),
 'mu_replay_30_failures':len(report.get('mu_replay_30_failures') or []),
 'stale_operator_confirmations':(
    len([x for x in (report.get('open_operator_tasks') or []) if str(x.get('status') or '')=='awaiting_confirmation'])
    if not (report.get('open_operator_actions') or []) else 0
 ),
 'stale_active_batch_uploads':len(report.get('stale_active_batch_uploads') or []),
 'orphan_payment_requests':len(((report.get('finance') or {}).get('payment_requests') or {}).get('orphan_tesserato_ids') or []),
}
report['severity_counts']=severity

print('[r80-stabilization-audit] '+json.dumps(report,ensure_ascii=False,default=str),flush=True)
print('[r80-audit-summary] '+json.dumps({
 'counts':report.get('counts'),'severity':severity,'integrity':report.get('integrity'),
 'foreign_keys':report.get('foreign_keys'),
 'new_athlete_sim':report.get('new_athlete_temp_simulation')
},ensure_ascii=False,default=str),flush=True)

if report.get('integrity','').lower()!='ok' or report.get('foreign_keys'):
    raise RuntimeError('R80 database integrity gate failed')

if sum(int(v or 0) for v in severity.values())!=0:
    raise RuntimeError('R80 structural regression gate failed: '+json.dumps(severity,ensure_ascii=False))

sim=report.get('new_athlete_temp_simulation') or {}
first=sim.get('first') or {}; second=sim.get('second') or {}
if not (first.get('created') is True and second.get('existing') is True and int(sim.get('rows_with_cf') or 0)==1):
    raise RuntimeError('R80 new-athlete idempotency regression: '+json.dumps(sim,ensure_ascii=False,default=str))

required_markers={
  'operator_autocreate':bool(markers.get('operator',{}).get('r74_autocreate')),
  'operator_autonomous':bool(markers.get('operator',{}).get('r78_autonomous')),
  'operator_self_canonical':bool(markers.get('operator',{}).get('r79_self_canonical')),
  'iphone_composer':bool(markers.get('operator',{}).get('r74_iphone_composer')),
  'tutela_from_mu':bool(markers.get('coherence',{}).get('r74_tutela')),
  'visible_docs_only':bool(markers.get('documents',{}).get('r81_visible_docs')),
  'hard_cf_conflict':bool(markers.get('mu_core',{}).get('r73_cf_gate')),
  'guardian_convergence':bool(markers.get('mu_core',{}).get('r82_guardian_convergence')),
}
missing=[k for k,v in required_markers.items() if not v]
if missing:
    raise RuntimeError('R80 architecture regression gate failed: '+repr(missing))

print('[r80-selftest] PASS HARD-GATE structural-zero temp-db-new-athlete-idempotency 30x-MU-replay shared-markers',flush=True)
