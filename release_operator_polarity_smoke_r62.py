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

cases=[
 ("positive1","Voglio sapere quanti hanno il certificato medico.","present_medical_count",14,"23"),
 ("positive2","Quanti sono i tesserati con documento medico riconosciuto?","present_medical_count",14,"23"),
 ("negative","Quanti tesserati non hanno il certificato medico riconosciuto?","missing_medical_count",23,"14"),
 ("ambiguous","Quanti certificati medici abbiamo?","medical_polarity_clarification",None,None),
]
out=[]
with app.test_request_context('/operatore-bodymind/chat'):
    session.update({'logged':True,'username':'admin','display_name':'R62 QA','role':'admin','tenant_slug':'default',
                    '_csrf_token':'r62','bodymind_operator_conversation':'r62','bodymind_operator_identity':'R62 QA'})
    conn=db()
    try:
        for name,q,target,expected,bad in cases:
            t=time.perf_counter(); r=op._answer(conn,q); ms=int((time.perf_counter()-t)*1000)
            txt=str((r or {}).get("text") or "")
            ok=(r or {}).get("target")==target and ms<2000
            if expected is not None:
                ok=ok and int((r or {}).get("value") or -1)==expected and str(expected) in txt and (bad not in txt if bad else True)
            else:
                ok=ok and (r or {}).get("mode")=="clarify"
            out.append({"name":name,"q":q,"mode":(r or {}).get("mode"),"target":(r or {}).get("target"),
                        "value":(r or {}).get("value"),"ms":ms,"text":txt,"ok":ok})
    finally:
        conn.close()

c=sqlite3.connect("/data/tenants/default/asd.db",timeout=20)
try:
    integrity=str(c.execute("PRAGMA integrity_check").fetchone()[0])
    fk=len(c.execute("PRAGMA foreign_key_check").fetchall())
finally:c.close()

result={"ok":all(x["ok"] for x in out) and integrity.lower()=="ok" and fk==0,
        "tests":out,"integrity":integrity,"foreign_keys":fk}
print(json.dumps(result,ensure_ascii=False))
'''
p=subprocess.run([sys.executable,"-c",code],capture_output=True,text=True,timeout=60)
if p.returncode!=0:
    raise RuntimeError("R62 child smoke failed: "+(p.stderr or p.stdout)[-1500:])
lines=[x for x in (p.stdout or "").splitlines() if x.strip()]
obj=json.loads(lines[-1])
print("[operator-r62-polarity-smoke] "+json.dumps(obj,ensure_ascii=False),flush=True)
if not obj.get("ok"):
    raise RuntimeError("R62 polarity smoke failed: "+json.dumps(obj,ensure_ascii=False))
