# -*- coding: utf-8 -*-
from __future__ import annotations
import json, sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
BACK=Path('/data/release_backups/20261003_r119_operator_pending_create')
BACK.mkdir(parents=True,exist_ok=True)

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

from flask import jsonify, request
from asd_app.core import app, db
import asd_app.routes_operator_bodymind as op
from asd_app.enrollment_ingest_core_r65 import (
    enrollment_identity_ready, find_existing_athlete, create_athlete_from_analysis,
    norm_cf, valid_italian_cf,
)
from asd_app.verified_mu_sync_core_r68 import sync_analysis_to_existing_athlete

ALIASES={'modulo_unico_tesseramento','modulo_unico','modulo iscrizione','domanda iscrizione','domanda_iscrizione','iscrizione'}
YES={'si','sì','yes','ok','confermo','procedi','crealo','creala','crea'}
NO={'no','annulla','annullo','lascia stare','non creare'}

def _table(c,n):
    return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(n,)).fetchone())

def _cols(c,n):
    return {str(r[1]) for r in c.execute("PRAGMA table_info("+n+")").fetchall()} if _table(c,n) else set()

def _backup_db(label):
    out=BACK/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+label+'.db')
    src=sqlite3.connect(str(DB),timeout=30); dst=sqlite3.connect(str(out))
    try: src.backup(dst)
    finally: dst.close(); src.close()
    return str(out)

def _schema(c):
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
    if not _table(c,'bodymind_document_semantics'):
        return None
    r=c.execute("""SELECT analysis_json FROM bodymind_document_semantics
      WHERE source_table='inbound_documents' AND source_id=? ORDER BY id DESC LIMIT 1""",(int(iid),)).fetchone()
    if not r: return None
    try:
        x=json.loads(str(r['analysis_json'] or '{}'))
        return x if isinstance(x,dict) else None
    except Exception:
        return None

def _doc_name(a):
    if not isinstance(a,dict): return ''
    return (' '.join(x for x in [str(a.get('first_name') or '').strip(),str(a.get('last_name') or '').strip()] if x)).strip() or str(a.get('person_name') or '').strip()

def _manual_confirmable(a):
    if not isinstance(a,dict): return False,'analisi_mancante'
    if str(a.get('document_type') or '').strip().lower()!='modulo_unico_tesseramento':
        return False,'non_modulo_unico'
    try: conf=float(a.get('confidence') or 0)
    except Exception: conf=0
    if conf<.90: return False,'confidence_sotto_90'
    first=str(a.get('first_name') or '').strip(); last=str(a.get('last_name') or '').strip()
    if not first or not last: return False,'nome_cognome_mancanti'
    cf=norm_cf(a.get('codice_fiscale')); birth=str(a.get('birth_date') or '').strip()
    if cf and not valid_italian_cf(cf):
        return False,'codice_fiscale_non_valido'
    if not cf and not birth:
        return False,'manca_cf_o_data_nascita'
    if not enrollment_identity_ready(a,require_valid_cf=False):
        return False,'identita_non_sufficientemente_certa'
    return True,'ok'

def _save_pending(c,iid,a):
    _schema(c)
    conv=op._conv_id(); now=datetime.now().isoformat(timespec='seconds')
    c.execute("UPDATE bodymind_operator_pending_entity_creation SET status='superseded',updated_at=? WHERE conversation_id=? AND status='pending'",
              (now,conv))
    c.execute("""INSERT INTO bodymind_operator_pending_entity_creation
      (conversation_id,inbound_id,entity_type,semantic_json,status,created_at,updated_at)
      VALUES(?,?, 'tesserato',?, 'pending',?,?)
      ON CONFLICT(conversation_id,inbound_id) DO UPDATE SET
        semantic_json=excluded.semantic_json,status='pending',updated_at=excluded.updated_at""",
      (conv,int(iid),json.dumps(a,ensure_ascii=False,separators=(',',':')),now,now))
    c.commit()

