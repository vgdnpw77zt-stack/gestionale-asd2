# -*- coding: utf-8 -*-
import json, os, sqlite3
from pathlib import Path
APP=Path('/data/top2_app'); DB=Path('/data/tenants/default/asd.db')
def kind(r):
    hay=' '.join(str(r.get(k) or '').lower() for k in ('doc_type','categoria','titolo','original_filename','filename'))
    if ('modulo_unico_tesseramento' in hay or 'modulo unico' in hay or 'modulo iscrizione' in hay or 'domanda iscrizione' in hay or 'domanda di iscrizione' in hay):
        return 'mu'
    if 'richiesta certificato' in hay or 'richiesta_certificato' in hay or 'ecg' in hay or 'elettrocard' in hay or 'referto' in hay:
        return 'other'
    if 'certificato_medico' in hay or ('certificat' in hay and 'medic' in hay):
        return 'medical'
    return 'other'

def exists_path(r):
    vals=[]
    for k in ('filename','file_path','path','stored_path','saved_path','content_path'):
        if k in r and r.get(k): vals.append(str(r.get(k)))
    roots=[Path('/'),APP,Path('/data'),Path('/data/tenants/default'),APP/'user_static',APP/'static']
    tried=[]
    for v in vals:
        if v.startswith('http://') or v.startswith('https://'): continue
        p=Path(v)
        cands=[p] if p.is_absolute() else [root/p for root in roots]
        for c in cands:
            tried.append(str(c))
            try:
                if c.is_file(): return True,str(c),tried
            except Exception: pass
    return False,None,tried

c=sqlite3.connect(str(DB),timeout=30); c.row_factory=sqlite3.Row
try:
    cols=[x[1] for x in c.execute('PRAGMA table_info(documenti)').fetchall()]
    rows=[dict(x) for x in c.execute("""SELECT d.*,t.nome AS atleta_nome,t.cognome AS atleta_cognome
      FROM documenti d LEFT JOIN tesserati t ON t.id=d.tesserato_id
      WHERE coalesce(d.visibile,1)=1 ORDER BY d.id""").fetchall()]
    out={'mu':{'total':0,'exists':0,'missing':0,'missing_rows':[]},'medical':{'total':0,'exists':0,'missing':0,'missing_rows':[]}}
    lud=[]
    for r in rows:
        k=kind(r)
        if k not in out: continue
        ok,path,tried=exists_path(r)
        out[k]['total']+=1; out[k]['exists' if ok else 'missing']+=1
        if not ok:
            out[k]['missing_rows'].append({'id':r.get('id'),'athlete':((r.get('atleta_cognome') or '')+' '+(r.get('atleta_nome') or '')).strip(),'doc_type':r.get('doc_type'),'categoria':r.get('categoria'),'titolo':r.get('titolo'),'filename':r.get('filename'),'status':r.get('status'),'tried':tried[:8]})
        if str(r.get('atleta_cognome') or '').strip().lower()=='angelucci' and str(r.get('atleta_nome') or '').strip().lower()=='ludovica':
            lud.append({'id':r.get('id'),'kind':k,'doc_type':r.get('doc_type'),'categoria':r.get('categoria'),'titolo':r.get('titolo'),'filename':r.get('filename'),'status':r.get('status'),'exists':ok,'resolved':path,'tried':tried[:8]})
    print('[r134-doc-columns] '+json.dumps(cols,ensure_ascii=False),flush=True)
    print('[r134-ludovica] '+json.dumps(lud,ensure_ascii=False,default=str),flush=True)
    print('[r134-summary] '+json.dumps(out,ensure_ascii=False,default=str),flush=True)
    print('[r134-db] integrity='+str(c.execute('PRAGMA integrity_check').fetchone()[0])+' fk='+str(len(c.execute('PRAGMA foreign_key_check').fetchall())),flush=True)
finally:c.close()
