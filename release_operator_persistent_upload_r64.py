# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import py_compile, shutil

APP=Path('/data/top2_app')
P=APP/'asd_app/routes_operator_bodymind.py'
BACK=Path('/data/release_backups/20261001_operator_r64/routes_operator_bodymind.py')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

s=P.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R64_PERSISTENT_UPLOAD_TASK' in s:
    print('[operator-r64] already applied',flush=True)
    raise SystemExit(0)

BACK.parent.mkdir(parents=True,exist_ok=True)
if not BACK.exists():
    shutil.copy2(P,BACK)

s=s.replace('OPERATOR_VERSION = "R63.0-cloud-first-brain"','OPERATOR_VERSION = "R64.0-persistent-upload-task"',1)

# Persistent task state + deterministic duplicate gate.
anchor='''def _productionize_inbound(inbound_id, type_hint=""):
'''
helpers=r'''# BODYMIND_R64_PERSISTENT_UPLOAD_TASK
def _ensure_operator_task_schema(conn):
    conn.execute("""
      CREATE TABLE IF NOT EXISTS bodymind_operator_tasks(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT NOT NULL,
        task_type TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        payload_json TEXT NOT NULL,
        summary_json TEXT,
        requested_by TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bodymind_operator_tasks_conv ON bodymind_operator_tasks(conversation_id,status,id)")
    conn.commit()

def _set_upload_task(conn,payload):
    _ensure_operator_task_schema(conn)
    now=datetime.now().isoformat(timespec="seconds")
    conv=_conv_id()
    conn.execute("UPDATE bodymind_operator_tasks SET status='superseded',updated_at=? WHERE conversation_id=? AND task_type='batch_upload' AND status='active'",(now,conv))
    cur=conn.execute(
        """INSERT INTO bodymind_operator_tasks(conversation_id,task_type,status,payload_json,summary_json,requested_by,created_at,updated_at)
           VALUES(?, 'batch_upload','active',?,NULL,?,?,?)""",
        (conv,json.dumps(payload,ensure_ascii=False,separators=(",",":")),_identity(),now,now)
    )
    conn.commit()
    task_id=int(cur.lastrowid)
    session["bodymind_operator_upload_task_id"]=task_id
    session["bodymind_operator_upload_intent"]=payload
    return task_id

def _current_upload_task(conn):
    _ensure_operator_task_schema(conn)
    task_id=int(session.get("bodymind_operator_upload_task_id") or 0)
    row=None
    if task_id:
        row=conn.execute("SELECT * FROM bodymind_operator_tasks WHERE id=? AND task_type='batch_upload' ORDER BY id DESC LIMIT 1",(task_id,)).fetchone()
    if not row:
        row=conn.execute("SELECT * FROM bodymind_operator_tasks WHERE conversation_id=? AND task_type='batch_upload' AND status IN ('active','awaiting_confirmation') ORDER BY id DESC LIMIT 1",(_conv_id(),)).fetchone()
    if not row:
        legacy=session.get("bodymind_operator_upload_intent")
        if isinstance(legacy,dict) and legacy.get("document_type"):
            return {"id":0,"status":"active","payload":legacy,"summary":{}}
        return None
    try: payload=json.loads(str(row["payload_json"] or "{}"))
    except Exception: payload={}
    try: summary=json.loads(str(row["summary_json"] or "{}"))
    except Exception: summary={}
    return {"id":int(row["id"]),"status":str(row["status"] or ""),"payload":payload if isinstance(payload,dict) else {},"summary":summary if isinstance(summary,dict) else {}}

def _update_upload_task(conn,task_id,summary=None,status=None):
    if not task_id:
        return
    _ensure_operator_task_schema(conn)
    sets=["updated_at=?"]; vals=[datetime.now().isoformat(timespec="seconds")]
    if summary is not None:
        sets.append("summary_json=?"); vals.append(json.dumps(summary,ensure_ascii=False,separators=(",",":")))
    if status:
        sets.append("status=?"); vals.append(str(status))
    vals.append(int(task_id))
    conn.execute("UPDATE bodymind_operator_tasks SET "+",".join(sets)+" WHERE id=?",tuple(vals))
    conn.commit()

def _upload_task_public_context(conn):
    task=_current_upload_task(conn)
    if not task:
        return {}
    payload=task.get("payload") or {}
    summary=task.get("summary") or {}
    return {
        "task_id":task.get("id"),"status":task.get("status"),
        "document_type":payload.get("document_type"),"production":bool(payload.get("production")),
        "deduplicate":bool(payload.get("deduplicate",True)),
        "associate_missing_only":bool(payload.get("associate_missing_only",True)),
        "last_batch":summary,
    }

def _semantic_key_duplicate(conn,tid,name,data,analysis):
    """One analysis per incoming file; existing analyses are cached.
    Duplicate only inside same athlete + same semantic document type.
    """
    tid=int(tid or 0)
    if tid<=0 or not isinstance(analysis,dict):
        return {"duplicate":False}
    wanted=_norm(analysis.get("document_type") or "")
    incoming_key=str(analysis.get("semantic_key") or "").strip()
    try: incoming_conf=float(analysis.get("confidence") or 0)
    except Exception: incoming_conf=0.0
    incoming_sha=_docsem_sha256(data)
    for row in _visible_docs(conn,tid)[:80]:
        if wanted and _norm(_canonical_document_kind(row))!=wanted:
            continue
        ename,edata,_=_document_bytes_from_row(row)
        if not edata:
            continue
        if _docsem_sha256(edata)==incoming_sha:
            return {"duplicate":True,"existing_id":int(row["id"]),"confidence":1.0,"reason":"contenuto identico SHA-256","method":"sha256"}
        existing=_semantic_for_document_row(conn,row,"documenti")
        if not existing:
            continue
        try: existing_conf=float(existing.get("confidence") or 0)
        except Exception: existing_conf=0.0
        existing_key=str(existing.get("semantic_key") or "").strip()
        if incoming_conf>=.90 and existing_conf>=.90 and incoming_key and existing_key and incoming_key==existing_key:
            return {"duplicate":True,"existing_id":int(row["id"]),"confidence":min(incoming_conf,existing_conf),"reason":"stesso contenuto semantico","method":"semantic_key"}
    return {"duplicate":False}

def _inbound_file_bytes(row):
    return _document_bytes_from_row(row)

'''
if anchor not in s:
    raise RuntimeError('R64 productionize anchor missing')
