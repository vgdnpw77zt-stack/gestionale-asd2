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
    'operator_r38':('OPERATOR_VERSION = "R67.0-async-upload-jobs"' in operator_text) or ('OPERATOR_VERSION = "R66.0-upload-truth-multidoc"' in operator_text) or ('OPERATOR_VERSION = "R65.0-handwriting-enrollment"' in operator_text) or ('OPERATOR_VERSION = "R64.0-persistent-upload-task"' in operator_text) or ('OPERATOR_VERSION = "R63.0-cloud-first-brain"' in operator_text) or ('OPERATOR_VERSION = "R62.0-query-polarity"' in operator_text) or ('OPERATOR_VERSION = "R61.0-response-scope-policy"' in operator_text) or ('OPERATOR_VERSION = "R60.0-targeted-missing"' in operator_text) or ('OPERATOR_VERSION = "R59.0-voice-state-fix"' in operator_text) or ('OPERATOR_VERSION = "R57.0-fast-safe-dedupe-avatar"' in operator_text) or ('OPERATOR_VERSION = "R56.0-fast-safe-dedupe"' in operator_text) or ('OPERATOR_VERSION = "R55.0-autonomous-secretary"' in operator_text) or ('OPERATOR_VERSION = "R52.0-semantic-secretary"' in operator_text) or ('OPERATOR_VERSION = "R50.0-cloud-secretary"' in operator_text) or ('OPERATOR_VERSION = "R49.0-chat-secretary"' in operator_text),
    'mobile_compact':'BODYMIND_R38_MOBILE' in body and '.bmo-status .bmo-pill{display:none;}' in body,
    'mobile_layout_fix':(('BODYMIND_R52_CHAT_NATIVE_UI' in body and 'width:100vw!important' in body and 'height:100dvh!important' in body) or ('BODYMIND_R39_IPHONE_LAYOUT_V2' in body and 'width:100vw' not in body)) and 'BODYMIND_R39_IPHONE_FILE_PICKER_DYNAMIC' in body and 'id="bmoMobileFiles"' not in body and "document.createElement('input')" in body and 'font-size:16px' in body,
    'operator_entry_no_overlap':mobile_home.status_code==200 and 'BODYMIND_R39_IPHONE_ENTRY_V2' in mobile_body and 'bottom:calc(86px + env(safe-area-inset-bottom))' in mobile_body and 'width:46px' in mobile_body,
    'family_logo_bodymind':family.status_code==200 and 'https://bodymindaerialstudio.life/seed-media/logo?v=9' in family_body and '/bodymind-media/logo' not in family_body,
    'cloud_native_ui_r49':'IA Cloud ·' in body and 'IA iMac:' not in body and 'BODYMIND_R49_CLOUD_NATIVE_VOICE_ONLY' in body,
    'cloud_voice_only_r49':'speechSynthesis' not in body and 'webkitSpeechRecognition' not in body and 'SpeechRecognition' not in body and 'MediaRecorder' in body and '/operatore-bodymind/voice/transcribe' in operator_text and '/operatore-bodymind/voice/speak' in operator_text,
    'chat_secretary_ui_r49':'BODYMIND_R49_CHATGPT_STYLE_SECRETARY' in operator_text and 'Segreteria BodyMind' in body and ('https://bodymindaerialstudio.life/seed-media/logo?v=9' in body or '/bodymind-media/logo' in body) and 'Messaggio a Segreteria BodyMind' in body,
    'chat_history_r49':'initialHistory' in operator_text and 'bodymind_operator_messages' in operator_text and "speaker IN ('user','assistant')" in operator_text,
    'new_chat_r49':'/operatore-bodymind/new-chat' in operator_text and 'bmoNewChat' in body and 'bodymind_operator_conversation' in operator_text,
    'agent_tools_r40':'BODYMIND_R40_AGENT_TOOLS' in operator_text and '_agent_tool_catalog' in operator_text and '_execute_agent_tool' in operator_text and 'archive_duplicate_documents' in operator_text and '_duplicate_document_groups' in operator_text,
    'agent_chat_planner_r40':'BODYMIND_R46_CLOUD_NATIVE_SECRETARY' in operator_text and 'bridge_plan_tool' not in operator_text and '_cloud_plan_tool' in operator_text and 'cleanup_duplicate_documents' in operator_text,
    'dedupe_safety_r43':'BODYMIND_R43_NO_AUTODELETE_DOCUMENTS' in operator_text and "status='blocked_safety'" in operator_text and "conn.execute(\"UPDATE documenti SET visibile=0 WHERE id IN (\"+placeholders+\"),tuple(existing))" not in operator_text,
    'cloud_full_agent_r45':'BODYMIND_R45_CLOUD_FULL_AGENT' in operator_text and '_cloud_plan_tool' in operator_text and '_execute_full_agent_plan' in operator_text and '_full_agent_tool_catalog' in operator_text,
    'cloud_total_knowledge_r45':'_bodymind_route_manifest' in operator_text and '_bodymind_function_manifest' in operator_text and '_bodymind_db_manifest' in operator_text and '_capability_search' in operator_text and '_BODYMIND_GLOSSARY' in operator_text,
    'semantic_ontology_r50':'BODYMIND_R50_SEMANTIC_GLOSSARY' in operator_text and 'collaboratori' in operator_text and 'corsi_lezioni' in operator_text and 'lista_attesa' in operator_text and 'registro_sportivo' in operator_text,
    'cloud_write_planning_r45':'propose_route_action' in operator_text and 'generic_route_action' in operator_text and '_propose_generic_route_action' in operator_text and '_resolve_route_action' in operator_text,
    'cloud_write_confirmation_r45':'_set_pending_action(conn,"generic_route_action"' in operator_text and 'bodymind_operator_pending_action' in operator_text and 'backup_file=backup_dir/' in operator_text,
    'cloud_generic_safety_r45':'_GENERIC_DESTRUCTIVE_HINTS' in operator_text and 'send_mail' in operator_text and 'stripe' in operator_text and 'shutil.rmtree' in operator_text and 'blocked_safety' in operator_text,
    'cloud_agent_loop_r45':'for agent_step in range(3)' in operator_text and '_compact_agent_observation' in operator_text and 'Risultati strumenti già usati in questa richiesta' in operator_text,
    'cloud_native_secretary_r50':'BODYMIND_R46_CLOUD_NATIVE_SECRETARY' in operator_text and ('R67.0-async-upload-jobs' in operator_text or 'R66.0-upload-truth-multidoc' in operator_text or 'R65.0-handwriting-enrollment' in operator_text or 'R64.0-persistent-upload-task' in operator_text or 'R63.0-cloud-first-brain' in operator_text or 'R62.0-query-polarity' in operator_text or 'R61.0-response-scope-policy' in operator_text or 'R60.0-targeted-missing' in operator_text or 'R59.0-voice-state-fix' in operator_text or 'R57.0-fast-safe-dedupe-avatar' in operator_text or 'R56.0-fast-safe-dedupe' in operator_text or 'R55.0-autonomous-secretary' in operator_text or 'R52.0-semantic-secretary' in operator_text or 'R50.0-cloud-secretary' in operator_text or 'R49.0-chat-secretary' in operator_text),
    'cloud_no_local_fallback_r46':'bridge_plan_tool' not in operator_text and 'bridge_enhance_result' not in operator_text and 'Mac/Qwen' not in operator_text and 'IA iMac' not in operator_text,
    'cloud_bridge_removed_r47':'/bodymind-ai-bridge' not in body and 'IA iMac:' not in body and 'routes_operator_bridge' not in app_text and not (APP/'asd_app/routes_operator_bridge.py').exists(),
    'cloud_voice_backend_r46':'/operatore-bodymind/voice/transcribe' in operator_text and '/operatore-bodymind/voice/speak' in operator_text and 'gpt-transcribe' in operator_text and 'gpt-4o-mini-tts' in operator_text,
    'cloud_voice_frontend_r49':'BODYMIND_R49_CLOUD_NATIVE_VOICE_ONLY' in operator_text and 'MediaRecorder' in operator_text and 'cloudStopAndTranscribe' in operator_text,
    'cloud_budget_meter_r47':'BODYMIND_R47_AI_BUDGET_METER' in operator_text and 'bodymind_ai_usage' in operator_text and '_usage_summary' in operator_text and 'BODYMIND_AI_BUDGET_USD' in operator_text,
    'cloud_budget_alerts_r47':"b.level==='critical'||b.level==='high'||b.level==='warning'" in operator_text and 'CREDITO ESAURITO' in operator_text and 'Budget IA: uso stimato' in operator_text,
    'cloud_tts_usage_r47':'/operatore-bodymind/cloud/usage/tts' in operator_text and 'X-BodyMind-Usage-Id' in operator_text and '_TTS_EST_USD_PER_MIN' in operator_text,
    'secretary_core_r48':'BODYMIND_R48_SECRETARY_CORE' in operator_text and 'secretary_audit' in operator_text and 'scan_document_storage' in operator_text,
    'secret_vault_r48':'bodymind_secure_settings' in operator_text and 'BODYMIND_VAULT_KEY' in operator_text and '_secret_box' in operator_text,
    'smtp_secure_r48':'/operatore-bodymind/secure/smtp' in operator_text and '/operatore-bodymind/smtp/setup' in operator_text and '_smtp_test_connection' in operator_text,
    'smtp_send_r48':'"name":"send_email"' in operator_text and '_smtp_send_message' in operator_text and 'bodymind_email_log' in operator_text and 'kind=="send_email"' in operator_text,
    'batch_intent_r48':'"name":"prepare_batch_upload"' in operator_text and 'bodymind_operator_upload_intent' in operator_text and 'document_type_hint' in operator_text,
    'document_production_r48':'_productionize_inbound' in operator_text and '_verify_document_production' in operator_text and (('produced} messi in produzione e verificati' in operator_text) or ('BODYMIND_R64_PERSISTENT_UPLOAD_TASK' in operator_text and 'productionize_batch' in operator_text and 'nuovo_pronto' in operator_text and 'awaiting_confirmation' in operator_text)),
    'autonomous_secretary_r55':'BODYMIND_R55_AUTONOMOUS_SECRETARY' in operator_text and 'BODYMIND_R55_LIVING_LOGO' in operator_text and '_sync_mu_after_production' in operator_text and '_operator_db_backup' in operator_text,
    'semantic_type_safety_r55':'documents of different semantic type are NEVER duplicate candidates' in operator_text and 'modulo_unico_tesseramento' in operator_text and 'certificato_medico' in operator_text,
    'fast_safe_dedupe_r56':'BODYMIND_R56_FAST_DEDUPE' in operator_text and 'askInFlight' in operator_text and 'live multimodal/OpenAI comparisons' in operator_text and 'semantic_duplicates_' in operator_text,
    'chat_avatar_r57':'BODYMIND_R57_CHAT_AVATAR' in operator_text and "bmo-msg-avatar" in operator_text,
    'voice_state_r59':'BODYMIND_R59_VOICE_STATE_MACHINE' in operator_text and 'voiceTranscribing' in operator_text and 'stt_empty' in operator_text and "Non ho inviato nulla al gestionale." in operator_text,
    'response_scope_r61':'BODYMIND_R61_RESPONSE_SCOPE_POLICY' in operator_text and '_explicit_global_request' in operator_text and 'scope_guard' in operator_text,
    'query_polarity_r62':'BODYMIND_R62_QUERY_POLARITY' in operator_text and '_query_polarity' in operator_text and 'medical_polarity_clarification' in operator_text,
    'cloud_first_brain_r63':'BODYMIND_R63_CLOUD_FIRST_BRAIN' in operator_text and 'resolved_question' in operator_text and 'R63 cloud-first planner unavailable' in operator_text,
    'persistent_upload_r64':'BODYMIND_R64_PERSISTENT_UPLOAD_TASK' in operator_text and 'bodymind_operator_tasks' in operator_text and 'productionize_batch' in operator_text and '_semantic_key_duplicate' in operator_text,
    'handwriting_enrollment_r65':'BODYMIND_R65_HANDWRITING_ENROLLMENT' in operator_text and 'process_enrollment_batch' in operator_text and 'nuova_tesserata_pronta' in operator_text,
    'upload_truth_multidoc_r66':'BODYMIND_R66_UPLOAD_TRUTH_MULTIDOC' in operator_text and 'uploadInFlight' in operator_text and 'physical_file_count' in operator_text and 'segment_pdf_documents' in operator_text,

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
print('[operator-experience-r38-selftest] PASS R49 chat-secretary cloud-native data-safe db-ok',flush=True)
