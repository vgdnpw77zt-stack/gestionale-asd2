from pathlib import Path
import py_compile, shutil

APP=Path('/data/top2_app')
P=APP/'asd_app/routes_operator_bodymind.py'
MARK=APP/'.BODYMIND_OPERATOR_UPLOAD_SEMANTIC_R52'
BACK=Path('/data/release_backups/20261001_operator_r52_upload/routes_operator_bodymind.py')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')
s=P.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R52_UPLOAD_SEMANTIC' in s:
    print('[operator-r52-upload] already applied',flush=True)
    raise SystemExit(0)

if not BACK.exists():
    BACK.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(P,BACK)

old='''            extracted=""
            try: extracted=extract_attachment_text(name,data) or ""
            except Exception: extracted=""
            athlete_match=None
            try: athlete_match=find_tesserato_for_text((name+" "+extracted).strip(),current_username())
            except Exception: athlete_match=None
            asd_kind=_classify_asd_document(name,extracted) if not athlete_match else None'''
new='''            extracted=""
            try: extracted=extract_attachment_text(name,data) or ""
            except Exception: extracted=""

            # BODYMIND_R52_UPLOAD_SEMANTIC
            semantic=None; semantic_error=""; semantic_athlete=None
            semantic_match_score=0.0; semantic_match_reason=""
            sem_conn=db()
            try:
                try:
                    semantic=_semantic_for_new_bytes(sem_conn,name,data,extracted,type_hint)
                    semantic_athlete,semantic_match_score,semantic_match_reason=_semantic_match_athlete(sem_conn,semantic)
                except Exception as exc:
                    semantic_error=str(exc)[:180]
                if semantic and semantic_athlete:
                    duplicate=_same_existing_document(sem_conn,int(semantic_athlete["id"]),name,data,semantic)
                    if duplicate.get("duplicate"):
                        results.append({
                            "name":name,"status":"gia_presente","tesserato_id":int(semantic_athlete["id"]),
                            "type":semantic.get("document_type"),"confidence":round(float(duplicate.get("confidence") or 0)*100),
                            "folder":"Dossier","production":False,"skipped_duplicate":True,
                            "existing_document_id":duplicate.get("existing_id"),
                            "reason":duplicate.get("reason"),"comparison_method":duplicate.get("method"),
                            "semantic_person":semantic.get("person_name"),"semantic_summary":semantic.get("content_summary")
                        })
                        continue
            finally:
                sem_conn.close()

            athlete_match=None
            try:
                athlete_match=find_tesserato_for_text((name+" "+extracted+" "+str((semantic or {}).get("person_name") or "")).strip(),current_username())
            except Exception: athlete_match=None
            asd_kind=_classify_asd_document(name,extracted) if not athlete_match and not semantic_athlete else None'''
if old not in s:
    raise RuntimeError('R52 upload extraction anchor missing')
s=s.replace(old,new,1)

old='''            res=process_inbound_attachment(
                name,data,subject="Operatore BodyMind",
                sender=current_username(),body_text="Caricato dalla segreteria Operatore BodyMind",
                source="operatore_bodymind"
            )'''
new='''            declared_mismatch=False
            if semantic and type_hint and float(semantic.get("confidence") or 0)>=.85:
                declared_mismatch=_norm(semantic.get("document_type"))!=_norm(type_hint)
            res=process_inbound_attachment(
                name,data,subject="Operatore BodyMind",
                sender=current_username(),
                body_text="Caricato dalla segreteria Operatore BodyMind. Lettura: "+str((semantic or {}).get("person_name") or "")+" "+str((semantic or {}).get("document_type") or ""),
                source="operatore_bodymind"
            )'''
if old not in s:
    raise RuntimeError('R52 upload process anchor missing')
s=s.replace(old,new,1)

old='''            conn1=db()
            try:
                inbound=_latest_inbound_after(conn1,before_id,name)
                inbound_id=int(inbound["id"]) if inbound else 0
            finally:
                conn1.close()
            produced=False; production_details={}
            if production_mode and inbound_id:
                produced,production_details=_productionize_inbound(inbound_id,type_hint=type_hint)'''
new='''            conn1=db()
            semantic_identity_conflict=False
            try:
                inbound=_latest_inbound_after(conn1,before_id,name)
                inbound_id=int(inbound["id"]) if inbound else 0
                if inbound_id and semantic:
                    _docsem_cache_put(conn1,"inbound_documents",inbound_id,semantic)
                if inbound_id and semantic_athlete and float(semantic_match_score or 0)>=.94:
                    current_tid=int(res.get("tesserato_id") or 0)
                    semantic_tid=int(semantic_athlete["id"])
                    if current_tid and current_tid!=semantic_tid:
                        semantic_identity_conflict=True
                    else:
                        ic=_cols(conn1,"inbound_documents")
                        sets=[]; vals=[]
                        for col in ("tesserato_id","matched_tesserato_id","suggested_tesserato_id"):
                            if col in ic:
                                sets.append(col+"=?"); vals.append(semantic_tid)
                        if "match_score" in ic:
                            sets.append("match_score=?"); vals.append(int(round(semantic_match_score*100)))
                        if sets:
                            vals.append(inbound_id)
                            conn1.execute("UPDATE inbound_documents SET "+",".join(sets)+" WHERE id=?",tuple(vals))
                            conn1.commit()
                            res["tesserato_id"]=semantic_tid
            finally:
                conn1.close()
            produced=False; production_details={}
            semantic_ready=bool(semantic) and not declared_mismatch and not semantic_identity_conflict
            if production_mode and inbound_id and semantic_ready:
                produced,production_details=_productionize_inbound(
                    inbound_id,type_hint=type_hint or str((semantic or {}).get("document_type") or "")
                )'''
if old not in s:
    raise RuntimeError('R52 upload production anchor missing')
s=s.replace(old,new,1)

P.write_text(s,encoding='utf-8')
py_compile.compile(str(P),doraise=True)
MARK.write_text('R52 semantic upload active\n',encoding='utf-8')
print('[operator-r52-upload] PASS read-before-store identity-aware duplicate-skip production-gate',flush=True)
