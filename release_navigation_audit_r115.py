# -*- coding: utf-8 -*-
from __future__ import annotations
import inspect, json, re, sqlite3, sys
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
sys.path.insert(0,str(APP))
import app as _full_app
from asd_app.core import app
import asd_app.core as core

TARGETS=(
    'dashboard','tesserati','mobile','pagamenti','documenti','document-hub',
    'documenti-automatici','cuore-operativo','motore-automazioni','risolvi-automatico',
    'dossier','critic'
)

def clean(s):
    return re.sub(r'\s+',' ',str(s or '')).strip()

def relevant_href(h):
    x=(h or '').lower()
    return any(t in x for t in TARGETS)

def source_of(obj):
    try: return inspect.getsource(obj)
    except Exception: return ''

routes=[]
for rule in app.url_map.iter_rules():
    rr=str(rule.rule)
    if any(t in rr.lower() for t in TARGETS):
        ep=str(rule.endpoint)
        fn=app.view_functions.get(ep)
        routes.append({
            'rule':rr,'endpoint':ep,'methods':sorted(m for m in rule.methods if m not in ('HEAD','OPTIONS')),
            'function':getattr(fn,'__name__','') if fn else ''
        })

views={}
for path in ('/dashboard','/mobile','/pagamenti','/document-hub','/documenti-automatici','/cuore-operativo','/motore-automazioni','/risolvi-automatico'):
    matches=[r for r in app.url_map.iter_rules() if str(r.rule)==path and 'GET' in r.methods]
    items=[]
    for r in matches:
        fn=app.view_functions.get(r.endpoint)
        src=source_of(fn)
        hrefs=sorted(set(re.findall(r"""href\s*=\s*['\"]([^'\"]+)""",src,re.I)))
        labels=[]
        for h in hrefs:
            if relevant_href(h): labels.append(h)
        items.append({'endpoint':r.endpoint,'function':getattr(fn,'__name__',''),'relevant_hrefs':labels[:80]})
    views[path]=items

layout_src=source_of(getattr(core,'layout',None))
layout_hrefs=sorted(set(re.findall(r"""href\s*=\s*['\"]([^'\"]+)""",layout_src,re.I)))
layout_relevant=[h for h in layout_hrefs if relevant_href(h)]

# Literal occurrences in the active source tree, grouped only by user-facing route.
source_hits={k:[] for k in ('/dossier','/cuore-operativo','/motore-automazioni','/risolvi-automatico','/document-hub','/documenti-automatici','/pagamenti')}
for p in (APP/'asd_app').glob('*.py'):
    try:s=p.read_text(encoding='utf-8',errors='replace')
    except Exception:continue
    for route in source_hits:
        n=s.count(route)
        if n:
            source_hits[route].append({'file':p.name,'count':n})

conn=sqlite3.connect(str(DB),timeout=30)
try:
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally: conn.close()

report={
 'layout_relevant_hrefs':layout_relevant,
 'active_views':views,
 'route_count':len(routes),
 'routes':routes,
 'source_route_hits':source_hits,
 'integrity':integrity,'fk':fk
}
print('[r115-navigation-audit] '+json.dumps(report,ensure_ascii=False),flush=True)
if integrity.lower()!='ok' or fk:
    raise RuntimeError('R115 navigation audit DB guard failed')
print('[r115-selftest] PASS active-route/navigation read-only audit db-ok',flush=True)
