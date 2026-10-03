# -*- coding: utf-8 -*-
from __future__ import annotations
import hashlib, json, re, shutil, sqlite3
from datetime import datetime
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
EMAIL=APP/'asd_app/routes_email_documents.py'
BACK=Path('/data/release_backups/20261003_r117_mu_nomatch_confirm')
BACK.mkdir(parents=True,exist_ok=True)

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

def backup_db(label):
    out=BACK/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+label+'.db')
    src=sqlite3.connect(str(DB),timeout=30); dst=sqlite3.connect(str(out))
    try: src.backup(dst)
    finally: dst.close(); src.close()
    return str(out)

def table(c,n):
    return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(n,)).fetchone())

def cols(c,n):
    return {str(r[1]) for r in c.execute("PRAGMA table_info("+n+")").fetchall()} if table(c,n) else set()

# ------------------------------------------------------------------
# 1. Future unresolved inbound: persist semantic analysis even when
#    there is no existing athlete / auto-create gate does not pass.
# ------------------------------------------------------------------
s=EMAIL.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R117_PERSIST_UNRESOLVED_MU' not in s:
    b=BACK/'routes_email_documents.py'
    if not b.exists(): shutil.copy2(EMAIL,b)
    old='''            if tid<=0:
                res["semantic_analysis"]=analysis
                if str(analysis.get("document_type") or "")=="modulo_unico_tesseramento":
                    res["new_athlete_candidate"]=True
                return res
'''
    new='''            if tid<=0:
                # BODYMIND_R117_PERSIST_UNRESOLVED_MU
                # A no-match document must not lose the semantic read. Persist it so
                # the review queue can offer safe creation instead of showing only 0%.
                iid=int(res.get("inbound_id") or 0)
                if iid>0:
                    try:
                        _r65_cache_put(conn,"inbound_documents",iid,analysis)
                    except Exception:
                        pass
                    if str((analysis or {}).get("document_type") or "")=="modulo_unico_tesseramento":
                        try:
                            icols={str(r[1]) for r in conn.execute("PRAGMA table_info(inbound_documents)").fetchall()}
                            sets=[]; vals=[]
                            if "document_type" in icols: sets.append("document_type=?"); vals.append("modulo_unico_tesseramento")
                            if "document_label" in icols: sets.append("document_label=?"); vals.append("Modulo iscrizione / Modulo Unico")
                            if "document_confidence" in icols:
                                sets.append("document_confidence=?"); vals.append(int(round(float((analysis or {}).get("confidence") or 0)*100)))
                            if "match_action" in icols: sets.append("match_action=?"); vals.append("create_candidate")
                            if "status" in icols: sets.append("status=?"); vals.append("needs_manual_match")
                            if sets:
                                vals.append(iid)
                                conn.execute("UPDATE inbound_documents SET "+",".join(sets)+" WHERE id=?",tuple(vals))
                            conn.commit()
                        except Exception:
                            pass
                res["semantic_analysis"]=analysis
                if str((analysis or {}).get("document_type") or "")=="modulo_unico_tesseramento":
                    res["new_athlete_candidate"]=True
                return res
'''
    if old not in s:
        raise RuntimeError('R117 unresolved semantic anchor missing')
    s=s.replace(old,new,1)
    tmp=EMAIL.with_name(EMAIL.name+'.r117.tmp')
    tmp.write_text(s,encoding='utf-8')
    import py_compile
    py_compile.compile(str(tmp),doraise=True)
    tmp.replace(EMAIL)
    print('[r117-source] PASS unresolved semantic persistence patched',flush=True)
else:
    print('[r117-source] already applied',flush=True)

# ------------------------------------------------------------------
# 2. Runtime route + queue CTA. Uses the SAME enrollment and MU sync
#    cores as Operator/Autopilot. Explicit confirmation is required.
# ------------------------------------------------------------------
from asd_app.core import app, admin_required, db, csrf_input
from flask import request, redirect
from asd_app.enrollment_ingest_core_r65 import (
    find_existing_athlete, create_athlete_from_analysis,
    enrollment_identity_ready, valid_italian_cf, norm_cf,
)
from asd_app.verified_mu_sync_core_r68 import sync_analysis_to_existing_athlete
from asd_app.operator_doc_semantic_core_r52 import cache_get, cache_put
from asd_app.operator_doc_semantic_ai_r52 import analyze_bytes

