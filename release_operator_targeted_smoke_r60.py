# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import json, subprocess, sys

APP=Path('/data/top2_app')
code=r'''
import json, sys, time
sys.path.insert(0,"/data/top2_app")
import app as _full_app
from flask import session
from asd_app.core import app,db
import asd_app.routes_operator_bodymind as op
phrases=[
  "A chi manca il modulo unico di iscrizione?",
  "A chi manca il modulo unico di iscrizione? non voglio l'audit",
]
out=[]
with app.test_request_context('/operatore-bodymind/chat'):
    session.update({'logged':True,'username':'admin','display_name':'R60 QA','role':'admin','tenant_slug':'default',
                    '_csrf_token':'r60','bodymind_operator_conversation':'r60','bodymind_operator_identity':'R60 QA'})
    conn=db()
    try:
        for q in phrases:
            t=time.perf_counter()
            r=op._answer(conn,q)
            ms=int((time.perf_counter()-t)*1000)
            text=str((r or {}).get('text') or '')
            out.append({'q':q,'mode':(r or {}).get('mode'),'target':(r or {}).get('target'),'elapsed_ms':ms,'text':text,
                        'ok':(r or {}).get('mode')=='targeted_fact' and (r or {}).get('target')=='missing_mu' and 'Audit segreteria:' not in text})
    finally:
        conn.close()
print(json.dumps({'ok':all(x['ok'] for x in out),'tests':out},ensure_ascii=False))
'''
p=subprocess.run([sys.executable,"-c",code],capture_output=True,text=True,timeout=45)
if p.returncode!=0:
    raise RuntimeError("R60 child smoke failed: "+(p.stderr or p.stdout)[-1200:])
lines=[x for x in (p.stdout or "").splitlines() if x.strip()]
obj=json.loads(lines[-1])
print("[operator-r60-targeted-smoke] "+json.dumps(obj,ensure_ascii=False),flush=True)
if not obj.get("ok"):
    raise RuntimeError("R60 targeted missing smoke failed: "+json.dumps(obj,ensure_ascii=False))