s=s.replace(anchor,helpers+anchor,1)

# Replace prepare_batch_upload with persistent operational task.
start=s.index('''    if tool=="prepare_batch_upload":
''')
end=s.index('''
    if tool=="search_tesserato":
''',start)
batch=r'''    if tool=="prepare_batch_upload":
        dtype=str(args.get("document_type") or "").strip().lower()
        aliases={
            "modulo unico":"modulo_unico_tesseramento","modulo_unico":"modulo_unico_tesseramento",
            "iscrizione":"modulo_unico_tesseramento","modulo iscrizione":"modulo_unico_tesseramento",
            "certificato":"certificato_medico","certificati":"certificato_medico",
            "certificato medico":"certificato_medico","certificati medici":"certificato_medico","cm":"certificato_medico"
        }
        dtype=aliases.get(dtype,dtype)
        nraw=_norm(raw_message)
        requested_write=any(x in nraw for x in (
            "carica solo","caricare solo","associa","associali","importa","importali","metti in produzione",
            "porta in produzione","quelli che mancano","quelli mancanti","solo quelli nuovi","solo i mancanti",
            "ti ho caricato","ho caricato"
        ))
        production=bool(args.get("production")) or requested_write
        deduplicate=bool(args.get("deduplicate",True)) or any(x in nraw for x in ("doppion","duplicat","gia present","già present"))
        missing_only=bool(args.get("associate_missing_only",True)) or any(x in nraw for x in ("solo quelli","quelli che mancano","mancanti","non presenti"))
        if dtype not in ("modulo_unico_tesseramento","certificato_medico","documento_identita","trasporto_minori","documenti_gara","documenti_saggio"):
            current=_current_upload_task(conn)
            if current and (current.get("payload") or {}).get("document_type"):
                dtype=str(current["payload"]["document_type"])
            else:
                return {"text":"Dimmi che tipo di documenti vuoi affidarmi, oppure caricali e li analizzerò prima di proporti l'importazione.","mode":"clarify"}
        if production and current_role()!="admin":
            return {"text":"La produzione massiva richiede un account amministratore.","mode":"warning"}
        payload={
            "document_type":dtype,"production":production,"deduplicate":deduplicate,
            "associate_missing_only":missing_only,
            "instruction":str(raw_message or "")[:2000],
            "created_at":datetime.now().isoformat(timespec="seconds")
        }
        task_id=_set_upload_task(conn,payload)
        return {
            "text":"Task documentale memorizzato. I prossimi file saranno trattati come "+dtype.replace("_"," ")+
                   ". Li leggerò, identificherò l'atleta, confronterò ciascun file con il suo dossier e non importerò le copie certe. "+
                   ("I nuovi certi verranno preparati per la tua conferma finale; gli ambigui resteranno in verifica." if production else "Ti mostrerò l'esito prima di qualsiasi produzione."),
            "mode":"action","upload_task_id":task_id,"upload_task":payload
        }
'''
s=s[:start]+batch+s[end:]

