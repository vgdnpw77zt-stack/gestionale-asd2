# -*- coding: utf-8 -*-
from __future__ import annotations
import hashlib, json, sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path
from flask import jsonify, request, redirect

from .core import app, db, admin_required, csrf_input
from .enrollment_ingest_core_r65 import (
    enrollment_identity_ready, find_existing_athlete, create_athlete_from_analysis,
    valid_italian_cf, norm_cf,
)
from .verified_mu_sync_core_r68 import sync_analysis_to_existing_athlete
import asd_app.routes_operator_bodymind as op

BACK=Path('/data/release_backups/20261003_r119_mu_nomatch')
BACK.mkdir(parents=True,exist_ok=True)
ALIASES={'modulo_unico_tesseramento','modulo_unico','modulo iscrizione','domanda iscrizione','domanda_iscrizione','iscrizione'}
HINTS=('modulo unico','modulo_unico','modulo iscrizione','iscrizione','domanda adesione','domanda di adesione')
YES={'si','sì','yes','ok','confermo','procedi','crealo','creala','crea'}
NO={'no','annulla','annullo','lascia stare','non creare'}
R119_VERSION = "R119.1-async-exact-sha"

def _table(c,n):
    return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(n,)).fetchone())

def _cols(c,n):
    return {str(r[1]) for r in c.execute("PRAGMA table_info("+n+")").fetchall()} if _table(c,n) else set()

def _backup_db(label):
    out=BACK/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+label+'.db')
    src=sqlite3.connect('/data/tenants/default/asd.db',timeout=30); dst=sqlite3.connect(str(out))
    try: src.backup(dst)
    finally: dst.close(); src.close()
    return str(out)

