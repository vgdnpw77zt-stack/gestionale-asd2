# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import json, sqlite3, sys, os

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MARKER=APP/'.BODYMIND_CLOUD_CREDIT_SMOKE_R50'

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
    print('[cloud-credit-r50-smoke] already attempted '+MARKER.read_text(encoding='utf-8',errors='replace')[:1800],flush=True)
else:
    before=counts()
    outcome={'ok':False,'tools':[],'text':'','model':str(os.environ.get('BODYMIND_AI_MODEL') or ''),'error':''}
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
            session['_csrf_token']='r50-credit-smoke'
            session['bodymind_operator_conversation']='r50-credit-smoke'
            session['bodymind_operator_identity']='Daniele'
            conn=db()
            try:
                op._schema(conn)
                question="Controlla il gestionale reale e dimmi quanti tesserati o iscritti abbiamo. Usa strumenti reali e non modificare nulla."
                trace=[]
                final=None
                discovery={'discover_capabilities','inspect_route','inspect_system_map','inspect_db_schema'}
                for step in range(3):
                    plan=op._cloud_plan_tool(conn,question,trace)
                    if not isinstance(plan,dict):
                        raise RuntimeError('cloud planner returned no plan')
                    tool=str(plan.get('tool') or '')
                    outcome['tools'].append(tool)
                    if tool in ('','none','unknown'):
                        ans=str(plan.get('answer') or '').strip()
                        final={'text':ans,'mode':'cloud_ai'} if ans else None
                        break
                    result=op._execute_full_agent_plan(conn,plan,question)
                    if not isinstance(result,dict):
                        raise RuntimeError('tool execution returned no result')
                    final=result
                    if tool in discovery and step<2:
                        trace.append(op._compact_agent_observation(tool,result))
                        continue
                    break
                text=str((final or {}).get('text') or '')
                outcome['text']=text[:2200]
                real_tools=[x for x in outcome['tools'] if x not in ('','none','unknown')]
                if not real_tools:
                    raise RuntimeError('no real BodyMind tool selected')
                expected=str(before.get('tesserati',0))
                if expected not in text:
                    raise RuntimeError('result missing tesserati count '+expected)
                outcome['ok']=True
            finally:
                conn.close()
    except Exception as exc:
        outcome['error']=repr(exc)[:2200]
    after=counts()
    outcome['counts_before']=before
    outcome['counts_after']=after
    outcome['counts_unchanged']=(before==after)
    if before!=after:
        outcome['ok']=False
        outcome['error']=(outcome.get('error')+' BUSINESS COUNTS CHANGED').strip()
    MARKER.write_text(json.dumps(outcome,ensure_ascii=False),encoding='utf-8')
    print('[cloud-credit-r50-smoke] '+json.dumps(outcome,ensure_ascii=False),flush=True)