# Add batch production action with backup + second duplicate check.
insert_before='''    if kind=="archive_semantic_duplicates":
'''
branch=r'''    if kind=="productionize_batch":
        if current_role()!="admin":
            return {"text":"La produzione del batch richiede un account amministratore. Non ho modificato il dossier.","mode":"warning"}
        inbound_ids=[int(x) for x in (payload.get("inbound_ids") or []) if str(x).isdigit()]
        dtype=str(payload.get("document_type") or "")
        task_id=int(payload.get("task_id") or 0)
        if not inbound_ids:
            conn.execute("UPDATE bodymind_operator_actions SET status='cancelled' WHERE id=?",(aid,))
            conn.commit(); session.pop("bodymind_operator_pending_action",None)
            return {"text":"Non ci sono documenti nuovi da importare.","mode":"warning"}
        try:
            backup_path=_operator_db_backup("batch_upload_"+str(aid))
        except Exception:
            backup_path=""
        imported=[]; blocked=[]; duplicates=[]
        for inbound_id in inbound_ids:
            row=conn.execute("SELECT * FROM inbound_documents WHERE id=?",(inbound_id,)).fetchone() if _table(conn,"inbound_documents") else None
            if not row:
                blocked.append({"inbound_id":inbound_id,"reason":"staging non trovato"}); continue
            tid=int(row["tesserato_id"] or 0) if "tesserato_id" in row.keys() else 0
            name,data,_=_inbound_file_bytes(row)
            analysis=_docsem_cache_get(conn,"inbound_documents",inbound_id,_docsem_sha256(data)) if data else None
            if tid<=0 or not data or not analysis:
                blocked.append({"inbound_id":inbound_id,"reason":"identità o analisi non più certa"}); continue
            if dtype and _norm(analysis.get("document_type") or "")!=_norm(dtype):
                blocked.append({"inbound_id":inbound_id,"reason":"tipo documentale non coincide più"}); continue
            dup=_semantic_key_duplicate(conn,tid,name,data,analysis)
            if dup.get("duplicate"):
                duplicates.append({"inbound_id":inbound_id,**dup}); continue
            ok,details=_productionize_inbound(inbound_id,type_hint=dtype)
            if ok:
                imported.append({"inbound_id":inbound_id,**(details or {})})
            else:
                blocked.append({"inbound_id":inbound_id,"reason":str((details or {}).get("reason") or "produzione non riuscita"),"details":details})
        status="executed" if not blocked else ("executed_partial" if imported else "blocked_safety")
        conn.execute("UPDATE bodymind_operator_actions SET status=?,confirmed_by=?,executed_at=?,payload_json=? WHERE id=?",
                     (status,_identity(),datetime.now().isoformat(timespec="seconds"),
                      json.dumps({**payload,"imported":imported,"blocked":blocked,"duplicates":duplicates,"backup":backup_path},ensure_ascii=False),aid))
        conn.commit(); session.pop("bodymind_operator_pending_action",None)
        summary={"received":len(inbound_ids)+len(duplicates),"imported":len(imported),"duplicates":len(duplicates),"review":len(blocked)}
        _update_upload_task(conn,task_id,summary,status="completed" if not blocked else "completed_with_review")
        text_out=f"Batch completato: {len(imported)} documenti nuovi importati, {len(duplicates)} duplicati non importati, {len(blocked)} lasciati in verifica."
        if backup_path:
            text_out+=" Backup preventivo creato."
        return {"text":text_out,"mode":"action","batch_imported":imported,"batch_duplicates":duplicates,"batch_blocked":blocked,
                "links":[{"label":"Apri Documenti","href":"/documenti"},{"label":"Apri Da verificare","href":"/documenti/da-verificare"}]}

'''
if insert_before not in s:
    raise RuntimeError('R64 execute-pending anchor missing')
