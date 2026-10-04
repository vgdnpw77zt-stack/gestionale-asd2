# -*- coding: utf-8 -*-
from __future__ import annotations
import inspect, json, sqlite3, sys
from pathlib import Path
APP=Path('/data/top2_app'); DB=Path('/data/tenants/default/asd.db')
sys.path.insert(0,str(APP))
import app as _full_app
from asd_app.core import app

def fn_detail(endpoint):
    fn=app.view_functions.get(endpoint); out={'endpoint':endpoint}
    if not fn:return out
    out['name']=getattr(fn,'__name__','')
    try: out['file']=inspect.getsourcefile(fn)
    except Exception: out['file']=''
    try: out['source']=inspect.getsource(fn)[:24000]
    except Exception: out['source']=''
    closure=[]
    for cell in (getattr(fn,'__closure__',None) or []):
        try: obj=cell.cell_contents
        except Exception: continue
        if callable(obj):
            try:
                src=inspect.getsource(obj)
                closure.append({'name':getattr(obj,'__name__',''),'file':inspect.getsourcefile(obj),'source':src[:30000]})
            except Exception: pass
    out['closure']=closure
    return out

print('[r122-detail-pagamenti] '+json.dumps(fn_detail('pagamenti'),ensure_ascii=False,default=str),flush=True)
print('[r122-detail-presenze] '+json.dumps(fn_detail('presenze'),ensure_ascii=False,default=str),flush=True)
print('[r122-detail-corsi] '+json.dumps(fn_detail('corsi'),ensure_ascii=False,default=str),flush=True)
conn=sqlite3.connect(str(DB),timeout=20); conn.row_factory=sqlite3.Row
try:
    vals=[{'corso':str(r['corso'] or ''),'n':int(r['n'])} for r in conn.execute("SELECT corso,COUNT(*) n FROM tesserati GROUP BY corso ORDER BY LOWER(TRIM(COALESCE(corso,'')))").fetchall()]
    courses=[dict(r) for r in conn.execute("SELECT * FROM corsi ORDER BY id").fetchall()]
    print('[r122-course-values] '+json.dumps({'tesserati':vals,'corsi':courses},ensure_ascii=False,default=str),flush=True)
finally: conn.close()

# R127 focused read-only audit: active payment route source + rendered history structure.
import inspect as _r127_inspect
for _rule in app.url_map.iter_rules():
    if str(_rule.rule)=='/pagamenti' and 'GET' in (_rule.methods or set()):
        _fn=app.view_functions.get(str(_rule.endpoint))
        try:
            print('[r127-payment-fn] '+_r127_inspect.getsource(_fn),flush=True)
        except Exception as _exc:
            print('[r127-payment-fn] source-unavailable '+repr(_exc),flush=True)
        break
_rr=client.get('/pagamenti',follow_redirects=False)
_body=_rr.get_data(as_text=True)
for _needle in ('NOME / STATO','AZIONI','STORICO INCASSI'):
    _i=_body.upper().find(_needle)
    if _i>=0:
        print('[r127-render-'+_needle.replace(' ','_').replace('/','_')+'] '+_body[max(0,_i-2500):_i+9000],flush=True)

# R128 focused source scan for the exact live payment history/nav markup.
for _p in (APP/'asd_app').rglob('*.py'):
    try:
        _src=_p.read_text(encoding='utf-8',errors='replace')
    except Exception:
        continue
    _hits=[x for x in ('I profili con alert tutela','NOME / STATO','STORICO INCASSI','Elenco pagamenti','Apri promemoria') if x in _src]
    if _hits:
        for _needle in _hits:
            _i=_src.find(_needle)
            print('[r128-runtime-source-hit] file='+str(_p)+' needle='+_needle+'\n'+_src[max(0,_i-5000):_i+14000],flush=True)
# Find mobile nav constant/source containing both Presenze and Pagamenti.
for _p in (APP/'asd_app').rglob('*.py'):
    try:
        _src=_p.read_text(encoding='utf-8',errors='replace')
    except Exception:
        continue
    if 'Presenze' in _src and 'Pagamenti' in _src and ('ATHLETE_NAV' in _src or 'bottom' in _src.lower() or '/presenze' in _src):
        _i=min([x for x in (_src.find('Presenze'),_src.find('Pagamenti')) if x>=0])
        print('[r128-nav-source-hit] file='+str(_p)+'\n'+_src[max(0,_i-5000):_i+12000],flush=True)
