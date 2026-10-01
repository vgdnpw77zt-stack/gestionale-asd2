# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import py_compile, shutil

APP=Path('/data/top2_app')
P=APP/'asd_app/routes_operator_bodymind.py'
BACK=Path('/data/release_backups/20261001_operator_r63/routes_operator_bodymind.py')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

s=P.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R63_CLOUD_FIRST_BRAIN' in s:
    print('[operator-r63] already applied',flush=True)
    raise SystemExit(0)

BACK.parent.mkdir(parents=True,exist_ok=True)
if not BACK.exists():
    shutil.copy2(P,BACK)

s=s.replace('OPERATOR_VERSION = "R62.0-query-polarity"','OPERATOR_VERSION = "R63.0-cloud-first-brain"',1)

# Strengthen planner semantics/context.
old='''            "Sei la Segreteria BodyMind: un assistente operativo cloud con qualità conversazionale paragonabile a un ottimo assistente generale, ma specializzato completamente nel gestionale BodyMind. "
            "Parla in italiano naturale, chiaro e sintetico; non mostrare route, nomi tecnici o ragionamenti interni se non richiesti. Devi capire italiano naturale, sinonimi, abbreviazioni e contesto. "'''
new='''            "BODYMIND_R63_CLOUD_FIRST_BRAIN. Sei la Segreteria BodyMind: il cervello operativo principale del gestionale, non un classificatore di parole chiave. "
            "Parla in italiano naturale, chiaro e sintetico; non mostrare route, nomi tecnici o ragionamenti interni se non richiesti. "
            "Comprendi il SIGNIFICATO della richiesta, inclusi negazioni, possesso, confronto, pronomi, ellissi e follow-up brevi. "
            "Usa il contesto recente per ricostruire frasi come 'e gli altri?', 'allora?', 'quanti ce l'hanno?', 'e quelli senza?' senza perdere l'argomento precedente. "
            "Se il contesto non basta davvero, fai UNA domanda di chiarimento naturale invece di inventare o rispondere a una domanda diversa. "
            "Non trasformare una domanda specifica in un audit generale. "'''
if old not in s:
    raise RuntimeError('R63 planner prompt anchor missing')
s=s.replace(old,new,1)

schema_old='''            "Restituisci SOLO JSON valido: {\\\"tool\\\":\\\"nome_o_none\\\",\\\"args\\\":{},\\\"answer\\\":\\\"\\\"}. "
'''
schema_new='''            "Restituisci SOLO JSON valido: {\\\"tool\\\":\\\"nome_o_none\\\",\\\"args\\\":{},\\\"answer\\\":\\\"\\\",\\\"resolved_question\\\":\\\"richiesta autonoma completa\\\"}. "
            "resolved_question deve sempre riscrivere la richiesta come frase autonoma, esplicitando l'argomento recuperato dal contesto recente senza cambiarne il significato. "
'''
if schema_old not in s:
    raise RuntimeError('R63 planner JSON schema anchor missing')
s=s.replace(schema_old,schema_new,1)

old='''        recent=_recent_operator_context(conn,4)'''
new='''        recent=_recent_operator_context(conn,10)'''
if old not in s:
    raise RuntimeError('R63 recent context anchor missing')
s=s.replace(old,new,1)

# Replace chat request path: cloud first, deterministic fallback.
start=s.index('@app.post("/operatore-bodymind/chat")')
end=s.index('\ndef _cloud_user_error',start)
new_route=r'''@app.post("/operatore-bodymind/chat")
@login_required
def bodymind_operator_chat():
    payload=request.get_json(silent=True) or {}
    message=str(payload.get("message") or "")[:8000]
    conn=db()
    try:
        _schema(conn)
        _log(conn,"user",message)

        # Confirmations/cancellations of already prepared writes are ALWAYS deterministic.
        # The model never gets to reinterpret a pending "sì/no".
        pending=bool(session.get("bodymind_operator_pending_action"))
        if pending and (_yes(message) or _no(message)):
            result=_answer(conn,message)
            _log(conn,"assistant",result.get("text",""),result)
            return jsonify(result)

        result=None
        planner_used=False
        trace=[]
        discovery_tools={"discover_capabilities","inspect_route","inspect_system_map","inspect_db_schema"}

        # BODYMIND_R63_CLOUD_FIRST_BRAIN:
        # Natural-language understanding belongs to the cloud planner first.
        # Local rules are a resilience fallback, not the primary brain.
        try:
            for agent_step in range(3):
                plan=_cloud_plan_tool(conn,message,trace)
                if not plan:
                    break
                planner_used=True
                tool=str(plan.get("tool") or "").strip()
                if tool in ("none","unknown",""):
                    answer=str(plan.get("answer") or "").strip()
                    if answer:
                        result={
                            "text":answer,
                            "mode":"cloud_ai",
                            "allow_device_ai":False,
                            "cloud_ai":True,
                            "agent_plan":"none",
                            "agent_steps":agent_step+1,
                            "cloud_first":True,
                            "resolved_question":str(plan.get("resolved_question") or message).strip() or message,
                        }
                    break
                resolved=str(plan.get("resolved_question") or message).strip() or message
                tool_result=_execute_full_agent_plan(conn,plan,resolved)
                if isinstance(tool_result,dict):
                    tool_result["resolved_question"]=resolved
                if not tool_result:
                    break
                tool_result["agent_steps"]=agent_step+1
                tool_result["cloud_first"]=True
                if tool in discovery_tools and agent_step<2:
                    trace.append(_compact_agent_observation(tool,tool_result))
                    result=tool_result
                    continue
                result=tool_result
                break
        except Exception as cloud_planner_exc:
            try:
                _log(conn,"system","R63 cloud-first planner unavailable: "+repr(cloud_planner_exc))
            except Exception:
                pass

        # Resilience fallback: deterministic knowledge/rules only if cloud could not answer.
        if not result:
            result=_answer(conn,message)
            if isinstance(result,dict):
                result["cloud_first_fallback"]=True

        # If even fallback says it needs cloud and cloud failed, explain accurately.
        if not planner_used and str((result or {}).get("mode") or "")=="fallback":
            err=str(_CLOUD_LAST_ERROR or "")
            low=err.lower()
            if "credit_balance_exhausted" in low or "insufficient_quota" in low or "no credits remaining" in low:
                msg="L’IA cloud è configurata ma il credito API è esaurito. Ricarica il credito per continuare."
            elif err:
                msg="Il cervello cloud non è disponibile in questo momento. Non ho eseguito modifiche."
            else:
                msg="Non sono riuscito a interpretare la richiesta con sufficiente certezza. Puoi riformularla?"
            result={"text":msg,"mode":"cloud_unavailable","allow_device_ai":False,"cloud_ai":False}

        _log(conn,"assistant",result.get("text",""),result)
        return jsonify(result)
    except Exception as exc:
        try:
            _log(conn,"system","ERROR "+repr(exc))
        except Exception:
            pass
        return jsonify({"text":"Ho incontrato un errore interno mentre controllavo i dati. Non ho eseguito modifiche.","mode":"error"}),500
    finally:
        conn.close()

'''
s=s[:start]+new_route+s[end:]

P.write_text(s,encoding='utf-8')
py_compile.compile(str(P),doraise=True)
print('[operator-r63] PASS cloud-first-language-understanding context-10 deterministic-write-confirmation local-fallback',flush=True)
