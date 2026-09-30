# -*- coding: utf-8 -*-
from __future__ import annotations
import compileall, os, sqlite3, sys
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

operator=APP/'asd_app/routes_operator_bodymind.py'
bridge=APP/'asd_app/routes_operator_bridge.py'
if not operator.exists() or not bridge.exists():
    raise RuntimeError('R38 operator/bridge runtime missing')
if not compileall.compile_file(str(operator),quiet=1):
    raise RuntimeError('R38 operator compile failed')
if not compileall.compile_file(str(bridge),quiet=1):
    raise RuntimeError('R38 bridge compile failed')

os.chdir(APP); sys.path.insert(0,str(APP))
import app as app_module
app=app_module.app

before={}
conn=sqlite3.connect(str(DB),timeout=20)
try:
    for table in ('tesserati','documenti','inbound_documents','pagamenti','ricevute'):
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
            before[table]=int(conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0])
finally:
    conn.close()

client=app.test_client()
with client.session_transaction() as sess:
    sess['logged']=True; sess['username']='admin'; sess['display_name']='Daniele'; sess['role']='admin'
    sess['tenant_slug']='default'; sess['_csrf_token']='qa-r38'
    sess['bodymind_operator_conversation']='qa-r38'; sess['bodymind_operator_identity']='Daniele'

home=client.get('/operatore-bodymind')
body=home.get_data(as_text=True)
installer=client.get('/bodymind-ai-bridge/install.sh')
install_text=installer.get_data(as_text=True)
bridge_text=bridge.read_text(encoding='utf-8',errors='replace')
checks={
    'home_200':home.status_code==200,
    'operator_r38':'OPERATORE IA · R38.0' in body,
    'mobile_compact':'BODYMIND_R38_MOBILE' in body and '.bmo-status .bmo-pill{display:none;}' in body,
    'mobile_layout_fix':'BODYMIND_R39_MOBILE_LAYOUT_FIX' in body and '#bmoMobileFiles[hidden]' in body,
    'operator_entry_no_overlap':'bottom:calc(104px + env(safe-area-inset-bottom))' in body or 'bmo-mobile-entry' not in body,
    'ios_tts_unlock':'BODYMIND_R39_IOS_TTS_UNLOCK' in body and "speechSynthesis.resume()" in body,
    'mobile_imac_only':'IA iMac:' in body and 'LanguageModel' not in body and 'window.ai' not in body,
    'installer_200':installer.status_code==200,
    'high_sierra_python_fallback':'command -v python3' in install_text and 'command -v python ' in install_text,
    'python27_bridge_compat':'from urllib2 import Request, urlopen' in install_text,
    'local_llama_health':'127.0.0.1:8088/health' in install_text,
    'heartbeat_verification':'/bodymind-ai-bridge/heartbeat' in install_text,
    'bridge_csrf_safe_get_pairing':'BODYMIND_R39_BRIDGE_CSRF_SAFE_GET_PAIRING' in install_text,
    'bridge_diag_checkpoints':'BODYMIND_R39_BRIDGE_DIAGNOSTIC_CHECKPOINTS' in install_text,
    'explicit_installer_file':'BODYMIND_R39_EXPLICIT_INSTALL_FILE' in install_text and '/tmp/bodymind-ai-r39.sh' in bridge_text and '/bin/bash /tmp/bodymind-ai-r39.sh' in bridge_text and '| bash' not in bridge_text,
}

conn=sqlite3.connect(str(DB),timeout=20)
try:
    after={t:int(conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]) for t in before}
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
    for table in ('bodymind_operator_messages','bodymind_operator_actions'):
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
            conn.execute('DELETE FROM '+table+' WHERE conversation_id=?',('qa-r38',))
    conn.commit()
finally:
    conn.close()

checks['business_counts_unchanged']=before==after
checks['db_integrity']=integrity.lower()=='ok' and fk==0
# Machine API uses safe GET routes and must reach its own auth logic without browser CSRF.
heartbeat_probe=client.get('/bodymind-ai-bridge/heartbeat',headers={'Authorization':'Bearer invalid-qa-token'})
result_probe=client.get('/bodymind-ai-bridge/result?job_id=0',headers={'Authorization':'Bearer invalid-qa-token'})
diag_probe=client.get('/bodymind-ai-bridge/diag?stage=qa',headers={'Authorization':'Bearer invalid-qa-token'})
checks['heartbeat_get_auth_handler']=heartbeat_probe.status_code==401 and 'application/json' in str(heartbeat_probe.content_type)
checks['result_get_auth_handler']=result_probe.status_code==401 and 'application/json' in str(result_probe.content_type)
checks['diag_get_auth_handler']=diag_probe.status_code==401 and 'application/json' in str(diag_probe.content_type)
checks['bridge_get_only_machine_api']='BODYMIND_R39_BRIDGE_GET_ONLY_MACHINE_API' in install_text
failed=[k for k,v in checks.items() if not v]
print('[operator-experience-r38] checks='+repr(checks),flush=True)
print('[operator-experience-r38] counts_before='+repr(before)+' counts_after='+repr(after),flush=True)
if failed:
    raise RuntimeError('R38 operator experience QA failed '+repr(failed))
print('[operator-experience-r38-selftest] PASS mobile-chat-first imac-only high-sierra-bridge data-safe db-ok',flush=True)
