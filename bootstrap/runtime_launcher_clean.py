#!/usr/bin/env python3
"""A258 STAGING ONLY: read-only preflight, no migrations or backup cleanup."""
import argparse, hashlib, json, os, pathlib, shutil, sqlite3, sys

HASHES = {
  "bodymind_a237_finance_truth.py": "468947794166d48147745260cb18b7200407354ddce76c485b9ed9bb661fbfa1",
  "bodymind_a250_finance_view.py": "e549a01a8968b9bf057357100279cd617159110211bf67e78efd6aeb11d3bc7f",
  "bodymind_a253_manual.py": "a093105ad5320c038fe2856f3603ea9be303939101c1fd398dbe5a9d3d22ea01",
  "routes_a202_operational_integrity.py": "7945b1f79a7ef0c162119686882d7f700bf9815c829689047382707a369070a8",
  "routes_bodymind_final.py": "f6c115a5cdedf24f0b5476bb19997977d7a6d79658789b7983f8c44b31c14786",
  "routes_bodymind_fix29.py": "4b6ad983d5d23431d1bb941ce4547081c45040e152ccb7ba21887fecbf03e12a",
  "routes_contabilita.py": "fe5eef0e974c28710e00d90337b09e5270323b5d2f09ee41eb410842300f82a9",
  "routes_operator_bodymind.py": "96bbf726d4f5aeaa0d812512af2a6b4b1a0c8ad655ecc65ea369e6d09827db97",
  "routes_quote_incassi.py": "e8eb09c84d44238590e3542266f12239d43be092a39cf70e0e4858320475ee49",
  "routes_ricevute.py": "235150dd07c85bcf9356c066bdbf8632205e143a4b83f5c0e7af6d383f3b1c7c"
}

def check(root, db, space=True):
    root = pathlib.Path(root).resolve(strict=True)
    db = pathlib.Path(db).resolve(strict=True)
    if not (root/'.TOP2_OFFICIAL').is_file() or not (root/'app.py').is_file():
        raise RuntimeError('Official application marker or app.py absent')
    if space and shutil.disk_usage(db.parent).free < 512*1024*1024:
        raise RuntimeError('Insufficient space: no cleanup attempted')
    for name, digest in HASHES.items():
        file = root/'asd_app'/name
        if not file.is_file() or file.is_symlink():
            raise RuntimeError('Required source missing: '+name)
        body = file.read_bytes()
        if hashlib.sha256(body).hexdigest() != digest:
            raise RuntimeError('Source mismatch, no changes applied: '+name)
        compile(body, str(file), 'exec')
    con = sqlite3.connect(db.as_uri()+'?mode=ro', uri=True, timeout=20)
    try:
        con.execute('PRAGMA query_only=ON')
        if con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('SQLite integrity failed: manual recovery required')
        if con.execute('PRAGMA foreign_key_check').fetchall():
            raise RuntimeError('SQLite foreign keys failed: manual recovery required')
        counts = {}
        for name in ('pagamenti','ricevute','movimenti'):
            if not con.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?',
                               ('table',name)).fetchone():
                raise RuntimeError('Missing table: '+name)
            counts[name] = con.execute('SELECT COUNT(*) FROM '+name).fetchone()[0]
    finally:
        con.close()
    return counts

def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument('mode',choices=('check','start'))
    ap.add_argument('--root',default='/data/top2_app')
    ap.add_argument('--db',default='/data/tenants/default/asd.db')
    ap.add_argument('--skip-space-check',action='store_true')
    opt=ap.parse_args(argv)
    try:
        counts=check(opt.root,opt.db,not opt.skip_space_check)
    except (OSError,RuntimeError,sqlite3.DatabaseError) as exc:
        print('STOP A258: '+str(exc),file=sys.stderr,flush=True)
        return 2
    print('A258 OK READ ONLY '+json.dumps(counts,sort_keys=True),flush=True)
    if opt.mode == 'check':
        return 0
    os.chdir(opt.root)
    os.execvp('gunicorn',['gunicorn','--bind','0.0.0.0:'+os.getenv('PORT','8080'),
                         '--workers','1','--threads','4','--timeout','300',
                         '--access-logfile','-','--error-logfile','-','app:app'])
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
