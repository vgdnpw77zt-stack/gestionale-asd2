# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import json, sqlite3

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MARKER=APP/'.BODYMIND_CLOUD_AGENT_SMOKE_R45'

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
    print('[cloud-agent-r45-smoke] already attempted '+MARKER.read_text(encoding='utf-8',errors='replace')[:800],flush=True)
else:
    before=counts()
    outcome={'ok':False,'tool':'','result_mode':'','result_text':'','error':''}
    try:
        from asd_app.core import app, db
        import asd_app.routes_operator_bodymind as op
        with app.test_request_context('/operatore-bodymind'):
            from flask import session
            session['logged']=True
            session['username']='admin'
            session['display_name']='Daniele'
            session['role']='admin'
            session['tenant_slug']='default'
            session['_csrf_token']='r45-smoke'
            session['bodymind_operator_conversation']='r45-cloud-smoke'
            session['bodymind_operator_identity']='Daniele'
            conn=db()
            try:
                op._schema(conn)
                question="Usa uno strumento reale del gestionale, non rispondere solo dalla mappa: quanti iscritti o tesserati abbiamo e quanti documenti sono da verificare?"
                trace=[]
                final=None
                chosen=[]
                for step in range(3):
                    plan=op._cloud_plan_tool(conn,question,trace)
                    if not isinstance(plan,dict):
                        raise RuntimeError('cloud planner returned no plan')
                    tool=str(plan.get('tool') or '')
                    chosen.append(tool)
                    if tool in ('','none','unknown'):
                        ans=str(plan.get('answer') or '').strip()
                        final={'text':ans,'mode':'cloud_ai'} if ans else None
                        break
                    res=op._execute_full_agent_plan(conn,plan,question)
                    if not isinstance(res,dict):
                        raise RuntimeError('tool execution returned no result')
                    final=res
                    if tool in {'discover_capabilities','inspect_route','inspect_system_map','inspect_db_schema'} and step<2:
                        trace.append(op._compact_agent_observation(tool,res))
                        continue
                    break
                outcome['tool']=' > '.join(chosen)
                outcome['result_mode']=str((final or {}).get('mode') or '')
                outcome['result_text']=str((final or {}).get('text') or '')[:1800]
                if not chosen or all(x in ('','none','unknown') for x in chosen):
                    raise RuntimeError('cloud did not select a real BodyMind tool')
                expected=str(before.get('tesserati',0))
                if expected and expected not in outcome['result_text']:
                    raise RuntimeError('tool result does not reflect current tesserati count '+expected)
                outcome['ok']=True
            finally:
                conn.close()
    except Exception as exc:
        outcome['error']=repr(exc)[:1200]
    after=counts()
    outcome['counts_before']=before
    outcome['counts_after']=after
    outcome['counts_unchanged']=(before==after)
    if before!=after:
        outcome['ok']=False
        outcome['error']=(outcome.get('error')+' BUSINESS COUNTS CHANGED').strip()
    MARKER.write_text(json.dumps(outcome,ensure_ascii=False),encoding='utf-8')
    print('[cloud-agent-r45-smoke] '+json.dumps(outcome,ensure_ascii=False),flush=True)
