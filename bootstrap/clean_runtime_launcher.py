#!/usr/bin/env python3
"""BodyMind A301 immutable-volume clean boot. No automatic migration, restore or cleanup."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

EXPECTED_SOURCE_COUNT=209
EXPECTED_SOURCE_DIGEST='8d19e46fa5313c3b6626a48830e1b00629ee16fa9c423d29d294083d194b53f4'
# A309B staged upgrade: BOTH exact verified hashes are accepted, nothing else.
# Production remains pinned to the prior 209-only image until isolated QA and post-A304 backup.
UPGRADE_SOURCE_COUNT=211
UPGRADE_SOURCE_DIGEST='c7cd7cd5c95e424d0fb43d4f32ad7dfbc752ad181446b247a94b31769c5788b0'
REQUIRED_TABLES=('tesserati','pagamenti','ricevute','quote_mensili')

def source_inventory(root:Path)->dict[str,str]:
    root=root.resolve(strict=True)
    # Match A301's AUTHORITATIVE source inventory: app.py and asd_app only.
    # The volume also contains four desktop-only Python files from older releases.
    allowed_root={'desktop_boot.py','desktop_webview.py','desktop_webview_browser_stabile.py','production_preflight.py'}
    other_root={p.name for p in root.glob('*.py') if p.name!='app.py'}
    if other_root-allowed_root:
        raise RuntimeError('unexpected root-level Python source')
    paths=[root/'app.py',*(root/'asd_app').rglob('*.py')]
    found={}
    for path in sorted(set(paths)):
        rel=path.relative_to(root)
        if any(part.startswith('.') or part=='__pycache__' for part in rel.parts):
            continue
        if path.is_symlink() or not path.is_file():
            raise RuntimeError('unsafe application source')
        content=path.read_bytes()
        if len(content)>5_000_000:
            raise RuntimeError('application source exceeds size guard')
        compile(content,rel.as_posix(),'exec')
        found[rel.as_posix()]=hashlib.sha256(content).hexdigest()
    return found

def inventory_digest(files:dict[str,str])->str:
    payload=''.join(f'{name}\t{sha}\n' for name,sha in sorted(files.items()))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()

def sqlite_readonly_check(db:Path)->dict[str,int]:
    if not db.is_file() or db.is_symlink():
        raise RuntimeError('missing or unsafe SQLite database')
    con=sqlite3.connect(db.resolve(strict=True).as_uri()+'?mode=ro',uri=True,timeout=25)
    try:
        con.execute('PRAGMA query_only=ON')
        if con.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise RuntimeError('SQLite integrity check failed (no automatic restore)')
        if con.execute('PRAGMA foreign_key_check').fetchone() is not None:
            raise RuntimeError('SQLite foreign key violation (no automatic restore)')
        counts={}
        for table in REQUIRED_TABLES:
            if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
                raise RuntimeError('missing required database table')
            counts[table]=int(con.execute('SELECT COUNT(*) FROM "'+table+'"').fetchone()[0])
        return counts
    finally:
        con.close()

def preflight(root:Path,db:Path)->dict:
    if not (root/'.TOP2_OFFICIAL').is_file() or not (root/'app.py').is_file():
        raise RuntimeError('official application root missing')
    found=source_inventory(root)
    valid={(EXPECTED_SOURCE_COUNT,EXPECTED_SOURCE_DIGEST),(UPGRADE_SOURCE_COUNT,UPGRADE_SOURCE_DIGEST)}
    if (len(found),inventory_digest(found)) not in valid:
        raise RuntimeError(f'source lock mismatch files={len(found)} expected={EXPECTED_SOURCE_COUNT}')
    return {'source_files':len(found),'sqlite':'ok','rows':sqlite_readonly_check(db),
            'historical_migrations_executed':0,'automatic_backup_cleanup':False,
            'automatic_database_restore':False}

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',nargs='?',choices=('check','start'),default='start')
    parser.add_argument('--root',type=Path,default=Path('/data/top2_app'))
    parser.add_argument('--db',type=Path,default=Path('/data/tenants/default/asd.db'))
    args=parser.parse_args(argv)
    try:
        result=preflight(args.root,args.db)
    except (OSError,RuntimeError,ValueError,sqlite3.DatabaseError) as exc:
        print('BODYMIND CLEAN BOOT STOP: '+str(exc),file=sys.stderr,flush=True)
        return 2
    print('BODYMIND CLEAN BOOT PASS '+json.dumps(result,sort_keys=True),flush=True)
    if args.mode=='check':return 0
    os.chdir(str(args.root.resolve()))
    port=os.environ.get('PORT','8080')
    if not port.isdigit() or not 1<=int(port)<=65535:
        print('BODYMIND CLEAN BOOT STOP: invalid port',file=sys.stderr)
        return 2
    os.execvp('gunicorn',['gunicorn','--bind','0.0.0.0:'+port,'--workers','1','--threads','4','--timeout','300','--access-logfile','-','--error-logfile','-','app:app'])
    return 0

if __name__=='__main__':
    raise SystemExit(main())
