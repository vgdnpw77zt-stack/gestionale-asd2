# -*- coding: utf-8 -*-
from pathlib import Path
import sqlite3, json
DB=Path('/data/tenants/default/asd.db')
conn=sqlite3.connect(str(DB),timeout=20); conn.row_factory=sqlite3.Row
try:
    rows=[]
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bodymind_operator_messages'").fetchone():
        rows=conn.execute("""SELECT id,speaker,message,created_at
            FROM bodymind_operator_messages
            WHERE conversation_id='r45b-cloud-smoke'
            ORDER BY id DESC LIMIT 20""").fetchall()
    safe=[]
    for r in rows:
        msg=str(r['message'] or '')
        msg=msg.replace('sk-proj-','[KEY-REDACTED]-')
        safe.append({'id':int(r['id']),'speaker':str(r['speaker'] or ''),'message':msg[:1800],'created_at':str(r['created_at'] or '')})
    print('[cloud-agent-r45c-diag] '+json.dumps(safe,ensure_ascii=False),flush=True)
finally:
    conn.close()