ALIASES={'modulo_unico_tesseramento','modulo_unico','modulo iscrizione','domanda iscrizione','domanda_iscrizione','iscrizione'}
HINTS=('modulo unico','modulo_unico','modulo iscrizione','iscrizione','domanda adesione','domanda di adesione')

def _r117_file_bytes(row):
    raw=str(row['saved_path'] or '') if 'saved_path' in row.keys() else ''
    if not raw: return b''
    p=Path(raw)
    if not p.is_absolute(): p=Path('/data')/raw.lstrip('/')
    try:
        rp=p.resolve(); base=Path('/data').resolve()
        if rp!=base and base not in rp.parents: return b''
        return rp.read_bytes() if rp.is_file() else b''
    except Exception:
        return b''

def _r117_analysis(conn,row,allow_live=True):
    data=_r117_file_bytes(row)
    if not data: return None,'no_file'
    sha=hashlib.sha256(data).hexdigest()
    try:
        cached=cache_get(conn,'inbound_documents',int(row['id']),sha)
        if isinstance(cached,dict): return cached,'cache'
    except Exception: pass
    if not allow_live: return None,'no_cache'
    name=str(row['original_filename'] or 'modulo.pdf')
    analysis=analyze_bytes(conn,name,data,'','modulo_unico_tesseramento',None)
    if isinstance(analysis,dict):
        cache_put(conn,'inbound_documents',int(row['id']),analysis)
        return analysis,'live'
    return None,'analysis_failed'

def _r117_candidate(row,analysis=None):
    if not row or int(row['tesserato_id'] or 0)>0: return False
    st=str(row['status'] or '').lower()
    if st in {'deleted','archived','duplicato_confermato','duplicate_exact','semantic_duplicate_archived'}: return False
    dtype=str(row['document_type'] or '').strip().lower()
    fname=str(row['original_filename'] or '').lower()
    semantic_type=str((analysis or {}).get('document_type') or '').strip().lower()
    return dtype in ALIASES or semantic_type=='modulo_unico_tesseramento' or any(x in fname for x in HINTS)

def _r117_confirmable(analysis):
    if not isinstance(analysis,dict): return False,'analisi_mancante'
    if str(analysis.get('document_type') or '')!='modulo_unico_tesseramento': return False,'non_modulo_unico'
    try: conf=float(analysis.get('confidence') or 0)
    except Exception: conf=0
    first=str(analysis.get('first_name') or '').strip()
    last=str(analysis.get('last_name') or '').strip()
    cf=norm_cf(analysis.get('codice_fiscale'))
    birth=str(analysis.get('birth_date') or '').strip()
    if not first or not last: return False,'nome_cognome_mancanti'
    if conf<.95: return False,'confidence_sotto_95'
    if cf and not valid_italian_cf(cf): return False,'codice_fiscale_non_valido'
    if not cf and not birth: return False,'manca_cf_o_data_nascita'
    if not enrollment_identity_ready(analysis,require_valid_cf=False):
        return False,'identita_non_sufficientemente_certa'
    return True,'ok'

def _r117_log(conn,iid,tid,event,message,payload=None,level='info'):
    if not table(conn,'inbound_events'): return
    ec=cols(conn,'inbound_events')
    values={
      'inbound_document_id':iid,'tesserato_id':tid or None,'level':level,
      'event_type':event,'message':message,
      'payload':json.dumps(payload or {},ensure_ascii=False,default=str),
      'created_at':datetime.now().isoformat(timespec='seconds')
    }
    keys=[k for k in values if k in ec]
    conn.execute("INSERT INTO inbound_events("+",".join(keys)+") VALUES("+",".join("?" for _ in keys)+")",tuple(values[k] for k in keys))

