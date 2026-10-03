# -*- coding: utf-8 -*-
from __future__ import annotations
import inspect, json, sqlite3, sys
from pathlib import Path
APP=Path('/data/top2_app'); DB=Path('/data/tenants/default/asd.db')
sys.path.insert(0,str(APP))
import app as _full_app
from asd_app.core import app
routes=[]
for rule in sorted(app.url_map.iter_rules(),key=lambda r:str(r.rule)):
    route=str(rule.rule); ep=str(rule.endpoint)
    if any(k in route.lower() or k in ep.lower() for k in ('pagament','presenz','attendance','lezion','corso')):
        fn=app.view_functions.get(ep); src=''
        try: src=inspect.getsource(fn)[:14000]
        except Exception: pass
        routes.append({'route':route,'endpoint':ep,'methods':sorted(rule.methods or []),'source':src})
conn=sqlite3.connect(str(DB),timeout=20); conn.row_factory=sqlite3.Row
try:
    tables=[]
    for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
        n=str(r[0])
        if any(k in n.lower() for k in ('pag','quot','pres','attend','lez','cors')):
            cols=[{'name':x[1],'type':x[2]} for x in conn.execute('PRAGMA table_info('+n+')').fetchall()]
            count=int(conn.execute('SELECT COUNT(*) FROM '+n).fetchone()[0])
            sample=[]
            try: sample=[dict(x) for x in conn.execute('SELECT * FROM '+n+' LIMIT 5').fetchall()]
            except Exception: pass
            tables.append({'table':n,'count':count,'columns':cols,'sample':sample})
finally: conn.close()
print('[r122-audit-routes] '+json.dumps(routes,ensure_ascii=False,default=str),flush=True)
print('[r122-audit-tables] '+json.dumps(tables,ensure_ascii=False,default=str),flush=True)