s=s.replace(insert_before,branch+insert_before,1)

# Replace upload endpoint: stage -> semantic analyse -> dedupe -> preview/confirm.
start=s.index('@app.post("/operatore-bodymind/upload")')
end=s.index('\n@app.after_request\ndef bodymind_family_logo_override',start)
upload=r'''@app.post("/operatore-bodymind/upload")
@login_required
def bodymind_operator_upload():
    if current_role() not in ("admin","manager"):
        return jsonify({"text":"L’account connesso non può affidare documenti all’Autopilot.","mode":"warning"}),403
    files=request.files.getlist("files")
    if not files:
        return jsonify({"text":"Non ho ricevuto file.","mode":"warning"}),400

    conn_task=db()
    try:
        _schema(conn_task); task=_current_upload_task(conn_task)
    finally:
        conn_task.close()
    payload=(task or {}).get("payload") or {}
    requested_hint=str(request.form.get("document_type_hint") or "").strip()
    type_hint=requested_hint or str(payload.get("document_type") or "").strip()
    production_mode=bool(payload.get("production")) if task else (str(request.form.get("production_mode") or "0").strip().lower() not in ("0","false","no","off"))
    deduplicate=bool(payload.get("deduplicate",True)) if task else True
    allowed_hints={"","modulo_unico_tesseramento","certificato_medico","documento_identita","trasporto_minori","documenti_gara","documenti_saggio"}
    if type_hint not in allowed_hints:
        return jsonify({"text":"Tipo documento indicato non valido.","mode":"warning"}),400

    from .routes_email_documents import process_inbound_attachment, ALLOWED_INBOUND_DOCS, extract_attachment_text, find_tesserato_for_text
    from .routes_documenti import _save_uploaded_asd_document

    results=[]; errors=[]; ready_ids=[]; duplicate_items=[]; review_items=[]
    for f in files[:120]:
        try:
            name=(f.filename or "documento").replace("\","/").split("/")[-1]
            ext=Path(name).suffix.lower()
            if ext not in ALLOWED_INBOUND_DOCS:
                errors.append(name+" · formato non supportato"); continue
            data=f.read()
            if len(data)>40*1024*1024:
                errors.append(name+" · oltre 40 MB"); continue
            extracted=""
            try: extracted=extract_attachment_text(name,data) or ""
            except Exception: extracted=""

            # ASD-level documents keep their dedicated archive path only when no user task declares athlete documents.
            athlete_match=None
            try: athlete_match=find_tesserato_for_text((name+" "+extracted).strip(),current_username())
            except Exception: athlete_match=None
            asd_kind=_classify_asd_document(name,extracted) if not athlete_match else None
            if asd_kind and not type_hint:
                try:
                    f.stream.seek(0); _,saved_name=_save_uploaded_asd_document(f,asd_kind["folder"])
                    results.append({"name":name,"status":"archiviato_asd","type":"documento_asd","production":False,"saved_name":saved_name})
                    continue
                except Exception as exc:
                    errors.append(name+" · archivio ASD: "+str(exc)[:160]); continue

            # One semantic reading of every uploaded athlete document.
            semantic=None
            conn_sem=db()
            try:
                semantic=_semantic_for_new_bytes(conn_sem,name,data,extracted,type_hint)
            except Exception as exc:
                semantic=None
            finally:
                conn_sem.close()

            conn0=db()
            try:
                before_id=int(conn0.execute("SELECT COALESCE(MAX(id),0) FROM inbound_documents").fetchone()[0]) if _table(conn0,"inbound_documents") else 0
            finally: conn0.close()

            res=process_inbound_attachment(name,data,subject="Operatore BodyMind",sender=current_username(),
                body_text="Caricato dalla Segreteria BodyMind per task documentale",source="operatore_bodymind")

            conn1=db()
            try:
                inbound=_latest_inbound_after(conn1,before_id,name)
                inbound_id=int(inbound["id"]) if inbound else 0
                if inbound_id and semantic:
                    _docsem_cache_put(conn1,"inbound_documents",inbound_id,semantic)
                    inbound=conn1.execute("SELECT * FROM inbound_documents WHERE id=?",(inbound_id,)).fetchone()
                    tid=int(inbound["tesserato_id"] or 0) if inbound and "tesserato_id" in inbound.keys() else 0
                    # Semantic identity can strengthen a missing/weak text match only at very high confidence.
                    athlete,match_conf,match_method=_semantic_match_athlete(conn1,semantic)
                    if athlete and match_conf>=.99 and (tid<=0 or (("match_score" in inbound.keys()) and int(inbound["match_score"] or 0)<95)):
                        ic=_cols(conn1,"inbound_documents"); sets=["tesserato_id=?"]; vals=[int(athlete["id"])]
                        if "matched_tesserato_id" in ic: sets.append("matched_tesserato_id=?"); vals.append(int(athlete["id"]))
                        if "match_score" in ic: sets.append("match_score=?"); vals.append(99)
                        vals.append(inbound_id)
                        conn1.execute("UPDATE inbound_documents SET "+",".join(sets)+" WHERE id=?",tuple(vals)); conn1.commit()
                        inbound=conn1.execute("SELECT * FROM inbound_documents WHERE id=?",(inbound_id,)).fetchone()
                tid=int(inbound["tesserato_id"] or 0) if inbound and "tesserato_id" in inbound.keys() else 0
            finally: conn1.close()

            item={"name":name,"inbound_id":inbound_id or None,"tesserato_id":tid or res.get("tesserato_id"),
                  "type":type_hint or ((semantic or {}).get("document_type") if semantic else (res.get("classification") or {}).get("type")),
                  "production":False}

            if not inbound_id or not semantic:
                item["status"]="verifica"; item["reason"]="analisi semantica non disponibile"
                review_items.append(item); results.append(item); continue

            sem_type=_norm(semantic.get("document_type") or "")
            try: sem_conf=float(semantic.get("confidence") or 0)
            except Exception: sem_conf=0
            if type_hint and sem_type!=_norm(type_hint):
                item["status"]="verifica"; item["reason"]="il contenuto non coincide con il tipo dichiarato"; item["semantic_type"]=semantic.get("document_type")
                review_items.append(item); results.append(item); continue
            if sem_conf<.90 or tid<=0:
                item["status"]="verifica"; item["reason"]="tipo o atleta non abbastanza certi"; item["semantic_confidence"]=sem_conf
                review_items.append(item); results.append(item); continue

            conn_dup=db()
            try:
                dup=_semantic_key_duplicate(conn_dup,tid,name,data,semantic) if deduplicate else {"duplicate":False}
                if dup.get("duplicate"):
                    ic=_cols(conn_dup,"inbound_documents")
                    if "status" in ic:
                        conn_dup.execute("UPDATE inbound_documents SET status=? WHERE id=?",("duplicato_non_importato",inbound_id)); conn_dup.commit()
                    item.update({"status":"duplicato_non_importato","duplicate":True,"duplicate_of":dup.get("existing_id"),"duplicate_reason":dup.get("reason")})
                    duplicate_items.append(item); results.append(item); continue
            finally: conn_dup.close()

            item["status"]="nuovo_pronto"
            ready_ids.append(inbound_id); results.append(item)
        except Exception as exc:
            errors.append((f.filename or "file")+" · "+str(exc)[:180])

    summary={"received":len(results),"ready":len(ready_ids),"duplicates":len(duplicate_items),"review":len(review_items),"errors":len(errors),"document_type":type_hint}
    conn2=db()
    try:
        task_id=int((task or {}).get("id") or 0)
        if not task_id:
            task_id=_set_upload_task(conn2,{"document_type":type_hint,"production":production_mode,"deduplicate":True,"associate_missing_only":True,
                                            "instruction":"upload diretto","created_at":datetime.now().isoformat(timespec="seconds")})
        _update_upload_task(conn2,task_id,summary,status="awaiting_confirmation" if ready_ids and production_mode else "active")
        if ready_ids and production_mode:
            aid=_set_pending_action(conn2,"productionize_batch",{"task_id":task_id,"inbound_ids":ready_ids,"document_type":type_hint})
        else:
            aid=None
        text=f"Ho analizzato {len(results)} file: {len(ready_ids)} nuovi e associabili con certezza, {len(duplicate_items)} duplicati già presenti che non importerò, {len(review_items)} da verificare."
        if errors: text+=f" {len(errors)} file non sono stati elaborati."
        if aid:
            text+=f" Posso importare i {len(ready_ids)} nuovi nel dossier delle atlete corrette. Confermi?"
        elif ready_ids:
            text+=" I nuovi sono pronti ma il task non richiede ancora la produzione."
        _log(conn2,"assistant",text,{"mode":"upload_preview","summary":summary,"action_id":aid,"task_id":task_id})
    finally: conn2.close()

    return jsonify({"text":text,"mode":"confirm" if aid else "upload_preview","results":results,"errors":errors,
                    "upload_task_id":task_id,"action_id":aid,"summary":summary,"production_mode":production_mode,
                    "document_type_hint":type_hint,
                    "links":[{"label":"Apri Da verificare","href":"/documenti/da-verificare"},{"label":"Apri Documenti","href":"/documenti"}]})
'''
s=s[:start]+upload+s[end:]

