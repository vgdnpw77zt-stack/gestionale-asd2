# -*- coding: utf-8 -*-
from __future__ import annotations
import inspect, json, sqlite3, sys
from pathlib import Path

APPROOT=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
sys.path.insert(0,str(APPROOT))
from asd_app import app

rows=[]
for rule in app.url_map.iter_rules():
    rs=str(rule)
    methods=sorted(m for m in rule.methods if m not in ('HEAD','OPTIONS'))
    if ('mobile/atleta' in rs or 'tesserat' in rs or 'critic' in rs):
        fn=app.view_functions.get(rule.endpoint)
        src=''
        try: src=inspect.getsource(fn) if fn else ''
        except Exception: src=''
        if any(m in methods for m in ('POST','PUT','PATCH')) or 'mobile/atleta' in rs or 'critic' in rs:
            rows.append({'rule':rs,'endpoint':rule.endpoint,'methods':methods,'source':src[:18000]})

print('[r99-active-routes] '+json.dumps(rows,ensure_ascii=False),flush=True)

# Smoke GETs only to identify canonical UI paths; no mutation.
client=app.test_client()
with client.session_transaction() as sess:
    sess['user_id']=1; sess['role']='admin'; sess['username']='admin'
smokes=[]
for path in ('/mobile/atlete','/mobile/atleta/19','/tesserati/19/scheda','/tesserati'):
    try:
        resp=client.get(path,follow_redirects=False)
        smokes.append({'path':path,'status':resp.status_code,'location':resp.headers.get('Location','')})
    except Exception as exc:
        smokes.append({'path':path,'error':repr(exc)})
print('[r99-route-smoke] '+json.dumps(smokes,ensure_ascii=False),flush=True)

conn=sqlite3.connect(str(DB),timeout=20)
try:
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0]); fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:
    conn.close()
print('[r99-selftest] PASS active Flask route/source audit integrity='+integrity+' fk='+str(fk),flush=True)
if integrity.lower()!='ok' or fk: raise RuntimeError('R99 DB integrity failed')
