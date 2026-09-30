# -*- coding: utf-8 -*-
from __future__ import annotations
import compileall, os, sqlite3, sys
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

operator=APP/'asd_app/routes_operator_bodymind.py'
if not operator.exists():
    raise RuntimeError('R47 operator runtime missing')
if not compileall.compile_file(str(operator),quiet=1):
    raise RuntimeError('R38 operator compile failed')

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
operator_text=operator.read_text(encoding='utf-8',errors='replace')
app_text=(APP/'app.py').read_text(encoding='utf-8',errors='replace')
checks={
    'home_200':home.status_code==200,
    'operator_r38':('OPERATOR_VERSION = "R47.0-cloud-native-secretary"' in operator_text) or ('OPERATOR_VERSION = "R46.0-cloud-native-secretary"' in operator_text),
    'mobile_compact':'BODYMIND_R38_MOBILE' in body and '.bmo-status .bmo-pill{display:none;}' in body,
    'mobile_layout_fix':'BODYMIND_R39_IPHONE_LAYOUT_V2' in body and 'BODYMIND_R39_IPHONE_FILE_PICKER_DYNAMIC' in body and 'id="bmoMobileFiles"' not in body and "document.createElement('input')" in body and 'width:100vw' not in body and 'font-size:16px' in body and 'bottom:calc(76px + env(safe-area-inset-bottom))' in body,
    'operator_entry_no_overlap':mobile_home.status_code==200 and 'BODYMIND_R39_IPHONE_ENTRY_V2' in mobile_body and 'bottom:calc(86px + env(safe-area-inset-bottom))' in mobile_body and 'width:46px' in mobile_body,
    'ios_tts_unlock':'BODYMIND_R39_IOS_TTS_UNLOCK' in body and "speechSynthesis.resume()" in body,
    'ios_tts_persistent':'BODYMIND_R39_IOS_TTS_PERSISTENT_FIX' in body and 'ttsUtterance' in body and 'bodymind_tts_enabled_v2' in body and 'bmoVoiceRecover' in body,
    'ios_natural_voice':'BODYMIND_R39_NATURAL_VOICE_V2' in body and 'refreshTTSVoices' in body and 'speechChunks' in body and "includes('premium')" in body and "includes('enhanced')" in body,
    'ios_webkit27_voice_v5':'BODYMIND_R39_IOS_WEBKIT27_V5' in body and 'BODYMIND_R39_IOS_SR_WEBKIT27_STATE_MACHINE_V5' in body and 'waitSpeechIdle' in body and 'startFreshRecognition' in body and "document.addEventListener('pointerdown',unlockOnce" not in body and "speak(lastSpeechText||'Voce attiva.',true)" in body,
    'ios_voice_stable_v6':'BODYMIND_R39_IOS_VOICE_STABLE_V6' in body and '7000' in body and 'sr_aborted_ignored' in body and 'sr_stale_error_ignored' in body and "score(best)>=200" in body and "includes('compact')" in body and "2200" not in body,
    'ios_mic_direct':'BODYMIND_R39_IOS_SR_RECREATE_V4' in body and "await ensureMic();recognition.start()" not in body and 'buildRecognition' in body,
    'ios_voice_recovery_v4':'BODYMIND_R39_IOS_VOICE_RECOVERY_V4' in body and 'bmoVoiceRecover' in body and 'buildRecognition' in body and 'sr_start_timeout' in body and 'sr_retry_call' in body,
    'ios_sr_recreate_v4':'BODYMIND_R39_IOS_SR_RECREATE_V4' in body and 'recognition=buildRecognition()' in body and "localStorage.getItem(TTS_KEY)==='1')ttsPrimed=true" not in body,
    'family_logo_bodymind':family.status_code==200 and 'https://bodymindaerialstudio.life/seed-media/logo?v=9' in family_body and '/bodymind-media/logo' not in family_body,
    'cloud_native_ui_r46':'IA Cloud ·' in body and 'IA iMac:' not in body and 'BODYMIND_R46_CLOUD_NATIVE_VOICE' in body,
    'agent_tools_r40':'BODYMIND_R40_AGENT_TOOLS' in operator_text and '_agent_tool_catalog' in operator_text and '_execute_agent_tool' in operator_text and 'archive_duplicate_documents' in operator_text and '_duplicate_document_groups' in operator_text,
    'agent_chat_planner_r40':'BODYMIND_R46_CLOUD_NATIVE_SECRETARY' in operator_text and 'bridge_plan_tool' not in operator_text and '_cloud_plan_tool' in operator_text and 'cleanup_duplicate_documents' in operator_text,
    'dedupe_safety_r43':'BODYMIND_R43_NO_AUTODELETE_DOCUMENTS' in operator_text and "status='blocked_safety'" in operator_text and "conn.execute(\"UPDATE documenti SET visibile=0 WHERE id IN (\"+placeholders+\"),tuple(existing))" not in operator_text,
    'cloud_full_agent_r45':'BODYMIND_R45_CLOUD_FULL_AGENT' in operator_text and '_cloud_plan_tool' in operator_text and '_execute_full_agent_plan' in operator_text and '_full_agent_tool_catalog' in operator_text,
    'cloud_total_knowledge_r45':'_bodymind_route_manifest' in operator_text and '_bodymind_function_manifest' in operator_text and '_bodymind_db_manifest' in operator_text and '_capability_search' in operator_text and '_BODYMIND_GLOSSARY' in operator_text,
    'cloud_write_planning_r45':'propose_route_action' in operator_text and 'generic_route_action' in operator_text and '_propose_generic_route_action' in operator_text and '_resolve_route_action' in operator_text,
    'cloud_write_confirmation_r45':'_set_pending_action(conn,"generic_route_action"' in operator_text and 'bodymind_operator_pending_action' in operator_text and 'backup_file=backup_dir/' in operator_text,
    'cloud_generic_safety_r45':'_GENERIC_DESTRUCTIVE_HINTS' in operator_text and 'send_mail' in operator_text and 'stripe' in operator_text and 'shutil.rmtree' in operator_text and 'blocked_safety' in operator_text,
    'cloud_agent_loop_r45':'for agent_step in range(3)' in operator_text and '_compact_agent_observation' in operator_text and 'Risultati strumenti già usati in questa richiesta' in operator_text,
    'cloud_native_secretary_r47':'BODYMIND_R46_CLOUD_NATIVE_SECRETARY' in operator_text and 'R47.0-cloud-native-secretary' in operator_text,
    'cloud_no_local_fallback_r46':'bridge_plan_tool' not in operator_text and 'bridge_enhance_result' not in operator_text and 'Mac/Qwen' not in operator_text and 'IA iMac' not in operator_text,
    'cloud_bridge_removed_r47':'/bodymind-ai-bridge' not in body and 'IA iMac:' not in body and 'routes_operator_bridge' not in app_text and not (APP/'asd_app/routes_operator_bridge.py').exists(),
    'cloud_voice_backend_r46':'/operatore-bodymind/voice/transcribe' in operator_text and '/operatore-bodymind/voice/speak' in operator_text and 'gpt-transcribe' in operator_text and 'gpt-4o-mini-tts' in operator_text,
    'cloud_voice_frontend_r46':'BODYMIND_R46_CLOUD_NATIVE_VOICE' in operator_text and 'MediaRecorder' in operator_text and 'cloudStopAndTranscribe' in operator_text,
    'cloud_budget_meter_r47':'BODYMIND_R47_AI_BUDGET_METER' in operator_text and 'bodymind_ai_usage' in operator_text and '_usage_summary' in operator_text and 'BODYMIND_AI_BUDGET_USD' in operator_text,
    'cloud_budget_alerts_r47':"b.level==='critical'||b.level==='high'||b.level==='warning'" in operator_text and 'CREDITO ESAURITO' in operator_text and 'Budget IA: uso stimato' in operator_text,
    'cloud_tts_usage_r47':'/operatore-bodymind/cloud/usage/tts' in operator_text and 'X-BodyMind-Usage-Id' in operator_text and '_TTS_EST_USD_PER_MIN' in operator_text,
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
# R47: local bridge endpoints must be gone.
bridge_probe=client.get('/bodymind-ai-bridge/heartbeat')
checks['cloud_bridge_routes_gone_r47']=bridge_probe.status_code==404
voice_diag_probe=client.post('/operatore-bodymind/voice-diag',json={'stage':'qa','sr':True,'synth':True,'voices':3},headers={'X-CSRFToken':'qa-r38'})
checks['voice_diag_runtime']=voice_diag_probe.status_code==200 and (voice_diag_probe.get_json(silent=True) or {}).get('ok') is True
failed=[k for k,v in checks.items() if not v]
print('[operator-experience-r38] checks='+repr(checks),flush=True)
print('[operator-experience-r38] counts_before='+repr(before)+' counts_after='+repr(after),flush=True)
if failed:
    raise RuntimeError('R38 operator experience QA failed '+repr(failed))
print('[operator-experience-r38-selftest] PASS cloud-native-secretary no-local-bridge data-safe db-ok',flush=True)
