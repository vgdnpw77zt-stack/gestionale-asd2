# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import py_compile, shutil

APP=Path('/data/top2_app')
P=APP/'asd_app/routes_operator_bodymind.py'
BACK=Path('/data/release_backups/20261001_operator_r67/routes_operator_bodymind.py')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

s=P.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R67_ASYNC_UPLOAD_SERVER' not in s:
    BACK.parent.mkdir(parents=True,exist_ok=True)
    if not BACK.exists():
        shutil.copy2(P,BACK)

    anchor='''@app.after_request
def bodymind_family_logo_override(resp):
'''
    routes=r'''# BODYMIND_R67_ASYNC_UPLOAD_SERVER
@app.post("/operatore-bodymind/upload-async")
@login_required
def bodymind_operator_upload_async():
    if current_role() not in ("admin","manager"):
        return jsonify({"text":"L’account connesso non può affidare documenti all’Autopilot.","mode":"warning"}),403
    incoming=request.files.getlist("files")
    if not incoming:
        return jsonify({"text":"Non ho ricevuto file.","mode":"warning"}),400
    if len(incoming)>120:
        return jsonify({"text":"Puoi inviare al massimo 120 file per batch.","mode":"warning"}),400
    job_id=uuid.uuid4().hex
    root=Path("/data/operator_upload_jobs")/job_id
    root.mkdir(parents=True,exist_ok=True)
    specs=[]; total_bytes=0
    allowed={".pdf",".png",".jpg",".jpeg",".webp",".docx"}
    try:
        for idx,f in enumerate(incoming,1):
            original=(f.filename or ("documento_"+str(idx))).replace(chr(92),"/").split("/")[-1]
            ext=Path(original).suffix.lower()
            if ext not in allowed:
                raise ValueError(original+" · formato non supportato")
            safe=re.sub(r"[^A-Za-z0-9._-]+","_",original).strip("._-") or ("documento_"+str(idx)+ext)
            target=root/(str(idx).zfill(3)+"_"+safe)
            size=0
            with target.open("wb") as out:
                while True:
                    chunk=f.stream.read(1024*1024)
                    if not chunk: break
                    size+=len(chunk); total_bytes+=len(chunk)
                    if size>40*1024*1024 or total_bytes>160*1024*1024:
                        raise ValueError("Batch troppo grande: massimo 40 MB per file e 160 MB complessivi.")
                    out.write(chunk)
            specs.append({"name":original,"path":str(target),"size":size})
    except Exception as exc:
        shutil.rmtree(root,ignore_errors=True)
        return jsonify({"text":"Caricamento rifiutato: "+str(exc)[:220],"mode":"warning"}),400

    hint=str(request.form.get("document_type_hint") or "").strip()
    production=str(request.form.get("production_mode") or "0").strip().lower() not in ("0","false","no","off")
    conn=db()
    try:
        _schema(conn)
        _async_upload_create_job(
            conn,job_id,_conv_id(),current_username(),current_role(),
            str(session.get("tenant_slug") or "default"),
            str(session.get("display_name") or current_username()),
            hint,production,specs
        )
        _log(conn,"system","Upload accettato dal server e accodato",{
            "job_id":job_id,"source_files":len(specs),"bytes":total_bytes,"document_type":hint
        })
    finally:
        conn.close()
    _async_upload_start_job(app,db,bodymind_operator_upload,job_id)
    return jsonify({
        "text":f"Il server BodyMind ha ricevuto {len(specs)} file. L’analisi continua in background.",
        "mode":"upload_processing","job_id":job_id,"status":"queued","source_files":len(specs)
    }),202


@app.get("/operatore-bodymind/upload-job/<job_id>")
@login_required
def bodymind_operator_upload_job_status(job_id):
    conn=db()
    try:
        row=_async_upload_get_job(conn,job_id)
        if not row:
            return jsonify({"text":"Job di caricamento non trovato.","status":"failed"}),404
        if current_role()!="admin" and str(row["username"] or "")!=current_username():
            return jsonify({"text":"Non hai accesso a questo job.","status":"failed"}),403
        status=str(row["status"] or "")
        if status=="completed":
            try: result=json.loads(str(row["result_json"] or "{}"))
            except Exception: result={}
            aid=int((result or {}).get("action_id") or 0)
            if aid:
                session["bodymind_operator_pending_action"]=aid
            return jsonify({"status":"completed","job_id":job_id,"result":result})
        if status=="failed":
            return jsonify({
                "status":"failed","job_id":job_id,
                "text":"L’analisi del file non si è completata. Non considero l’importazione conclusa.",
                "error":str(row["error"] or "")[:500]
            })
        return jsonify({"status":status,"job_id":job_id,"text":"Il server ha ricevuto i file e li sta analizzando."})
    finally:
        conn.close()


'''
    if anchor not in s:
        raise RuntimeError('R67 route anchor missing')
    s=s.replace(anchor,routes+anchor,1)

if 'OPERATOR_VERSION = "R66.0-upload-truth-multidoc"' in s:
    s=s.replace('OPERATOR_VERSION = "R66.0-upload-truth-multidoc"','OPERATOR_VERSION = "R67.0-async-upload-jobs"',1)

P.write_text(s,encoding='utf-8')
py_compile.compile(str(P),doraise=True)
print('[operator-r67] PASS async-upload-routes persistent-job-core background-analysis session-confirmation',flush=True)
