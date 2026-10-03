# -*- coding: utf-8 -*-
from __future__ import annotations
import importlib, importlib.util, py_compile, shutil, sqlite3, sys
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
SRC=Path('/opt/bodymind/routes_mu_nomatch_r119.py')
DST=APP/'asd_app/routes_mu_nomatch_r119.py'
EMAIL=APP/'asd_app/routes_email_documents.py'
APP_PY=APP/'app.py'
BACK=Path('/data/release_backups/20261003_r119_mu_nomatch')
BACK.mkdir(parents=True,exist_ok=True)

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')
if not SRC.exists():
    raise RuntimeError('R119 persistent route source missing')

# Persistent route module for the actual Gunicorn import.
DST.write_text(SRC.read_text(encoding='utf-8'),encoding='utf-8')
py_compile.compile(str(DST),doraise=True)

# Persist semantic analysis when a recognized MU has no athlete match.
s=EMAIL.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R119_PERSIST_UNRESOLVED_MU' not in s:
    b=BACK/'routes_email_documents.py'
    if not b.exists(): shutil.copy2(EMAIL,b)
    old='''            if tid<=0:
                res["semantic_analysis"]=analysis
                if str(analysis.get("document_type") or "")=="modulo_unico_tesseramento":
                    res["new_athlete_candidate"]=True
                return res
'''
    new='''            if tid<=0:
                # BODYMIND_R119_PERSIST_UNRESOLVED_MU
                iid=int(res.get("inbound_id") or 0)
                if iid>0:
                    try:
                        _r65_cache_put(conn,"inbound_documents",iid,analysis)
                    except Exception:
                        pass
                    if str((analysis or {}).get("document_type") or "")=="modulo_unico_tesseramento":
                        try:
                            icols={str(r[1]) for r in conn.execute("PRAGMA table_info(inbound_documents)").fetchall()}
                            sets=[]; vals=[]
                            if "document_type" in icols: sets.append("document_type=?"); vals.append("modulo_unico_tesseramento")
                            if "document_label" in icols: sets.append("document_label=?"); vals.append("Modulo iscrizione / Modulo Unico")
                            if "document_confidence" in icols:
                                sets.append("document_confidence=?"); vals.append(int(round(float((analysis or {}).get("confidence") or 0)*100)))
                            if "match_action" in icols: sets.append("match_action=?"); vals.append("create_candidate")
                            if "status" in icols: sets.append("status=?"); vals.append("needs_manual_match")
                            if sets:
                                vals.append(iid)
                                conn.execute("UPDATE inbound_documents SET "+",".join(sets)+" WHERE id=?",tuple(vals))
                            conn.commit()
                        except Exception:
                            pass
                res["semantic_analysis"]=analysis
                if str((analysis or {}).get("document_type") or "")=="modulo_unico_tesseramento":
                    res["new_athlete_candidate"]=True
                return res
'''
    if old not in s:
        raise RuntimeError('R119 unresolved MU persistence anchor missing')
    s=s.replace(old,new,1)
    tmp=EMAIL.with_name(EMAIL.name+'.r119.tmp')
    tmp.write_text(s,encoding='utf-8'); py_compile.compile(str(tmp),doraise=True); tmp.replace(EMAIL)
print('[r119-source] PASS unresolved MU semantic persistence')

# Ensure actual app import loads the persistent module after all normal routes.
ap=APP_PY.read_text(encoding='utf-8',errors='replace')
marker='# BODYMIND_R119_MU_NOMATCH_IMPORT'
line='\n'+marker+'\nimport asd_app.routes_mu_nomatch_r119\n'
if marker not in ap:
    b=BACK/'app.py'
    if not b.exists(): shutil.copy2(APP_PY,b)
    ap=ap.rstrip()+line
    APP_PY.write_text(ap,encoding='utf-8')
    py_compile.compile(str(APP_PY),doraise=True)

# Register it also in the pre-Gunicorn QA process.
# asd_app is already imported at this point, so load the freshly-created module
# directly from its file path rather than relying on package cache discovery.
sys.path.insert(0,str(APP))
importlib.invalidate_caches()
_mod_name='asd_app.routes_mu_nomatch_r119'
if _mod_name in sys.modules:
    mod=sys.modules[_mod_name]
else:
    spec=importlib.util.spec_from_file_location(_mod_name,str(DST))
    if spec is None or spec.loader is None:
        raise RuntimeError('R119 cannot create module spec for '+str(DST))
    mod=importlib.util.module_from_spec(spec)
    sys.modules[_mod_name]=mod
    spec.loader.exec_module(mod)

from asd_app.core import app
rules=[(str(r.rule),str(r.endpoint),set(r.methods)) for r in app.url_map.iter_rules()]
create_route=any(rule=='/documenti-automatici/<int:inbound_id>/crea-tesserato' and 'POST' in methods for rule,ep,methods in rules)
upload_wrapped=False;chat_wrapped=False
for rule,ep,methods in rules:
    if rule=='/operatore-bodymind/upload' and 'POST' in methods:
        upload_wrapped=bool(getattr(app.view_functions.get(ep),'_bodymind_r119_wrapped',False))
    if rule=='/operatore-bodymind/chat' and 'POST' in methods:
        chat_wrapped=bool(getattr(app.view_functions.get(ep),'_bodymind_r119_wrapped',False))

conn=sqlite3.connect(str(DB),timeout=30)
try:
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally: conn.close()
checks={'create_route':create_route,'upload_wrapped':upload_wrapped,'chat_wrapped':chat_wrapped,
        'app_import':marker in APP_PY.read_text(encoding='utf-8',errors='replace'),
        'db_ok':integrity.lower()=='ok' and fk==0}
print('[r119-persistent-registration] '+repr(checks)+' integrity='+integrity+' fk='+str(fk),flush=True)
if not all(checks.values()):
    raise RuntimeError('R119 persistent registration failed '+repr(checks))
print('[r119-selftest] PASS persistent-Gunicorn-import queue-create operator-pending-yes-no db-ok',flush=True)
