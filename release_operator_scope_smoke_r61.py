# -*- coding: utf-8 -*-
from __future__ import annotations
import json, subprocess, sys

code=r'''
import json, sqlite3, sys, time
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

cases=[
 ("missing_mu","A chi manca il modulo unico di iscrizione?",("targeted_fact",),"Audit segreteria:"),
 ("pending","Quanti documenti ci sono da verificare?",("targeted_fact",),"Audit segreteria:"),
 ("missing_med","A chi manca il certificato medico?",("targeted_fact",),"Audit segreteria:"),
 ("expiring","Quali certificati medici sono scaduti o in scadenza?",("targeted_fact",),"Audit segreteria:"),
 ("athletes","Quanti tesserati abbiamo?",("fast_fact","targeted_fact"),"Audit segreteria:"),
 ("payments","Quanti pagamenti abbiamo?",("targeted_fact",),"Audit segreteria:"),
 ("receipts","Quante ricevute abbiamo?",("targeted_fact",),"Audit segreteria:"),
 ("minors","Quali minori hanno la tutela da rivedere?",("targeted_fact",),"Audit segreteria:"),
]
before=counts(); tests=[]
with app.test_request_context('/operatore-bodymind/chat'):
    session.update({'logged':True,'username':'admin','display_name':'R61 QA','role':'admin','tenant_slug':'default',
                    '_csrf_token':'r61','bodymind_operator_conversation':'r61','bodymind_operator_identity':'R61 QA'})
    conn=db()
    try:
        for name,q,modes,forbidden in cases:
            t=time.perf_counter(); r=op._answer(conn,q); ms=int((time.perf_counter()-t)*1000)
            txt=str((r or {}).get("text") or "")
            ok=(r or {}).get("mode") in modes and forbidden not in txt and ms<2000
            tests.append({"name":name,"mode":(r or {}).get("mode"),"ms":ms,"text":txt[:500],"ok":ok})
        # Force a broad tool chosen by a planner on a narrow question: scope guard must narrow it.
        r=op._execute_agent_tool(conn,{"tool":"secretary_audit","args":{}},"A chi manca il modulo unico?")
        txt=str((r or {}).get("text") or "")
        tests.append({"name":"broad_tool_guard","mode":(r or {}).get("mode"),"text":txt[:500],
                      "ok":bool((r or {}).get("scope_guard")) and "Audit segreteria:" not in txt})
        # Explicit global request must still allow the real audit.
        r=op._execute_agent_tool(conn,{"tool":"secretary_audit","args":{}},"Fammi un audit completo della segreteria")
        txt=str((r or {}).get("text") or "")
        tests.append({"name":"explicit_audit_allowed","mode":(r or {}).get("mode"),"text":txt[:500],
                      "ok":"Audit segreteria:" in txt and not (r or {}).get("scope_guard")})
    finally:
        conn.close()
after=counts()
c=sqlite3.connect(DB,timeout=20)
try:
    integrity=str(c.execute("PRAGMA integrity_check").fetchone()[0])
    fk=len(c.execute("PRAGMA foreign_key_check").fetchall())
finally:c.close()
result={"ok":all(x["ok"] for x in tests) and before==after and integrity.lower()=="ok" and fk==0,
        "tests":tests,"counts_unchanged":before==after,"integrity":integrity,"foreign_keys":fk}
print(json.dumps(result,ensure_ascii=False))
'''
p=subprocess.run([sys.executable,"-c",code],capture_output=True,text=True,timeout=60)
if p.returncode!=0:
    raise RuntimeError("R61 child smoke failed: "+(p.stderr or p.stdout)[-1500:])
lines=[x for x in (p.stdout or "").splitlines() if x.strip()]
obj=json.loads(lines[-1])
print("[operator-r61-scope-smoke] "+json.dumps(obj,ensure_ascii=False),flush=True)
if not obj.get("ok"):
    raise RuntimeError("R61 response-scope smoke failed: "+json.dumps(obj,ensure_ascii=False))