def _pending(c):
    _schema(c)
    r=c.execute("""SELECT * FROM bodymind_operator_pending_entity_creation
      WHERE conversation_id=? AND status='pending' ORDER BY id DESC LIMIT 1""",(op._conv_id(),)).fetchone()
    if not r:return None,None,None
    try:a=json.loads(str(r['semantic_json'] or '{}'))
    except Exception:a=None
    inbound=c.execute("SELECT * FROM inbound_documents WHERE id=?",(int(r['inbound_id']),)).fetchone() if _table(c,'inbound_documents') else None
    return r,inbound,(a if isinstance(a,dict) else None)

def _set_pending_status(c,pid,status):
    c.execute("UPDATE bodymind_operator_pending_entity_creation SET status=?,updated_at=? WHERE id=?",
              (status,datetime.now().isoformat(timespec='seconds'),int(pid)))
    c.commit()

def _associate_inbound(c,iid,tid,a):
    ic=_cols(c,'inbound_documents'); sets=[]; vals=[]
    for col in ('tesserato_id','matched_tesserato_id','suggested_tesserato_id'):
        if col in ic: sets.append(col+'=?'); vals.append(int(tid))
    if 'match_score' in ic: sets.append('match_score=?'); vals.append(100)
    if 'match_action' in ic: sets.append('match_action=?'); vals.append('auto_save')
    if 'document_type' in ic: sets.append('document_type=?'); vals.append('modulo_unico_tesseramento')
    if 'document_label' in ic: sets.append('document_label=?'); vals.append('Modulo iscrizione / Modulo Unico')
    if 'document_confidence' in ic:
        try: conf=int(round(float((a or {}).get('confidence') or 0)*100))
        except Exception: conf=0
        sets.append('document_confidence=?'); vals.append(conf)
    if 'status' in ic: sets.append('status=?'); vals.append('associato')
    if sets:
        vals.append(int(iid)); c.execute("UPDATE inbound_documents SET "+",".join(sets)+" WHERE id=?",tuple(vals))
    c.commit()

def _productionize(c,inbound,tid,a):
    iid=int(inbound['id'])
    name=data=None
    reader=getattr(op,'_r107_read_inbound_bytes',None) or getattr(op,'_inbound_file_bytes',None) or getattr(op,'_document_bytes_from_row',None)
    if callable(reader):
        try:
            rr=reader(inbound)
            if isinstance(rr,tuple):
                name=rr[0] if len(rr)>0 else ''
                data=rr[1] if len(rr)>1 else b''
        except Exception:
            data=b''
    if data and callable(getattr(op,'_semantic_key_duplicate',None)):
        dup=op._semantic_key_duplicate(c,int(tid),str(name or ''),data,a)
        if dup.get('duplicate') and callable(getattr(op,'_r78_finalize_duplicate',None)):
            resolved=op._r78_finalize_duplicate(c,iid,int(tid),a,dup)
            return bool(resolved.get('ok')),{'duplicate':True,'resolved':resolved}
    return op._productionize_inbound(iid,type_hint='modulo_unico_tesseramento')

def _execute(c,inbound,a,source):
    if not inbound or not isinstance(a,dict):
        return {'ok':False,'reason':'pending_context_missing'}
    iid=int(inbound['id'])
    ok,why=_manual_confirmable(a)
    if not ok:
        return {'ok':False,'reason':why}
    existing,reason=find_existing_athlete(c,a)
    created=False
    if existing:
        tid=int(existing['id'])
    else:
        cr=create_athlete_from_analysis(c,a,source=source,require_valid_cf=False)
        tid=int(cr.get('tesserato_id') or 0); created=bool(cr.get('created'))
        if tid<=0:
            return {'ok':False,'reason':str(cr.get('reason') or 'create_failed')}
    _associate_inbound(c,iid,tid,a)
    prod_ok,prod=_productionize(c,inbound,tid,a)
    sync=sync_analysis_to_existing_athlete(c,tid,a,source=source)
    try:
        from asd_app.onboarding_flow import sync_unified_module_flags,recompute_onboarding_status
        sync_unified_module_flags(c,tid,source=source)
        recompute_onboarding_status(c,tid)
    except Exception:
        pass
    c.commit()
    return {'ok':True,'tesserato_id':tid,'created':created,'match_reason':reason,'production_ok':bool(prod_ok),'production':prod,'sync':sync}

