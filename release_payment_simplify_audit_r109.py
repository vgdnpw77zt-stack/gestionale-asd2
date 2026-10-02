# -*- coding: utf-8 -*-
from __future__ import annotations
import json, re, sqlite3
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')

def table(conn,n):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(n,)).fetchone())

def cols(conn,n):
    return [dict(zip(['cid','name','type','notnull','default','pk'],r)) for r in conn.execute("PRAGMA table_info("+n+")").fetchall()] if table(conn,n) else []

def rows(conn,sql,args=()):
    return [dict(r) for r in conn.execute(sql,args).fetchall()]

def snippet(path, needles, radius=1800):
    p=APP/path
    if not p.exists(): return {'path':str(p),'exists':False}
    s=p.read_text(encoding='utf-8',errors='replace')
    out=[]
    for needle in needles:
        pos=s.find(needle)
        if pos>=0:
            out.append({'needle':needle,'text':s[max(0,pos-radius):min(len(s),pos+radius)]})
    return {'path':str(p),'exists':True,'matches':out}

conn=sqlite3.connect(str(DB),timeout=30); conn.row_factory=sqlite3.Row
try:
    report={'tables':{},'payment_mismatch':{},'integrity':'','fk':0}
    names=['pagamenti','quote_mensili','payment_requests','payment_notifications','smart_alerts',
           'operational_task_state','onboarding_practices','document_hub','tesserati','ricevute']
    for n in names:
        report['tables'][n]={
            'exists':table(conn,n),
            'count':int(conn.execute("SELECT COUNT(*) FROM "+n).fetchone()[0]) if table(conn,n) else 0,
            'columns':cols(conn,n)
        }

    if table(conn,'quote_mensili'):
        qc={x['name'] for x in report['tables']['quote_mensili']['columns']}
        order=' ORDER BY id DESC LIMIT 80' if 'id' in qc else ' LIMIT 80'
        report['quote_samples']=rows(conn,'SELECT * FROM quote_mensili'+order)

    if table(conn,'pagamenti'):
        report['payment_samples']=rows(conn,'SELECT * FROM pagamenti ORDER BY id DESC LIMIT 50')

    # Flexible mismatch analysis: identify rows in quote_mensili that look paid and lack a matching canonical payment.
    mism=[]
    if table(conn,'quote_mensili') and table(conn,'pagamenti'):
        qc={x['name'] for x in report['tables']['quote_mensili']['columns']}
        pc={x['name'] for x in report['tables']['pagamenti']['columns']}
        qrows=conn.execute('SELECT * FROM quote_mensili').fetchall()
        for q in qrows:
            qd=dict(q)
            tid=int(qd.get('tesserato_id') or qd.get('athlete_id') or 0)
            mese=int(qd.get('mese') or 0); anno=int(qd.get('anno') or 0)
            state=' '.join(str(qd.get(k) or '').lower() for k in ('stato','status','pagato','paid','esito'))
            paid=(
                str(qd.get('pagato') or '').strip().lower() in ('1','true','si','sì','yes')
                or str(qd.get('paid') or '').strip().lower() in ('1','true','yes')
                or any(x in state for x in ('pagat','saldat','paid','incassat'))
            )
            if not paid or tid<=0: continue
            clauses=['tesserato_id=?']; args=[tid]
            if mese and 'mese' in pc: clauses.append('mese=?'); args.append(mese)
            if anno and 'anno' in pc: clauses.append('anno=?'); args.append(anno)
            found=conn.execute('SELECT id FROM pagamenti WHERE '+' AND '.join(clauses)+' LIMIT 1',tuple(args)).fetchone()
            if not found:
                who=conn.execute('SELECT nome,cognome FROM tesserati WHERE id=?',(tid,)).fetchone()
                mism.append({'quote':qd,'tesserato':((' '.join([who['nome'] or '',who['cognome'] or ''])).strip() if who else ''),'matched_payment':False})
    report['payment_mismatch']={'count':len(mism),'rows':mism[:80]}

    # Duplicate open task shapes by athlete/category/message to expose redundant surfaces.
    task_dups=[]
    if table(conn,'smart_alerts'):
        sc={x['name'] for x in report['tables']['smart_alerts']['columns']}
        useful=[x for x in ('tesserato_id','categoria','category','tipo','type','message','messaggio','stato','status') if x in sc]
        if useful:
            report['smart_alert_samples']=rows(conn,'SELECT * FROM smart_alerts ORDER BY id DESC LIMIT 80')
    if table(conn,'operational_task_state'):
        report['operational_task_samples']=rows(conn,'SELECT * FROM operational_task_state ORDER BY rowid DESC LIMIT 80')

    report['integrity']=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    report['fk']=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:
    conn.close()

sources=[
 snippet('asd_app/routes_tesserati.py',['def tesserato_scheda','def tesserati(', 'monthly_status(', 'quote_mensili','INSERT INTO pagamenti','UPDATE pagamenti']),
 snippet('asd_app/quote_engine.py',['def monthly_status','quote_mensili','pagamenti']),
 snippet('asd_app/core.py',['def get_operational_tasks','smart_alerts','quote_mensili','pagamenti','dossier']),
 snippet('asd_app/routes_bodymind_fix23.py',['def fix23_mobile_athlete_documents','dossier','pagamenti']),
 snippet('asd_app/routes_bodymind_fix24.py',['def fix24_mobile_atlete','pagamenti','monthly_status']),
 snippet('asd_app/routes_pagamenti.py',['def ','quote_mensili','INSERT INTO pagamenti']),
]
report['sources']=sources
print('[r109-payment-simplify-audit] '+json.dumps(report,ensure_ascii=False,default=str),flush=True)
if report['integrity'].lower()!='ok' or report['fk']!=0:
    raise RuntimeError('R109 read-only audit DB failed')
print('[r109-selftest] PASS read-only payment/task/dossier architecture audit db-ok',flush=True)
