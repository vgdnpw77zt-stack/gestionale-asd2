# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import os, sqlite3, sys

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MARKER=APP/'.BODYMIND_OPERATOR_LOGIC_QA_R34'

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

if not MARKER.exists():
    os.chdir(APP);sys.path.insert(0,str(APP))
    import app as app_module
    app=app_module.app

    conn=sqlite3.connect(str(DB),timeout=20)
    try:
        before={}
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
        sess['_csrf_token']='qa-r34'
        sess['bodymind_operator_conversation']='qa-r34'
        sess['bodymind_operator_identity']='Daniele'

    def chat(msg):
        r=client.post('/operatore-bodymind/chat',json={'message':msg},headers={'X-CSRFToken':'qa-r34'})
        return r.status_code,(r.get_json(silent=True) or {})

    checks={}
    st,d=chat('Quali documenti sono da verificare?')
    checks['documents_not_identity']=st==200 and d.get('mode')!='identity' and 'document' in str(d.get('text') or '').lower()

    st,d=chat('I documenti sono da verificare')
    checks['sono_not_identity']=st==200 and d.get('mode')!='identity'

    st,d=chat('Ci sono tutele minori incomplete?')
    checks['minor_global_intent']=st==200 and d.get('mode')!='fallback' and d.get('mode')!='identity' and 'tutel' in str(d.get('text') or '').lower()

    st,d=chat('Ciao, sono Katia')
    checks['explicit_identity']=st==200 and d.get('mode')=='identity' and 'Katia' in str(d.get('text') or '')

    st,d=chat('Controlla BodyMind')
    checks['global_audit']=st==200 and d.get('mode')=='audit'

    # If Ludovica has a trusted MU after R34 reconciliation, the operator must not report tutela incomplete.
    conn=sqlite3.connect(str(DB),timeout=20);conn.row_factory=sqlite3.Row
    try:
        lud=conn.execute("SELECT * FROM tesserati WHERE lower(nome)='ludovica' AND lower(cognome)='angelucci' LIMIT 1").fetchone()
        trusted=False
        if lud:
            tid=int(lud['id'])
            # Trust via accepted onboarding or dossier status.
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='onboarding_document_requests'").fetchone():
                trusted=bool(conn.execute("""
                    SELECT 1 FROM onboarding_document_requests
                    WHERE tesserato_id=? AND lower(coalesce(document_type,''))='modulo_unico_tesseramento'
                      AND lower(coalesce(status,'')) IN ('accepted','manual_accepted') LIMIT 1
                """,(tid,)).fetchone())
            if not trusted and conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documenti'").fetchone():
                rows=conn.execute("SELECT * FROM documenti WHERE tesserato_id=?",(tid,)).fetchall()
                for r in rows:
                    hay=' '.join(str(r[k] or '').lower() for k in r.keys() if k in ('doc_type','categoria','titolo','original_filename','filename'))
                    status=str(r['status'] or '').lower() if 'status' in r.keys() else ''
                    visible=int((r['visibile'] if 'visibile' in r.keys() else 1) or 0)
                    if visible and any(x in hay for x in ('modulo_unico','modulo unico','mu-2026','modulo iscrizione','domanda iscrizione')) and status in ('verificato','salvato','accepted','manual_accepted','ok'):
                        trusted=True;break
        else:
            tid=0
    finally:
        conn.close()

    if lud and trusted:
        st,d=chat('Controlla la tutela minore di Ludovica Angelucci')
        checks['ludovica_tutela']=st==200 and 'coperta' in str(d.get('text') or '').lower()
    else:
        checks['ludovica_tutela']=True

    # Clear QA traces and prove business data unchanged.
    conn=sqlite3.connect(str(DB),timeout=20)
    try:
        for table in ('bodymind_operator_messages','bodymind_operator_actions'):
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
                conn.execute('DELETE FROM '+table+' WHERE conversation_id=?',('qa-r34',))
        conn.commit()
        after={t:int(conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]) for t in before}
        integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
        fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
    finally:
        conn.close()

    checks['business_counts_unchanged']=before==after
    checks['db_integrity']=integrity.lower()=='ok' and fk==0
    failed=[k for k,v in checks.items() if not v]
    print('[operator-logic-qa-r34] checks='+repr(checks),flush=True)
    print('[operator-logic-qa-r34] counts_before='+repr(before)+' counts_after='+repr(after),flush=True)
    if failed:
        raise RuntimeError('R34 operator logic QA failed '+repr(failed))
    MARKER.write_text('BodyMind operator logic QA R34 passed\n',encoding='utf-8')
    print('[operator-logic-qa-r34-selftest] PASS identity-parser document-intent minor-intent ludovica-if-trusted data-safe db-ok',flush=True)
else:
    print('[operator-logic-qa-r34] already applied',flush=True)