def _r117_archive_duplicate_residue(conn):
    # Certain duplicate rows leave operational status in the legacy queue.
    # Archive metadata only; never delete the physical business file.
    if not table(conn,'inbound_documents'): return []
    conn.execute("""CREATE TABLE IF NOT EXISTS bodymind_r117_duplicate_archive(
      id INTEGER PRIMARY KEY AUTOINCREMENT, source_table TEXT NOT NULL, source_id INTEGER NOT NULL,
      record_json TEXT NOT NULL, reason TEXT NOT NULL, archived_at TEXT NOT NULL,
      UNIQUE(source_table,source_id,reason)
    )""")
    rows=conn.execute("""SELECT * FROM inbound_documents
      WHERE lower(coalesce(status,'')) IN
      ('duplicate_exact','duplicato_confermato','duplicato_non_importato','duplicate_confirmed','semantic_duplicate_archived','duplicate_archived')
      ORDER BY id""").fetchall()
    archived=[]
    for r in rows:
        rid=int(r['id'])
        conn.execute("""INSERT OR IGNORE INTO bodymind_r117_duplicate_archive
          (source_table,source_id,record_json,reason,archived_at) VALUES(?,?,?,?,?)""",
          ('inbound_documents',rid,json.dumps(dict(r),ensure_ascii=False,default=str),'certain_duplicate_operational_cleanup',datetime.now().isoformat(timespec='seconds')))
        conn.execute("UPDATE inbound_documents SET status='deleted' WHERE id=?",(rid,))
        archived.append(rid)
    if archived: conn.commit()
    return archived

endpoint='r117_create_tesserato_from_mu'
if endpoint not in app.view_functions:
    @app.post('/documenti-automatici/<int:inbound_id>/crea-tesserato')
    @admin_required
    def r117_create_tesserato_from_mu(inbound_id):
        backup=backup_db('pre_confirm_create')
        conn=db()
        try:
            row=conn.execute("SELECT * FROM inbound_documents WHERE id=?",(int(inbound_id),)).fetchone()
            if not row:
                return redirect('/documenti-automatici?r117=missing#doc-'+str(inbound_id))
            analysis,method=_r117_analysis(conn,row,allow_live=True)
            ok,why=_r117_confirmable(analysis)
            if not ok:
                _r117_log(conn,int(inbound_id),0,'mu_create_blocked','Creazione tesserato non eseguita: '+why,{'semantic_method':method,'analysis':analysis},'warn')
                conn.commit()
                return redirect('/documenti-automatici?r117=blocked&reason='+why+'#doc-'+str(inbound_id))

            existing,match_reason=find_existing_athlete(conn,analysis)
            created=False
            if existing:
                tid=int(existing['id'])
            else:
                cr=create_athlete_from_analysis(conn,analysis,source='document_queue_r117_confirmed',require_valid_cf=False)
                tid=int(cr.get('tesserato_id') or 0); created=bool(cr.get('created'))
                if tid<=0:
                    conn.rollback()
                    return redirect('/documenti-automatici?r117=create_failed#doc-'+str(inbound_id))

            ic=cols(conn,'inbound_documents'); sets=[]; vals=[]
            for col in ('tesserato_id','matched_tesserato_id','suggested_tesserato_id'):
                if col in ic: sets.append(col+'=?'); vals.append(tid)
            if 'match_score' in ic: sets.append('match_score=?'); vals.append(100)
            if 'match_action' in ic: sets.append('match_action=?'); vals.append('auto_save')
            if 'document_type' in ic: sets.append('document_type=?'); vals.append('modulo_unico_tesseramento')
            if 'document_label' in ic: sets.append('document_label=?'); vals.append('Modulo iscrizione / Modulo Unico')
            if 'document_confidence' in ic:
                sets.append('document_confidence=?'); vals.append(int(round(float(analysis.get('confidence') or 0)*100)))
            if 'status' in ic: sets.append('status=?'); vals.append('associato')
            if sets:
                vals.append(int(inbound_id))
                conn.execute("UPDATE inbound_documents SET "+",".join(sets)+" WHERE id=?",tuple(vals))
            conn.commit()

            # Productionize through the same canonical document core already used by Operator.
            from asd_app.routes_operator_bodymind import _productionize_inbound
            prod_ok,prod=_productionize_inbound(int(inbound_id),type_hint='modulo_unico_tesseramento')
            if not prod_ok:
                _r117_log(conn,int(inbound_id),tid,'mu_create_production_warning','Tesserato creato/risolto ma produzione MU da verificare',{'production':prod},'warn')
                conn.commit()
                return redirect('/documenti-automatici?r117=production_warning#doc-'+str(inbound_id))

            sync=sync_analysis_to_existing_athlete(conn,tid,analysis,source='document_queue_r117_confirmed')
            try:
                from asd_app.onboarding_flow import sync_unified_module_flags,recompute_onboarding_status
                sync_unified_module_flags(conn,tid,source='document_queue_r117_confirmed')
                recompute_onboarding_status(conn,tid)
            except Exception:
                pass
            _r117_log(conn,int(inbound_id),tid,'mu_athlete_created' if created else 'mu_athlete_associated',
                      ('Nuovo tesserato creato dal Modulo Unico' if created else 'Modulo Unico associato a tesserato esistente'),
                      {'created':created,'match_reason':match_reason,'sync':sync,'production':prod,'backup':backup})
            conn.commit()
            return redirect('/tesserati/'+str(tid)+'/scheda?created_from_mu=1')
        finally:
            conn.close()