def _pending_schema(c):
    c.execute("""
      CREATE TABLE IF NOT EXISTS bodymind_operator_pending_entity_creation(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT NOT NULL,
        inbound_id INTEGER NOT NULL,
        entity_type TEXT NOT NULL DEFAULT 'tesserato',
        semantic_json TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(conversation_id,inbound_id)
      )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_r119_pending_conv ON bodymind_operator_pending_entity_creation(conversation_id,status,id)")
    c.commit()

def _semantic_for_inbound(c,iid):
    if not _table(c,'bodymind_document_semantics'): return None
    r=c.execute("""SELECT analysis_json FROM bodymind_document_semantics
      WHERE source_table='inbound_documents' AND source_id=? ORDER BY id DESC LIMIT 1""",(int(iid),)).fetchone()
    if not r:return None
    try:
        x=json.loads(str(r['analysis_json'] or '{}'))
        return x if isinstance(x,dict) else None
    except Exception:return None

def _file_bytes(row):
    if not row:return b''
    for k in ('saved_path','stored_path','filename'):
        if k not in row.keys() or not row[k]: continue
        p=Path(str(row[k]))
        candidates=[p] if p.is_absolute() else [Path('/data')/str(row[k]).lstrip('/'),Path('/data/tenants/default/media')/str(row[k]).lstrip('/')]
        for q in candidates:
            try:
                if q.is_file(): return q.read_bytes()
            except Exception: pass
    return b''

def _analysis(c,row,allow_live=False):
    a=_semantic_for_inbound(c,int(row['id']))
    if isinstance(a,dict): return a,'cache'
    if not allow_live:return None,'no_cache'
    data=_file_bytes(row)
    if not data:return None,'no_file'
    try:
        from .operator_doc_semantic_ai_r52 import analyze_bytes
        from .operator_doc_semantic_core_r52 import cache_put
        name=str(row['original_filename'] or 'modulo.pdf')
        a=analyze_bytes(c,name,data,'','modulo_unico_tesseramento',None)
        if isinstance(a,dict):
            cache_put(c,'inbound_documents',int(row['id']),a)
            return a,'live'
    except Exception:
        pass
    return None,'analysis_failed'

def _name(a):
    if not isinstance(a,dict):return ''
    return (' '.join(x for x in (str(a.get('first_name') or '').strip(),str(a.get('last_name') or '').strip()) if x)).strip() or str(a.get('person_name') or '').strip()

def _candidate(row,a=None):
    if not row or int(row['tesserato_id'] or 0)>0:return False
    st=str(row['status'] or '').lower()
    if st in {'deleted','archived','duplicato_confermato','duplicate_exact','semantic_duplicate_archived'}:return False
    dtype=str(row['document_type'] or '').strip().lower()
    fname=str(row['original_filename'] or '').lower()
    sem=str((a or {}).get('document_type') or '').strip().lower()
    return dtype in ALIASES or sem=='modulo_unico_tesseramento' or any(x in fname for x in HINTS)

def _confirmable(a):
    if not isinstance(a,dict):return False,'analisi_mancante'
    if str(a.get('document_type') or '').strip().lower()!='modulo_unico_tesseramento':return False,'non_modulo_unico'
    try:conf=float(a.get('confidence') or 0)
    except Exception:conf=0
    if conf<.90:return False,'confidence_sotto_90'
    if not str(a.get('first_name') or '').strip() or not str(a.get('last_name') or '').strip():
        return False,'nome_cognome_mancanti'
    cf=norm_cf(a.get('codice_fiscale')); birth=str(a.get('birth_date') or '').strip()
    if cf and not valid_italian_cf(cf):return False,'codice_fiscale_non_valido'
    if not cf and not birth:return False,'manca_cf_o_data_nascita'
    if not enrollment_identity_ready(a,require_valid_cf=False):
        return False,'identita_non_sufficientemente_certa'
    return True,'ok'

def _save_pending(c,iid,a):
    _pending_schema(c); conv=op._conv_id(); now=datetime.now().isoformat(timespec='seconds')
    c.execute("UPDATE bodymind_operator_pending_entity_creation SET status='superseded',updated_at=? WHERE conversation_id=? AND status='pending'",(now,conv))
    c.execute("""INSERT INTO bodymind_operator_pending_entity_creation
      (conversation_id,inbound_id,entity_type,semantic_json,status,created_at,updated_at)
      VALUES(?,?, 'tesserato',?, 'pending',?,?)
      ON CONFLICT(conversation_id,inbound_id) DO UPDATE SET semantic_json=excluded.semantic_json,status='pending',updated_at=excluded.updated_at""",
      (conv,int(iid),json.dumps(a,ensure_ascii=False,separators=(',',':')),now,now))
    c.commit()

def _pending(c):
    _pending_schema(c)
    p=c.execute("""SELECT * FROM bodymind_operator_pending_entity_creation
      WHERE conversation_id=? AND status='pending' ORDER BY id DESC LIMIT 1""",(op._conv_id(),)).fetchone()
    if not p:return None,None,None
    try:a=json.loads(str(p['semantic_json'] or '{}'))
    except Exception:a=None
    row=c.execute("SELECT * FROM inbound_documents WHERE id=?",(int(p['inbound_id']),)).fetchone() if _table(c,'inbound_documents') else None
    return p,row,(a if isinstance(a,dict) else None)

def _pending_status(c,pid,status):
    c.execute("UPDATE bodymind_operator_pending_entity_creation SET status=?,updated_at=? WHERE id=?",(status,datetime.now().isoformat(timespec='seconds'),int(pid)))
    c.commit()

def _associate(c,iid,tid,a):
    ic=_cols(c,'inbound_documents');sets=[];vals=[]
    for col in ('tesserato_id','matched_tesserato_id','suggested_tesserato_id'):
        if col in ic:sets.append(col+'=?');vals.append(int(tid))
    if 'match_score' in ic:sets.append('match_score=?');vals.append(100)
    if 'match_action' in ic:sets.append('match_action=?');vals.append('auto_save')
    if 'document_type' in ic:sets.append('document_type=?');vals.append('modulo_unico_tesseramento')
    if 'document_label' in ic:sets.append('document_label=?');vals.append('Modulo iscrizione / Modulo Unico')
    if 'document_confidence' in ic:
        try:conf=int(round(float((a or {}).get('confidence') or 0)*100))
        except Exception:conf=0
        sets.append('document_confidence=?');vals.append(conf)
    if 'status' in ic:sets.append('status=?');vals.append('associato')
    if sets:
        vals.append(int(iid));c.execute("UPDATE inbound_documents SET "+",".join(sets)+" WHERE id=?",tuple(vals))
    c.commit()

def _productionize(c,row,tid,a):
    iid=int(row['id']); data=_file_bytes(row); name=str(row['original_filename'] or '')
    if data and callable(getattr(op,'_semantic_key_duplicate',None)):
        dup=op._semantic_key_duplicate(c,int(tid),name,data,a)
        if dup.get('duplicate') and callable(getattr(op,'_r78_finalize_duplicate',None)):
            resolved=op._r78_finalize_duplicate(c,iid,int(tid),a,dup)
            return bool(resolved.get('ok')),{'duplicate':True,'resolved':resolved}
    return op._productionize_inbound(iid,type_hint='modulo_unico_tesseramento')

def _execute(c,row,a,source):
    if not row or not isinstance(a,dict):return {'ok':False,'reason':'contesto_mancante'}
    ok,why=_confirmable(a)
    if not ok:return {'ok':False,'reason':why}
    existing,reason=find_existing_athlete(c,a);created=False
    if existing:
        tid=int(existing['id'])
    else:
        cr=create_athlete_from_analysis(c,a,source=source,require_valid_cf=False)
        tid=int(cr.get('tesserato_id') or 0);created=bool(cr.get('created'))
        if tid<=0:return {'ok':False,'reason':str(cr.get('reason') or 'create_failed')}
    _associate(c,int(row['id']),tid,a)
    prod_ok,prod=_productionize(c,row,tid,a)
    sync=sync_analysis_to_existing_athlete(c,tid,a,source=source)
    try:
        from .onboarding_flow import sync_unified_module_flags,recompute_onboarding_status
        sync_unified_module_flags(c,tid,source=source);recompute_onboarding_status(c,tid)
    except Exception:pass
    c.commit()
    return {'ok':True,'tesserato_id':tid,'created':created,'match_reason':reason,'production_ok':bool(prod_ok),'production':prod,'sync':sync}

@app.post('/documenti-automatici/<int:inbound_id>/crea-tesserato')
@admin_required
def r119_create_tesserato_from_mu(inbound_id):
    backup=_backup_db('queue_confirm_'+str(inbound_id))
    c=db()
    try:
        row=c.execute("SELECT * FROM inbound_documents WHERE id=?",(int(inbound_id),)).fetchone()
        if not row:return redirect('/documenti-automatici?r119=missing#doc-'+str(inbound_id))
        a,method=_analysis(c,row,allow_live=True)
        res=_execute(c,row,a,'document_queue_r119_confirmed')
        if not res.get('ok'):
            return redirect('/documenti-automatici?r119=blocked&reason='+str(res.get('reason') or 'review')+'#doc-'+str(inbound_id))
        return redirect('/tesserati/'+str(res['tesserato_id'])+'/scheda?created_from_mu=1')
    finally:c.close()

@app.after_request
def r119_mu_create_cta(resp):
    try:
        if request.method!='GET' or request.path!='/documenti-automatici' or resp.status_code!=200:return resp
        if 'text/html' not in str(resp.headers.get('Content-Type') or ''):return resp
        html=resp.get_data(as_text=True);c=db()
        try:
            rows=c.execute("""SELECT * FROM inbound_documents WHERE coalesce(tesserato_id,0)=0
              AND lower(coalesce(status,'')) NOT IN ('deleted','archived') ORDER BY id DESC LIMIT 100""").fetchall()
            items=[]
            for row in rows:
                a,_=_analysis(c,row,allow_live=False)
                if _candidate(row,a):items.append((row,a))
        finally:c.close()
        for row,a in items:
            rid=int(row['id']); marker="<tr id='doc-"+str(rid)+"'>";start=html.find(marker)
            if start<0:continue
            end=html.find('</tr>',start)
            if end<0:continue
            block=html[start:end]
            if '/crea-tesserato' in block:continue
            ok,why=_confirmable(a)
            nm=_name(a)
            if ok:
                label="Modulo riconosciuto"+((" per "+nm) if nm else "")+" ma non associabile. Vuoi creare il tesserato?"
                form=("<div class='r119-mu-create' style='margin-top:8px;padding:8px;border:1px solid rgba(34,197,94,.35);border-radius:10px'>"
                      "<div class='small-muted' style='margin-bottom:6px'>"+label+"</div>"
                      "<form method='post' action='/documenti-automatici/"+str(rid)+"/crea-tesserato' onsubmit=\"return confirm('Creare il tesserato usando i dati letti dal Modulo Unico?');\">"
                      +csrf_input()+"<button class='pro-cta slim strong' type='submit'>Sì, crea tesserato</button></form></div>")
            else:
                form="<div class='small-muted' style='margin-top:8px'>Modulo riconosciuto ma identità da verificare: "+why+".</div>"
            last=block.rfind('</td>')
            if last>=0:
                block=block[:last]+form+block[last:];html=html[:start]+block+html[end:]
        resp.set_data(html);resp.headers['Content-Length']=str(len(resp.get_data()))
    except Exception:pass
    return resp

def _latest_job_exact_inbound(c):
    """Recover the file the user actually just uploaded, even when the async
    pipeline summarized it as already present/resolved instead of returning a
    fresh inbound id.  Exact SHA only: no filename-only attachment guessing."""
    if not _table(c,'bodymind_operator_upload_jobs') or not _table(c,'inbound_documents'):
        return None,None,None
    try:
        job=c.execute("""SELECT * FROM bodymind_operator_upload_jobs
          WHERE conversation_id=? AND status IN ('processing','completed')
          ORDER BY created_at DESC,id DESC LIMIT 1""",(op._conv_id(),)).fetchone()
    except Exception:
        return None,None,None
    if not job:return None,None,None
    try:specs=json.loads(str(job['files_json'] or '[]'))
    except Exception:specs=[]
    for spec in reversed(specs if isinstance(specs,list) else []):
        p=Path(str((spec or {}).get('path') or ''))
        try:
            if not p.is_file():continue
            data=p.read_bytes()
        except Exception:
            continue
        if not data or len(data)>40*1024*1024:continue
        wanted=hashlib.sha256(data).hexdigest()
        try:
            rows=c.execute("SELECT * FROM inbound_documents ORDER BY id DESC LIMIT 300").fetchall()
        except Exception:
            rows=[]
        for row in rows:
            other=_file_bytes(row)
            if not other or hashlib.sha256(other).hexdigest()!=wanted:continue
            a,_=_analysis(c,row,allow_live=False)
            if not isinstance(a,dict):
                try:
                    from .operator_doc_semantic_ai_r52 import analyze_bytes
                    from .operator_doc_semantic_core_r52 import cache_put
                    name=str((spec or {}).get('name') or row['original_filename'] or 'documento')
                    a=analyze_bytes(c,name,data,'','',None)
                    if isinstance(a,dict):
                        cache_put(c,'inbound_documents',int(row['id']),a)
                except Exception:
                    a=None
            return row,(a if isinstance(a,dict) else None),spec
    return None,None,None

def _offer_for_row(c,row,a,source):
    if not row or not isinstance(a,dict):return None
    if int(row['tesserato_id'] or 0)>0:
        return None
    # A duplicate staging status must not suppress creation of the PERSON.
    # The document may be a duplicate; an unrepresented strong identity is not.
    dtype=str(a.get('document_type') or '').strip().lower()
    if dtype!='modulo_unico_tesseramento':
        return None
    iid=int(row['id'])
    if enrollment_identity_ready(a,require_valid_cf=True):
        backup=_backup_db('operator_auto_'+str(iid))
        res=_execute(c,row,a,source)
        if res.get('ok'):
            tid=int(res['tesserato_id']);nm=_name(a) or ('#'+str(tid))
            return {'text':('Creato automaticamente il tesserato ' if res.get('created') else 'Tesserato esistente riconosciuto: ')+nm+
                    '. Ho associato il Modulo Unico e sincronizzato scheda, minore/genitore, consensi espliciti, tutela e onboarding.',
                    'mode':'action','created':bool(res.get('created')),'tesserato_id':tid,'backup':backup,
                    'links':[{'label':'Apri scheda','href':'/tesserati/'+str(tid)+'/scheda'}]}
    ok,why=_confirmable(a)
    if ok:
        _save_pending(c,iid,a);nm=_name(a) or 'la persona letta nel modulo'
        return {'text':'Modulo Unico / iscrizione riconosciuto per '+nm+', ma non trovo un tesserato associabile. Vuoi creare il tesserato usando i dati letti dal modulo? Rispondi Sì o No.',
                'mode':'confirm_create_tesserato','pending_create':True,'inbound_id':iid,'document_name':nm}
    return {'text':'Modulo Unico riconosciuto, ma i dati identificativi non sono abbastanza certi per creare una persona senza rischio ('+why+'). Lo lascio in verifica senza inventare dati.',
            'mode':'identity_review','pending_create':False,'inbound_id':iid,'reason':why}

def _upload_offer(payload):
    if not isinstance(payload,dict):return None
    results=payload.get('results') if isinstance(payload.get('results'),list) else []
    c=db()
    try:
        _pending_schema(c)
        for item in reversed(results):
            iid=int((item or {}).get('inbound_id') or 0)
            if iid<=0:continue
            row=c.execute("SELECT * FROM inbound_documents WHERE id=?",(iid,)).fetchone()
            if not row or int(row['tesserato_id'] or 0)>0:continue
            a,_=_analysis(c,row,allow_live=False)
            if not isinstance(a,dict):continue
            out=_offer_for_row(c,row,a,'operator_r119_upload')
            if isinstance(out,dict):return out

        # Async/dedupe fallback: the result can truthfully say "already present /
        # resolved" and omit a fresh inbound id. Recover only by exact bytes within
        # the same conversation's latest upload job; never by filename or name alone.
        row,a,spec=_latest_job_exact_inbound(c)
        if row and isinstance(a,dict):
            out=_offer_for_row(c,row,a,'operator_r119_async_exact_sha')
            if isinstance(out,dict):return out
    finally:c.close()
    return None

def _explicit_attachment_create_message(message):
    try:n=op._norm(message)
    except Exception:n=' '.join(str(message or '').lower().split())
    explicit=bool(__import__('re').search(r"\b(crea|creare|nuov[oa])\b",n)) and ('tesserat' in n or 'atlet' in n)
    attached=any(x in n for x in ('allegat','appena caricat','modulo appena','file appena','usa il modulo','aggiungi il modulo'))
    return bool(explicit and attached)

def _recover_chat_attachment_create():
    try:
        body=request.get_json(silent=True) or {}
        message=str(body.get('message') or body.get('text') or '')
    except Exception:
        return None
    if not _explicit_attachment_create_message(message):return None
    c=db()
    try:
        row,a,spec=_latest_job_exact_inbound(c)
        if not row or not isinstance(a,dict):return None
        requested=''
        try:
            if callable(getattr(op,'_r107_requested_name',None)):
                requested=op._r107_requested_name(message)
            if requested and callable(getattr(op,'_r107_name_conflict',None)) and op._r107_name_conflict(requested,a):
                return {'text':'Il nome scritto nel comando ('+requested+') non coincide con l’identità letta dal Modulo Unico ('+(_name(a) or 'non determinata')+'). Non ho creato nulla: conferma quale identità è corretta.',
                        'mode':'identity_conflict','requested_name':requested,'document_name':_name(a)}
        except Exception:
            pass
        ok,why=_confirmable(a)
        if not ok:
            return {'text':'Il file appena caricato è stato recuperato, ma non supera il controllo identità sicuro ('+why+'). Non creo una persona incerta.',
                    'mode':'identity_review','attachment_context':True,'reason':why}
        backup=_backup_db('operator_chat_recover_'+str(int(row['id'])))
        res=_execute(c,row,a,'operator_r119_chat_exact_sha')
        if not res.get('ok'):
            return {'text':'Ho recuperato il file appena caricato ma non ho creato il tesserato: '+str(res.get('reason') or 'verifica necessaria')+'.',
                    'mode':'warning','attachment_context':True,'result':res}
        tid=int(res['tesserato_id']);nm=_name(a) or ('#'+str(tid))
        return {'text':('Creato' if res.get('created') else 'Tesserato già esistente riconosciuto')+': '+nm+
                '. Ho usato il file appena caricato, associato il Modulo Unico e sincronizzato scheda, minore/genitore, consensi, tutela e onboarding.',
                'mode':'action','attachment_context':True,'created':bool(res.get('created')),'tesserato_id':tid,'backup':backup,
                'links':[{'label':'Apri scheda','href':'/tesserati/'+str(tid)+'/scheda'}]}
    finally:c.close()

def _norm_answer(v):
    return ' '.join(str(v or '').strip().lower().replace('ì','i').split())

def _pending_answer():
    try:body=request.get_json(silent=True) or {};msg=str(body.get('message') or body.get('text') or '')
    except Exception:msg=''
    nm=_norm_answer(msg);yes={_norm_answer(x) for x in YES};no={_norm_answer(x) for x in NO}
    if nm not in yes|no:return None
    c=db()
    try:
        p,row,a=_pending(c)
        if not p:return None
        if nm in no:
            _pending_status(c,int(p['id']),'declined')
            return {'text':'Va bene: non creo alcun tesserato. Il Modulo Unico resta in verifica e non viene perso.','mode':'action','pending_create':False}
        backup=_backup_db('operator_confirm_'+str(int(p['inbound_id'])));res=_execute(c,row,a,'operator_r119_confirmed')
        if not res.get('ok'):
            return {'text':'Non ho creato il tesserato perché il controllo finale non è sicuro: '+str(res.get('reason') or 'verifica necessaria')+'. Il modulo resta disponibile.',
                    'mode':'warning','pending_create':True,'result':res}
        _pending_status(c,int(p['id']),'completed');tid=int(res['tesserato_id']);nm=_name(a) or ('#'+str(tid))
        return {'text':('Creato' if res.get('created') else 'Tesserato già esistente riconosciuto')+': '+nm+
                '. Ho associato il Modulo Unico e sincronizzato tutti i dati leggibili, minore/genitore, consensi espliciti, tutela e onboarding.',
                'mode':'action','pending_create':False,'created':bool(res.get('created')),'tesserato_id':tid,'backup':backup,
                'links':[{'label':'Apri scheda','href':'/tesserati/'+str(tid)+'/scheda'}]}
    finally:c.close()

def _endpoint(rule,method):
    for r in app.url_map.iter_rules():
        if str(r.rule)==rule and method in r.methods:return str(r.endpoint)
    return ''

_upload_ep=_endpoint('/operatore-bodymind/upload','POST')
if _upload_ep:
    _cur=app.view_functions.get(_upload_ep)
    if _cur and not getattr(_cur,'_bodymind_r119_wrapped',False):
        _orig=_cur
        @wraps(_orig)
        def _r119_upload_wrapper(*args,**kwargs):
            resp=app.make_response(_orig(*args,**kwargs))
            if resp.status_code>=400:return resp
            offer=_upload_offer(resp.get_json(silent=True))
            return jsonify(offer) if isinstance(offer,dict) else resp
        _r119_upload_wrapper._bodymind_r119_wrapped=True
        app.view_functions[_upload_ep]=_r119_upload_wrapper

_chat_ep=_endpoint('/operatore-bodymind/chat','POST')
if _chat_ep:
    _cur=app.view_functions.get(_chat_ep)
    if _cur and not getattr(_cur,'_bodymind_r119_wrapped',False):
        _orig_chat=_cur
        @wraps(_orig_chat)
        def _r119_chat_wrapper(*args,**kwargs):
            try:role=op.current_role()
            except Exception:role=''
            if role in ('admin','manager'):
                out=_pending_answer()
                if isinstance(out,dict):return jsonify(out)
                # If an async upload was summarized/deduplicated, R107 may have no
                # fresh inbound context. Recover the same conversation's file by exact SHA.
                out=_recover_chat_attachment_create()
                if isinstance(out,dict):return jsonify(out)
            return _orig_chat(*args,**kwargs)
        _r119_chat_wrapper._bodymind_r119_wrapped=True
        app.view_functions[_chat_ep]=_r119_chat_wrapper
