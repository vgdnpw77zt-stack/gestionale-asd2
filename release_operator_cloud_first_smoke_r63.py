# -*- coding: utf-8 -*-
from __future__ import annotations
import json, sqlite3, subprocess, sys

code=r'''
import json, sqlite3, sys, uuid
sys.path.insert(0,"/data/top2_app")
import app as _full_app
from flask import session
from asd_app.core import app
import asd_app.routes_operator_bodymind as op

DB="/data/tenants/default/asd.db"
conv="r63-smoke-"+uuid.uuid4().hex[:10]

def business_counts():
    c=sqlite3.connect(DB,timeout=20)
    try:
        out={}
        for t in ("tesserati","documenti","inbound_documents","pagamenti","ricevute"):
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone():
                out[t]=int(c.execute("SELECT COUNT(*) FROM "+t).fetchone()[0])
        return out
    finally:c.close()

before=business_counts()
tests=[]
for q in (
    "Voglio sapere quanti hanno il certificato medico.",
    "E quanti non ce l'hanno?"
):
    with app.test_request_context('/operatore-bodymind/chat',method='POST',json={"message":q}):
        session.update({
            'logged':True,'username':'admin','display_name':'R63 QA','role':'admin','tenant_slug':'default',
            '_csrf_token':'r63','bodymind_operator_conversation':conv,'bodymind_operator_identity':'R63 QA'
        })
        resp=op.bodymind_operator_chat()
        if isinstance(resp,tuple):
            flask_resp,status=resp[0],int(resp[1])
        else:
            flask_resp,status=resp,200
        data=flask_resp.get_json()
        tests.append({
            "q":q,"status":status,"text":str(data.get("text") or ""),
            "mode":data.get("mode"),"cloud_first":bool(data.get("cloud_first")),
            "resolved_question":str(data.get("resolved_question") or ""),
            "target":data.get("target"),"value":data.get("value")
        })

after=business_counts()
t1,t2=tests
ok1=(t1["status"]==200 and t1["cloud_first"] and ("14" in t1["text"] or t1.get("value")==14))
ok2=(t2["status"]==200 and t2["cloud_first"] and ("23" in t2["text"] or t2.get("value")==23) and ("certificat" in t2["resolved_question"].lower() or "documento medico" in t2["resolved_question"].lower()))
c=sqlite3.connect(DB,timeout=20)
try:
    integrity=str(c.execute("PRAGMA integrity_check").fetchone()[0])
    fk=len(c.execute("PRAGMA foreign_key_check").fetchall())
finally:c.close()
result={"ok":ok1 and ok2 and before==after and integrity.lower()=="ok" and fk==0,
        "conversation_id":conv,"tests":tests,"counts_unchanged":before==after,"integrity":integrity,"foreign_keys":fk}
print(json.dumps(result,ensure_ascii=False))
'''
p=subprocess.run([sys.executable,"-c",code],capture_output=True,text=True,timeout=70)
if p.returncode!=0:
    raise RuntimeError("R63 child smoke failed: "+(p.stderr or p.stdout)[-1800:])
lines=[x for x in (p.stdout or "").splitlines() if x.strip()]
obj=json.loads(lines[-1])
print("[operator-r63-cloud-first-smoke] "+json.dumps(obj,ensure_ascii=False),flush=True)
if not obj.get("ok"):
    raise RuntimeError("R63 cloud-first contextual smoke failed: "+json.dumps(obj,ensure_ascii=False))
