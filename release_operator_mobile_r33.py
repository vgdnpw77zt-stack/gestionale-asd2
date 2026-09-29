# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import compileall, os, sqlite3, sys

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MARKER=APP/'.BODYMIND_OPERATOR_MOBILE_R33'

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

if not MARKER.exists():
    src=APP/'asd_app/routes_operator_bodymind.py'
    if not src.exists():
        raise RuntimeError('R33 operator module missing')
    if not compileall.compile_file(str(src),quiet=1):
        raise RuntimeError('R33 operator syntax compile failed')

    os.chdir(APP); sys.path.insert(0,str(APP))
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
        sess['_csrf_token']='qa-r33'
        sess['bodymind_operator_conversation']='qa-r33'
        sess['bodymind_operator_identity']='Daniele'

    checks={}
    home=client.get('/operatore-bodymind')
    body=home.get_data(as_text=True)
    checks['home_200']=home.status_code==200
    checks['mic_permission']='getUserMedia' in body and 'microphone=(self)' in str(home.headers.get('Permissions-Policy',''))
    checks['speech_recognition']='SpeechRecognition' in body and 'webkitSpeechRecognition' in body
    checks['animated_logo']='bmoAudioBars' in body and 'bmoTalk' in body and 'bmoVoiceStatus' in body
    checks['voice_first_mobile']='.bmo-side{display:none!important}' in body and 'Tocca il microfono e parlami' in body
    checks['mobile_attach']='bmoMobileFiles' in body and 'bmoAttach' in body
    checks['desktop_preserved']='Scrivania' in body and 'bmo-quick' in body

    logo=client.get('/bodymind-media/logo')
    checks['logo_200']=logo.status_code==200 and str(logo.content_type).startswith('image/')

    conn=sqlite3.connect(str(DB),timeout=20)
    try:
        for table in ('bodymind_operator_messages','bodymind_operator_actions'):
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
                conn.execute('DELETE FROM '+table+' WHERE conversation_id=?',('qa-r33',))
        conn.commit()
        after={t:int(conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]) for t in before}
        integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
        fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
    finally:
        conn.close()

    checks['business_counts_unchanged']=before==after
    checks['db_integrity']=integrity.lower()=='ok' and fk==0
    failed=[k for k,v in checks.items() if not v]
    print('[operator-mobile-r33] checks='+repr(checks),flush=True)
    print('[operator-mobile-r33] counts_before='+repr(before)+' counts_after='+repr(after),flush=True)
    if failed:
        raise RuntimeError('R33 mobile operator QA failed '+repr(failed))
    MARKER.write_text('BodyMind mobile operator R33 passed\n',encoding='utf-8')
    print('[operator-mobile-r33-selftest] PASS iPhone-mic-permission animated-logo voice-first-mobile desktop-preserved logo-route data-safe',flush=True)
else:
    print('[operator-mobile-r33] already applied',flush=True)
