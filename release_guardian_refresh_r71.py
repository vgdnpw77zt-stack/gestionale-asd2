# -*- coding: utf-8 -*-
from __future__ import annotations
import json, sqlite3, sys
from datetime import datetime
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
BACK=Path('/data/release_backups/20261002_guardian_refresh_r71')
BACK.mkdir(parents=True,exist_ok=True)

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')
sys.path.insert(0,str(APP))

from asd_app.verified_mu_sync_core_r68 import sync_verified_mu_inbound

# Full SQLite backup before any profile enrichment.
backup=BACK/('pre_guardian_refresh_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.db')
src=sqlite3.connect(str(DB),timeout=30)
dst=sqlite3.connect(str(backup))
try:
    src.backup(dst)
finally:
    dst.close(); src.close()

conn=sqlite3.connect(str(DB),timeout=45)
conn.row_factory=sqlite3.Row
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
        if tid in seen:
            continue
        seen.add(tid)
        r=sync_verified_mu_inbound(conn,row,allow_live=True)
        results.append({'id':int(row['id']),'tid':tid,'result':r})
    conn.commit()
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())

    # Read-only post-check: trusted MU minors that still have no guardian after the visual refresh.
    unresolved=[]
    tcols={str(x[1]) for x in conn.execute("PRAGMA table_info(tesserati)").fetchall()}
    for item in results:
        tid=int(item['tid'])
        t=conn.execute("SELECT * FROM tesserati WHERE id=?",(tid,)).fetchone()
        if not t: continue
        keys=set(t.keys())
        is_minor=False
        try: is_minor=int(t['minorenne'] or 0)==1 if 'minorenne' in keys else False
        except Exception: pass
        if not is_minor: continue
        guardian=''
        for k in ('genitore','nome_genitore'):
            if k in keys and t[k]:
                guardian=str(t[k]).strip()
                if guardian: break
        if not guardian:
            unresolved.append({'tid':tid,'inbound_id':int(item['id']),'reason':str(item['result'].get('semantic_method') or '')})
finally:
    conn.close()

summary={
  'trusted_mu_checked':len(results),
  'visual_guardian_refreshes':sum(1 for x in results if str(x['result'].get('semantic_method') or '')=='live_guardian_refresh'),
  'fields_filled':[
    {'tid':x['tid'],'id':x['id'],'fields':x['result'].get('fields_filled',[]),'minor_fields':x['result'].get('minor_fields_filled',[]),
     'method':x['result'].get('semantic_method'),'ok':x['result'].get('ok')}
    for x in results if x['result'].get('fields_filled') or x['result'].get('minor_fields_filled') or str(x['result'].get('semantic_method') or '')=='live_guardian_refresh'
  ],
  'minor_guardian_still_missing':unresolved,
  'backup':backup.name,
  'integrity':integrity,
  'foreign_keys':fk,
}
print('[r71-guardian-refresh] '+json.dumps(summary,ensure_ascii=False),flush=True)
if integrity.lower()!='ok' or fk:
    raise RuntimeError('R71 database integrity failed')
print('[operator-r71] PASS stale-guardian-cache visual-refresh empty-only existing-athlete-only db-ok',flush=True)
