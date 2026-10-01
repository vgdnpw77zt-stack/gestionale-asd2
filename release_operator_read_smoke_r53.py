# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import json, os, sqlite3, sys

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MARK=APP/'.BODYMIND_OPERATOR_READ_SMOKE_R53C'

def business_counts():
    c=sqlite3.connect(str(DB),timeout=20)
    try:
        out={}
        for t in ('tesserati','documenti','inbound_documents','pagamenti','ricevute'):
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone():
                out[t]=int(c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0])
        return out
    finally:
        c.close()

def usage_totals():
    c=sqlite3.connect(str(DB),timeout=20)
    try:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bodymind_ai_usage'").fetchone():
            return {'rows':0,'input_tokens':0,'output_tokens':0}
        r=c.execute("SELECT COUNT(*),coalesce(sum(input_tokens),0),coalesce(sum(output_tokens),0) FROM bodymind_ai_usage").fetchone()
        return {'rows':int(r[0]),'input_tokens':int(r[1]),'output_tokens':int(r[2])}
    finally:
        c.close()

if MARK.exists():
    print('[operator-read-r53-smoke] already attempted '+MARK.read_text(encoding='utf-8',errors='replace')[:4000],flush=True)
else:
    before=business_counts()
    usage_before=usage_totals()
    outcome={'ok':False,'model':str(os.environ.get('BODYMIND_AI_MODEL') or ''),'tests':[],'counts_before':before,'error':''}
    try:
        os.chdir(str(APP))
        if str(APP) not in sys.path: sys.path.insert(0,str(APP))
        from asd_app.core import app, db
        import asd_app.routes_operator_bodymind as op
        questions=[
            ('tesserati','Quanti tesserati abbiamo?',{'global_status'}),
            ('pending','Quanti documenti sono da verificare?',{'global_status','list_pending_documents','secretary_audit'}),
            ('search_elena','Cercami Elena',{'search_tesserato'}),
            ('dossier_elena','Fammi vedere il dossier di Elena',{'inspect_tesserato','list_documents','search_tesserato'}),
            ('cert_scadenza','Quali certificati medici stanno scadendo?',{'secretary_audit','global_status','discover_capabilities'}),
            ('mancanze_elena','Che cosa manca a Elena?',{'inspect_tesserato','secretary_audit','search_tesserato'}),
            ('navigate_dossier','Portami alla pagina corretta per il dossier di Elena',{'navigate','inspect_tesserato','search_tesserato'}),
        ]
        with app.test_request_context('/operatore-bodymind'):
            from flask import session
            session.update({'logged':True,'username':'admin','display_name':'Daniele','role':'admin','tenant_slug':'default',
                            '_csrf_token':'r53-read-smoke','bodymind_operator_conversation':'r53c-read-smoke',
                            'bodymind_operator_identity':'Daniele'})
            conn=db()
            try:
                op._schema(conn)
                for name,q,allowed in questions:
                    plan=op._cloud_plan_tool(conn,q,[])
                    tool=str((plan or {}).get('tool') or '')
                    result=op._execute_full_agent_plan(conn,plan,q) if plan and tool not in ('','none','unknown') else None
                    mode=str((result or {}).get('mode') or '')
                    text_out=str((result or {}).get('text') or '')
                    passed=tool in allowed
                    if name=='tesserati':
                        passed=passed and str(before.get('tesserati',0)) in text_out
                    if name=='pending':
                        passed=passed and ('document' in text_out.lower())
                    outcome['tests'].append({'name':name,'tool':tool,'mode':mode,'ok':bool(passed)})
                    if not passed:
                        raise RuntimeError(name+' unexpected tool/result: '+tool+' '+mode)
            finally:
                conn.close()
    except Exception as exc:
        outcome['error']=repr(exc)[:1200]
    after=business_counts()
    usage_after=usage_totals()
    c=sqlite3.connect(str(DB),timeout=20)
    try:
        integrity=str(c.execute('PRAGMA integrity_check').fetchone()[0])
        fk=len(c.execute('PRAGMA foreign_key_check').fetchall())
    finally:
        c.close()
    outcome['counts_after']=after
    outcome['counts_unchanged']=(before==after)
    outcome['usage_before']=usage_before
    outcome['usage_after']=usage_after
    outcome['usage_recorded']=usage_after['rows']>usage_before['rows'] and usage_after['input_tokens']>usage_before['input_tokens']
    outcome['db_integrity']=(integrity.lower()=='ok' and fk==0)
    outcome['ok']=not outcome['error'] and all(x['ok'] for x in outcome['tests']) and outcome['counts_unchanged'] and outcome['usage_recorded'] and outcome['db_integrity']
    MARK.write_text(json.dumps(outcome,ensure_ascii=False),encoding='utf-8')
    print('[operator-read-r53-smoke] '+json.dumps(outcome,ensure_ascii=False),flush=True)
