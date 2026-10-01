# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import py_compile, shutil

APP=Path('/data/top2_app')
P=APP/'asd_app/routes_operator_bodymind.py'
BACK=Path('/data/release_backups/20261001_operator_r66/routes_operator_bodymind.py')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

s=P.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R66_UPLOAD_TRUTH_MULTIDOC' in s:
    print('[operator-r66] already applied',flush=True)
    raise SystemExit(0)

BACK.parent.mkdir(parents=True,exist_ok=True)
if not BACK.exists():
    shutil.copy2(P,BACK)

# Imports used to materialize logical PDF segments as in-memory uploads.
if 'from io import BytesIO\n' not in s:
    s=s.replace('from pathlib import Path\n','from pathlib import Path\nfrom io import BytesIO\n',1)
if 'from werkzeug.datastructures import FileStorage\n' not in s:
    s=s.replace('from flask import Response, jsonify, redirect, request, session, send_file\n',
                'from flask import Response, jsonify, redirect, request, session, send_file\nfrom werkzeug.datastructures import FileStorage\n',1)

# Semantic module now also exposes multi-document PDF segmentation.
old='''from .operator_doc_semantic_ai_r52 import (
    analyze_bytes as _docsem_analyze_bytes,
    compare_bytes as _docsem_compare_bytes,
)
'''
new='''from .operator_doc_semantic_ai_r52 import (
    analyze_bytes as _docsem_analyze_bytes,
    compare_bytes as _docsem_compare_bytes,
    segment_pdf_documents as _docsem_segment_pdf_documents,
)
'''
if old not in s:
    raise RuntimeError('R66 semantic import anchor missing')
s=s.replace(old,new,1)

# Frontend: never claim that a file was received before HTTP success.
old="addMsg('Ho ricevuto '+files.length+' file. Li analizzo e porto in produzione quelli certi.','bot');"
new="addMsg('Sto inviando '+files.length+' file al server BodyMind. Ti confermo la ricezione appena il server li prende in carico.','bot');"
if old not in s:
    raise RuntimeError('R66 quick-upload optimistic message anchor missing')
s=s.replace(old,new,1)

old="const data=await r.json();addMsg(data.text||'Analisi completata.','bot',data);speak(data.text||'Analisi completata.');"
new="const data=await r.json();if(!r.ok)throw new Error(data.text||('Upload HTTP '+r.status));addMsg(data.text||'Ricezione e analisi completate.','bot',data);speak(data.text||'Ricezione e analisi completate.');"
if old not in s:
    raise RuntimeError('R66 quick-upload response anchor missing')
s=s.replace(old,new,1)

old="addMsg('Sto elaborando '+files.length+' file. I match certi verranno portati fino alla produzione e verificati.','bot');"
new="addMsg('Sto inviando '+files.length+' file al server BodyMind. L’analisi inizierà dopo la conferma di ricezione.','bot');"
if old not in s:
    raise RuntimeError('R66 form-upload optimistic message anchor missing')
s=s.replace(old,new,1)

old='''          const data=await r.json();
          addMsg(data.text||'Analisi completata.','bot',data);
          speak(data.text||'Analisi completata.');
'''
new='''          const data=await r.json();
          if(!r.ok)throw new Error(data.text||('Upload HTTP '+r.status));
          addMsg(data.text||'Ricezione e analisi completate.','bot',data);
          speak(data.text||'Ricezione e analisi completate.');
'''
if old not in s:
    raise RuntimeError('R66 form-upload response anchor missing')
s=s.replace(old,new,1)

# Backend: persist "upload in progress" immediately when Flask has actually received the request.
anchor='''    if type_hint not in allowed_hints:
        return jsonify({"text":"Tipo documento indicato non valido.","mode":"warning"}),400

    from .routes_email_documents import process_inbound_attachment, ALLOWED_INBOUND_DOCS, extract_attachment_text, find_tesserato_for_text
'''
insert='''    if type_hint not in allowed_hints:
        return jsonify({"text":"Tipo documento indicato non valido.","mode":"warning"}),400

    # BODYMIND_R66_UPLOAD_TRUTH_MULTIDOC
    source_file_count=len(files)
    source_file_names=[str(getattr(x,"filename","") or "documento")[:180] for x in files[:120]]
    conn_started=db()
    try:
        _schema(conn_started)
        task_id=int((task or {}).get("id") or 0)
        if not task_id:
            task_id=_set_upload_task(conn_started,{
                "document_type":type_hint,"production":production_mode,"deduplicate":deduplicate,
                "associate_missing_only":True,"instruction":"upload diretto",
                "created_at":datetime.now().isoformat(timespec="seconds")
            })
            task={"id":task_id,"payload":payload}
        _update_upload_task(conn_started,task_id,{
            "uploading":True,"source_files":source_file_count,"file_names":source_file_names,
            "document_type":type_hint
        },status="active")
        _log(conn_started,"system","R66 upload ricevuto dal server",{
            "task_id":task_id,"source_files":source_file_count,"file_names":source_file_names
        })
    finally:
        conn_started.close()

    from .routes_email_documents import process_inbound_attachment, ALLOWED_INBOUND_DOCS, extract_attachment_text, find_tesserato_for_text
'''
if anchor not in s:
    raise RuntimeError('R66 upload-start anchor missing')
s=s.replace(anchor,insert,1)

