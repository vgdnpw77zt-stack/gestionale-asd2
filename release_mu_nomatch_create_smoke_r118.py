# -*- coding: utf-8 -*-
from __future__ import annotations
import json, os, sqlite3, subprocess, sys, tempfile
from pathlib import Path

DB=Path('/data/tenants/default/asd.db')
from asd_app.enrollment_ingest_core_r65 import create_athlete_from_analysis
from asd_app.verified_mu_sync_core_r68 import sync_analysis_to_existing_athlete

checks={}
fresh_code=r'''
import json,sys
sys.path.insert(0,"/data/top2_app")
import app as _full_app
from asd_app.core import app
rules=[(str(r.rule),str(r.endpoint),set(r.methods)) for r in app.url_map.iter_rules()]
out={"queue_create_route":False,"operator_upload_wrapped":False,"operator_chat_wrapped":False}
out["queue_create_route"]=any(rule=="/documenti-automatici/<int:inbound_id>/crea-tesserato" and "POST" in methods for rule,ep,methods in rules)
for rule,ep,methods in rules:
    if rule=="/operatore-bodymind/upload" and "POST" in methods:
        out["operator_upload_wrapped"]=bool(getattr(app.view_functions.get(ep),"_bodymind_r119_wrapped",False))
    if rule=="/operatore-bodymind/chat" and "POST" in methods:
        out["operator_chat_wrapped"]=bool(getattr(app.view_functions.get(ep),"_bodymind_r119_wrapped",False))
print(json.dumps(out))
'''
fp=subprocess.run([sys.executable,"-c",fresh_code],cwd="/data/top2_app",capture_output=True,text=True,timeout=45)
if fp.returncode!=0:
    raise RuntimeError("R118 fresh app route check failed: "+(fp.stderr or fp.stdout)[-1600:])
fresh=json.loads((fp.stdout or "").strip().splitlines()[-1])
checks.update(fresh)

fd,tmp=tempfile.mkstemp(prefix='bodymind_r118_',suffix='.db'); os.close(fd)
src=sqlite3.connect(str(DB),timeout=30); dst=sqlite3.connect(tmp)
try: src.backup(dst)
finally: dst.close(); src.close()

c=sqlite3.connect(tmp,timeout=30); c.row_factory=sqlite3.Row
try:
    analysis={
      'document_type':'modulo_unico_tesseramento','person_name':'R118QA Minore',
      'first_name':'R118QA','last_name':'Minore','birth_date':'01/01/2012',
      'birth_place':'Roma','address':'Via Test QA 1','city':'Aprilia','postal_code':'04011','province':'LT',
      'phone':'0000000000','email':'r118@example.invalid','course_requested':'Cerchio Base',
      'guardian_name':'Genitore QA','guardian_phone':'1111111111','guardian_email':'genitore-r118@example.invalid',
      'privacy_consent':'yes','image_consent':'yes','guardian_signature':'yes','athlete_signature':'yes',
      'confidence':0.99
    }
    before=int(c.execute('SELECT COUNT(*) FROM tesserati').fetchone()[0])
    first=create_athlete_from_analysis(c,analysis,source='r118_fixture',require_valid_cf=False); c.commit()
    tid=int(first.get('tesserato_id') or 0)
    second=create_athlete_from_analysis(c,analysis,source='r118_fixture_replay',require_valid_cf=False); c.commit()
    after=int(c.execute('SELECT COUNT(*) FROM tesserati').fetchone()[0])
    sync=sync_analysis_to_existing_athlete(c,tid,analysis,source='r118_sync') if tid else {'ok':False}; c.commit()
    t=c.execute('SELECT * FROM tesserati WHERE id=?',(tid,)).fetchone() if tid else None
    m=c.execute('SELECT * FROM minori WHERE tesserato_id=? ORDER BY id LIMIT 1',(tid,)).fetchone() if tid else None
    tk=set(t.keys()) if t else set(); mk=set(m.keys()) if m else set()
    checks['temp_create']=bool(first.get('created') and tid>0 and after==before+1)
    checks['temp_idempotent']=bool(not second.get('created') and int(second.get('tesserato_id') or 0)==tid)
    checks['course_filled']=bool(t and 'corso' in tk and str(t['corso'] or '')=='Cerchio Base')
    checks['guardian_profile']=bool(t and 'genitore' in tk and str(t['genitore'] or '')=='Genitore QA')
    checks['minor_row']=bool(m and 'genitore' in mk and str(m['genitore'] or '')=='Genitore QA')
    checks['privacy_positive']=bool(t and 'consenso_informato' in tk and int(t['consenso_informato'] or 0)==1 and 'privacy_ok' in tk and int(t['privacy_ok'] or 0)==1)
    checks['image_positive']=bool(t and 'liberatoria_immagini' in tk and int(t['liberatoria_immagini'] or 0)==1)
    checks['signature_positive']=bool(t and 'iscrizione_firmata' in tk and int(t['iscrizione_firmata'] or 0)==1)
    checks['shared_mu_sync']=bool(sync.get('ok'))
    integrity=str(c.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(c.execute('PRAGMA foreign_key_check').fetchall())
finally:
    c.close()
    try: os.unlink(tmp)
    except Exception: pass

checks['db_ok']=integrity.lower()=='ok' and fk==0
checks['ok']=all(checks.values())
print('[r118-mu-confirm-create-smoke] '+json.dumps({'checks':checks,'integrity':integrity,'fk':fk},ensure_ascii=False),flush=True)
if not checks['ok']:
    raise RuntimeError('R118 generic MU confirmation regression failed '+json.dumps(checks,ensure_ascii=False))
print('[r118-selftest] PASS persistent queue/operator create flow temp-create-idempotent full-profile guardian-course-explicit-consents db-ok',flush=True)
