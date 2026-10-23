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
import base64
import zlib
import tempfile
import stat

EXPECTED_SOURCE_COUNT=209
EXPECTED_SOURCE_DIGEST='8d19e46fa5313c3b6626a48830e1b00629ee16fa9c423d29d294083d194b53f4'
# A309B staged upgrade: BOTH exact verified hashes are accepted, nothing else.
# Production remains pinned to the prior 209-only image until isolated QA and post-A304 backup.
UPGRADE_SOURCE_COUNT=211
UPGRADE_SOURCE_DIGEST='c7cd7cd5c95e424d0fb43d4f32ad7dfbc752ad181446b247a94b31769c5788b0'
# A310 manual course roster: source-only surgical release (no automatic roster migration).
MANUAL_ROSTER_SOURCE_COUNT=212
MANUAL_ROSTER_SOURCE_DIGEST='fc66a79bc5c86415b3fca60c1fc2134bc4e7194e3303aaf12691fac49724bf28'
# A311: group-only attendance with persisted Kids/Adults/Pro members, no course assignment.
SIMPLE_GROUP_SOURCE_COUNT=212
SIMPLE_GROUP_SOURCE_DIGEST='451abcf3cfab5faab68a82993bd0767f97c3a0413025d361fa8df36b2583ac9f'
A317_SOURCE_COUNT=214
A317_SOURCE_DIGEST='ed36df177eb122933c784e236edf1f72e7f11a147151381672217f547dd4a5bc'
A328_SOURCE_COUNT=214
A328_SOURCE_DIGEST='f8b3de5cd7e6feb98f0aee595cc8317965b57205a4270994274cab7390907cfe'
A330_SOURCE_COUNT=214
A330_SOURCE_DIGEST='b205d41fc30351841899267ea78deed761f86ff6b1d47d5e65763d7fb9c5cb62'
A336_SOURCE_COUNT=214
A336_SOURCE_DIGEST='92356aac5eb1f25c642088a684e17273b6141804e4501f50ee63c79fd5d4cf47'
A337_SOURCE_COUNT=214
A337_SOURCE_DIGEST='ddcbc2d6b7614d01e34bb822a2ae254e3d08d7ebb10fd395849c5760da43fd46'
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
    valid={(EXPECTED_SOURCE_COUNT,EXPECTED_SOURCE_DIGEST),(UPGRADE_SOURCE_COUNT,UPGRADE_SOURCE_DIGEST),
           (MANUAL_ROSTER_SOURCE_COUNT,MANUAL_ROSTER_SOURCE_DIGEST),
           (SIMPLE_GROUP_SOURCE_COUNT,SIMPLE_GROUP_SOURCE_DIGEST),(A317_SOURCE_COUNT,A317_SOURCE_DIGEST),(A328_SOURCE_COUNT,A328_SOURCE_DIGEST),(A330_SOURCE_COUNT,A330_SOURCE_DIGEST),(A336_SOURCE_COUNT,A336_SOURCE_DIGEST),(A337_SOURCE_COUNT,A337_SOURCE_DIGEST)}
    if (len(found),inventory_digest(found)) not in valid and not a340_matches(root,found):
        raise RuntimeError(f'source lock mismatch files={len(found)} expected={EXPECTED_SOURCE_COUNT}')
    return {'source_files':len(found),'sqlite':'ok','rows':sqlite_readonly_check(db),
            'historical_migrations_executed':0,'automatic_backup_cleanup':False,
            'automatic_database_restore':False}


