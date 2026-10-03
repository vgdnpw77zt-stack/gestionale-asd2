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
