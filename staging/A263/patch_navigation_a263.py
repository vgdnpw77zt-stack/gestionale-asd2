"""A263 UI navigation refinement, applied only to a reviewed offline A261/A262 clone.

Do not delete automation/task/timeline records and do not change route handlers.
"""
from pathlib import Path
import hashlib
import json


def patch(folder):
    folder=Path(folder)
    path=folder/'core.py'
    text=path.read_text(encoding='utf-8')
    if 'A263_NAV_SIMPLIFIED' in text:
        return {'changed':False,'sha256':hashlib.sha256(text.encode()).hexdigest()}
    if 'A259: timeline hidden from quickdock.' not in text:
        raise RuntimeError('STOP: input non riconosciuto come A259/A261')
    before=hashlib.sha256(text.encode()).hexdigest()
    line=next((x for x in text.splitlines() if "nav_link('/cuore-operativo'" in x),None)
    if not line or text.count(line)!=1 or "tier='money'" not in line:
        raise RuntimeError('STOP: riferimento Cuore ambiguo')
    start=line.index("nav_link('/cuore-operativo'")
    close="title='Cabina unica: alert, documenti, pagamenti, invii, verifiche e timeline.')"
    stop=line.find(close,start)
    if stop<0:raise RuntimeError('STOP: firma menu Cuore cambiata')
    line2=line[:start]+"''"+line[stop+len(close):]
    text=text.replace(line,line2,1)
    old='''   items = [
      ("/cuore-operativo", "Cuore", "Cabina di controllo: stati, errori, da verificare, timeline"),
      ("/risolvi-automatico", "Risolvi", "Esegue le automazioni abilitate dal Motore"),
      ("/motore-automazioni", "Motore", "Decide regole, canali e livello di automatismo"),
      ("/comunicazioni-automatiche", "Invii", "Coda e storico comunicazioni automatiche"),
   ]'''
    new='''   # A263_NAV_SIMPLIFIED: uno sportello di automazioni, backend storico preservato.
   items = [
      ("/", "Dashboard", "Da fare, in scadenza e tutto in regola"),
      ("/motore-automazioni", "Automazioni", "Scadenze, canali, regole e solleciti"),
   ]'''
    if text.count(old)!=1:raise RuntimeError('STOP: quickdock precedente non corrisponde')
    text=text.replace(old,new,1)
    compile(text,str(path),'exec')
    path.write_text(text,encoding='utf-8')
    return {'changed':True,'before_sha256':before,'after_sha256':hashlib.sha256(text.encode()).hexdigest(), 'routes_removed':0, 'records_removed':0}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',required=True)
    x=p.parse_args();print(json.dumps(patch(x.root),indent=2))