# A337 cinematic family UI overlay. Only the public stylesheet lives in this image.
# Private application sources and their backups remain on the existing volume.
def maybe_apply_a337_family_ui(root:Path,db:Path)->None:
    found=source_inventory(root)
    actual=(len(found),inventory_digest(found))
    desired=(A337_SOURCE_COUNT,A337_SOURCE_DIGEST)
    if actual==desired:
        return
    if actual!=(A336_SOURCE_COUNT,A336_SOURCE_DIGEST):
        return
    # Visual-only upgrade: refuse any write unless the live database checks pass.
    sqlite_readonly_check(db)
    compressed=Path('/opt/bodymind/family_a337.css.zlib.base64').read_text(encoding='ascii').strip()
    css=zlib.decompress(base64.b64decode(compressed,validate=True))
    if hashlib.sha256(css).hexdigest()!='69210cc584ab72980e061f1db340f2533f9fa7c356c4f6d3dc1d75783e5283ae':
        raise RuntimeError('A337 stylesheet checksum mismatch')
    target=root/'asd_app'/'routes_bodymind_final.py'
    if target.is_symlink() or not target.is_file():
        raise RuntimeError('A337 unsafe target path')
    old=target.read_bytes()
    old_sha=hashlib.sha256(old).hexdigest()
    if old_sha!='24361f208b5ddf3d24180b7a15f429071d332130ba0c95d4fc9b2ae9f24ca4e9':
        raise RuntimeError('A337 existing UI changed, nothing written')
    anchor=b'</style>\n</head>'
    if old.count(anchor)!=1:
        raise RuntimeError('A337 unique stylesheet anchor not found')
    new=old.replace(anchor,css+b'\n'+anchor,1)
    new_sha=hashlib.sha256(new).hexdigest()
    if new_sha!='3aa21ab21216bd72d1dc26030f5cb0f04d1c312f42ad545aed4736220fbe8ecc':
        raise RuntimeError('A337 candidate source hash mismatch')
    proposed=dict(found)
    proposed['asd_app/routes_bodymind_final.py']=new_sha
    if (len(proposed),inventory_digest(proposed))!=desired:
        raise RuntimeError('A337 candidate manifest mismatch')
    releases=Path('/data/release_packages')
    if not releases.is_dir() or releases.is_symlink():
        raise RuntimeError('A337 safe backup directory unavailable')
    backup=releases/'BODYMIND_A337_PREUI_ROLLBACK_24361f208b5d.py'
    if backup.exists():
        if backup.is_symlink() or hashlib.sha256(backup.read_bytes()).hexdigest()!=old_sha:
            raise RuntimeError('A337 previous source backup mismatch')
    else:
        with open(backup,'xb') as fh:
            fh.write(old)
            fh.flush()
            os.fsync(fh.fileno())
    temp_path=None
    try:
        with tempfile.NamedTemporaryFile(prefix='.a337_ui_patch_',suffix='.py',dir=str(target.parent),delete=False) as fh:
            temp_path=Path(fh.name)
            fh.write(new)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(temp_path,stat.S_IMODE(target.stat().st_mode))
        os.replace(str(temp_path),str(target))
        temp_path=None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    final=source_inventory(root)
    if (len(final),inventory_digest(final))!=desired:
        raise RuntimeError('A337 post-write manifest mismatch')
    print('BODYMIND A337 FAMILY UI APPLIED; 214 verified sources; SQLite not modified',flush=True)


# A340 — approved BodyMind design overlay, with exact A337 source-lock verification.
# All private source and athlete documents stay on the existing Railway volume.
A340_CSS_SHA256='c7212f04470de83fd3f6a95175d23e11bd594e836dfc0dbd4cf434bf96af92dc'
A340_OLD_MODULE_SHA256='3aa21ab21216bd72d1dc26030f5cb0f04d1c312f42ad545aed4736220fbe8ecc'
A340_REL='asd_app/routes_bodymind_final.py'
A340_BACKUP=Path('/data/release_packages/BODYMIND_A340_PREUI_A337_3aa21ab21216bd7.py')

def a340_css()->bytes:
    content=Path('/opt/bodymind/family_a340.css.zlib.base64').read_text(encoding='ascii').strip()
    css=zlib.decompress(base64.b64decode(content,validate=True))
    if hashlib.sha256(css).hexdigest()!=A340_CSS_SHA256:
        raise RuntimeError('A340 approved style checksum mismatch')
    if b"'''" in css or b'</style>' in css:
        raise RuntimeError('A340 unsafe style delimiter')
    return css

