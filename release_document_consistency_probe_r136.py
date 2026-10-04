# -*- coding: utf-8 -*-
from __future__ import annotations
import hashlib, inspect, json, sqlite3, sys
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
sys.path.insert(0,str(APP))

NAMES=[
 ('Ussia','Viola'),('Santese','Martina'),('Tuzzo','Serena'),('Tuzi','Gloria'),
 ('Testa','Lorenza'),('Testa','Chiara'),('Montemagno','Swamy'),('Menegoni','Federica'),
 ('Mellini','Alice'),('Mantoni','Arianna'),('Ilare','Alice'),('Giammei',''),
 ('Frioli','Azzurra'),('Fabiani','Sofia'),('Di Francia','Giulia'),("D'Angelo",'Virginia'),
 ('Caruso','Vincenza'),('Balbinetti','Irene'),('Baffoni','Giorgia'),('Annunziato','Ludovica'),
 ('Angelucci','Ludovica')
]

def norm(s):
    return ' '.join(str(s or '').strip().lower().replace('’',"'").split())

def doc_kind(r):
    hay=' '.join(norm(r.get(k)) for k in ('doc_type','categoria','titolo','original_filename','filename'))
    if any(x in hay for x in ('modulo_unico_tesseramento','modulo unico','modulo iscrizione','domanda iscrizione','domanda di iscrizione','adesione atleta','domanda adesione')):
        return 'mu'
    if any(x in hay for x in ('richiesta certificato','richiesta_certificato','ecg','elettrocard','referto')):
        return 'other'
    if 'certificato_medico' in hay or ('certificat' in hay and 'medic' in hay):
        return 'medical'
    if 'liberatoria' in hay and ('immagin' in hay or 'foto' in hay):
        return 'liberatoria_immagini'
    if 'adesione' in hay:
        return 'adesione'
    return 'other'

def resolve_file(r):
    raw=Path(str(r.get('filename') or '').strip())
    roots=[Path('/data/tenants/default/media'),APP/'user_static',APP/'static',APP,Path('/data/tenants/default')]
    cands=[raw] if raw.is_absolute() else [x/raw for x in roots]
    for c in cands:
        try:
            if c.is_file():
                return str(c.resolve())
        except Exception:
            pass
    return ''

def sha(path):
    if not path: return ''
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for ch in iter(lambda:f.read(1024*1024),b''): h.update(ch)
    return h.hexdigest()