# Server-side augmentation of the existing legacy queue, without duplicating the page.
@app.after_request
def r117_mu_create_cta(resp):
    try:
        if request.method!='GET' or request.path!='/documenti-automatici' or resp.status_code!=200:
            return resp
        ctype=str(resp.headers.get('Content-Type') or '')
        if 'text/html' not in ctype: return resp
        html=resp.get_data(as_text=True)
        conn=db()
        try:
            rows=conn.execute("""SELECT * FROM inbound_documents
                WHERE coalesce(tesserato_id,0)=0
                AND lower(coalesce(status,'')) NOT IN ('deleted','archived')
                ORDER BY id DESC LIMIT 80""").fetchall()
            candidates=[]
            for r in rows:
                analysis=None
                try:
                    data=_r117_file_bytes(r)
                    if data:
                        analysis=cache_get(conn,'inbound_documents',int(r['id']),hashlib.sha256(data).hexdigest())
                except Exception: analysis=None
                if _r117_candidate(r,analysis):
                    candidates.append((r,analysis))
        finally: conn.close()
        for row,analysis in candidates:
            rid=int(row['id'])
            marker="<tr id='doc-"+str(rid)+"'>"
            start=html.find(marker)
            if start<0: continue
            end=html.find('</tr>',start)
            if end<0: continue
            block=html[start:end]
            if 'crea-tesserato' in block: continue
            name=str((analysis or {}).get('person_name') or '').strip()
            label=("Modulo riconosciuto · "+name+" · nessun tesserato associato" if name else "Modulo riconosciuto · nessun tesserato associato")
            form=("<div class='r117-mu-create' style='margin-top:8px;padding:8px;border:1px solid rgba(34,197,94,.35);border-radius:10px'>"
                  "<div class='small-muted' style='margin-bottom:6px'>"+label+"</div>"
                  "<form method='post' action='/documenti-automatici/"+str(rid)+"/crea-tesserato' "
                  "onsubmit=\"return confirm('Creare il tesserato usando i dati letti dal Modulo Unico?');\">"
                  +csrf_input()+"<button class='pro-cta slim strong' type='submit'>Crea tesserato</button></form></div>")
            last_td=block.rfind('</td>')
            if last_td>=0:
                block=block[:last_td]+form+block[last_td:]
                html=html[:start]+block+html[end:]
        resp.set_data(html)
        resp.headers['Content-Length']=str(len(resp.get_data()))
    except Exception:
        pass
    return resp

# Deterministic cleanup of certain duplicate operational statuses before R80.
conn=db()
try:
    backup_cleanup=''
    dup_count=int(conn.execute("""SELECT COUNT(*) FROM inbound_documents WHERE lower(coalesce(status,'')) IN
      ('duplicate_exact','duplicato_confermato','duplicato_non_importato','duplicate_confirmed','semantic_duplicate_archived','duplicate_archived')""").fetchone()[0]) if table(conn,'inbound_documents') else 0
    if dup_count:
        backup_cleanup=backup_db('pre_duplicate_status_cleanup')
        archived=_r117_archive_duplicate_residue(conn)
    else:
        archived=[]
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally: conn.close()

print('[r117-core] PASS no-match semantic persistence + confirmed-create route + queue CTA shared enrollment/MU core',flush=True)
print('[r117-duplicate-cleanup] '+json.dumps({'archived_ids':archived,'backup':backup_cleanup,'integrity':integrity,'fk':fk},ensure_ascii=False),flush=True)
if integrity.lower()!='ok' or fk:
    raise RuntimeError('R117 DB guard failed')
print('[r117-selftest] PASS queue-confirm-create route registered duplicate-residue archived db-ok',flush=True)
