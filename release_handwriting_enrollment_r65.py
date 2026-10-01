# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import py_compile, shutil

APP=Path('/data/top2_app')
OP=APP/'asd_app/routes_operator_bodymind.py'
EMAIL=APP/'asd_app/routes_email_documents.py'
HELPER_SRC=Path('/opt/bodymind/enrollment_ingest_core_r65.py')
HELPER_DST=APP/'asd_app/enrollment_ingest_core_r65.py'
BACK=Path('/data/release_backups/20261001_operator_r65')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')
if not HELPER_SRC.exists():
    raise RuntimeError('R65 enrollment helper source missing')
BACK.mkdir(parents=True,exist_ok=True)

# Shared helper refreshed each boot.
HELPER_DST.write_text(HELPER_SRC.read_text(encoding='utf-8'),encoding='utf-8')

# ---------------- Operator ----------------
s=OP.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R65_HANDWRITING_ENROLLMENT' not in s:
    b=BACK/'routes_operator_bodymind.py'
    if not b.exists(): shutil.copy2(OP,b)

    import_anchor='''from .operator_doc_semantic_ai_r52 import (
    analyze_bytes as _docsem_analyze_bytes,
    compare_bytes as _docsem_compare_bytes,
)
'''
    import_new=import_anchor+'''from .enrollment_ingest_core_r65 import (
    enrollment_identity_ready as _enrollment_identity_ready,
    find_existing_athlete as _enrollment_find_existing,
    athlete_fields_from_analysis as _enrollment_fields,
    create_athlete_from_analysis as _enrollment_create,
)
'''
    if import_anchor not in s:
        raise RuntimeError('R65 operator import anchor missing')
    s=s.replace(import_anchor,import_new,1)

    # Extend R64 upload collections.
    old='''    results=[]; errors=[]; ready_ids=[]; duplicate_items=[]; review_items=[]
'''
    new='''    from .operator_doc_semantic_ai_r52 import segment_pdf_documents as _docsem_segment_pdf_documents
    from io import BytesIO
    from werkzeug.datastructures import FileStorage

    expanded_files=[]
    for original in files[:120]:
        original_name=(getattr(original,"filename","") or "documento").replace(chr(92),"/").split("/")[-1]
        if Path(original_name).suffix.lower()!=".pdf" or type_hint!="certificato_medico":
            expanded_files.append(original)
            continue
        try:
            raw=original.read()
            original.stream.seek(0)
            conn_seg=db()
            try:
                segmented=_docsem_segment_pdf_documents(conn_seg,original_name,raw,type_hint,_record_response_usage)
            finally:
                conn_seg.close()
            parts=(segmented or {}).get("segments") or []
            if bool((segmented or {}).get("multiple")) and len(parts)>1:
                for part in parts:
                    pdata=bytes(part.get("data") or b"")
                    if pdata:
                        expanded_files.append(FileStorage(stream=BytesIO(pdata),filename=str(part.get("filename") or original_name),content_type="application/pdf"))
            else:
                expanded_files.append(original)
        except Exception:
            try:
                original.stream.seek(0)
            except Exception:
                pass
            expanded_files.append(original)
    files=expanded_files

    results=[]; errors=[]; ready_ids=[]; duplicate_items=[]; review_items=[]; new_athletes=[]
'''
    if old not in s:
        raise RuntimeError('R65 upload collections anchor missing')
    s=s.replace(old,new,1)

    # Intercept strong enrollment forms that do not match an existing athlete.
    old='''            if sem_conf<.90 or tid<=0:
                item["status"]="verifica"; item["reason"]="tipo o atleta non abbastanza certi"; item["semantic_confidence"]=sem_conf
                review_items.append(item); results.append(item); continue
'''
    new=r'''            # BODYMIND_R65_HANDWRITING_ENROLLMENT
            if tid<=0 and sem_type=="modulo_unico_tesseramento" and sem_conf>=.95 and _enrollment_identity_ready(semantic,require_valid_cf=False):
                candidate_conn=db()
                try:
                    existing,existing_reason=_enrollment_find_existing(candidate_conn,semantic)
                    if existing:
                        tid=int(existing["id"])
                        ic=_cols(candidate_conn,"inbound_documents")
                        sets=[]; vals=[]
                        for col in ("tesserato_id","matched_tesserato_id","suggested_tesserato_id"):
                            if col in ic:
                                sets.append(col+"=?"); vals.append(tid)
                        if "match_score" in ic:
                            sets.append("match_score=?"); vals.append(100)
                        if "document_type" in ic:
                            sets.append("document_type=?"); vals.append("modulo_unico_tesseramento")
                        if "document_confidence" in ic:
                            sets.append("document_confidence=?"); vals.append(int(round(sem_conf*100)))
                        if sets:
                            vals.append(inbound_id)
                            candidate_conn.execute("UPDATE inbound_documents SET "+",".join(sets)+" WHERE id=?",tuple(vals))
                            candidate_conn.commit()
                        item["tesserato_id"]=tid
                        item["matched_existing_by"]=existing_reason
                    else:
                        fields=_enrollment_fields(candidate_conn,semantic)
                        candidate={
                            "inbound_id":inbound_id,
                            "name":name,
                            "analysis":semantic,
                            "preview_fields":fields,
                        }
                        new_athletes.append(candidate)
                        item["status"]="nuova_tesserata_pronta"
                        item["reason"]="Modulo di iscrizione leggibile: nuova anagrafica da confermare"
                        item["new_athlete_preview"]=fields
                        item["handwriting_present"]=semantic.get("handwriting_present")
                        item["handwriting_legibility"]=semantic.get("handwriting_legibility")
                        results.append(item)
                        continue
                finally:
                    candidate_conn.close()

            if sem_conf<.90 or tid<=0:
                item["status"]="verifica"; item["reason"]="tipo o atleta non abbastanza certi"; item["semantic_confidence"]=sem_conf
                item["handwriting_present"]=(semantic or {}).get("handwriting_present")
                item["handwriting_legibility"]=(semantic or {}).get("handwriting_legibility")
                review_items.append(item); results.append(item); continue
'''
    if old not in s:
        raise RuntimeError('R65 enrollment candidate anchor missing')
    s=s.replace(old,new,1)

    # Replace R64 final summary/action preparation.
    old='''    summary={"received":len(results),"ready":len(ready_ids),"duplicates":len(duplicate_items),"review":len(review_items),"errors":len(errors),"document_type":type_hint}
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
'''
    new=r'''    summary={"received":len(results),"ready":len(ready_ids),"new_athletes":len(new_athletes),"duplicates":len(duplicate_items),"review":len(review_items),"errors":len(errors),"document_type":type_hint}
    conn2=db()
    try:
        task_id=int((task or {}).get("id") or 0)
        if not task_id:
            task_id=_set_upload_task(conn2,{"document_type":type_hint,"production":production_mode,"deduplicate":True,"associate_missing_only":True,
                                            "instruction":"upload diretto","created_at":datetime.now().isoformat(timespec="seconds")})
        has_actionable=bool(ready_ids or new_athletes)
        _update_upload_task(conn2,task_id,summary,status="awaiting_confirmation" if has_actionable and production_mode else "active")
        if new_athletes and production_mode:
            aid=_set_pending_action(conn2,"process_enrollment_batch",{
                "task_id":task_id,"existing_inbound_ids":ready_ids,"new_candidates":new_athletes,"document_type":type_hint
            })
        elif ready_ids and production_mode:
            aid=_set_pending_action(conn2,"productionize_batch",{"task_id":task_id,"inbound_ids":ready_ids,"document_type":type_hint})
        else:
            aid=None
        text=f"Ho analizzato {len(results)} file: {len(ready_ids)} documenti nuovi per tesserate già presenti, {len(new_athletes)} moduli di nuove tesserate leggibili, {len(duplicate_items)} duplicati che non importerò, {len(review_items)} da verificare."
        if new_athletes:
            names=[]
            for c in new_athletes[:8]:
                pf=c.get("preview_fields") or {}
                names.append((str(pf.get("nome") or "")+" "+str(pf.get("cognome") or "")).strip())
            names=[x for x in names if x]
            if names:
                text+=" Nuove anagrafiche proposte: "+", ".join(names)+(". " if len(names)==len(new_athletes) else "… ")
        if errors: text+=f" {len(errors)} file non sono stati elaborati."
        if aid:
            text+=" Posso creare le nuove anagrafiche confermate e importare i documenti pronti, con un secondo controllo anti-duplicato. Confermi?"
        elif has_actionable:
            text+=" I dati sono pronti ma il task non richiede ancora la produzione."
        _log(conn2,"assistant",text,{"mode":"upload_preview","summary":summary,"action_id":aid,"task_id":task_id})
    finally: conn2.close()
'''
    if old not in s:
        raise RuntimeError('R65 upload final anchor missing')
    s=s.replace(old,new,1)

    # Add execution branch before R64 productionize_batch.
    anchor='''    if kind=="productionize_batch":
'''
    branch=r'''    if kind=="process_enrollment_batch":
        if current_role()!="admin":
            return {"text":"La creazione di nuove tesserate da modulo richiede un account amministratore. Non ho modificato nulla.","mode":"warning"}
        existing_ids=[int(x) for x in (payload.get("existing_inbound_ids") or []) if str(x).isdigit()]
        new_candidates=payload.get("new_candidates") if isinstance(payload.get("new_candidates"),list) else []
        task_id=int(payload.get("task_id") or 0)
        dtype=str(payload.get("document_type") or "modulo_unico_tesseramento")
        try:
            backup_path=_operator_db_backup("enrollment_batch_"+str(aid))
        except Exception:
            backup_path=""
        imported=[]; created=[]; duplicates=[]; blocked=[]

        # Existing athletes: same second gate as R64.
        for inbound_id in existing_ids:
            row=conn.execute("SELECT * FROM inbound_documents WHERE id=?",(inbound_id,)).fetchone() if _table(conn,"inbound_documents") else None
            if not row:
                blocked.append({"inbound_id":inbound_id,"reason":"staging non trovato"}); continue
            tid=int(row["tesserato_id"] or 0) if "tesserato_id" in row.keys() else 0
            name,data,_=_inbound_file_bytes(row)
            analysis=_docsem_cache_get(conn,"inbound_documents",inbound_id,_docsem_sha256(data)) if data else None
            if tid<=0 or not data or not analysis:
                blocked.append({"inbound_id":inbound_id,"reason":"identità o analisi non più certa"}); continue
            dup=_semantic_key_duplicate(conn,tid,name,data,analysis)
            if dup.get("duplicate"):
                duplicates.append({"inbound_id":inbound_id,**dup}); continue
            ok,details=_productionize_inbound(inbound_id,type_hint=dtype or str(analysis.get("document_type") or ""))
            if ok: imported.append({"inbound_id":inbound_id,**(details or {})})
            else: blocked.append({"inbound_id":inbound_id,"reason":str((details or {}).get("reason") or "produzione non riuscita")})

        # New athletes: re-read cached semantic result, re-check collision, create only after confirmation.
        for candidate in new_candidates:
            try: inbound_id=int(candidate.get("inbound_id") or 0)
            except Exception: inbound_id=0
            row=conn.execute("SELECT * FROM inbound_documents WHERE id=?",(inbound_id,)).fetchone() if inbound_id and _table(conn,"inbound_documents") else None
            if not row:
                blocked.append({"inbound_id":inbound_id,"reason":"modulo non più disponibile"}); continue
            name,data,_=_inbound_file_bytes(row)
            analysis=_docsem_cache_get(conn,"inbound_documents",inbound_id,_docsem_sha256(data)) if data else None
            if not analysis or not _enrollment_identity_ready(analysis,require_valid_cf=False):
                blocked.append({"inbound_id":inbound_id,"reason":"dati anagrafici non più abbastanza certi"}); continue
            existing,reason=_enrollment_find_existing(conn,analysis)
            if existing:
                tid=int(existing["id"]); was_created=False
            else:
                cr=_enrollment_create(conn,analysis,source="operator_r65",require_valid_cf=False)
                tid=int(cr.get("tesserato_id") or 0); was_created=bool(cr.get("created"))
                if tid<=0:
                    blocked.append({"inbound_id":inbound_id,"reason":str(cr.get("reason") or "creazione anagrafica non riuscita")}); continue
                created.append({"tesserato_id":tid,"name":(str(analysis.get("first_name") or "")+" "+str(analysis.get("last_name") or "")).strip()})
            ic=_cols(conn,"inbound_documents")
            sets=[]; vals=[]
            for col in ("tesserato_id","matched_tesserato_id","suggested_tesserato_id"):
                if col in ic: sets.append(col+"=?"); vals.append(tid)
            if "match_score" in ic: sets.append("match_score=?"); vals.append(100)
            if "document_type" in ic: sets.append("document_type=?"); vals.append("modulo_unico_tesseramento")
            if "document_confidence" in ic: sets.append("document_confidence=?"); vals.append(int(round(float(analysis.get("confidence") or 0)*100)))
            if sets:
                vals.append(inbound_id)
                conn.execute("UPDATE inbound_documents SET "+",".join(sets)+" WHERE id=?",tuple(vals))
                conn.commit()
            ok,details=_productionize_inbound(inbound_id,type_hint="modulo_unico_tesseramento")
            if ok:
                imported.append({"inbound_id":inbound_id,"tesserato_id":tid,"created":was_created,**(details or {})})
            else:
                blocked.append({"inbound_id":inbound_id,"tesserato_id":tid,"reason":str((details or {}).get("reason") or "modulo non prodotto")})

        action_status="executed" if not blocked else ("executed_partial" if (imported or created) else "blocked_safety")
        conn.execute("UPDATE bodymind_operator_actions SET status=?,confirmed_by=?,executed_at=?,payload_json=? WHERE id=?",
                     (action_status,_identity(),datetime.now().isoformat(timespec="seconds"),
                      json.dumps({**payload,"imported":imported,"created":created,"duplicates":duplicates,"blocked":blocked,"backup":backup_path},ensure_ascii=False),aid))
        conn.commit(); session.pop("bodymind_operator_pending_action",None)
        summary={"imported":len(imported),"new_athletes_created":len(created),"duplicates":len(duplicates),"review":len(blocked)}
        _update_upload_task(conn,task_id,summary,status="completed" if not blocked else "completed_with_review")
        out=f"Operazione completata: {len(created)} nuove tesserate create, {len(imported)} documenti importati, {len(duplicates)} duplicati non importati, {len(blocked)} elementi lasciati in verifica."
        if backup_path: out+=" Backup preventivo creato."
        return {"text":out,"mode":"action","created_athletes":created,"batch_imported":imported,"batch_duplicates":duplicates,"batch_blocked":blocked,
                "links":[{"label":"Apri Tesserati","href":"/tesserati"},{"label":"Apri Documenti","href":"/documenti"}]}

'''
    if anchor not in s:
        raise RuntimeError('R65 pending action anchor missing')
    s=s.replace(anchor,branch+anchor,1)

    s=s.replace('OPERATOR_VERSION = "R64.0-persistent-upload-task"','OPERATOR_VERSION = "R65.0-handwriting-enrollment"',1)
    OP.write_text(s,encoding='utf-8')
    py_compile.compile(str(OP),doraise=True)
    print('[operator-r65] PASS handwriting-enrollment preview-confirm create-profile second-gate',flush=True)
