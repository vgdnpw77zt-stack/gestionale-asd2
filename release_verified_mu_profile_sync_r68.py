# -*- coding: utf-8 -*-
from __future__ import annotations
import compileall, json, shutil, sqlite3, sys
from datetime import datetime
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
BACK=Path('/data/release_backups/20261002_mu_profile_sync_r68')
SRC=Path('/opt/bodymind/verified_mu_sync_core_r68.py')
DST=APP/'asd_app/verified_mu_sync_core_r68.py'

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')
if not SRC.exists():
    raise RuntimeError('R68 MU helper source missing')

BACK.mkdir(parents=True,exist_ok=True)
DST.write_text(SRC.read_text(encoding='utf-8'),encoding='utf-8')

# Queue confirmation: after final human OK, copy verified MU fields into the existing athlete/minor profile.
P=APP/'asd_app/routes_a202_operational_integrity.py'
s=P.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R68_MU_PROFILE_SYNC_QUEUE' not in s:
    b=BACK/'routes_a202_operational_integrity.py'
    if not b.exists(): shutil.copy2(P,b)
    old='''        _r11_sync_documento(conn,row)
        _r13_accept_unified(conn,row)
        conn.commit()
'''
    new='''        _r11_sync_documento(conn,row)
        _r13_accept_unified(conn,row)
        # BODYMIND_R68_MU_PROFILE_SYNC_QUEUE
        try:
            from .verified_mu_sync_core_r68 import sync_verified_mu_inbound
            _r68_sync=sync_verified_mu_inbound(conn,row,allow_live=True)
            try:
                app.logger.info("R68 MU queue sync doc=%s result=%s",doc_id,_r68_sync)
            except Exception:
                pass
        except Exception as _r68_exc:
            try:
                app.logger.exception("R68 MU queue sync failed doc=%s",doc_id)
            except Exception:
                pass
        conn.commit()
'''
    if old not in s:
        raise RuntimeError('R68 queue OK anchor missing')
    s=s.replace(old,new,1)
    P.write_text(s,encoding='utf-8')

# Dossier confirmation: same behavior regardless of where the human confirms the document.
P2=APP/'asd_app/routes_documenti.py'
s=P2.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R68_MU_PROFILE_SYNC_DOSSIER' not in s:
    b=BACK/'routes_documenti.py'
    if not b.exists(): shutil.copy2(P2,b)
    old="""            sync_unified_module_flags(conn,tesserato_id,source='dossier_ok')
"""
    new="""            sync_unified_module_flags(conn,tesserato_id,source='dossier_ok')
            # BODYMIND_R68_MU_PROFILE_SYNC_DOSSIER
            try:
                from .verified_mu_sync_core_r68 import sync_verified_mu_document
                _r68_sync=sync_verified_mu_document(conn,row,tesserato_id,allow_live=True)
                try:
                    app.logger.info("R68 MU dossier sync doc=%s tid=%s result=%s",doc_id,tesserato_id,_r68_sync)
                except Exception:
                    pass
            except Exception:
                try:
                    app.logger.exception("R68 MU dossier sync failed doc=%s",doc_id)
                except Exception:
                    pass
"""
    if old not in s:
        raise RuntimeError('R68 dossier MU anchor missing')
    s=s.replace(old,new,1)
    P2.write_text(s,encoding='utf-8')

# UI coherence: recognize both "non generato" and "non ancora generato".
PC=APP/'asd_app/routes_document_coherence_r41.py'
cs=PC.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R68_NOT_YET_GENERATED_TEXT' not in cs:
    b=BACK/'routes_document_coherence_r41.py'
    if not b.exists(): shutil.copy2(PC,b)
    cs=cs.replace(
        "r'(?i)(Modulo\\s+Unico(?:\\s+MU[- ]?2026(?:\\.1)?)?\\s*(?:[:·\\-]\\s*)?)(non\\s+generat[oa])'",
        "r'(?i)(Modulo\\s+Unico(?:\\s+MU[- ]?2026(?:\\.1)?)?\\s*(?:[:·\\-]\\s*)?)(non\\s+(?:ancora\\s+)?generat[oa])'"
    )
    cs=cs.replace(
        "r'(?i)>\\s*non\\s+generat[oa]\\s*<'",
        "r'(?i)>\\s*non\\s+(?:ancora\\s+)?generat[oa](?:\\s+per\\s+questo\\s+tesserato\\.?)?\\s*<'"
    )
    cs=cs.replace("# BODYMIND_R41_DOCUMENT_STATE_COHERENCE","# BODYMIND_R41_DOCUMENT_STATE_COHERENCE\n# BODYMIND_R68_NOT_YET_GENERATED_TEXT",1)
    PC.write_text(cs,encoding='utf-8')

for p in (DST,P,P2,PC):
    compileall.compile_file(str(p),quiet=1)

# Safe cached backfill for already human-confirmed MUs (including the current Annunziato case).
# No live AI at startup. Existing non-empty profile fields are never overwritten.
backfill=[]
if DB.exists():
    backup_db=BACK/('pre_backfill_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.db')
    src=sqlite3.connect(str(DB),timeout=20)
    dst=sqlite3.connect(str(backup_db))
    try: src.backup(dst)
    finally: dst.close(); src.close()

    sys.path.insert(0,str(APP))
    from asd_app.verified_mu_sync_core_r68 import sync_verified_mu_inbound
    conn=sqlite3.connect(str(DB),timeout=30); conn.row_factory=sqlite3.Row
    try:
        rows=conn.execute(
          """SELECT * FROM inbound_documents
             WHERE coalesce(tesserato_id,0)>0
               AND lower(coalesce(document_type,'')) IN
                   ('modulo_unico_tesseramento','iscrizione','domanda_iscrizione','manleva',
                    'liberatoria_immagini','consenso_minore','autorizzazione_genitore',
                    'privacy','privacy_consenso','safeguarding','tutela_minore')
               AND lower(coalesce(status,'')) IN ('associato','accepted','manual_accepted','verificato')
               AND coalesce(document_confidence,0)>=95
             ORDER BY id DESC LIMIT 120"""
        ).fetchall()
        for row in rows:
            result=sync_verified_mu_inbound(conn,row,allow_live=False)
            if result.get('ok') or result.get('reason') not in ('no_cache','analysis_missing'):
                backfill.append({'id':int(row['id']),'tid':int(row['tesserato_id'] or 0),'result':result})
        conn.commit()
        integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
        fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
    finally:
        conn.close()
else:
    integrity='missing'; fk=-1

print('[r68-mu-backfill] '+json.dumps({'items':backfill[:40],'count':len(backfill),'integrity':integrity,'foreign_keys':fk},ensure_ascii=False),flush=True)
if integrity.lower()!='ok' or fk:
    raise RuntimeError('R68 database integrity failed')
print('[operator-r68] PASS queue+dossier verified-MU profile guardian sync empty-only cached-backfill UI-not-ancora-generato',flush=True)
