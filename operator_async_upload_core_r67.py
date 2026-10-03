# -*- coding: utf-8 -*-
from __future__ import annotations
import json, threading
from datetime import datetime
from pathlib import Path
from flask import session

def ensure_schema(conn):
    conn.execute("""
      CREATE TABLE IF NOT EXISTS bodymind_operator_upload_jobs(
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        username TEXT NOT NULL,
        role TEXT NOT NULL,
        tenant_slug TEXT NOT NULL,
        display_name TEXT,
        document_type_hint TEXT,
        production_mode INTEGER NOT NULL DEFAULT 0,
        files_json TEXT NOT NULL,
        status TEXT NOT NULL,
        result_json TEXT,
        error TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bodymind_upload_jobs_conv ON bodymind_operator_upload_jobs(conversation_id,created_at)")
    conn.commit()

def create_job(conn,job_id,conversation_id,username,role,tenant_slug,display_name,hint,production,files):
    ensure_schema(conn)
    now=datetime.now().isoformat(timespec="seconds")
    conn.execute(
      """INSERT INTO bodymind_operator_upload_jobs
         (id,conversation_id,username,role,tenant_slug,display_name,document_type_hint,production_mode,files_json,status,created_at,updated_at)
         VALUES(?,?,?,?,?,?,?,?,?,'queued',?,?)""",
      (job_id,conversation_id,username,role,tenant_slug,display_name,hint,1 if production else 0,
       json.dumps(files,ensure_ascii=False),now,now)
    )
    conn.commit()

def get_job(conn,job_id):
    ensure_schema(conn)
    return conn.execute("SELECT * FROM bodymind_operator_upload_jobs WHERE id=?",(str(job_id),)).fetchone()

def update_job(db,job_id,status,result=None,error=""):
    conn=db()
    try:
        ensure_schema(conn)
        conn.execute(
          "UPDATE bodymind_operator_upload_jobs SET status=?,result_json=?,error=?,updated_at=? WHERE id=?",
          (status,json.dumps(result,ensure_ascii=False) if isinstance(result,dict) else None,
           str(error or "")[:1200],datetime.now().isoformat(timespec="seconds"),str(job_id))
        )
        conn.commit()
    finally:
        conn.close()

def run_job(app,db,upload_func,job_id):
    conn=db()
    try:
        row=get_job(conn,job_id)
        if not row:
            return
        cur=conn.execute(
          "UPDATE bodymind_operator_upload_jobs SET status='processing',updated_at=? WHERE id=? AND status='queued'",
          (datetime.now().isoformat(timespec="seconds"),str(job_id))
        )
        conn.commit()
        if int(cur.rowcount or 0)!=1:
            return
        meta={k:row[k] for k in row.keys()}
    finally:
        conn.close()

    opened=[]
    try:
        specs=json.loads(str(meta.get("files_json") or "[]"))
        data={"files":[],"production_mode":"1" if int(meta.get("production_mode") or 0) else "0"}
        hint=str(meta.get("document_type_hint") or "")
        if hint:
            data["document_type_hint"]=hint
        for spec in specs:
            path=Path(str(spec.get("path") or ""))
            if not path.is_file():
                raise FileNotFoundError("staging non disponibile: "+path.name)
            fh=path.open("rb"); opened.append(fh)
            data["files"].append((fh,str(spec.get("name") or path.name)))
        with app.test_request_context("/operatore-bodymind/upload",method="POST",data=data,content_type="multipart/form-data"):
            session.update({
              "logged":True,
              "username":str(meta.get("username") or ""),
              "display_name":str(meta.get("display_name") or meta.get("username") or ""),
              "role":str(meta.get("role") or "viewer"),
              "tenant_slug":str(meta.get("tenant_slug") or "default"),
              "_csrf_token":"r67-background",
              "bodymind_operator_conversation":str(meta.get("conversation_id") or ""),
              "bodymind_operator_identity":str(meta.get("display_name") or meta.get("username") or ""),
            })
            # BODYMIND_ASYNC_WRAPPED_UPLOAD_DISPATCH
            # Resolve the live Flask view instead of calling the stale function object
            # captured by /upload-async.  Runtime wrappers (notably the canonical
            # no-match MU flow) must run identically for foreground and background uploads.
            effective_upload=upload_func
            try:
                for rule in app.url_map.iter_rules():
                    if str(rule.rule)=="/operatore-bodymind/upload" and "POST" in rule.methods:
                        candidate=app.view_functions.get(str(rule.endpoint))
                        if callable(candidate):
                            effective_upload=candidate
                        break
            except Exception:
                effective_upload=upload_func
            response=effective_upload()
            if isinstance(response,tuple):
                flask_response,status=response[0],int(response[1])
            else:
                flask_response,status=response,200
            result=flask_response.get_json(silent=True) or {}
            if status>=400:
                raise RuntimeError(str(result.get("text") or ("upload HTTP "+str(status))))
            update_job(db,job_id,"completed",result=result)
    except Exception as exc:
        update_job(db,job_id,"failed",error=repr(exc))
        try: app.logger.exception("R67 upload job failed id=%s",job_id)
        except Exception: pass
    finally:
        for fh in opened:
            try: fh.close()
            except Exception: pass

def start_job(app,db,upload_func,job_id):
    thread=threading.Thread(
      target=run_job,args=(app,db,upload_func,str(job_id)),
      daemon=True,name="bodymind-upload-"+str(job_id)[:8]
    )
    thread.start()
