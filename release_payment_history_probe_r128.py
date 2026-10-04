# -*- coding: utf-8 -*-
from pathlib import Path
APP=Path('/data/top2_app')
needles=('I profili con alert tutela','NOME / STATO','STORICO INCASSI','Elenco pagamenti','Apri promemoria')
for p in (APP/'asd_app').rglob('*.py'):
    try: s=p.read_text(encoding='utf-8',errors='replace')
    except Exception: continue
    for n in needles:
        if n in s:
            i=s.find(n)
            print('[r128-probe] file='+str(p)+' needle='+n+'\n'+s[max(0,i-4500):i+12000],flush=True)
            break
for p in (APP/'asd_app').rglob('*.py'):
    try: s=p.read_text(encoding='utf-8',errors='replace')
    except Exception: continue
    if 'Presenze' in s and 'Pagamenti' in s and '/presenze' in s and '/pagamenti' in s:
        i=min(x for x in (s.find('Presenze'),s.find('Pagamenti')) if x>=0)
        print('[r128-nav-probe] file='+str(p)+'\n'+s[max(0,i-4000):i+10000],flush=True)
