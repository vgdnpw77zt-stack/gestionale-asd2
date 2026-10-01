# -*- coding: utf-8 -*-
from __future__ import annotations
import json, sqlite3, subprocess, sys, uuid

code=r'''
import json, sqlite3, sys, uuid
sys.path.insert(0,"/data/top2_app")
import app as _full_app
from flask import session
from asd_app.core import app,db
import asd_app.routes_operator_bodymind as op

DB="/data/tenants/default/asd.db"
def counts():
    c=sqlite3.connect(DB,timeout=20)
    try:
        out={}
        for t in ("tesserati","documenti","inbound_documents","pagamenti","ricevute"):
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone():
                out[t]=int(c.execute("SELECT COUNT(*) FROM "+t).fetchone()[0])
        return out
    finally:c.close()

before=counts()
result={"task_ok":False,"summary_ok":False,"duplicate_ok":False,"counts_unchanged":False,"integrity":"","foreign_keys":None}
conv="r64-smoke-"+uuid.uuid4().hex[:10]

with app.test_request_context('/operatore-bodymind'):
    session.update({'logged':True,'username':'admin','display_name':'R64 QA','role':'admin','tenant_slug':'default',
                    '_csrf_token':'r64','bodymind_operator_conversation':conv,'bodymind_operator_identity':'R64 QA'})
    conn=db()
    try:
        op._schema(conn)
        task_id=op._set_upload_task(conn,{
            "document_type":"certificato_medico","production":True,"deduplicate":True,
            "associate_missing_only":True,"instruction":"QA","created_at":"2026-10-01T00:00:00"
        })
        task=op._current_upload_task(conn)
        result["task_ok"]=bool(task and task.get("id")==task_id and (task.get("payload") or {}).get("document_type")=="certificato_medico")
        op._update_upload_task(conn,task_id,{"received":21,"ready":7,"duplicates":12,"review":2},"awaiting_confirmation")
        task2=op._current_upload_task(conn)
        result["summary_ok"]=bool(task2 and (task2.get("summary") or {}).get("received")==21 and task2.get("status")=="awaiting_confirmation")

        row=conn.execute("SELECT * FROM documenti WHERE coalesce(tesserato_id,0)>0 ORDER BY id LIMIT 1").fetchone()
        if row:
            name,data,_=op._document_bytes_from_row(row)
            if data:
                analysis={"document_type":op._canonical_document_kind(row),"semantic_key":"qa","confidence":1.0}
                dup=op._semantic_key_duplicate(conn,int(row["tesserato_id"]),name,data,analysis)
                result["duplicate_ok"]=bool(dup.get("duplicate") and dup.get("method")=="sha256")
    finally:
        conn.close()

after=counts()
result["counts_unchanged"]=(before==after)
c=sqlite3.connect(DB,timeout=20)
try:
    result["integrity"]=str(c.execute("PRAGMA integrity_check").fetchone()[0])
    result["foreign_keys"]=len(c.execute("PRAGMA foreign_key_check").fetchall())
finally:c.close()
result["ok"]=all([result["task_ok"],result["summary_ok"],result["duplicate_ok"],result["counts_unchanged"],result["integrity"].lower()=="ok",result["foreign_keys"]==0])
print(json.dumps(result,ensure_ascii=False))
'''
p=subprocess.run([sys.executable,"-c",code],capture_output=True,text=True,timeout=60)
if p.returncode!=0:
    raise RuntimeError("R64 child smoke failed: "+(p.stderr or p.stdout)[-1500:])
lines=[x for x in (p.stdout or "").splitlines() if x.strip()]
obj=json.loads(lines[-1])
print("[operator-r64-upload-smoke] "+json.dumps(obj,ensure_ascii=False),flush=True)
if not obj.get("ok"):
    raise RuntimeError("R64 upload smoke failed: "+json.dumps(obj,ensure_ascii=False))