# Before the normal per-file pipeline, split a PDF containing several logical certificates.
anchor='''    results=[]; errors=[]; ready_ids=[]; duplicate_items=[]; review_items=[]; new_athletes=[]
    for f in files[:120]:
'''
insert='''    multidoc_sources=[]
    expanded_files=[]
    for original in files[:120]:
        original_name=(getattr(original,"filename","") or "documento").replace(chr(92),"/").split("/")[-1]
        original_ext=Path(original_name).suffix.lower()
        should_segment=(original_ext==".pdf" and type_hint=="certificato_medico")
        if not should_segment:
            expanded_files.append(original)
            continue
        try:
            raw=original.read()
            original.stream.seek(0)
            if not raw or len(raw)>40*1024*1024:
                expanded_files.append(original)
                continue
            conn_seg=db()
            try:
                segmented=_docsem_segment_pdf_documents(
                    conn_seg,original_name,raw,type_hint,_record_response_usage
                )
            finally:
                conn_seg.close()
            segments=(segmented or {}).get("segments") or []
            if bool((segmented or {}).get("multiple")) and len(segments)>1:
                # Preserve the original source PDF on the persistent volume.
                src_dir=Path("/data/operator_upload_sources")
                src_dir.mkdir(parents=True,exist_ok=True)
                src_name=datetime.now().strftime("%Y%m%d_%H%M%S")+"_"+_docsem_sha256(raw)[:12]+"_"+re.sub(r"[^A-Za-z0-9._-]+","_",original_name)
                try:
                    (src_dir/src_name).write_bytes(raw)
                except Exception:
                    pass
                multidoc_sources.append({
                    "source_name":original_name,"page_count":int((segmented or {}).get("page_count") or 0),
                    "logical_documents":len(segments)
                })
                for seg in segments:
                    piece=bytes(seg.get("data") or b"")
                    if not piece:
                        continue
                    expanded_files.append(FileStorage(
                        stream=BytesIO(piece),
                        filename=str(seg.get("filename") or original_name),
                        content_type="application/pdf"
                    ))
            else:
                expanded_files.append(original)
        except Exception as exc:
            try:
                original.stream.seek(0)
            except Exception:
                pass
            expanded_files.append(original)
            print("[operator-r66] multidoc_segment_error="+repr(exc)[:500],flush=True)
    files=expanded_files

    results=[]; errors=[]; ready_ids=[]; duplicate_items=[]; review_items=[]; new_athletes=[]
    for f in files[:120]:
'''
if anchor not in s:
    raise RuntimeError('R66 multidoc expansion anchor missing')
s=s.replace(anchor,insert,1)

# Final summary must distinguish physical files from logical documents.
old='''    summary={"received":len(results),"ready":len(ready_ids),"new_athletes":len(new_athletes),"duplicates":len(duplicate_items),"review":len(review_items),"errors":len(errors),"document_type":type_hint}
'''
new='''    summary={"received":len(results),"source_files":source_file_count,"logical_documents":len(results),
             "multidoc_sources":multidoc_sources,"uploading":False,
             "ready":len(ready_ids),"new_athletes":len(new_athletes),"duplicates":len(duplicate_items),
             "review":len(review_items),"errors":len(errors),"document_type":type_hint}
'''
if old not in s:
    raise RuntimeError('R66 summary anchor missing')
s=s.replace(old,new,1)

old='''        text=f"Ho analizzato {len(results)} file: {len(ready_ids)} documenti nuovi per tesserate già presenti, {len(new_athletes)} moduli di nuove tesserate leggibili, {len(duplicate_items)} duplicati che non importerò, {len(review_items)} da verificare."
'''
new='''        text=f"Il server ha ricevuto {source_file_count} file e ha analizzato {len(results)} documenti logici: {len(ready_ids)} documenti nuovi per tesserate già presenti, {len(new_athletes)} moduli di nuove tesserate leggibili, {len(duplicate_items)} duplicati che non importerò, {len(review_items)} da verificare."
        if multidoc_sources:
            text+=" Ho rilevato file multipli interni: "+", ".join(
                str(x.get("source_name"))+" → "+str(x.get("logical_documents"))+" documenti" for x in multidoc_sources
            )+"."
'''
if old not in s:
    raise RuntimeError('R66 final-text anchor missing')
s=s.replace(old,new,1)

# Make upload state authoritative for conversational follow-ups.
old='''            "\\nSe il task documentale contiene document_type o last_batch, NON chiedere di nuovo che tipo di file sono e NON fingere di non averli ricevuti. "+
'''
new='''            "\\nSe il task documentale contiene document_type o last_batch, NON chiedere di nuovo che tipo di file sono. "+
            "\\nSe last_batch.uploading=true, il server HA ricevuto la richiesta di upload e la sta elaborando: dillo chiaramente, senza sostenere che non ci sono allegati. "+
            "\\nSe last_batch.uploading=false e contiene source_files/logical_documents, usa quei numeri come fonte di verità sul batch. "+
'''
if old not in s:
    raise RuntimeError('R66 planner upload-state anchor missing')
s=s.replace(old,new,1)

s=s.replace('OPERATOR_VERSION = "R65.0-handwriting-enrollment"','OPERATOR_VERSION = "R66.0-upload-truth-multidoc"',1)

P.write_text(s,encoding='utf-8')
py_compile.compile(str(P),doraise=True)
print('[operator-r66] PASS truthful-upload-ui server-receipt-state multidoc-pdf-segmentation source-preserve planner-upload-state',flush=True)
