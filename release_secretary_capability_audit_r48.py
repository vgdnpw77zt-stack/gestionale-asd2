# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import ast, json, sqlite3, sys, os

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
KEYWORDS=('collabor','lul','lavoro sportivo','lavoratore sportivo','cococo','co.co.co','compens','contratt','busta','cedolin','unilav')

os.chdir(str(APP))
if str(APP) not in sys.path:
    sys.path.insert(0,str(APP))

from asd_app.core import app

route_hits=[]
for rule in sorted(app.url_map.iter_rules(),key=lambda r:str(r.rule)):
    hay=(str(rule.rule)+' '+str(rule.endpoint)).lower()
    if any(k in hay for k in KEYWORDS):
        route_hits.append({
            'route':str(rule.rule),
            'methods':sorted(m for m in (rule.methods or set()) if m not in ('HEAD','OPTIONS')),
            'endpoint':str(rule.endpoint),
        })

function_hits=[]
root=APP/'asd_app'
for p in sorted(root.glob('*.py')):
    try:
        src=p.read_text(encoding='utf-8',errors='replace')
        low=src.lower()
        if not any(k in low for k in KEYWORDS):
            continue
        tree=ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                seg=ast.get_source_segment(src,node) or ''
                hay=(node.name+' '+(ast.get_docstring(node) or '')+' '+seg[:3000]).lower()
                if any(k in hay for k in KEYWORDS):
                    function_hits.append({'module':p.name,'function':node.name,'line':int(getattr(node,'lineno',0) or 0)})
    except Exception:
        continue

table_hits=[]
conn=sqlite3.connect(str(DB),timeout=20)
try:
    tables=[str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
    for t in tables:
        cols=[str(r[1]) for r in conn.execute('PRAGMA table_info('+t+')').fetchall()]
        hay=(t+' '+' '.join(cols)).lower()
        if any(k in hay for k in KEYWORDS):
            table_hits.append({'table':t,'columns':cols,'count':int(conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0])})
finally:
    conn.close()

print('[secretary-capability-r48] '+json.dumps({
    'routes':route_hits[:80],
    'functions':function_hits[:120],
    'tables':table_hits[:80],
},ensure_ascii=False),flush=True)
