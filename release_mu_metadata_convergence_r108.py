# -*- coding: utf-8 -*-
from __future__ import annotations
import json, shutil, sqlite3
from datetime import datetime
from pathlib import Path

DB=Path('/data/tenants/default/asd.db')
BACK=Path('/data/release_backups/20261002_r108_mu_metadata')
BACK.mkdir(parents=True,exist_ok=True)

def table(conn,name):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())

def cols(conn,name):
    return {str(r[1]) for r in conn.execute("PRAGMA table_info("+name+")").fetchall()} if table(conn,name) else set()

def is_mu_row(r):
    ks=set(r.keys())
    hay=' '.join(str(r[k] or '').lower() for k in ('doc_type','categoria','titolo','original_filename','filename') if k in ks)
    return (
      'modulo_unico_tesseramento' in hay or 'modulo unico' in hay or 'modulo_unico' in hay
      or 'modulo iscrizione' in hay or 'domanda iscrizione' in hay or 'iscrizione manleva' in hay
    )

conn=sqlite3.connect(str(DB),timeout=45); conn.row_factory=sqlite3.Row
try:
    dcols=cols(conn,'documenti')
    rows=conn.execute("SELECT * FROM documenti WHERE COALESCE(visibile,1)=1 ORDER BY id").fetchall()
    targets=[]
    for r in rows:
        if not is_mu_row(r):
            continue
        dtype=str(r['doc_type'] or '').strip().lower() if 'doc_type' in r.keys() else ''
        cat=str(r['categoria'] or '').strip().lower() if 'categoria' in r.keys() else ''
        if dtype!='modulo_unico_tesseramento' or 'modulo iscrizione' not in cat:
            targets.append(dict(r))

    if targets:
        stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
        b=BACK/('pre_r108_'+stamp+'.db')
        src=sqlite3.connect(str(DB),timeout=45)
        dst=sqlite3.connect(str(b))
        try: src.backup(dst)
        finally: dst.close(); src.close()

        changed=[]
        for r in targets:
            sets=[]; vals=[]
            if 'doc_type' in dcols:
                sets.append("doc_type=?"); vals.append('modulo_unico_tesseramento')
            if 'categoria' in dcols:
                sets.append("categoria=?"); vals.append('Modulo iscrizione BodyMind')
            if sets:
                vals.append(int(r['id']))
                conn.execute("UPDATE documenti SET "+",".join(sets)+" WHERE id=?",tuple(vals))
                changed.append({
                    'id':int(r['id']),
                    'tesserato_id':int(r.get('tesserato_id') or 0),
                    'old_doc_type':r.get('doc_type'),
                    'old_categoria':r.get('categoria'),
                })
        conn.commit()
    else:
        changed=[]; b=None

    integrity=str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    fk=len(conn.execute("PRAGMA foreign_key_check").fetchall())

    remaining=[]
    for r in conn.execute("SELECT * FROM documenti WHERE COALESCE(visibile,1)=1 ORDER BY id").fetchall():
        if not is_mu_row(r): continue
        dtype=str(r['doc_type'] or '').strip().lower() if 'doc_type' in r.keys() else ''
        cat=str(r['categoria'] or '').strip().lower() if 'categoria' in r.keys() else ''
        if dtype!='modulo_unico_tesseramento' or 'modulo iscrizione' not in cat:
            remaining.append(int(r['id']))
finally:
    conn.close()

print('[r108-mu-metadata] '+json.dumps({
  'changed':changed,'changed_count':len(changed),'backup':str(b) if b else '',
  'remaining_incoherent':remaining,'integrity':integrity,'fk':fk
},ensure_ascii=False,default=str),flush=True)
if remaining or integrity.lower()!='ok' or fk:
    raise RuntimeError('R108 MU metadata convergence failed')
print('[r108-selftest] PASS visible-MU canonical metadata integrity/fk',flush=True)