def _upload_offer(payload):
    if not isinstance(payload,dict): return None
    results=payload.get('results') if isinstance(payload.get('results'),list) else []
    if not results: return None
    c=db()
    try:
        _schema(c)
        for item in reversed(results):
            iid=int((item or {}).get('inbound_id') or 0)
            if iid<=0: continue
            inbound=c.execute("SELECT * FROM inbound_documents WHERE id=?",(iid,)).fetchone()
            if not inbound or int(inbound['tesserato_id'] or 0)>0: continue
            a=_semantic_for_inbound(c,iid)
            if not a: continue
            if str(a.get('document_type') or '').strip().lower()!='modulo_unico_tesseramento': continue

            # If identity is strict enough, no human confirmation is needed.
            if enrollment_identity_ready(a,require_valid_cf=True):
                backup=_backup_db('auto_create_'+str(iid))
                res=_execute(c,inbound,a,'operator_r119_strict_auto')
                if res.get('ok'):
                    name=_doc_name(a) or ('#'+str(res.get('tesserato_id')))
                    return {'text':('Creato automaticamente il tesserato '+name+'. ' if res.get('created') else 'Tesserato esistente riconosciuto: '+name+'. ')
                                   +'Ho associato il Modulo Unico e sincronizzato scheda, tutela/minore, consensi e onboarding.',
                            'mode':'action','created':bool(res.get('created')),'tesserato_id':res.get('tesserato_id'),
                            'backup':backup,'result':res,
                            'links':[{'label':'Apri scheda','href':'/tesserati/'+str(res.get('tesserato_id'))+'/scheda'}]}

            ok,why=_manual_confirmable(a)
            if ok:
                _save_pending(c,iid,a)
                name=_doc_name(a) or 'la persona letta nel modulo'
                return {'text':'Modulo Unico / iscrizione riconosciuto per '+name+', ma non trovo un tesserato associabile. Vuoi creare il tesserato usando i dati letti dal modulo? Rispondi Sì o No.',
                        'mode':'confirm_create_tesserato','pending_create':True,'inbound_id':iid,'document_name':name,
                        'confirmation':{'yes':'Sì','no':'No'}}
            # Recognized MU, but identity is not safe enough to offer creation.
            return {'text':'Modulo Unico riconosciuto, ma i dati identificativi non sono abbastanza certi per creare una persona senza rischio ('+why+'). Lo lascio in verifica senza inventare dati.',
                    'mode':'identity_review','pending_create':False,'inbound_id':iid,'reason':why}
    finally:
        c.close()
    return None

def _norm_answer(v):
    return ' '.join(str(v or '').strip().lower().replace('ì','i').split())

