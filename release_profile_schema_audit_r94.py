# -*- coding: utf-8 -*-
import json, sqlite3
from pathlib import Path

DB=Path('/data/tenants/default/asd.db')
conn=sqlite3.connect(str(DB),timeout=30); conn.row_factory=sqlite3.Row
try:
    info=[{'cid':r[0],'name':r[1],'type':r[2],'notnull':r[3],'default':r[4],'pk':r[5]} for r in conn.execute('PRAGMA table_info(tesserati)').fetchall()]
    sql=conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tesserati'").fetchone()
    rows=[]
    for tid in (44,45,46):
        r=conn.execute('SELECT * FROM tesserati WHERE id=?',(tid,)).fetchone()
        if r:
            rows.append({'id':tid,'values':{k:r[k] for k in r.keys() if r[k] not in (None,'')}})
    print('[r94-tesserati-schema] '+json.dumps({'columns':info,'create_sql':sql[0] if sql else '','rows':rows},ensure_ascii=False,default=str),flush=True)
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:
    conn.close()
print('[r94-selftest] PASS read-only schema audit integrity='+integrity+' fk='+str(fk),flush=True)
if integrity.lower()!='ok' or fk:
    raise RuntimeError('R94 DB integrity failed')
