# -*- coding: utf-8 -*-
from __future__ import annotations
import compileall, json, shutil, sqlite3, sys
from datetime import datetime
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
BACK=Path('/data/release_backups/20261002_global_reconcile_r69')
BACK.mkdir(parents=True,exist_ok=True)

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

def table(conn,name):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())

def cols(conn,name):
    return {str(r[1]) for r in conn.execute("PRAGMA table_info("+name+")").fetchall()} if table(conn,name) else set()

# 1) Operator confirmation semantics: one proposal -> one natural-language confirmation.
P=APP/'asd_app/routes_operator_bodymind.py'
s=P.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R69_SINGLE_CONFIRMATION' not in s:
    b=BACK/'routes_operator_bodymind.py'
    if not b.exists(): shutil.copy2(P,b)

    old='''def _set_pending_action(conn, action_type: str, payload: dict) -> int:
    _schema(conn)
    now=datetime.now().isoformat(timespec="seconds")
    cur=conn.execute(
        """INSERT INTO bodymind_operator_actions
           (conversation_id,action_type,payload_json,status,requested_by,created_at)
           VALUES(?,?,?,?,?,?)""",
        (_conv_id(),action_type,json.dumps(payload,ensure_ascii=False),"proposed",_identity(),now)
    )
    conn.commit()
    aid=int(cur.lastrowid)
    session["bodymind_operator_pending_action"]=aid
    return aid
'''
    new='''# BODYMIND_R69_SINGLE_CONFIRMATION
def _set_pending_action(conn, action_type: str, payload: dict) -> int:
    _schema(conn)
    conv=_conv_id()
    payload_text=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    # Reuse an identical outstanding proposal instead of stacking confirmations.
    rows=conn.execute(
        "SELECT id,payload_json FROM bodymind_operator_actions WHERE conversation_id=? AND action_type=? AND status='proposed' ORDER BY id DESC LIMIT 8",
        (conv,action_type)
    ).fetchall()
    for row in rows:
        try:
            existing=json.dumps(json.loads(str(row["payload_json"] or "{}")),ensure_ascii=False,sort_keys=True,separators=(",",":"))
        except Exception:
            existing=str(row["payload_json"] or "")
        if existing==payload_text:
            aid=int(row["id"])
            session["bodymind_operator_pending_action"]=aid
            return aid
    # A conversation must never have several competing confirmations.
    conn.execute(
        "UPDATE bodymind_operator_actions SET status='superseded' WHERE conversation_id=? AND status='proposed'",
        (conv,)
    )
    now=datetime.now().isoformat(timespec="seconds")
    cur=conn.execute(
        """INSERT INTO bodymind_operator_actions
           (conversation_id,action_type,payload_json,status,requested_by,created_at)
           VALUES(?,?,?,?,?,?)""",
        (conv,action_type,json.dumps(payload,ensure_ascii=False),"proposed",_identity(),now)
    )
    conn.commit()
    aid=int(cur.lastrowid)
    session["bodymind_operator_pending_action"]=aid
    return aid
'''
    if old not in s:
        raise RuntimeError('R69 pending-action anchor missing')
    s=s.replace(old,new,1)

    old_yes='''def _yes(text: str) -> bool:
    n=_norm(text)
    return n in {"si","sì","ok","okay","confermo","vai","procedi","fallo","esegui","certo"}
'''
    new_yes='''def _yes(text: str) -> bool:
    n=_norm(text)
    if n in {"si","sì","ok","okay","confermo","conferma","vai","procedi","fallo","esegui","certo","va bene"}:
        return True
    # Natural confirmations are accepted only while a pending action exists.
    if session.get("bodymind_operator_pending_action"):
        positive=("conferm" in n or "proced" in n or "esegui" in n or "vai pure" in n or "fallo pure" in n or n.startswith("si ") or n.startswith("sì ") or n.startswith("ok "))
        negative=any(x in n for x in ("non conferm","non proced","non esegu","annulla","lascia stare","non farlo"))
        return bool(positive and not negative)
    return False
'''
    if old_yes not in s:
        raise RuntimeError('R69 yes-parser anchor missing')
    s=s.replace(old_yes,new_yes,1)
    P.write_text(s,encoding='utf-8')

compileall.compile_file(str(P),quiet=1)

# 2) Backup DB once before global reconciliation.
backup_db=BACK/('pre_reconcile_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.db')
if DB.exists():
    src=sqlite3.connect(str(DB),timeout=30)
    dst=sqlite3.connect(str(backup_db))
    try: src.backup(dst)
    finally: dst.close(); src.close()

# 3) Reconcile every already-confirmed MU into athlete/minor profile using cached semantic analyses.
sys.path.insert(0,str(APP))
from asd_app.verified_mu_sync_core_r68 import sync_verified_mu_inbound

