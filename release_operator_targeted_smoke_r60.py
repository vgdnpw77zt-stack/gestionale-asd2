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
            out.append({
                'q':q,'mode':(r or {}).get('mode'),'target':(r or {}).get('target'),
                'elapsed_ms':ms,'text':text,
                'ok':(r or {}).get('mode')=='targeted_fact' and (r or {}).get('target')=='missing_mu' and 'Audit segreteria:' not in text
            })
    finally:
        conn.close()

c=sqlite3.connect(str(DB),timeout=20)
try:
    integrity=str(c.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(c.execute('PRAGMA foreign_key_check').fetchall())
finally:
    c.close()

result={'ok':all(x['ok'] for x in out) and integrity.lower()=='ok' and fk==0,'tests':out,'integrity':integrity,'foreign_keys':fk}
print('[operator-r60-targeted-smoke] '+json.dumps(result,ensure_ascii=False),flush=True)
if not result['ok']:
    raise RuntimeError('R60 targeted missing smoke failed: '+json.dumps(result,ensure_ascii=False))
