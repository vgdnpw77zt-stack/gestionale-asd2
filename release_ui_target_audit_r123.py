# -*- coding: utf-8 -*-
from pathlib import Path
import inspect, sys
APP=Path('/data/top2_app')
phrases=['Tesseramento / iscrizione','Seleziona periodo e tesserato','OPERATIVITÀ IMMEDIATA','Tesserati senza quota iscrizione/tesseramento','Giornata operativa']
for p in APP.rglob('*.py'):
    try:s=p.read_text(encoding='utf-8',errors='replace')
    except Exception:continue
    hits=[x for x in phrases if x.lower() in s.lower()]
    if hits:
        print('[r123-file] '+str(p)+' hits='+repr(hits),flush=True)
        low=s.lower()
        for h in hits:
            i=low.find(h.lower())
            print('[r123-snippet] '+str(p)+' :: '+s[max(0,i-5000):i+12000],flush=True)
sys.path.insert(0,str(APP))
import app as _full
from asd_app.core import app
for ep in ('pagamenti','presenze','presenze_rapide'):
    fn=app.view_functions.get(ep)
    if fn:
        try: print('[r123-view] '+ep+' file='+inspect.getsourcefile(fn)+'\n'+inspect.getsource(fn),flush=True)
        except Exception as e: print('[r123-view-error] '+ep+' '+repr(e),flush=True)
