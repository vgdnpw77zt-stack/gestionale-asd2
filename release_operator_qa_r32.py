# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import os, sqlite3, sys

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MARKER=APP/'.BODYMIND_OPERATOR_QA_R32'

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

if not MARKER.exists():
    os.chdir(APP)
    sys.path.insert(0,str(APP))
    import app as app_module

    app=app_module.app
    before={}
    conn=sqlite3.connect(str(DB),timeout=20)
    try:
        for t in ('tesserati','documenti','inbound_documents','pagamenti','ricevute'):
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone():
                before[t]=int(conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0])
    finally:
        conn.close()

    client=app.test_client()
    with client.session_transaction() as sess:
        sess['logged']=True
        sess['username']='admin'
        sess['display_name']='Daniele'
        sess['role']='admin'
        sess['tenant_slug']='default'
        sess['_csrf_token']='qa-r32'
        sess['bodymind_operator_conversation']='qa-r32'
        sess['bodymind_operator_identity']='Daniele'

    checks={}
    home=client.get('/operatore-bodymind')
    body=home.get_data(as_text=True)
    checks['home_200']=home.status_code==200
    checks['voice_ui']='SpeechRecognition' in body and 'speechSynthesis' in body and 'bmoMic' in body
    checks['logo_ui']='/bodymind-media/logo' in body
    checks['upload_ui']='/operatore-bodymind/upload' in body
    checks['identity_ui']='Ciao, Daniele' in body

    r=client.post('/operatore-bodymind/chat',json={'message':'ciao'},headers={'X-CSRFToken':'qa-r32'})
    data=r.get_json(silent=True) or {}
    checks['chat_greeting']=r.status_code==200 and 'Daniele' in str(data.get('text') or '')

    r2=client.post('/operatore-bodymind/chat',json={'message':'Controlla BodyMind'},headers={'X-CSRFToken':'qa-r32'})
    data2=r2.get_json(silent=True) or {}
    checks['chat_audit']=r2.status_code==200 and ('tesserati' in str(data2.get('text') or '').lower() or 'bodymind' in str(data2.get('text') or '').lower())

    # Test real athlete read path without mutating business data.
    conn=sqlite3.connect(str(DB),timeout=20)
    conn.row_factory=sqlite3.Row
    sample=conn.execute("SELECT nome,cognome FROM tesserati ORDER BY id LIMIT 1").fetchone()
    conn.close()
    if sample:
        q=f"Cosa manca a {sample['nome']} {sample['cognome']}?"
        r3=client.post('/operatore-bodymind/chat',json={'message':q},headers={'X-CSRFToken':'qa-r32'})
        d3=r3.get_json(silent=True) or {}
        checks['athlete_read']=r3.status_code==200 and str(sample['nome']).lower() in str(d3.get('text') or '').lower()
    else:
        checks['athlete_read']=True

    # Exact route collisions.
    exact={}
    for rule in app.url_map.iter_rules():
        methods=tuple(sorted(m for m in rule.methods if m not in ('HEAD','OPTIONS')))
        exact.setdefault((str(rule.rule),methods),[]).append(str(rule.endpoint))
    dup=[{'rule':k[0],'methods':k[1],'endpoints':v} for k,v in exact.items() if len(v)>1]
    checks['no_exact_route_duplicates']=not dup

    # Remove QA conversation traces and prove business counts unchanged.
    conn=sqlite3.connect(str(DB),timeout=20)
    try:
        for table in ('bodymind_operator_messages','bodymind_operator_actions'):
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
                conn.execute('DELETE FROM '+table+' WHERE conversation_id=?',('qa-r32',))
        conn.commit()
        after={}
        for t in before:
            after[t]=int(conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0])
        integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
        fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
    finally:
        conn.close()
    checks['business_counts_unchanged']=before==after
    checks['db_integrity']=integrity.lower()=='ok' and fk==0

    failed=[k for k,v in checks.items() if not v]
    print('[operator-qa-r32] checks='+repr(checks),flush=True)
    print('[operator-qa-r32] exact_duplicates='+repr(dup[:20]),flush=True)
    print('[operator-qa-r32] counts_before='+repr(before)+' counts_after='+repr(after),flush=True)
    if failed:
        raise RuntimeError('R32 operator QA failed '+repr(failed))
    MARKER.write_text('BodyMind operator QA R32 passed\n',encoding='utf-8')
    print('[operator-qa-r32-selftest] PASS live-flask-session voice-ui identity chat audit athlete-read route-uniqueness data-unchanged db-integrity',flush=True)
else:
    print('[operator-qa-r32] already applied',flush=True)
