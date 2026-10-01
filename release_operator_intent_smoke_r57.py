# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import json, sqlite3, sys, time

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
sys.path.insert(0,str(APP))
import app as _full_app
from flask import session
from asd_app.core import app,db
import asd_app.routes_operator_bodymind as op

result={"ok":False,"mode":"","elapsed_ms":None,"has_action":False,"business_unchanged":False,"error":""}
def counts():
    c=sqlite3.connect(str(DB),timeout=20)
    try:
        out={}
        for t in ("tesserati","documenti","inbound_documents","pagamenti","ricevute"):
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone():
                out[t]=int(c.execute("SELECT COUNT(*) FROM "+t).fetchone()[0])
        return out
    finally:
        c.close()

before=counts()
try:
    with app.test_request_context('/operatore-bodymind/chat'):
        session.update({'logged':True,'username':'admin','display_name':'R57 QA','role':'admin','tenant_slug':'default',
                        '_csrf_token':'r57-smoke','bodymind_operator_conversation':'r57-smoke',
                        'bodymind_operator_identity':'R57 QA'})
        conn=db()
        try:
            op._schema(conn)
            started=time.perf_counter()
            out=op._answer(conn,"Vorrei sapere se ci sono duplicati; ne va lasciato solamente uno di certificato medico per atleta e va lasciato solo un modulo unico per atleta.")
            elapsed_ms=int((time.perf_counter()-started)*1000)
            mode=str((out or {}).get("mode") or "")
            aid=(out or {}).get("action_id")
            result.update({"mode":mode,"elapsed_ms":elapsed_ms,"has_action":bool(aid)})
            if aid:
                conn.execute("DELETE FROM bodymind_operator_actions WHERE id=?",(int(aid),))
                conn.commit()
                session.pop("bodymind_operator_pending_action",None)
        finally:
            conn.close()
except Exception as exc:
    result["error"]=repr(exc)[:500]

after=counts()
result["business_unchanged"]=(before==after)
result["ok"]=not result["error"] and result["business_unchanged"] and int(result["elapsed_ms"] or 999999)<8000 and result["mode"] in ("confirm","agent_tool")
print("[operator-r57-intent-smoke] "+json.dumps(result,ensure_ascii=False),flush=True)
if not result["ok"]:
    raise RuntimeError("R57 intent smoke failed: "+json.dumps(result,ensure_ascii=False))