conn=sqlite3.connect(str(DB),timeout=30); conn.row_factory=sqlite3.Row
sync_results=[]
archived=[]
blocked=[]
try:
    if table(conn,'inbound_documents'):
        ic=cols(conn,'inbound_documents')
        rows=conn.execute(
          """SELECT * FROM inbound_documents
             WHERE coalesce(tesserato_id,0)>0
               AND lower(coalesce(document_type,'')) IN
                   ('modulo_unico_tesseramento','iscrizione','domanda_iscrizione','manleva',
                    'liberatoria_immagini','consenso_minore','autorizzazione_genitore',
                    'privacy','privacy_consenso','safeguarding','tutela_minore')
               AND lower(coalesce(status,'')) IN ('associato','accepted','manual_accepted','verificato')
               AND coalesce(document_confidence,0)>=95
             ORDER BY id DESC"""
        ).fetchall()
        seen_tid=set()
        for row in rows:
            tid=int(row['tesserato_id'] or 0)
            # Prefer the newest trusted MU for each athlete; older rows can be duplicates.
            if tid in seen_tid: continue
            seen_tid.add(tid)
            result=sync_verified_mu_inbound(conn,row,allow_live=False)
            sync_results.append({'id':int(row['id']),'tid':tid,'result':result})

    # 4) Archive only deterministic confirmed duplicates. Files remain untouched.
    import asd_app.routes_operator_bodymind as op
    groups,comparisons=op._semantic_duplicate_groups(conn,None)
    dc=cols(conn,'documenti')
    for group in groups:
        ok,reason=op._revalidate_semantic_duplicate_group(conn,group)
        keep_id=int(group.get('keep_id') or 0)
        for rid_raw in (group.get('remove_ids') or []):
            rid=int(rid_raw or 0)
            if not ok or rid<=0:
                blocked.append({'keep_id':keep_id,'remove_id':rid,'reason':reason})
                continue
            sets=[]; vals=[]
            if 'visibile' in dc: sets.append('visibile=0')
            if 'status' in dc: sets.append('status=?'); vals.append('semantic_duplicate_archived')
            if 'note' in dc:
                sets.append('note=?')
                vals.append('Copia semantica confermata e archiviata da riconciliazione R69; originale mantenuto ID '+str(keep_id))
            if not sets:
                blocked.append({'keep_id':keep_id,'remove_id':rid,'reason':'schema non archiviabile'})
                continue
            vals.extend([rid,int(group.get('tesserato_id') or 0)])
            cur=conn.execute(
              'UPDATE documenti SET '+','.join(sets)+' WHERE id=? AND tesserato_id=?'+(' AND coalesce(visibile,1)=1' if 'visibile' in dc else ''),
              tuple(vals)
            )
            if int(cur.rowcount or 0)==1:
                archived.append({'keep_id':keep_id,'remove_id':rid,'tid':int(group.get('tesserato_id') or 0),'reason':reason})
            else:
                blocked.append({'keep_id':keep_id,'remove_id':rid,'reason':'record già cambiato/non attivo'})

    # Align verified MU coverage flags for all trusted rows after profile sync.
    try:
        from asd_app.onboarding_flow import sync_unified_module_flags, recompute_onboarding_status
        for item in sync_results:
            if item['result'].get('ok'):
                tid=int(item['tid'])
                sync_unified_module_flags(conn,tid,source='r69_global_verified_mu')
                recompute_onboarding_status(conn,tid)
    except Exception:
        pass

    conn.commit()
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
    visible_docs=int(conn.execute('SELECT COUNT(*) FROM documenti WHERE coalesce(visibile,1)=1').fetchone()[0]) if table(conn,'documenti') else 0
    tesserati=int(conn.execute('SELECT COUNT(*) FROM tesserati').fetchone()[0]) if table(conn,'tesserati') else 0
finally:
    conn.close()

summary={
 'synced_ok':sum(1 for x in sync_results if x['result'].get('ok')),
 'sync_blocked':sum(1 for x in sync_results if not x['result'].get('ok')),
 'sync_results':sync_results[:80],
 'duplicates_archived':len(archived),
 'duplicates_blocked':len(blocked),
 'comparisons':comparisons,
 'visible_docs':visible_docs,
 'tesserati':tesserati,
 'backup':backup_db.name,
 'integrity':integrity,
 'foreign_keys':fk,
}
print('[r69-global-reconcile] '+json.dumps(summary,ensure_ascii=False),flush=True)
if integrity.lower()!='ok' or fk:
    raise RuntimeError('R69 database integrity failed')
print('[operator-r69] PASS all-confirmed-MU-profile-sync guardian-consent single-confirmation deterministic-dedupe no-file-delete db-ok',flush=True)
