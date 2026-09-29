# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import os, sqlite3, sys

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MARKER=APP/'.BODYMIND_OPERATOR_LOGIC_QA_R37'

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')
if not APP.joinpath('.BODYMIND_MU_TUTELA_R37').exists():
    raise SystemExit('R37 tutela marker missing')

if not MARKER.exists():
    os.chdir(APP);sys.path.insert(0,str(APP))
    import app as app_module
    import asd_app.routes_operator_bodymind as op
    app=app_module.app

    conn=sqlite3.connect(str(DB),timeout=20)
    conn.row_factory=sqlite3.Row
    try:
        before={}
        for t in ('tesserati','documenti','inbound_documents','pagamenti','ricevute'):
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone():
                before[t]=int(conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0])
        lud=conn.execute("SELECT * FROM tesserati WHERE lower(nome)='ludovica' AND lower(cognome)='angelucci' ORDER BY id LIMIT 1").fetchone()
        lud_minor=dict(op._minor_state(conn,lud)) if lud else {}
        global_state=op._global_check(conn)
    finally:
        conn.close()

    client=app.test_client()
    with client.session_transaction() as sess:
        sess['logged']=True
        sess['username']='admin'
        sess['display_name']='Daniele'
        sess['role']='admin'
        sess['tenant_slug']='default'
        sess['_csrf_token']='qa-r37'
        sess['bodymind_operator_conversation']='qa-r37'
        sess['bodymind_operator_identity']='Daniele'

    def chat(msg):
        r=client.post('/operatore-bodymind/chat',json={'message':msg},headers={'X-CSRFToken':'qa-r37'})
        return r.status_code,(r.get_json(silent=True) or {})

    checks={}
    st,d=chat('Quali documenti sono da verificare?')
    checks['documents_not_identity']=st==200 and d.get('mode')!='identity' and 'document' in str(d.get('text') or '').lower()

    st,d=chat('I documenti sono da verificare')
    checks['sono_not_identity']=st==200 and d.get('mode')!='identity'

    st,d=chat('Ci sono tutele minori incomplete?')
    checks['minor_global_intent']=st==200 and d.get('mode') not in ('fallback','identity') and 'tutel' in str(d.get('text') or '').lower()

    st,d=chat('Ciao, sono Katia')
    checks['explicit_identity']=st==200 and d.get('mode')=='identity' and 'Katia' in str(d.get('text') or '')

    st,d=chat('Controlla BodyMind')
    checks['global_audit']=st==200 and d.get('mode')=='audit'

    # Trusted MU is authoritative for the included parental-tutela declarations.
    if lud:
        guardian=str(lud['genitore'] or '').strip() if 'genitore' in lud.keys() else ''
        trusted=bool(lud_minor.get('trusted_mu'))
        if guardian and trusted:
            checks['ludovica_engine_state']=bool(lud_minor.get('consent')) and bool(lud_minor.get('authorizations'))
            checks['ludovica_not_global_issue']='Ludovica Angelucci' not in set(global_state.get('minor_issues') or [])
            st,d=chat('Controlla la tutela minore di Ludovica Angelucci')
            txt=str(d.get('text') or '').lower()
            negative=('non è completa','non e completa','incompleta','manca o va verificato','richiede ancora un controllo')
            checks['ludovica_chat']=st==200 and not any(x in txt for x in negative) and ('coperta' in txt or 'verificat' in txt or 'completa' in txt)
            print('[operator-logic-qa-r37] ludovica_response='+repr({'status':st,'mode':d.get('mode'),'text':d.get('text'),'minor':lud_minor}),flush=True)
        else:
            checks['ludovica_engine_state']=True
            checks['ludovica_not_global_issue']=True
            checks['ludovica_chat']=True
    else:
        checks['ludovica_engine_state']=True
        checks['ludovica_not_global_issue']=True
        checks['ludovica_chat']=True

    conn=sqlite3.connect(str(DB),timeout=20)
    try:
        for table in ('bodymind_operator_messages','bodymind_operator_actions'):
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
                conn.execute('DELETE FROM '+table+' WHERE conversation_id=?',('qa-r37',))
        conn.commit()
        after={t:int(conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]) for t in before}
        integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
        fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
    finally:
        conn.close()

    checks['business_counts_unchanged']=before==after
    checks['db_integrity']=integrity.lower()=='ok' and fk==0
    failed=[k for k,v in checks.items() if not v]
    print('[operator-logic-qa-r37] checks='+repr(checks),flush=True)
    print('[operator-logic-qa-r37] counts_before='+repr(before)+' counts_after='+repr(after),flush=True)
    if failed:
        raise RuntimeError('R37 operator logic QA failed '+repr(failed))
    MARKER.write_text('BodyMind operator logic QA R37 passed\n',encoding='utf-8')
    print('[operator-logic-qa-r37-selftest] PASS identity-parser document-intent minor-intent trusted-MU-tutela data-safe db-ok',flush=True)
else:
    print('[operator-logic-qa-r37] already applied',flush=True)
