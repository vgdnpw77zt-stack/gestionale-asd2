# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import py_compile, shutil

APP=Path('/data/top2_app')
P=APP/'asd_app/routes_operator_bodymind.py'
BACK=Path('/data/release_backups/20261001_operator_r61/routes_operator_bodymind.py')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

s=P.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R61_RESPONSE_SCOPE_POLICY' in s:
    print('[operator-r61] already applied',flush=True)
    raise SystemExit(0)

BACK.parent.mkdir(parents=True,exist_ok=True)
if not BACK.exists():
    shutil.copy2(P,BACK)

s=s.replace('OPERATOR_VERSION = "R60.0-targeted-missing"','OPERATOR_VERSION = "R61.0-response-scope-policy"',1)

anchor='''def _execute_agent_tool(conn, plan, raw_message=""):
'''
helpers=r'''# BODYMIND_R61_RESPONSE_SCOPE_POLICY
def _explicit_global_request(n):
    n=_norm(n)
    return any(x in n for x in (
        "audit","situazione generale","stato generale","controlla tutto","controllo completo",
        "come siamo messi","cosa c e da fare","cosa c'è da fare","panoramica","riepilogo generale",
        "stato gestionale","verifica generale","analisi completa"
    ))

def _targeted_query_response(conn, raw_message):
    """General response-scope contract.
    If the user asks for one fact/list, answer only that fact/list.
    Full audits are reserved for explicit global requests.
    """
    raw=str(raw_message or "").strip()
    n=_norm(raw)
    if not raw or _explicit_global_request(n):
        return None

    asks_list=any(x in n for x in ("a chi","chi ","quali","quale","elenca","lista","fammi vedere","mostrami"))
    asks_count=bool(re.search(r"\b(quanti|quante|numero|totale)\b",n))
    missing=any(x in n for x in ("manca","mancano","senza","non ha","non hanno"))
    expiring=any(x in n for x in ("scad","scaden","in scadenza"))

    if any(x in n for x in ("modulo unico","modulo di iscrizione","modulo iscrizione"," mu ")):
        a=_secretary_audit(conn)
        names=list(a.get("missing_mu") or [])
        if missing or asks_list:
            return {
                "text":(f"Manca il Modulo Unico riconosciuto a {len(names)} tesserati: "+", ".join(names)+".") if names
                       else "Non risultano tesserati attivi senza Modulo Unico riconosciuto.",
                "mode":"targeted_fact","cloud_ai":False,"target":"missing_mu","names":names,
                "links":[{"label":"Apri Tesserati","href":"/tesserati"},{"label":"Apri Documenti","href":"/documenti"}]
            }
        if asks_count:
            return {"text":f"I tesserati attivi senza Modulo Unico riconosciuto sono {len(names)}.","mode":"targeted_fact","cloud_ai":False,"target":"missing_mu_count","value":len(names)}

    if ("certificat" in n or "documento medico" in n):
        a=_secretary_audit(conn)
        if expiring and asks_list:
            vals=list(a.get("expiring_cert") or [])
            if vals:
                shown=", ".join((x[0]+" ("+x[1]+")") if isinstance(x,(list,tuple)) and len(x)>1 else str(x) for x in vals)
                return {"text":"Certificati scaduti/in scadenza: "+shown+".","mode":"targeted_fact","cloud_ai":False,"target":"expiring_cert","items":vals}
            return {"text":"Non risultano certificati scaduti o in scadenza nel periodo controllato.","mode":"targeted_fact","cloud_ai":False,"target":"expiring_cert","items":[]}
        if expiring and asks_count:
            vals=list(a.get("expiring_cert") or [])
            return {"text":f"I certificati scaduti/in scadenza sono {len(vals)}.","mode":"targeted_fact","cloud_ai":False,"target":"expiring_cert_count","value":len(vals)}
        wants_expiry=any(x in n for x in ("scadenza","data di scadenza","senza data"))
        if missing or asks_list:
            names=list(a.get("missing_cert_expiry") if wants_expiry else a.get("no_medical_doc") or [])
            label="la scadenza del certificato" if wants_expiry else "il documento medico riconosciuto"
            return {
                "text":(f"Manca {label} a {len(names)} tesserati: "+", ".join(names)+".") if names
                       else f"Non risultano tesserati attivi senza {label}.",
                "mode":"targeted_fact","cloud_ai":False,
                "target":"missing_cert_expiry" if wants_expiry else "missing_medical_document","names":names
            }
        if asks_count:
            vals=list(a.get("missing_cert_expiry") if wants_expiry else a.get("no_medical_doc") or [])
            label="senza scadenza certificato" if wants_expiry else "senza documento medico riconosciuto"
            return {"text":f"I tesserati {label} sono {len(vals)}.","mode":"targeted_fact","cloud_ai":False,"target":"medical_count","value":len(vals)}

    if any(x in n for x in ("documenti da verificare","documenti in verifica","coda documenti","documenti pendenti","da verificare")):
        cnt=_pending_count(conn)
        if asks_count or not asks_list:
            return {"text":f"I documenti che richiedono verifica sono {cnt}.","mode":"targeted_fact","cloud_ai":False,"target":"pending_documents","value":cnt,
                    "links":[{"label":"Apri Da verificare","href":"/documenti/da-verificare"}]}

    if ("minor" in n) and any(x in n for x in ("tutela","consenso","genitor","autorizz")):
        a=_secretary_audit(conn); names=list(a.get("minor_issues") or [])
        if asks_list or missing:
            return {"text":("Minori con tutela da rivedere: "+", ".join(names)+".") if names else "Non risultano minori con tutela da rivedere.",
                    "mode":"targeted_fact","cloud_ai":False,"target":"minor_issues","names":names}
        if asks_count:
            return {"text":f"I minori con tutela da rivedere sono {len(names)}.","mode":"targeted_fact","cloud_ai":False,"target":"minor_issues_count","value":len(names)}

    if re.search(r"\b(quanti|quante|numero|totale)\b",n):
        if any(x in n for x in ("tesserat","iscritt","atlet","alliev","soci")):
            cnt=len(_athletes(conn))
            return {"text":f"Nel gestionale risultano {cnt} tesserati.","mode":"targeted_fact","cloud_ai":False,"target":"athletes_count","value":cnt}
        if "pagament" in n or "incass" in n:
            cnt=int(conn.execute("SELECT COUNT(*) FROM pagamenti").fetchone()[0]) if _table(conn,"pagamenti") else 0
            return {"text":f"I pagamenti registrati sono {cnt}.","mode":"targeted_fact","cloud_ai":False,"target":"payments_count","value":cnt}
        if "ricevut" in n:
            cnt=int(conn.execute("SELECT COUNT(*) FROM ricevute").fetchone()[0]) if _table(conn,"ricevute") else 0
            return {"text":f"Le ricevute registrate sono {cnt}.","mode":"targeted_fact","cloud_ai":False,"target":"receipts_count","value":cnt}

    return None

'''
if anchor not in s:
    raise RuntimeError('R61 execute-agent anchor missing')
