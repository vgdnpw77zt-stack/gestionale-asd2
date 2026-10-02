# -*- coding: utf-8 -*-
from __future__ import annotations
import json, sqlite3, sys
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')
sys.path.insert(0,str(APP))
from asd_app.verified_mu_sync_core_r68 import sync_verified_mu_inbound

conn=sqlite3.connect(str(DB),timeout=45); conn.row_factory=sqlite3.Row
results=[]
try:
    rows=conn.execute(
      """SELECT i.* FROM inbound_documents i
         JOIN tesserati t ON t.id=i.tesserato_id
         WHERE coalesce(i.tesserato_id,0)>0
           AND lower(coalesce(i.document_type,'')) IN
               ('modulo_unico_tesseramento','iscrizione','domanda_iscrizione','manleva',
                'liberatoria_immagini','consenso_minore','autorizzazione_genitore',
                'privacy','privacy_consenso','safeguarding','tutela_minore')
           AND lower(coalesce(i.status,'')) IN ('associato','accepted','manual_accepted','verificato')
           AND coalesce(i.document_confidence,0)>=95
         ORDER BY i.id DESC"""
    ).fetchall()
    seen=set()
    for row in rows:
        tid=int(row['tesserato_id'] or 0)
        if tid in seen: continue
        seen.add(tid)
        # First try cached path; only invoke vision when this trusted MU genuinely lacks cache.
        r=sync_verified_mu_inbound(conn,row,allow_live=False)
        if not r.get('ok') and r.get('reason')=='analysis_missing':
            r=sync_verified_mu_inbound(conn,row,allow_live=True)
        results.append({'id':int(row['id']),'tid':tid,'result':r})
    conn.commit()
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
    unresolved=[x for x in results if not x['result'].get('ok')]
finally:
    conn.close()

print('[r70-mu-complete] '+json.dumps({
  'total_existing_trusted_mu':len(results),
  'synced':sum(1 for x in results if x['result'].get('ok')),
  'unresolved':unresolved,
  'integrity':integrity,'foreign_keys':fk
},ensure_ascii=False),flush=True)
if integrity.lower()!='ok' or fk:
    raise RuntimeError('R70 DB integrity failed')
print('[operator-r70] PASS missing-cache trusted-MU visual-analysis existing-athletes-only db-ok',flush=True)
