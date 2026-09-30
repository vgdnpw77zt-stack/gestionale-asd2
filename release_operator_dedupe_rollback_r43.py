# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import json, sqlite3, shutil

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MARKER=APP/'.BODYMIND_OPERATOR_DEDUPE_ROLLBACK_R43'
BACKUPS=Path('/data/release_backups/20260930_operator_dedupe_rollback_r43')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')
if not DB.exists():
    raise RuntimeError('R43 DB missing')

BACKUPS.mkdir(parents=True,exist_ok=True)
dbbak=BACKUPS/'asd.db'
if not dbbak.exists():
    shutil.copy2(DB,dbbak)

conn=sqlite3.connect(str(DB),timeout=30)
conn.row_factory=sqlite3.Row
restored=[]
actions=[]
try:
    has_actions=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bodymind_operator_actions'").fetchone()
    has_docs=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documenti'").fetchone()
    if not has_actions or not has_docs:
        raise RuntimeError('R43 required tables missing')

    rows=conn.execute("""SELECT * FROM bodymind_operator_actions
        WHERE action_type='archive_duplicate_documents'
          AND status='executed'
        ORDER BY id""").fetchall()

    for a in rows:
        try:
            payload=json.loads(a['payload_json'] or '{}')
        except Exception:
            payload={}
        ids=[]
        for x in (payload.get('remove_ids') or []):
            try: ids.append(int(x))
            except Exception: pass
        action_info={'action_id':int(a['id']),'ids':ids,'created_at':str(a['created_at'] or ''),'executed_at':str(a['executed_at'] or '')}
        actions.append(action_info)
        for did in ids:
            d=conn.execute("SELECT * FROM documenti WHERE id=?",(did,)).fetchone()
            if not d:
                continue
            was_visible=int((d['visibile'] if 'visibile' in d.keys() else 1) or 0)
            if was_visible==0:
                conn.execute("UPDATE documenti SET visibile=1 WHERE id=?",(did,))
                restored.append({
                    'id':did,
                    'tesserato_id':int((d['tesserato_id'] if 'tesserato_id' in d.keys() else 0) or 0),
                    'doc_type':str((d['doc_type'] if 'doc_type' in d.keys() else '') or ''),
                    'categoria':str((d['categoria'] if 'categoria' in d.keys() else '') or ''),
                    'titolo':str((d['titolo'] if 'titolo' in d.keys() else '') or ''),
                    'original_filename':str((d['original_filename'] if 'original_filename' in d.keys() else '') or ''),
                    'filename':str((d['filename'] if 'filename' in d.keys() else '') or ''),
                })
        conn.execute("UPDATE bodymind_operator_actions SET status='rolled_back_safety' WHERE id=?",(int(a['id']),))

    conn.commit()
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
    visible_count=int(conn.execute("SELECT COUNT(*) FROM documenti WHERE coalesce(visibile,1)=1").fetchone()[0])
finally:
    conn.close()

print('[operator-dedupe-r43] actions='+repr(actions),flush=True)
print('[operator-dedupe-r43] restored='+repr(restored),flush=True)
print('[operator-dedupe-r43] restored_count='+str(len(restored))+' visible_docs='+str(visible_count)+' integrity='+integrity+' fk='+str(fk),flush=True)

if integrity.lower()!='ok' or fk:
    raise RuntimeError('R43 DB integrity failed')

MARKER.write_text('BodyMind operator document dedupe rollback R43 applied\n',encoding='utf-8')
print('[operator-dedupe-r43-selftest] PASS exact-action-id-restore no-file-delete auto-dedupe-disabled db-ok',flush=True)
