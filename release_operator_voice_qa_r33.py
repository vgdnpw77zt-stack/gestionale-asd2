# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import os, sqlite3, sys

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MARKER=APP/'.BODYMIND_OPERATOR_VOICE_QA_R33'

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
        sess['_csrf_token']='qa-r33'
        sess['bodymind_operator_conversation']='qa-r33'
        sess['bodymind_operator_identity']='Daniele'

    checks={}
    page=client.get('/operatore-bodymind')
    html=page.get_data(as_text=True)
    checks['page_200']=page.status_code==200
    checks['r33']='R33.0' in html
    checks['real_mic_permission']='navigator.mediaDevices.getUserMedia' in html
    checks['speech_recognition']='SpeechRecognition' in html and 'webkitSpeechRecognition' in html
    checks['speech_synthesis']='speechSynthesis' in html and 'SpeechSynthesisUtterance' in html
    checks['animated_logo']='bmoAudioBars' in html and 'bmoTalk' in html and 'speaking' in html and 'listening' in html
    checks['voice_status']='bmoVoiceStatus' in html and 'Tocca il microfono e parlami' in html
    checks['mobile_voice_first']='.bmo-side{display:none!important}' in html and 'bmoMobileFiles' in html
    checks['desktop_side_preserved']='<aside class="bmo-side">' in html
    logo=client.get('/bodymind-media/logo')
    checks['logo_200']=logo.status_code==200 and str(logo.content_type or '').startswith(('image/','application/octet-stream'))
    checks['logo_payload']=len(logo.data)>100

    # Explicitly verify no route collision was introduced.
    exact={}
    for rule in app.url_map.iter_rules():
        methods=tuple(sorted(m for m in rule.methods if m not in ('HEAD','OPTIONS')))
        exact.setdefault((str(rule.rule),methods),[]).append(str(rule.endpoint))
    dup=[{'rule':k[0],'methods':k[1],'endpoints':v} for k,v in exact.items() if len(v)>1]
    checks['no_exact_route_duplicates']=not dup

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
    print('[operator-voice-qa-r33] checks='+repr(checks),flush=True)
    print('[operator-voice-qa-r33] exact_duplicates='+repr(dup[:20]),flush=True)
    print('[operator-voice-qa-r33] counts_before='+repr(before)+' counts_after='+repr(after),flush=True)
    if failed:
        raise RuntimeError('R33 voice QA failed '+repr(failed))
    MARKER.write_text('BodyMind operator voice QA R33 passed\n',encoding='utf-8')
    print('[operator-voice-qa-r33-selftest] PASS real-mic-permission speech-recognition speech-synthesis animated-logo mobile-voice-first desktop-preserved route-unique data-unchanged db-ok',flush=True)
else:
    print('[operator-voice-qa-r33] already applied',flush=True)
