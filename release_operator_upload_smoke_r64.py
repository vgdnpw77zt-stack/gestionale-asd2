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
        for t in ("tesserati","documenti","inbound_documents","pagamenti","ricevute","bodymind_operator_tasks","bodymind_operator_actions"):
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

        # Deterministic dedupe fixture on a temporary database copy only.
        # Do not depend on production documents still having a locally readable file.
        import os, tempfile
        fd,tmpdb=tempfile.mkstemp(prefix="bodymind_r64_",suffix=".db"); os.close(fd)
        fd,tmpfile=tempfile.mkstemp(prefix="bodymind_r64_doc_",suffix=".pdf")
        os.write(fd,b"%PDF-1.4\nBODYMIND-R64-DEDUPE-FIXTURE\n%%EOF\n"); os.close(fd)
        try:
            src=sqlite3.connect(DB,timeout=20); dst=sqlite3.connect(tmpdb)
            try: src.backup(dst)
            finally: dst.close(); src.close()
            tc=sqlite3.connect(tmpdb,timeout=20); tc.row_factory=sqlite3.Row
            try:
                tid=int(tc.execute("SELECT id FROM tesserati ORDER BY id LIMIT 1").fetchone()[0])
                info=tc.execute("PRAGMA table_info(documenti)").fetchall()
                desired={
                  "tesserato_id":tid,"titolo":"R64 dedupe fixture","categoria":"Certificato medico",
                  "doc_type":"certificato_medico","status":"salvato","visibile":1,
                  "filename":tmpfile,"original_filename":"r64_fixture.pdf","created_at":"2026-10-02T00:00:00",
                  "updated_at":"2026-10-02T00:00:00"
                }
                fields={}
                for ci in info:
                    name=str(ci[1]); typ=str(ci[2] or "").upper(); notnull=bool(ci[3]); default=ci[4]; pk=bool(ci[5])
                    if pk: continue
                    if name in desired:
                        fields[name]=desired[name]
                    elif notnull and default is None:
                        fields[name]=0 if any(x in typ for x in ("INT","REAL","NUM","DEC","FLOAT","DOUBLE")) else ""
                names=list(fields)
                cur=tc.execute("INSERT INTO documenti ("+",".join(names)+") VALUES ("+",".join("?" for _ in names)+")",
                               tuple(fields[k] for k in names))
                did=int(cur.lastrowid); tc.commit()
                row=tc.execute("SELECT * FROM documenti WHERE id=?",(did,)).fetchone()
                incoming=open(tmpfile,"rb").read()
                analysis={"document_type":"certificato_medico","semantic_key":"r64-fixture","confidence":1.0}
                dup=op._semantic_key_duplicate(tc,tid,"r64_fixture.pdf",incoming,analysis)
                result["duplicate_ok"]=bool(dup.get("duplicate") and dup.get("method")=="sha256" and int(dup.get("existing_id") or 0)==did)
            finally:
                tc.close()
        finally:
            try: os.unlink(tmpfile)
            except Exception: pass
            try: os.unlink(tmpdb)
            except Exception: pass
        # QA must leave no persistent workflow state behind.
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bodymind_operator_tasks'").fetchone():
            conn.execute("DELETE FROM bodymind_operator_tasks WHERE conversation_id=?",(conv,))
            conn.commit()
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