else:
    print('[operator-r65] already applied',flush=True)

# ---------------- Autopilot shared inbound fallback ----------------
es=EMAIL.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R65_AUTOPILOT_HANDWRITING' not in es:
    b=BACK/'routes_email_documents.py'
    if not b.exists(): shutil.copy2(EMAIL,b)

    wrapper=r'''

# BODYMIND_R65_AUTOPILOT_HANDWRITING
# Semantic visual fallback for unresolved inbound documents.
# It runs after the legacy classifier, so it does not disturb already-certain matches.
_original_process_inbound_attachment_r65 = process_inbound_attachment

def process_inbound_attachment(*args, **kwargs):
    res=_original_process_inbound_attachment_r65(*args, **kwargs)
    try:
        if not isinstance(res,dict) or int(res.get("tesserato_id") or 0)>0:
            return res
        filename=str(kwargs.get("filename") or (args[0] if len(args)>0 else "") or "")
        payload=kwargs.get("payload")
        if payload is None: payload=kwargs.get("data")
        if payload is None and len(args)>1: payload=args[1]
        payload=bytes(payload or b"")
        if not payload or len(payload)>18*1024*1024:
            return res
        source=str(kwargs.get("source") or "")
        # Operator has its own preview/confirmation workflow; never auto-create here for operator uploads.
        operator_source=(source=="operatore_bodymind")
        extracted=""
        try: extracted=str(extract_attachment_text(filename,payload) or "")
        except Exception: extracted=""
        probe=(filename+" "+extracted[:12000]).lower()
        enrollment_hint=any(x in probe for x in ("modulo unico","modulo iscrizione","modulo di iscrizione","domanda iscrizione","domanda di iscrizione","tesseramento","iscrizione"))
        type_hint="modulo_unico_tesseramento" if enrollment_hint else ""

        from .operator_doc_semantic_ai_r52 import analyze_bytes as _r65_analyze
        from .operator_doc_semantic_core_r52 import cache_put as _r65_cache_put
        from .enrollment_ingest_core_r65 import (
            find_existing_athlete as _r65_find_existing,
            create_athlete_from_analysis as _r65_create,
            enrollment_identity_ready as _r65_ready,
        )
        from .core import db as _r65_db
        conn=_r65_db()
        try:
            analysis=_r65_analyze(conn,filename,payload,extracted,type_hint,None)
            existing,match_reason=_r65_find_existing(conn,analysis)
            tid=int(existing["id"]) if existing else 0
            created=False
            if tid<=0 and not operator_source and _r65_ready(analysis,require_valid_cf=True):
                cr=_r65_create(conn,analysis,source="autopilot_r65",require_valid_cf=True)
                tid=int(cr.get("tesserato_id") or 0); created=bool(cr.get("created"))
            if tid<=0:
                res["semantic_analysis"]=analysis
                if str(analysis.get("document_type") or "")=="modulo_unico_tesseramento":
                    res["new_athlete_candidate"]=True
                return res

            icols={str(r[1]) for r in conn.execute("PRAGMA table_info(inbound_documents)").fetchall()}
            row=conn.execute("SELECT * FROM inbound_documents WHERE original_filename=? ORDER BY id DESC LIMIT 1",(filename,)).fetchone() if "original_filename" in icols else None
            if row:
                iid=int(row["id"])
                try: _r65_cache_put(conn,"inbound_documents",iid,analysis)
                except Exception: pass
                sets=[]; vals=[]
                for col in ("tesserato_id","matched_tesserato_id","suggested_tesserato_id"):
                    if col in icols: sets.append(col+"=?"); vals.append(tid)
                if "match_score" in icols: sets.append("match_score=?"); vals.append(100)
                if "document_type" in icols: sets.append("document_type=?"); vals.append(str(analysis.get("document_type") or "altro"))
                if "document_confidence" in icols: sets.append("document_confidence=?"); vals.append(int(round(float(analysis.get("confidence") or 0)*100)))
                if "status" in icols: sets.append("status=?"); vals.append("associato_tipo_da_verificare")
                if sets:
                    vals.append(iid)
                    conn.execute("UPDATE inbound_documents SET "+",".join(sets)+" WHERE id=?",tuple(vals))
                saved=str(row["saved_path"] or "") if "saved_path" in row.keys() else ""
                dcols={str(r[1]) for r in conn.execute("PRAGMA table_info(documenti)").fetchall()}
                if saved and "tesserato_id" in dcols and "filename" in dcols:
                    upd=["tesserato_id=?"]; uvals=[tid]
                    if "doc_type" in dcols: upd.append("doc_type=?"); uvals.append(str(analysis.get("document_type") or "altro"))
                    if "confidence" in dcols: upd.append("confidence=?"); uvals.append(int(round(float(analysis.get("confidence") or 0)*100)))
                    if "status" in dcols: upd.append("status=?"); uvals.append("da_verificare")
                    uvals.append(saved)
                    conn.execute("UPDATE documenti SET "+",".join(upd)+" WHERE filename=? AND coalesce(tesserato_id,0)=0",tuple(uvals))
            conn.commit()
            res["tesserato_id"]=tid
            res["semantic_match_reason"]=match_reason or ("nuova_tesserata_da_modulo" if created else "semantic")
            res["semantic_analysis"]=analysis
            res["new_athlete_created"]=created
            return res
        finally:
            conn.close()
    except Exception as exc:
        try: res["semantic_fallback_error"]=str(exc)[:180]
        except Exception: pass
        return res
'''
    es += wrapper
    EMAIL.write_text(es,encoding='utf-8')
    py_compile.compile(str(EMAIL),doraise=True)
    print('[autopilot-r65] PASS unresolved-handwriting-semantic-fallback strict-CF-auto-create',flush=True)
else:
    print('[autopilot-r65] already applied',flush=True)

py_compile.compile(str(HELPER_DST),doraise=True)
print('[r65] PASS shared handwriting vision + enrollment ingestion core',flush=True)
