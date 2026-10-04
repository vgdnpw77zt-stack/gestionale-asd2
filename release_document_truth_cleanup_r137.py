from __future__ import annotations
import hashlib, sqlite3, shutil
from datetime import datetime
from pathlib import Path

DB=Path('/data/tenants/default/asd.db')
APP=Path('/data/top2_app')
BACK=Path('/data/release_backups/20261004_r137_document_truth')
BACK.mkdir(parents=True,exist_ok=True)

def backup_db():
    dst=BACK/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_pre_cleanup.db')
    src=sqlite3.connect(str(DB),timeout=30); out=sqlite3.connect(str(dst))
    try: src.backup(out)
    finally: out.close(); src.close()
    return dst

def resolve_file(filename):
    raw=Path(str(filename or '').strip())
    roots=[Path('/data/tenants/default/media'),APP/'user_static',APP/'static',APP,Path('/data/tenants/default')]
    cands=[raw] if raw.is_absolute() else [x/raw for x in roots]
    for c in cands:
        try:
            if c.is_file(): return c.resolve()
        except Exception: pass
    return None

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for ch in iter(lambda:f.read(1024*1024),b''): h.update(ch)
    return h.hexdigest()

def kind(row):
    vals=[]
    for k in ('doc_type','categoria','titolo','original_filename','filename'):
        try: vals.append(str(row[k] or '').lower())
        except Exception: pass
    hay=' '.join(vals)
    if any(x in hay for x in ('modulo_unico_tesseramento','modulo unico','modulo iscrizione',"modulo d'iscrizione",'domanda iscrizione')):
        return 'mu'
    if 'richiesta certificato' in hay or 'richiesta_certificato' in hay:
        return 'other'
    if 'certificato_medico' in hay or ('certificat' in hay and 'medic' in hay):
        return 'medical'
    return 'other'

bak=backup_db()
conn=sqlite3.connect(str(DB),timeout=30); conn.row_factory=sqlite3.Row
actions=[]
try:
    # Persist transient operator uploads into canonical media.
    for r in conn.execute("SELECT * FROM documenti WHERE coalesce(visibile,1)=1 ORDER BY id").fetchall():
        fn=str(r['filename'] or '')
        if not fn.startswith('/data/operator_upload_jobs/'): continue
        src=Path(fn)
        if not src.is_file(): continue
        tid=int(r['tesserato_id'] or 0)
        destdir=Path('/data/tenants/default/media/tesserati')/str(tid); destdir.mkdir(parents=True,exist_ok=True)
        dest=destdir/(datetime.now().strftime('%Y-%m-%d_%H%M%S')+'_R137_'+Path(str(r['original_filename'] or src.name)).name)
        if not dest.exists(): shutil.copy2(src,dest)
        conn.execute("UPDATE documenti SET filename=?,updated_at=datetime('now') WHERE id=?",(str(dest),int(r['id'])))
        actions.append(('migrate',int(r['id']),str(dest)))

    # Archive exact same-file duplicates for the same athlete.
    groups={}
    rows=conn.execute("SELECT * FROM documenti WHERE coalesce(visibile,1)=1 ORDER BY tesserato_id,id").fetchall()
    for r in rows:
        fp=resolve_file(r['filename'])
        if not fp: continue
        groups.setdefault((int(r['tesserato_id'] or 0),sha256(fp)),[]).append(r)
    for (tid,digest),items in groups.items():
        if tid<=0 or len(items)<2: continue
        def rank(r):
            score=0
            if kind(r) in ('mu','medical'): score+=4
            if str(r['doc_type'] or '').strip(): score+=2
            if str(r['status'] or '').lower() in ('salvato','verificato','verified','ok'): score+=1
            return (score,-int(r['id']))
        keep=sorted(items,key=rank,reverse=True)[0]
        for r in items:
            if int(r['id'])==int(keep['id']): continue
            conn.execute("UPDATE documenti SET visibile=0,status='duplicate_exact_archived_r137',updated_at=datetime('now') WHERE id=?",(int(r['id']),))
            actions.append(('duplicate',int(r['id']),int(keep['id'])))

    # User-confirmed legacy/redundant rows; soft archive only.
    explicit=[48,42,43,44,134,136,138,149,148,115]
    for did in explicit:
        r=conn.execute("SELECT visibile FROM documenti WHERE id=?",(did,)).fetchone()
        if r and int(r['visibile'] or 0)==1:
            conn.execute("UPDATE documenti SET visibile=0,status='archived_r137',updated_at=datetime('now') WHERE id=?",(did,))
            actions.append(('archive',did))

    # MU flags follow visible + physically present canonical MU only.
    for a in conn.execute("SELECT * FROM tesserati ORDER BY id").fetchall():
        tid=int(a['id'])
        has_mu=False
        for r in conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1",(tid,)).fetchall():
            if kind(r)=='mu' and resolve_file(r['filename']):
                has_mu=True; break
        if 'iscrizione_firmata' in a.keys():
            conn.execute("UPDATE tesserati SET iscrizione_firmata=? WHERE id=?",(1 if has_mu else 0,tid))
        if 'documenti_onboarding_ok' in a.keys():
            conn.execute("UPDATE tesserati SET documenti_onboarding_ok=? WHERE id=?",(1 if has_mu else 0,tid))

    conn.commit()
    integ=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:
    conn.close()

print('[r137-data] backup='+str(bak)+' actions='+repr(actions),flush=True)
print('[r137-db] integrity='+integ+' fk='+str(fk),flush=True)
if integ.lower()!='ok' or fk: raise RuntimeError('R137 DB integrity failed')
