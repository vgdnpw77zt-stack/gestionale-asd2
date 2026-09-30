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
mobile_home=client.get('/mobile')
mobile_body=mobile_home.get_data(as_text=True)
family=client.get('/area-famiglie')
family_body=family.get_data(as_text=True)
installer=client.get('/bodymind-ai-bridge/install.sh')
install_text=installer.get_data(as_text=True)
operator_text=operator.read_text(encoding='utf-8',errors='replace')
bridge_text=bridge.read_text(encoding='utf-8',errors='replace')
checks={
    'home_200':home.status_code==200,
    'operator_r38':('OPERATORE IA · R40.0-agent-tools' in body) or ('OPERATOR_VERSION = "R45.0-cloud-full-agent"' in operator_text) or ('OPERATOR_VERSION = "R40.0-agent-tools"' in operator_text),
    'mobile_compact':'BODYMIND_R38_MOBILE' in body and '.bmo-status .bmo-pill{display:none;}' in body,
    'mobile_layout_fix':'BODYMIND_R39_IPHONE_LAYOUT_V2' in body and 'BODYMIND_R39_IPHONE_FILE_PICKER_DYNAMIC' in body and 'id="bmoMobileFiles"' not in body and "document.createElement('input')" in body and 'width:100vw' not in body and 'font-size:16px' in body and 'bottom:calc(76px + env(safe-area-inset-bottom))' in body,
    'operator_entry_no_overlap':mobile_home.status_code==200 and 'BODYMIND_R39_IPHONE_ENTRY_V2' in mobile_body and 'bottom:calc(86px + env(safe-area-inset-bottom))' in mobile_body and 'width:46px' in mobile_body,
    'ios_tts_unlock':'BODYMIND_R39_IOS_TTS_UNLOCK' in body and "speechSynthesis.resume()" in body,
    'ios_tts_persistent':'BODYMIND_R39_IOS_TTS_PERSISTENT_FIX' in body and 'ttsUtterance' in body and 'bodymind_tts_enabled_v2' in body and 'bmoVoiceRecover' in body,
    'ios_natural_voice':'BODYMIND_R39_NATURAL_VOICE_V2' in body and 'refreshTTSVoices' in body and 'speechChunks' in body and "includes('premium')" in body and "includes('enhanced')" in body,
    'ios_webkit27_voice_v5':'BODYMIND_R39_IOS_WEBKIT27_V5' in body and 'BODYMIND_R39_IOS_SR_WEBKIT27_STATE_MACHINE_V5' in body and 'waitSpeechIdle' in body and 'startFreshRecognition' in body and "document.addEventListener('pointerdown',unlockOnce" not in body and "speak(lastSpeechText||'Voce attiva.',true)" in body,
    'ios_voice_stable_v6':'BODYMIND_R39_IOS_VOICE_STABLE_V6' in body and '7000' in body and 'sr_aborted_ignored' in body and 'sr_stale_error_ignored' in body and "score(best)>=200" in body and "includes('compact')" in body and "2200" not in body,
    'ios_mic_prime_v7':'BODYMIND_R39_IOS_MIC_PRIME_V7' in body and 'primeMicForRecognition' in body and 'mic_prime_signal' in body and 'getByteTimeDomainData' in body and "print(line, flush=True)" in bridge_text or 'BODYMIND_R39_IOS_MIC_PRIME_V7' in body and 'primeMicForRecognition' in body and 'mic_prime_signal' in body and 'getByteTimeDomainData' in body,
    'ios_mic_direct':'BODYMIND_R39_IOS_SR_RECREATE_V4' in body and "await ensureMic();recognition.start()" not in body and 'buildRecognition' in body,
    'ios_voice_recovery_v4':'BODYMIND_R39_IOS_VOICE_RECOVERY_V4' in body and 'bmoVoiceRecover' in body and 'buildRecognition' in body and 'sr_start_timeout' in body and 'sr_retry_call' in body,
    'ios_sr_recreate_v4':'BODYMIND_R39_IOS_SR_RECREATE_V4' in body and 'recognition=buildRecognition()' in body and "localStorage.getItem(TTS_KEY)==='1')ttsPrimed=true" not in body,
    'family_logo_bodymind':family.status_code==200 and 'https://bodymindaerialstudio.life/seed-media/logo?v=9' in family_body and '/bodymind-media/logo' not in family_body,
    'mobile_imac_only':'IA iMac:' in body and 'LanguageModel' not in body and 'window.ai' not in body,
    'installer_200':installer.status_code==200,
    'high_sierra_python_fallback':'command -v python3' in install_text and 'command -v python ' in install_text,
    'python27_bridge_compat':'from urllib2 import Request, urlopen' in install_text,
    'local_llama_health':'127.0.0.1:8088/health' in install_text,
    'heartbeat_verification':'/bodymind-ai-bridge/heartbeat' in install_text,
    'bridge_csrf_safe_get_pairing':'BODYMIND_R39_BRIDGE_CSRF_SAFE_GET_PAIRING' in install_text,
    'bridge_diag_checkpoints':'BODYMIND_R39_BRIDGE_DIAGNOSTIC_CHECKPOINTS' in install_text,
    'explicit_installer_file':'BODYMIND_R39_EXPLICIT_INSTALL_FILE' in install_text and '/tmp/bodymind-ai-r39.sh' in bridge_text and '/bin/bash /tmp/bodymind-ai-r39.sh' in bridge_text and '| bash' not in bridge_text,
    'custom_token_header':'BODYMIND_R39_CUSTOM_TOKEN_HEADER' in install_text and 'X-BodyMind-Token' in install_text and 'https://app.bodymindaerialstudio.life' in bridge_text,
    'curl_remote_transport':'BODYMIND_R39_CURL_REMOTE_TRANSPORT' in install_text and '/usr/bin/curl' in install_text,
    'local_ai_quality_v2':'BODYMIND_R39_LOCAL_AI_QUALITY_V2' in install_text and '_bridge_recent_context' in bridge_text and '_bridge_token_budget' in bridge_text and 'temperature":0.35' in install_text,
    'local_ai_fast_split':'BODYMIND_R39_LOCAL_AI_FAST_SPLIT' in install_text and "allowed_read_modes={'fallback'}" in bridge_text and 'DEFAULT 80' not in bridge_text,
    'local_ai_latency_v3':'BODYMIND_R39_LOCAL_AI_LATENCY_V3' in install_text and 'return 70' in bridge_text and 'return 100' in bridge_text and 'limit=3' in bridge_text and "'42'" in bridge_text,
    'agent_tools_r40':'BODYMIND_R40_AGENT_TOOLS' in operator_text and '_agent_tool_catalog' in operator_text and '_execute_agent_tool' in operator_text and 'archive_duplicate_documents' in operator_text and '_duplicate_document_groups' in operator_text,
    'local_tool_planner_r40':'BODYMIND_R40_LOCAL_TOOL_PLANNER' in bridge_text and 'bridge_plan_tool' in bridge_text and 'Non fingere mai di aver eseguito azioni' in bridge_text,
    'agent_chat_planner_r40':'bridge_plan_tool' in operator_text and 'planner_used=False' in operator_text and 'agent_plan' in operator_text and 'cleanup_duplicate_documents' in operator_text,
    'dedupe_safety_r43':'BODYMIND_R43_NO_AUTODELETE_DOCUMENTS' in operator_text and "status='blocked_safety'" in operator_text and "conn.execute(\"UPDATE documenti SET visibile=0 WHERE id IN (\"+placeholders+\"),tuple(existing))" not in operator_text,
    'cloud_full_agent_r45':'BODYMIND_R45_CLOUD_FULL_AGENT' in operator_text and '_cloud_plan_tool' in operator_text and '_execute_full_agent_plan' in operator_text and '_full_agent_tool_catalog' in operator_text,
    'cloud_total_knowledge_r45':'_bodymind_route_manifest' in operator_text and '_bodymind_function_manifest' in operator_text and '_bodymind_db_manifest' in operator_text and '_capability_search' in operator_text and '_BODYMIND_GLOSSARY' in operator_text,
    'cloud_write_planning_r45':'propose_route_action' in operator_text and 'generic_route_action' in operator_text and '_propose_generic_route_action' in operator_text and '_resolve_route_action' in operator_text,
    'cloud_write_confirmation_r45':'_set_pending_action(conn,"generic_route_action"' in operator_text and 'bodymind_operator_pending_action' in operator_text and 'backup_file=backup_dir/' in operator_text,
    'cloud_generic_safety_r45':'_GENERIC_DESTRUCTIVE_HINTS' in operator_text and 'send_mail' in operator_text and 'stripe' in operator_text and 'shutil.rmtree' in operator_text and 'blocked_safety' in operator_text,
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
heartbeat_probe=client.get('/bodymind-ai-bridge/heartbeat',headers={'X-BodyMind-Token':'invalid-qa-token'})
result_probe=client.get('/bodymind-ai-bridge/result?job_id=0',headers={'X-BodyMind-Token':'invalid-qa-token'})
diag_probe=client.get('/bodymind-ai-bridge/diag?stage=qa',headers={'X-BodyMind-Token':'invalid-qa-token'})
voice_diag_probe=client.post('/operatore-bodymind/voice-diag',json={'stage':'qa','sr':True,'synth':True,'voices':3},headers={'X-CSRFToken':'qa-r38'})
checks['heartbeat_get_auth_handler']=heartbeat_probe.status_code==401 and 'application/json' in str(heartbeat_probe.content_type)
checks['result_get_auth_handler']=result_probe.status_code==401 and 'application/json' in str(result_probe.content_type)
checks['diag_get_auth_handler']=diag_probe.status_code==401 and 'application/json' in str(diag_probe.content_type)
checks['voice_diag_runtime']=voice_diag_probe.status_code==200 and (voice_diag_probe.get_json(silent=True) or {}).get('ok') is True
checks['bridge_get_only_machine_api']='BODYMIND_R39_BRIDGE_GET_ONLY_MACHINE_API' in install_text
failed=[k for k,v in checks.items() if not v]
print('[operator-experience-r38] checks='+repr(checks),flush=True)
print('[operator-experience-r38] counts_before='+repr(before)+' counts_after='+repr(after),flush=True)
if failed:
    raise RuntimeError('R38 operator experience QA failed '+repr(failed))
print('[operator-experience-r38-selftest] PASS mobile-chat-first imac-only high-sierra-bridge data-safe db-ok',flush=True)