def _chat_pending_answer():
    try:
        body=request.get_json(silent=True) or {}
        msg=str(body.get('message') or body.get('text') or '').strip()
    except Exception:
        msg=''
    nm=_norm_answer(msg)
    if nm not in {_norm_answer(x) for x in YES|NO}:
        return None
    c=db()
    try:
        p,inbound,a=_pending(c)
        if not p:
            return None
        if nm in {_norm_answer(x) for x in NO}:
            _set_pending_status(c,int(p['id']),'declined')
            out={'text':'Va bene: non creo alcun tesserato. Il Modulo Unico resta in verifica e non viene perso.','mode':'action','pending_create':False}
            try: op._log(c,'assistant',out['text'],out)
            except Exception: pass
            return out
        backup=_backup_db('confirmed_create_'+str(int(p['inbound_id'])))
        res=_execute(c,inbound,a,'operator_r119_confirmed')
        if not res.get('ok'):
            out={'text':'Non ho creato il tesserato perché il controllo finale non è sicuro: '+str(res.get('reason') or 'verifica necessaria')+'. Il modulo resta disponibile.','mode':'warning','pending_create':True,'result':res}
            try: op._log(c,'assistant',out['text'],out)
            except Exception: pass
            return out
        _set_pending_status(c,int(p['id']),'completed')
        tid=int(res['tesserato_id']); name=_doc_name(a) or ('#'+str(tid))
        out={'text':('Creato' if res.get('created') else 'Tesserato già esistente riconosciuto')+': '+name+
                    '. Ho associato il Modulo Unico e sincronizzato tutti i dati leggibili, minore/genitore, consensi espliciti, tutela e onboarding.',
             'mode':'action','pending_create':False,'created':bool(res.get('created')),'tesserato_id':tid,'backup':backup,'result':res,
             'links':[{'label':'Apri scheda','href':'/tesserati/'+str(tid)+'/scheda'}]}
        try: op._log(c,'assistant',out['text'],out)
        except Exception: pass
        return out
    finally:
        c.close()

def _endpoint_for(rule,method):
    for r in app.url_map.iter_rules():
        if str(r.rule)==rule and method in r.methods:
            return str(r.endpoint)
    return ''

# Wrap upload after the original authenticated view has done semantic ingestion.
upload_ep=_endpoint_for('/operatore-bodymind/upload','POST')
if upload_ep:
    current=app.view_functions.get(upload_ep)
    if current and not getattr(current,'_bodymind_r119_wrapped',False):
        original=current
        @wraps(original)
        def r119_upload_wrapper(*args,**kwargs):
            rv=original(*args,**kwargs)
            resp=app.make_response(rv)
            if resp.status_code>=400:
                return resp
            payload=resp.get_json(silent=True)
            offer=_upload_offer(payload)
            return jsonify(offer) if isinstance(offer,dict) else resp
        r119_upload_wrapper._bodymind_r119_wrapped=True
        app.view_functions[upload_ep]=r119_upload_wrapper

# Wrap chat only for a pending yes/no; all other language still goes to the normal cloud-first operator.
chat_ep=_endpoint_for('/operatore-bodymind/chat','POST')
if chat_ep:
    current=app.view_functions.get(chat_ep)
    if current and not getattr(current,'_bodymind_r119_wrapped',False):
        original_chat=current
        @wraps(original_chat)
        def r119_chat_wrapper(*args,**kwargs):
            try:
                role=op.current_role()
            except Exception:
                role=''
            if role in ('admin','manager'):
                out=_chat_pending_answer()
                if isinstance(out,dict):
                    return jsonify(out)
            return original_chat(*args,**kwargs)
        r119_chat_wrapper._bodymind_r119_wrapped=True
        app.view_functions[chat_ep]=r119_chat_wrapper

# Basic guards.
c=db()
try:
    _schema(c)
    integrity=str(c.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(c.execute('PRAGMA foreign_key_check').fetchall())
finally:
    c.close()
checks={
 'upload_wrapped':bool(upload_ep and getattr(app.view_functions.get(upload_ep),'_bodymind_r119_wrapped',False)),
 'chat_wrapped':bool(chat_ep and getattr(app.view_functions.get(chat_ep),'_bodymind_r119_wrapped',False)),
 'db_ok':integrity.lower()=='ok' and fk==0,
}
print('[r119-operator-pending-create] '+json.dumps(checks,ensure_ascii=False)+' integrity='+integrity+' fk='+str(fk),flush=True)
if not all(checks.values()):
    raise RuntimeError('R119 operator pending-create registration failed '+repr(checks))
print('[r119-selftest] PASS upload-no-match offer pending-create yes/no wrapper shared-create/sync core db-ok',flush=True)