s=s.replace(anchor,helpers+anchor,1)

# Enforce scope before broad tools execute.
old='''    if not tool or tool in ("none","unknown"):
        return None

    athlete=None
'''
new='''    if not tool or tool in ("none","unknown"):
        return None

    if tool in ("secretary_audit","global_status") and raw_message and not _explicit_global_request(raw_message):
        scoped=_targeted_query_response(conn,raw_message)
        if scoped:
            scoped["scope_guard"]=True
            return scoped

    athlete=None
'''
if old not in s:
    raise RuntimeError('R61 tool-scope anchor missing')
s=s.replace(old,new,1)

# Apply targeted scope before athlete/context/planner routing.
old='''    athlete, ambiguous=_match_athlete(conn,raw)
'''
new='''    scoped=_targeted_query_response(conn,raw)
    if scoped:
        return scoped

    athlete, ambiguous=_match_athlete(conn,raw)
'''
if old not in s:
    raise RuntimeError('R61 answer-scope anchor missing')
s=s.replace(old,new,1)

# Strengthen planner contract globally, not per phrase.
old='''            "Parla in italiano naturale, chiaro e sintetico; non mostrare route, nomi tecnici o ragionamenti interni se non richiesti. Devi capire italiano naturale, sinonimi, abbreviazioni e contesto. "
'''
new='''            "Parla in italiano naturale, chiaro e sintetico; non mostrare route, nomi tecnici o ragionamenti interni se non richiesti. Devi capire italiano naturale, sinonimi, abbreviazioni e contesto. "
            "REGOLA DI SCOPE OBBLIGATORIA: rispondi soltanto a ciò che è stato chiesto. Una domanda stretta deve produrre una risposta stretta; una richiesta di elenco deve produrre solo quell'elenco; una domanda su una persona deve restare su quella persona. Non aggiungere audit, riepiloghi generali, priorità o altre categorie non richieste. Usa secretary_audit/global_status come risposta generale SOLO se l'utente chiede esplicitamente audit, situazione generale, panoramica, stato gestionale o controllo completo. "
'''
if old not in s:
    raise RuntimeError('R61 planner prompt anchor missing')
s=s.replace(old,new,1)

# Same scope contract for conversational final answers.
old='''            "Devi parlare in italiano naturale, professionale, amichevole e molto competente. "
'''
new='''            "Devi parlare in italiano naturale, professionale, amichevole e molto competente. "
            "Rispondi esattamente alla domanda: non allargare mai una richiesta specifica ad audit, riepiloghi generali o informazioni non richieste. "
'''
if old not in s:
    raise RuntimeError('R61 answer prompt anchor missing')
s=s.replace(old,new,1)

P.write_text(s,encoding='utf-8')
py_compile.compile(str(P),doraise=True)
print('[operator-r61] PASS global-response-scope targeted-first broad-tool-guard planner-scope',flush=True)
