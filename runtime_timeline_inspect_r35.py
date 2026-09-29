# -*- coding: utf-8 -*-
from pathlib import Path
import re

APP=Path('/data/top2_app')
MARKER=APP/'.BODYMIND_TIMELINE_INSPECT_R35'

def emit(tag,val):
    print('[timeline-inspect-r35-'+tag+'] '+repr(val),flush=True)

if not MARKER.exists():
    terms=['timeline','reset','seleziona tutto','select all','elimina selezion','bulk delete','bulk-delete']
    hits=[]
    for p in list(APP.rglob('*.py'))+list(APP.rglob('*.html'))+list(APP.rglob('*.js'))+list(APP.rglob('*.css')):
        try:
            txt=p.read_text(encoding='utf-8',errors='ignore')
        except Exception:
            continue
        low=txt.lower()
        if not any(t in low for t in terms):
            continue
        lines=txt.splitlines()
        for i,line in enumerate(lines):
            ll=line.lower()
            if any(t in ll for t in terms):
                a=max(0,i-5);b=min(len(lines),i+8)
                hits.append({
                    'file':str(p.relative_to(APP)),
                    'line':i+1,
                    'snippet':'\n'.join(f'{j+1}:{lines[j]}' for j in range(a,b))
                })
                if len(hits)>=120: break
        if len(hits)>=120: break
    emit('hits',hits)
    MARKER.write_text('done\n',encoding='utf-8')
    emit('done','PASS')
else:
    emit('skip','already done')
