# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import py_compile, shutil

APP=Path('/data/top2_app')
P=APP/'asd_app/routes_operator_bodymind.py'
BACK=Path('/data/release_backups/20261001_operator_r62/routes_operator_bodymind.py')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

s=P.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R62_QUERY_POLARITY' in s:
    print('[operator-r62] already applied',flush=True)
    raise SystemExit(0)

BACK.parent.mkdir(parents=True,exist_ok=True)
if not BACK.exists():
    shutil.copy2(P,BACK)

s=s.replace('OPERATOR_VERSION = "R61.0-response-scope-policy"','OPERATOR_VERSION = "R62.0-query-polarity"',1)

anchor='''def _targeted_query_response(conn, raw_message):
'''
helpers=r'''# BODYMIND_R62_QUERY_POLARITY
def _query_polarity(n):
    n=_norm(n)
    negative=any(x in n for x in (
        "manca","mancano","senza","non ha","non hanno","privo","privi","assente","assenti",
        "da integrare","da completare"
    ))
    positive=any(x in n for x in (
        " hanno "," ha "," con ","presente","presenti","riconosciuto","riconosciuti",
        "possiede","possiedono","in possesso","disponibile","disponibili"
    ))
    if negative:
        return "negative"
    if positive:
        return "positive"
    return "neutral"

def _active_athlete_names(conn):
    out=[]
    for a in _athletes(conn):
        if "attivo" in a.keys() and int(a["attivo"] or 0)==0:
            continue
        out.append(_athlete_name(a))
    return out

def _complement_names(conn, missing_names):
    missing={_norm(x) for x in (missing_names or [])}
    return [x for x in _active_athlete_names(conn) if _norm(x) not in missing]

'''
if anchor not in s:
    raise RuntimeError('R62 targeted response anchor missing')
s=s.replace(anchor,helpers+anchor,1)

# Add polarity near shared query features.
old='''    missing=any(x in n for x in ("manca","mancano","senza","non ha","non hanno"))
    expiring=any(x in n for x in ("scad","scaden","in scadenza"))
'''
new='''    polarity=_query_polarity(" "+n+" ")
    missing=(polarity=="negative")
    positive=(polarity=="positive")
    expiring=any(x in n for x in ("scad","scaden","in scadenza"))
'''
if old not in s:
    raise RuntimeError('R62 polarity feature anchor missing')
s=s.replace(old,new,1)

# Replace MU block with positive/negative/ambiguous behavior.
start=s.index('''    if any(x in n for x in ("modulo unico","modulo di iscrizione","modulo iscrizione"," mu ")):
''')
end=s.index('''
    if ("certificat" in n or "documento medico" in n):
''',start)
mu=r'''    if any(x in n for x in ("modulo unico","modulo di iscrizione","modulo iscrizione"," mu ")):
        a=_secretary_audit(conn)
        missing_names=list(a.get("missing_mu") or [])
        present_names=_complement_names(conn,missing_names)
        if polarity=="negative":
            if asks_list:
                return {
                    "text":(f"Manca il Modulo Unico riconosciuto a {len(missing_names)} tesserati: "+", ".join(missing_names)+".") if missing_names
                           else "Non risultano tesserati attivi senza Modulo Unico riconosciuto.",
                    "mode":"targeted_fact","cloud_ai":False,"target":"missing_mu","names":missing_names
                }
            if asks_count:
                return {"text":f"I tesserati attivi senza Modulo Unico riconosciuto sono {len(missing_names)}.",
                        "mode":"targeted_fact","cloud_ai":False,"target":"missing_mu_count","value":len(missing_names)}
        if polarity=="positive":
            if asks_list:
                return {"text":(f"Hanno un Modulo Unico riconosciuto {len(present_names)} tesserati: "+", ".join(present_names)+".") if present_names
                               else "Non risultano tesserati attivi con Modulo Unico riconosciuto.",
                        "mode":"targeted_fact","cloud_ai":False,"target":"present_mu","names":present_names}
            if asks_count:
                return {"text":f"I tesserati attivi con Modulo Unico riconosciuto sono {len(present_names)}.",
                        "mode":"targeted_fact","cloud_ai":False,"target":"present_mu_count","value":len(present_names)}
        if asks_count or asks_list:
            return {
                "text":"Vuoi sapere quanti tesserati hanno un Modulo Unico riconosciuto oppure quanti ne sono privi?",
                "mode":"clarify","cloud_ai":False,"target":"mu_polarity_clarification"
            }
'''
s=s[:start]+mu+s[end:]

# Replace medical block.
start=s.index('''    if ("certificat" in n or "documento medico" in n):
''')
end=s.index('''
    if any(x in n for x in ("documenti da verificare","documenti in verifica","coda documenti","documenti pendenti","da verificare")):
''',start)
medical=r'''    if ("certificat" in n or "documento medico" in n):
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
        missing_names=list(a.get("missing_cert_expiry") if wants_expiry else a.get("no_medical_doc") or [])
        present_names=_complement_names(conn,missing_names)

        if polarity=="negative":
            label="la scadenza del certificato" if wants_expiry else "il documento medico riconosciuto"
            if asks_list:
                return {
                    "text":(f"Manca {label} a {len(missing_names)} tesserati: "+", ".join(missing_names)+".") if missing_names
                           else f"Non risultano tesserati attivi senza {label}.",
                    "mode":"targeted_fact","cloud_ai":False,
                    "target":"missing_cert_expiry" if wants_expiry else "missing_medical_document","names":missing_names
                }
            if asks_count:
                return {
                    "text":f"I tesserati senza {label} sono {len(missing_names)}.",
                    "mode":"targeted_fact","cloud_ai":False,
                    "target":"missing_cert_expiry_count" if wants_expiry else "missing_medical_count","value":len(missing_names)
                }

        if polarity=="positive":
            label="una scadenza certificato registrata" if wants_expiry else "un documento medico riconosciuto"
            if asks_list:
                return {
                    "text":(f"Hanno {label} {len(present_names)} tesserati: "+", ".join(present_names)+".") if present_names
                           else f"Non risultano tesserati attivi con {label}.",
                    "mode":"targeted_fact","cloud_ai":False,
                    "target":"present_cert_expiry" if wants_expiry else "present_medical_document","names":present_names
                }
            if asks_count:
                return {
                    "text":f"I tesserati con {label} sono {len(present_names)}.",
                    "mode":"targeted_fact","cloud_ai":False,
                    "target":"present_cert_expiry_count" if wants_expiry else "present_medical_count","value":len(present_names)
                }

        if asks_count or asks_list:
            return {
                "text":"Vuoi sapere quanti tesserati hanno un certificato medico riconosciuto, quanti non lo hanno, oppure quanti file di certificato sono presenti nel dossier?",
                "mode":"clarify","cloud_ai":False,"target":"medical_polarity_clarification"
            }
'''
s=s[:start]+medical+s[end:]

P.write_text(s,encoding='utf-8')
py_compile.compile(str(P),doraise=True)
print('[operator-r62] PASS query-polarity positive-negative-neutral document-possession semantics',flush=True)