c=sqlite3.connect(str(DB),timeout=30); c.row_factory=sqlite3.Row
try:
    tcols=[x[1] for x in c.execute('PRAGMA table_info(tesserati)').fetchall()]
    dcols=[x[1] for x in c.execute('PRAGMA table_info(documenti)').fetchall()]
    print('[r136-tesserati-columns] '+json.dumps(tcols,ensure_ascii=False),flush=True)
    print('[r136-documenti-columns] '+json.dumps(dcols,ensure_ascii=False),flush=True)

    athletes=[dict(x) for x in c.execute('SELECT * FROM tesserati ORDER BY cognome,nome').fetchall()]
    docs=[dict(x) for x in c.execute("""SELECT d.*,t.nome AS atleta_nome,t.cognome AS atleta_cognome
        FROM documenti d LEFT JOIN tesserati t ON t.id=d.tesserato_id ORDER BY d.tesserato_id,d.id""").fetchall()]
    by_tid={}
    for r in docs: by_tid.setdefault(int(r.get('tesserato_id') or 0),[]).append(r)

    matched=[]
    for surname,name in NAMES:
        ns,nn=norm(surname),norm(name)
        cand=[]
        for a in athletes:
            s,n=norm(a.get('cognome')),norm(a.get('nome'))
            if ns and ns not in s: continue
            if nn and nn not in n: continue
            cand.append(a)
        matched.append({'query':surname+' '+name,'matches':[{'id':a['id'],'nome':a.get('nome'),'cognome':a.get('cognome')} for a in cand]})
    print('[r136-name-matches] '+json.dumps(matched,ensure_ascii=False),flush=True)

    requested_ids=set()
    for item in matched:
        if len(item['matches'])==1: requested_ids.add(int(item['matches'][0]['id']))

    detail=[]
    for a in athletes:
        tid=int(a['id'])
        if tid not in requested_ids: continue
        rows=[]
        for r in by_tid.get(tid,[]):
            fp=resolve_file(r); digest=sha(fp) if fp else ''
            rows.append({
              'id':r.get('id'),'visible':int(r.get('visibile') or 0),'kind':doc_kind(r),
              'doc_type':r.get('doc_type'),'categoria':r.get('categoria'),'titolo':r.get('titolo'),
              'filename':r.get('filename'),'status':r.get('status'),'inbound_id':r.get('inbound_id'),
              'exists':bool(fp),'sha':digest[:16] if digest else ''
            })
        flags={k:a.get(k) for k in tcols if any(x in k.lower() for x in ('iscr','onboard','tutel','consens','genitor','certificat','scadenza','liberator'))}
        detail.append({'id':tid,'name':(str(a.get('cognome') or '')+' '+str(a.get('nome') or '')).strip(),'flags':flags,'documents':rows})
    print('[r136-detail] '+json.dumps(detail,ensure_ascii=False,default=str),flush=True)

    # Global operational truth.
    false_mu=[]; false_tutela=[]; missing_files=[]; dup_mu=[]; dup_med=[]
    for a in athletes:
        tid=int(a['id']); rows=by_tid.get(tid,[])
        visible=[r for r in rows if int(r.get('visibile') if r.get('visibile') is not None else 1)==1]
        phys=[]
        for r in visible:
            fp=resolve_file(r)
            if fp: phys.append((r,fp,sha(fp)))
            else: missing_files.append({'id':r.get('id'),'athlete':(str(a.get('cognome') or '')+' '+str(a.get('nome') or '')).strip(),'kind':doc_kind(r),'filename':r.get('filename')})
        mu=[x for x in phys if doc_kind(x[0])=='mu']
        med=[x for x in phys if doc_kind(x[0])=='medical']
        mu_ok=bool(mu)
        flag_mu=bool(int(a.get('iscrizione_firmata') or 0)) if 'iscrizione_firmata' in a else False
        onboard=bool(int(a.get('documenti_onboarding_ok') or 0)) if 'documenti_onboarding_ok' in a else False
        if (flag_mu or onboard) and not mu_ok:
            false_mu.append({'id':tid,'athlete':(str(a.get('cognome') or '')+' '+str(a.get('nome') or '')).strip(),'iscrizione_firmata':a.get('iscrizione_firmata'),'documenti_onboarding_ok':a.get('documenti_onboarding_ok')})
        # Generic tutela contradiction signal from any explicit tutela/consenso flag = true while no MU.
        tutkeys=[k for k in tcols if any(x in k.lower() for x in ('tutela','consenso'))]
        tvals={k:a.get(k) for k in tutkeys}
        truthy=False
        for v in tvals.values():
            try:
                if int(v or 0): truthy=True
            except Exception:
                if str(v or '').strip().lower() in ('si','sì','true','ok','completo','1'): truthy=True
        if truthy and not mu_ok:
            false_tutela.append({'id':tid,'athlete':(str(a.get('cognome') or '')+' '+str(a.get('nome') or '')).strip(),'flags':tvals})

        for family,arr,out in [('mu',mu,dup_mu),('medical',med,dup_med)]:
            groups={}
            for r,fp,digest in arr: groups.setdefault(digest,[]).append(int(r['id']))
            for digest,ids in groups.items():
                if digest and len(ids)>1:
                    out.append({'athlete':(str(a.get('cognome') or '')+' '+str(a.get('nome') or '')).strip(),'tid':tid,'ids':ids,'sha':digest[:16]})
    print('[r136-global] '+json.dumps({'false_mu':false_mu,'false_tutela':false_tutela,'missing_files':missing_files,'duplicate_mu_exact':dup_mu,'duplicate_medical_exact':dup_med},ensure_ascii=False,default=str),flush=True)

    print('[r136-db] integrity='+str(c.execute('PRAGMA integrity_check').fetchone()[0])+' fk='+str(len(c.execute('PRAGMA foreign_key_check').fetchall())),flush=True)
finally:
    c.close()

# Inspect available document-delete routes/source.
try:
    import app as _full
    from asd_app.core import app
    route_info=[]
    for rule in app.url_map.iter_rules():
        rr=str(rule.rule); ep=str(rule.endpoint)
        if 'document' in rr.lower() and ('delete' in rr.lower() or 'elimina' in rr.lower() or 'document' in ep.lower()):
            if 'POST' in (rule.methods or set()):
                fn=app.view_functions.get(ep); src=''
                try: src=inspect.getsource(fn)[:8000]
                except Exception: pass
                route_info.append({'rule':rr,'endpoint':ep,'methods':sorted(rule.methods or []),'source':src})
    print('[r136-doc-delete-routes] '+json.dumps(route_info,ensure_ascii=False),flush=True)
except Exception as exc:
    print('[r136-doc-delete-routes-error] '+repr(exc),flush=True)
