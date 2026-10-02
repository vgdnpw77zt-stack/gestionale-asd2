# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import compileall, sqlite3

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MARKER=APP/'.BODYMIND_DOCUMENT_COHERENCE_R42'

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

target=APP/'asd_app/routes_document_coherence_r41.py'
if not target.exists():
    raise RuntimeError('R42 coherence module missing')

s=target.read_text(encoding='utf-8')
if 'BODYMIND_R73_GLOBAL_MU_PRESENCE' not in s and 'BODYMIND_R42_INBOUND_PRIORITY' not in s:
    old=r'''def _mu_state(tid):
    if tid<=0:
        return None
    conn=db()
    try:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documenti'").fetchone():
            return None
        rows=conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1 ORDER BY id DESC",(tid,)).fetchall()
        found=[]
        for r in rows:
            hay=' '.join(str(r[k] or '').strip().lower() for k in ('doc_type','categoria','titolo','original_filename','filename') if k in r.keys())
            if any(x in hay for x in _MU_ALIASES):
                found.append(r)
        if not found:
            return None
        statuses=[str(r['status'] or '').strip().lower() if 'status' in r.keys() else '' for r in found]
        if any(x in _TRUSTED for x in statuses):
            return 'verified'
        return 'pending'
    finally:
        conn.close()
'''
    new=r'''# BODYMIND_R42_INBOUND_PRIORITY
def _mu_state(tid):
    if tid<=0:
        return None
    conn=db()
    try:
        present=False
        # Autopilot/inbound is the trust boundary while a human confirmation is pending.
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inbound_documents'").fetchone():
            rows=conn.execute("""SELECT * FROM inbound_documents
                WHERE coalesce(tesserato_id,matched_tesserato_id,suggested_tesserato_id,0)=?
                  AND coalesce(deleted_at,'')=''
                ORDER BY id DESC""",(tid,)).fetchall()
            for r in rows:
                hay=' '.join(str(r[k] or '').strip().lower() for k in ('document_type','document_label','original_filename','saved_path') if k in r.keys())
                if not any(x in hay for x in _MU_ALIASES):
                    continue
                present=True
                status=str(r['status'] or '').strip().lower() if 'status' in r.keys() else ''
                if status in _PENDING:
                    return 'pending'
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documenti'").fetchone():
            rows=conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1 ORDER BY id DESC",(tid,)).fetchall()
            statuses=[]
            for r in rows:
                hay=' '.join(str(r[k] or '').strip().lower() for k in ('doc_type','categoria','titolo','original_filename','filename') if k in r.keys())
                if any(x in hay for x in _MU_ALIASES):
                    present=True
                    statuses.append(str(r['status'] or '').strip().lower() if 'status' in r.keys() else '')
            if any(x in _PENDING for x in statuses):
                return 'pending'
            if any(x in _TRUSTED for x in statuses):
                return 'verified'
        return 'pending' if present else None
    finally:
        conn.close()
'''
    if old not in s:
        raise RuntimeError('R42 old _mu_state anchor missing')
    s=s.replace(old,new,1)
    target.write_text(s,encoding='utf-8')

if not compileall.compile_file(str(target),quiet=1):
    raise RuntimeError('R42 coherence module compile failed')

conn=sqlite3.connect(str(DB),timeout=20); conn.row_factory=sqlite3.Row
try:
    pending=[]
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inbound_documents'").fetchone():
        rows=conn.execute("""SELECT i.*,t.nome,t.cognome
            FROM inbound_documents i
            LEFT JOIN tesserati t ON t.id=coalesce(i.tesserato_id,i.matched_tesserato_id,i.suggested_tesserato_id)
            WHERE lower(coalesce(i.status,'')) IN ('needs_manual_match','associato_tipo_da_verificare','richiede_conferma','needs_review','da_verificare','pending')
              AND coalesce(i.deleted_at,'')=''
            ORDER BY i.id DESC""").fetchall()
        aliases=('modulo_unico_tesseramento','modulo unico','modulo_unico','mu-2026','mu 2026','modulo iscrizione','domanda iscrizione','iscrizione manleva')
        for r in rows:
            hay=' '.join(str(r[k] or '').strip().lower() for k in ('document_type','document_label','original_filename','saved_path') if k in r.keys())
            if any(x in hay for x in aliases):
                pending.append((int(r['id']),int((r['tesserato_id'] if 'tesserato_id' in r.keys() else 0) or 0),((str(r['nome'] or '')+' '+str(r['cognome'] or '')).strip()),str(r['status'] or '')))
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:
    conn.close()

text=target.read_text(encoding='utf-8',errors='replace')
r73='BODYMIND_R73_GLOBAL_MU_PRESENCE' in text
checks={
    'inbound-priority':r73 or 'BODYMIND_R42_INBOUND_PRIORITY' in text,
    'pending-wins':(("if states:" in text and "return 'pending'" in text) if r73 else ("if status in _PENDING:" in text and "return 'pending'" in text)),
    'document-fallback':(("if 'verified' in states:" in text and "return 'verified'" in text) if r73 else "if any(x in _TRUSTED for x in statuses):" in text),
    'db-integrity':integrity.lower()=='ok' and fk==0,
}
failed=[k for k,v in checks.items() if not v]
print('[document-coherence-r42] checks='+repr(checks),flush=True)
print('[document-coherence-r42] pending_inbound_mu='+repr(pending[:20]),flush=True)
if failed:
    raise RuntimeError('R42 coherence failed '+repr(failed))
MARKER.write_text('BodyMind document coherence R42 inbound-priority applied\n',encoding='utf-8')
print('[document-coherence-r42-selftest] PASS inbound-presence-priority R73-compatible db-ok',flush=True)
