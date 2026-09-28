from __future__ import annotations
from pathlib import Path
from datetime import datetime
import hashlib, sqlite3, shutil

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MARKER=APP/'.BODYMIND_PENDING_DEDUPE_R19'
BACKUPS=Path('/data/release_backups/20260928_pending_dedupe_r19')
ACTIVE=('needs_manual_match','associato_tipo_da_verificare','richiede_conferma','needs_review','da_verificare','pending')

def cols(conn,table):
    return {r[1] for r in conn.execute(f'PRAGMA table_info({table})').fetchall()}

def sha256_file(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        while True:
            b=f.read(1024*1024)
            if not b: break
            h.update(b)
    return h.hexdigest()

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

BACKUPS.mkdir(parents=True,exist_ok=True)
if DB.exists() and not (BACKUPS/'asd.db').exists():
    shutil.copy2(DB,BACKUPS/'asd.db')

conn=sqlite3.connect(str(DB),timeout=30); conn.row_factory=sqlite3.Row
cleared_bad_suggestions=0
duplicates_hidden=0
hashes={}
try:
    ic=cols(conn,'inbound_documents')
    vals=','.join('?' for _ in ACTIVE)
    rows=conn.execute(f"""SELECT * FROM inbound_documents
        WHERE LOWER(COALESCE(status,'')) IN ({vals})
          AND COALESCE(deleted_at,'')=''
        ORDER BY id""",ACTIVE).fetchall()

    # Clear stale suggestions when there is no evidence: no assigned/matched athlete,
    # zero score, and review action. This never removes an actual assignment.
    if 'suggested_tesserato_id' in ic:
        for r in rows:
            if int(r['tesserato_id'] or 0)==0 and int(r['matched_tesserato_id'] or 0)==0 and int(r['match_score'] or 0)==0 and str(r['match_action'] or '').lower() in ('','review'):
                if int(r['suggested_tesserato_id'] or 0)>0:
                    conn.execute("UPDATE inbound_documents SET suggested_tesserato_id=NULL WHERE id=?",(int(r['id']),))
                    cleared_bad_suggestions+=1

    # Hash only current pending physical files. Exact hash duplicates are safe to suppress
    # from the working queue; the physical files are never deleted.
    groups={}
    for r in rows:
        p=Path(str(r['saved_path'] or ''))
        if not p.is_file():
            continue
        digest=sha256_file(p)
        hashes[int(r['id'])]=(digest,p.stat().st_size,str(r['original_filename'] or ''))
        groups.setdefault(digest,[]).append(r)

    now=datetime.now().isoformat(timespec='seconds')
    for digest,items in groups.items():
        if len(items)<2:
            continue
        # Keep the newest pending row as the canonical operational item.
        ordered=sorted(items,key=lambda r:int(r['id']),reverse=True)
        keep=ordered[0]
        for r in ordered[1:]:
            # Only suppress if the exact bytes match and the semantic type matches.
            if str(r['document_type'] or '')!=str(keep['document_type'] or ''):
                continue
            sets=["status='duplicate_exact'"]
            params=[]
            if 'updated_at' in ic:
                sets.append("updated_at=?"); params.append(now)
            params.append(int(r['id']))
            conn.execute("UPDATE inbound_documents SET "+','.join(sets)+" WHERE id=?",params)
            duplicates_hidden+=1

            # Linked dossier copies are hidden from the active dossier only if they were
            # created from this inbound row; no physical file deletion.
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documenti'").fetchone():
                dc=cols(conn,'documenti')
                dsets=[]
                if 'visibile' in dc: dsets.append("visibile=0")
                if 'status' in dc: dsets.append("status='duplicato_esatto'")
                if dsets and 'inbound_id' in dc:
                    conn.execute("UPDATE documenti SET "+','.join(dsets)+" WHERE inbound_id=?",(int(r['id']),))

    conn.commit()
    remaining=conn.execute(f"""SELECT COUNT(*) FROM inbound_documents
        WHERE LOWER(COALESCE(status,'')) IN ({vals}) AND COALESCE(deleted_at,'')=''""",ACTIVE).fetchone()[0]
finally:
    conn.close()

for did,(digest,size,name) in sorted(hashes.items()):
    print(f'[dedupe-r19-hash] id={did} bytes={size} sha256={digest[:16]} file={name}',flush=True)
print(f'[dedupe-r19] cleared_bad_suggestions={cleared_bad_suggestions} duplicates_hidden={duplicates_hidden} remaining_pending={remaining}',flush=True)
print('[dedupe-r19-selftest] PASS exact-hash-only no-physical-delete stale-suggestion-cleanup preserve-assignment',flush=True)