A340_EDITORIAL_CSS="/* Home editorial order: gallery follows dashboard summary without changing routes. */\n.main{display:flex;flex-direction:column}\n.main>.flash{order:-3}\n.main>.stats{order:-2}\n.main>#media{order:-1;margin-bottom:32px}\n.main>#corsi{order:0}\n.main>#pagamenti{order:1}\n.main>#documenti{order:2}\n.main>.section:not(#media):not(#corsi):not(#pagamenti){order:3}\n"

def a340_expected_source(old:bytes)->tuple[bytes,str]:
    if hashlib.sha256(old).hexdigest()!=A340_OLD_MODULE_SHA256:
        raise RuntimeError('A340 historical UI source checksum mismatch')
    anchor=b'</style>\n</head>'
    if old.count(anchor)!=1:
        raise RuntimeError('A340 UI stylesheet anchor not unique')
    new=old.replace(anchor,b'\n'+a340_css()+b'\n'+A340_EDITORIAL_CSS.encode('utf-8')+b'\n'+anchor,1)
    compile(new,A340_REL,'exec')
    return new,hashlib.sha256(new).hexdigest()

def a340_matches(root:Path,found:dict[str,str])->bool:
    if len(found)!=214 or A340_REL not in found or not A340_BACKUP.is_file() or A340_BACKUP.is_symlink():
        return False
    _,new_sha=a340_expected_source(A340_BACKUP.read_bytes())
    if found[A340_REL]!=new_sha:
        return False
    # Verify all 213 OTHER active source hashes by virtually restoring the
    # single known A337 module digest before checking the signed A337 manifest.
    prior=dict(found)
    prior[A340_REL]=A340_OLD_MODULE_SHA256
    return inventory_digest(prior)==A337_SOURCE_DIGEST

def maybe_apply_a340_family_ui(root:Path,db:Path)->None:
    found=source_inventory(root)
    if a340_matches(root,found):
        return
    if (len(found),inventory_digest(found))!=(A337_SOURCE_COUNT,A337_SOURCE_DIGEST):
        return
    sqlite_readonly_check(db)
    target=root/A340_REL
    if target.is_symlink() or not target.is_file():
        raise RuntimeError('A340 unsafe source path')
    old=target.read_bytes()
    new,new_sha=a340_expected_source(old)
    if A340_BACKUP.exists():
        if A340_BACKUP.is_symlink() or A340_BACKUP.read_bytes()!=old:
            raise RuntimeError('A340 backup source conflict')
    else:
        if not A340_BACKUP.parent.is_dir() or A340_BACKUP.parent.is_symlink():
            raise RuntimeError('A340 protected source backup directory missing')
        with open(A340_BACKUP,'xb') as f:
            f.write(old)
            f.flush()
            os.fsync(f.fileno())
    temp=None
    try:
        with tempfile.NamedTemporaryFile(prefix='.a340_design_',suffix='.py',dir=str(target.parent),delete=False) as fh:
            temp=Path(fh.name)
            fh.write(new)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(temp,stat.S_IMODE(target.stat().st_mode))
        os.replace(str(temp),str(target))
        temp=None
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
    final=source_inventory(root)
    if not a340_matches(root,final) or final[A340_REL]!=new_sha:
        raise RuntimeError('A340 post-write source manifest mismatch')
    print('BODYMIND A340 APPROVED FAMILY DESIGN APPLIED; previous source preserved; SQLite unchanged',flush=True)

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',nargs='?',choices=('check','start'),default='start')
    parser.add_argument('--root',type=Path,default=Path('/data/top2_app'))
    parser.add_argument('--db',type=Path,default=Path('/data/tenants/default/asd.db'))
    args=parser.parse_args(argv)
    try:
        if args.mode=='start':
            maybe_apply_a337_family_ui(args.root,args.db)
            maybe_apply_a340_family_ui(args.root,args.db)
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
