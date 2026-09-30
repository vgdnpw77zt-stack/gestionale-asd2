# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import json, sqlite3, sys, os

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MARKER=APP/'.BODYMIND_CLOUD_CREDIT_SMOKE_R47'

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

def counts():
    conn=sqlite3.connect(str(DB),timeout=20)
    try:
        out={}
        for t in ('tesserati','documenti','inbound_documents','pagamenti','ricevute'):
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone():
                out[t]=int(conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0])
        return out
    finally:
        conn.close()

if MARKER.exists():
    print('[cloud-credit-r47-smoke] already attempted '+MARKER.read_text(encoding='utf-8',errors='replace')[:1400],flush=True)
else:
    before=counts()
    outcome={'ok':False,'tool':'','text':'','model':str(os.environ.get('BODYMIND_AI_MODEL') or ''),'error':''}
    try:
        os.chdir(str(APP))
        if str(APP) not in sys.path:
            sys.path.insert(0,str(APP))
        from asd_app.core import app, db
        import asd_app.routes_operator_bodymind as op
        with app.test_request_context('/operatore-bodymind'):
            from flask import session
            session['logged']=True
            session['username']='admin'
            session['display_name']='Daniele'
            session['role']='admin'
            session['tenant_slug']='default'
            session['_csrf_token']='r47-credit-smoke'
            session['bodymind_operator_conversation']='r47-credit-smoke'
            session['bodymind_operator_identity']='Daniele'
            conn=db()
            try:
                op._schema(conn)
                question="Usa lo strumento reale global_status del gestionale e dimmi quanti tesserati abbiamo. Non modificare nulla."
                plan=op._cloud_plan_tool(conn,question,[])
                if not isinstance(plan,dict):
                    raise RuntimeError('cloud planner returned no plan')
                tool=str(plan.get('tool') or '')
                outcome['tool']=tool
                if tool!='global_status':
                    raise RuntimeError('unexpected tool '+tool)
                result=op._execute_full_agent_plan(conn,plan,question)
                if not isinstance(result,dict):
                    raise RuntimeError('tool execution returned no result')
                text=str(result.get('text') or '')
                outcome['text']=text[:1800]
                expected=str(before.get('tesserati',0))
                if expected not in text:
                    raise RuntimeError('result missing tesserati count '+expected)
                outcome['ok']=True
            finally:
                conn.close()
    except Exception as exc:
        outcome['error']=repr(exc)[:1800]
    after=counts()
    outcome['counts_before']=before
    outcome['counts_after']=after
    outcome['counts_unchanged']=(before==after)
    if before!=after:
        outcome['ok']=False
        outcome['error']=(outcome.get('error')+' BUSINESS COUNTS CHANGED').strip()
    MARKER.write_text(json.dumps(outcome,ensure_ascii=False),encoding='utf-8')
    print('[cloud-credit-r47-smoke] '+json.dumps(outcome,ensure_ascii=False),flush=True)
