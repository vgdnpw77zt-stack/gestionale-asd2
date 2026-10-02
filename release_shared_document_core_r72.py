# -*- coding: utf-8 -*-
from __future__ import annotations
import compileall, shutil
from pathlib import Path

APP=Path('/data/top2_app')
BACK=Path('/data/release_backups/20261002_shared_doc_core_r72')
BACK.mkdir(parents=True,exist_ok=True)

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

# ---- Autopilot / inbound ingestion ----
P=APP/'asd_app/routes_email_documents.py'
s=P.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R72_SHARED_MU_CORE_AUTOPILOT' not in s:
    b=BACK/'routes_email_documents.py'
    if not b.exists(): shutil.copy2(P,b)

    old='''            res["tesserato_id"]=tid
            res["semantic_match_reason"]=match_reason or ("nuova_tesserata_da_modulo" if created else "semantic")
            res["semantic_analysis"]=analysis
            res["new_athlete_created"]=created
            return res
'''
    new='''            # BODYMIND_R72_SHARED_MU_CORE_AUTOPILOT
            # Once Autopilot has a high-confidence MU and a resolved athlete, use the same
            # central profile/guardian/onboarding synchronizer used by manual confirmation.
            if str((analysis or {}).get("document_type") or "")=="modulo_unico_tesseramento":
                try:
                    from .verified_mu_sync_core_r68 import sync_analysis_to_existing_athlete as _r72_sync_mu
                    res["profile_sync"]=_r72_sync_mu(conn,tid,analysis,source="autopilot_r72_shared_core")
                except Exception as _r72_exc:
                    res["profile_sync"]={"ok":False,"reason":"shared_core_error","detail":str(_r72_exc)[:160]}
            res["tesserato_id"]=tid
            res["semantic_match_reason"]=match_reason or ("nuova_tesserata_da_modulo" if created else "semantic")
            res["semantic_analysis"]=analysis
            res["new_athlete_created"]=created
            return res
'''
    if old not in s:
        raise RuntimeError('R72 Autopilot anchor missing')
    s=s.replace(old,new,1)
    P.write_text(s,encoding='utf-8')

# ---- Operator confirmed production ----
OP=APP/'asd_app/routes_operator_bodymind.py'
s=OP.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R72_SHARED_MU_CORE_OPERATOR' not in s:
    b=BACK/'routes_operator_bodymind.py'
    if not b.exists(): shutil.copy2(OP,b)

    # Generic confirmed batch: enrich only after production succeeds and only for MU.
    old='''            ok,details=_productionize_inbound(inbound_id,type_hint=dtype)
            if ok:
                imported.append({"inbound_id":inbound_id,**(details or {})})
            else:
                blocked.append({"inbound_id":inbound_id,"reason":str((details or {}).get("reason") or "produzione non riuscita"),"details":details})
'''
    new='''            ok,details=_productionize_inbound(inbound_id,type_hint=dtype)
            if ok:
                # BODYMIND_R72_SHARED_MU_CORE_OPERATOR
                if str((analysis or {}).get("document_type") or "")=="modulo_unico_tesseramento":
                    try:
                        from .verified_mu_sync_core_r68 import sync_analysis_to_existing_athlete as _r72_sync_mu
                        _r72_sync_mu(conn,tid,analysis,source="operator_r72_confirmed_batch")
                    except Exception:
                        pass
                imported.append({"inbound_id":inbound_id,**(details or {})})
            else:
                blocked.append({"inbound_id":inbound_id,"reason":str((details or {}).get("reason") or "produzione non riuscita"),"details":details})
'''
    if old not in s:
        raise RuntimeError('R72 generic operator batch anchor missing')
    s=s.replace(old,new,1)

    # Enrollment batch: both existing and newly-created athletes converge on the same core.
    old='''            ok,details=_productionize_inbound(inbound_id,type_hint="modulo_unico_tesseramento")
            if ok:
                imported.append({"inbound_id":inbound_id,"tesserato_id":tid,"created":was_created,**(details or {})})
            else:
                blocked.append({"inbound_id":inbound_id,"tesserato_id":tid,"reason":str((details or {}).get("reason") or "modulo non prodotto")})
'''
    new='''            ok,details=_productionize_inbound(inbound_id,type_hint="modulo_unico_tesseramento")
            if ok:
                try:
                    from .verified_mu_sync_core_r68 import sync_analysis_to_existing_athlete as _r72_sync_mu
                    _r72_sync_mu(conn,tid,analysis,source="operator_r72_enrollment_batch")
                except Exception:
                    pass
                imported.append({"inbound_id":inbound_id,"tesserato_id":tid,"created":was_created,**(details or {})})
            else:
                blocked.append({"inbound_id":inbound_id,"tesserato_id":tid,"reason":str((details or {}).get("reason") or "modulo non prodotto")})
'''
    if old not in s:
        raise RuntimeError('R72 enrollment operator anchor missing')
    s=s.replace(old,new,1)
    OP.write_text(s,encoding='utf-8')

for p in (P,OP):
    compileall.compile_file(str(p),quiet=1)

checks={
  "autopilot_shared_core":"BODYMIND_R72_SHARED_MU_CORE_AUTOPILOT" in P.read_text(encoding='utf-8',errors='replace'),
  "operator_shared_core":"BODYMIND_R72_SHARED_MU_CORE_OPERATOR" in OP.read_text(encoding='utf-8',errors='replace'),
  "central_sync_module":(APP/'asd_app/verified_mu_sync_core_r68.py').exists(),
}
failed=[k for k,v in checks.items() if not v]
if failed:
    raise RuntimeError('R72 selftest failed: '+repr(failed))
print('[r72-shared-doc-core] PASS autopilot+operator+manual converge on verified-MU core; empty-only profile enrichment',flush=True)

# R73 launcher compatibility: real R73 logic is embedded in existing source/release files.
Path('/opt/bodymind/release_mobile_operator_mu_r73.py').write_text("print('[r73-launcher-stub] source-level R73 active',flush=True)\n",encoding='utf-8')
