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
result={"ok":False,"elapsed_ms":None,"groups":0,"comparisons":0,"business_unchanged":False,"cross_type":False,"error":""}
original=op._semantic_same_pair

def forbidden_live_ai(*args,**kwargs):
    raise RuntimeError("R56 smoke: live AI comparison must never run in request-path duplicate scan")

try:
    with app.test_request_context('/operatore-bodymind'):
        session.update({'logged':True,'username':'admin','display_name':'R56 QA','role':'admin','tenant_slug':'default',
                        '_csrf_token':'r56-smoke','bodymind_operator_conversation':'r56-smoke',
                        'bodymind_operator_identity':'R56 QA'})
        conn=db()
        try:
            op._schema(conn)
            op._semantic_same_pair=forbidden_live_ai
            started=time.perf_counter()
            groups,comparisons=op._semantic_duplicate_groups(conn,None,200)
            elapsed_ms=int((time.perf_counter()-started)*1000)
            cross=False
            for g in groups:
                keep=conn.execute("SELECT * FROM documenti WHERE id=?",(int(g["keep_id"]),)).fetchone()
                for rid in g.get("remove_ids") or []:
                    rem=conn.execute("SELECT * FROM documenti WHERE id=?",(int(rid),)).fetchone()
                    if not keep or not rem:
                        cross=True; continue
                    if int(keep["tesserato_id"] or 0)!=int(rem["tesserato_id"] or 0):
                        cross=True
                    if op._canonical_document_kind(keep)!=op._canonical_document_kind(rem):
                        cross=True
            result.update({"elapsed_ms":elapsed_ms,"groups":len(groups),"comparisons":comparisons,"cross_type":cross})
        finally:
            op._semantic_same_pair=original
            conn.close()
except Exception as exc:
    result["error"]=repr(exc)[:500]

after=counts()
result["business_unchanged"]=(before==after)
result["ok"]=not result["error"] and result["business_unchanged"] and not result["cross_type"] and int(result["elapsed_ms"] or 999999)<8000
print("[operator-r56-dedupe-smoke] "+json.dumps(result,ensure_ascii=False),flush=True)
if not result["ok"]:
    raise RuntimeError("R56 duplicate latency/safety smoke failed: "+json.dumps(result,ensure_ascii=False))