# Feed persistent upload state to the cloud planner.
old='''        recent=_recent_operator_context(conn,10)
        trace=tool_trace if isinstance(tool_trace,list) else []
'''
new='''        recent=_recent_operator_context(conn,10)
        upload_task=_upload_task_public_context(conn)
        trace=tool_trace if isinstance(tool_trace,list) else []
'''
if old not in s:
    raise RuntimeError('R64 planner context anchor missing')
s=s.replace(old,new,1)
old='''            "\nContesto recente: "+json.dumps(recent,ensure_ascii=False)[:6000]+
            "\nRisultati strumenti già usati in questa richiesta: "+json.dumps(trace,ensure_ascii=False)[:8000]+
'''
new='''            "\nContesto recente: "+json.dumps(recent,ensure_ascii=False)[:6000]+
            "\nTASK DOCUMENTALE CORRENTE (fonte di verità sul batch caricato): "+json.dumps(upload_task,ensure_ascii=False)[:5000]+
            "\nSe il task documentale contiene document_type o last_batch, NON chiedere di nuovo che tipo di file sono e NON fingere di non averli ricevuti. "+
            "\nRisultati strumenti già usati in questa richiesta: "+json.dumps(trace,ensure_ascii=False)[:8000]+
'''
if old not in s:
    raise RuntimeError('R64 planner prompt task anchor missing')
s=s.replace(old,new,1)

P.write_text(s,encoding='utf-8')
py_compile.compile(str(P),doraise=True)
print('[operator-r64] PASS persistent-upload-task semantic-read exact-dedupe staging-preview confirmation second-gate planner-task-memory',flush=True)
