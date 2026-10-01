# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import py_compile, shutil

APP=Path('/data/top2_app')
P=APP/'asd_app/routes_operator_bodymind.py'
BACK=Path('/data/release_backups/20261001_operator_r60/routes_operator_bodymind.py')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

s=P.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R60_TARGETED_MISSING' in s:
    print('[operator-r60] already applied',flush=True)
    raise SystemExit(0)

BACK.parent.mkdir(parents=True,exist_ok=True)
if not BACK.exists():
    shutil.copy2(P,BACK)

s=s.replace('OPERATOR_VERSION = "R59.0-voice-state-fix"','OPERATOR_VERSION = "R60.0-targeted-missing"',1)

anchor='''    athlete, ambiguous=_match_athlete(conn,raw)
'''
block='''    # BODYMIND_R60_TARGETED_MISSING
    # Narrow questions must receive narrow answers. Do not route "a chi manca X?"
    # to the full secretary audit just because the audit contains that datum.
    if any(x in n for x in ("a chi manca","chi non ha","chi manca","senza modulo","manca il modulo","manca modulo")) and any(x in n for x in ("modulo unico","modulo di iscrizione","modulo iscrizione","iscrizione")):
        a=_secretary_audit(conn)
        names=list(a.get("missing_mu") or [])
        if names:
            return {
                "text":f"Manca il Modulo Unico riconosciuto a {len(names)} tesserati: "+", ".join(names)+".",
                "mode":"targeted_fact",
                "cloud_ai":False,
                "target":"missing_mu",
                "names":names,
                "links":[{"label":"Apri Tesserati","href":"/tesserati"},{"label":"Apri Documenti","href":"/documenti"}]
            }
        return {
            "text":"Non risultano tesserati attivi senza Modulo Unico riconosciuto.",
            "mode":"targeted_fact","cloud_ai":False,"target":"missing_mu","names":[],
            "links":[{"label":"Apri Tesserati","href":"/tesserati"}]
        }

    if any(x in n for x in ("a chi manca","chi non ha","chi manca","senza certificato","manca il certificato")) and ("certificat" in n or "documento medico" in n):
        a=_secretary_audit(conn)
        # Distinguish missing medical document from missing expiry date.
        wants_expiry=any(x in n for x in ("scaden","data"))
        names=list(a.get("missing_cert_expiry") if wants_expiry else a.get("no_medical_doc") or [])
        if names:
            label="la scadenza del certificato" if wants_expiry else "il documento medico riconosciuto"
            return {
                "text":f"Manca {label} a {len(names)} tesserati: "+", ".join(names)+".",
                "mode":"targeted_fact","cloud_ai":False,
                "target":"missing_cert_expiry" if wants_expiry else "missing_medical_document",
                "names":names,
                "links":[{"label":"Apri Tesserati","href":"/tesserati"}]
            }
        return {
            "text":"Non risultano mancanze per questa voce.",
            "mode":"targeted_fact","cloud_ai":False,
            "target":"missing_cert_expiry" if wants_expiry else "missing_medical_document",
            "names":[],"links":[{"label":"Apri Tesserati","href":"/tesserati"}]
        }

'''
if anchor not in s: raise RuntimeError('R60 answer anchor missing')
s=s.replace(anchor,block+anchor,1)

P.write_text(s,encoding='utf-8')
py_compile.compile(str(P),doraise=True)
print('[operator-r60] PASS targeted-missing-mu targeted-medical no-audit no-cloud',flush=True)
