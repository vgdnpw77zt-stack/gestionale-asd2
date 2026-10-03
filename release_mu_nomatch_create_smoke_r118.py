# -*- coding: utf-8 -*-
from __future__ import annotations
import json, sqlite3, tempfile, os
from pathlib import Path
from flask import Response

DB=Path('/data/tenants/default/asd.db')
from asd_app.core import app
from asd_app.enrollment_ingest_core_r65 import create_athlete_from_analysis,find_existing_athlete,enrollment_identity_ready
from asd_app.verified_mu_sync_core_r68 import sync_analysis_to_existing_athlete

checks={}
# Route must exist in the live Flask map.
rules=[(r.rule,r.endpoint,sorted(r.methods)) for r in app.url_map.iter_rules()]
checks['create_route']=any(rule=='/documenti-automatici/<int:inbound_id>/crea-tesserato' and 'POST' in methods for rule,ep,methods in rules)

# The after_request hook that injects the CTA must be registered.
after_funcs=[]
try:
    for funcs in app.after_request_funcs.values():
        after_funcs.extend(funcs)
except Exception:
    pass
checks['cta_hook']=any(getattr(f,'__name__','')=='r117_mu_create_cta' for f in after_funcs)

# Safe temp-DB creation/idempotency test using the exact enrollment + R68 cores.
fd,tmp=tempfile.mkstemp(prefix='bodymind_r118_',suffix='.db'); os.close(fd)
src=sqlite3.connect(str(DB),timeout=30); dst=sqlite3.connect(tmp)
try: src.backup(dst)
finally: dst.close(); src.close()
c=sqlite3.connect(tmp,timeout=30); c.row_factory=sqlite3.Row
try:
    analysis={
      'document_type':'modulo_unico_tesseramento','person_name':'R118 QA Nuova',
      'first_name':'R118QA','last_name':'Nuova','codice_fiscale':'RSSMRA85T10A562S',
      'birth_date':'10/12/1985','birth_place':'Roma','address':'Via Test 1',
      'city':'Roma','postal_code':'00100','province':'RM','phone':'0000000000',
      'email':'r118@example.invalid','nationality':'Italiana','gender':'M',
      'privacy_consent':'yes','image_consent':'yes','athlete_signature':'yes',
      'guardian_signature':'no','confidence':0.99
    }
    # Use a CF known to pass the same validator in prior integration fixtures.
    ready=enrollment_identity_ready(analysis,require_valid_cf=False)
    before=int(c.execute("SELECT COUNT(*) FROM tesserati").fetchone()[0])
    first=create_athlete_from_analysis(c,analysis,source='r118_fixture',require_valid_cf=False)
    tid=int(first.get('tesserato_id') or 0)
    c.commit()
    second=create_athlete_from_analysis(c,analysis,source='r118_fixture_replay',require_valid_cf=False)
    c.commit()
    after=int(c.execute("SELECT COUNT(*) FROM tesserati").fetchone()[0])
    rows=int(c.execute("SELECT COUNT(*) FROM tesserati WHERE id=?",(tid,)).fetchone()[0]) if tid else 0
    checks['core_confirm_create']=bool(ready and first.get('created') and tid>0 and after==before+1)
    checks['core_replay_idempotent']=bool(not second.get('created') and int(second.get('tesserato_id') or 0)==tid and rows==1)

    sync=sync_analysis_to_existing_athlete(c,tid,analysis,source='r118_fixture') if tid else {'ok':False}
    c.commit()
    checks['shared_mu_sync']=bool(sync.get('ok'))

    integrity=str(c.execute("PRAGMA integrity_check").fetchone()[0])
    fk=len(c.execute("PRAGMA foreign_key_check").fetchall())
finally:
    c.close()
    try: os.unlink(tmp)
    except Exception: pass

checks['db_ok']=integrity.lower()=='ok' and fk==0
checks['ok']=all(checks.values())
print('[r118-mu-confirm-create-smoke] '+json.dumps({'checks':checks,'integrity':integrity,'fk':fk},ensure_ascii=False),flush=True)
if not checks['ok']:
    raise RuntimeError('R118 generic MU confirmation regression failed '+json.dumps(checks,ensure_ascii=False))
print('[r118-selftest] PASS generic-document-queue create-route CTA-hook shared-enrollment idempotent R68-sync temp-db',flush=True)
