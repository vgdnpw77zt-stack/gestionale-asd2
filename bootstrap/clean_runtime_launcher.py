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
    if (len(found),inventory_digest(found)) not in valid and not a340_matches(root,found) and not a341_matches(root,found) and not a342_matches(root,found) and not a343_matches(root,found) and not a344_matches(root,found) and not a345_matches(root,found) and not a346_matches(root,found) and not a347_matches(root,found) and not a348_matches(root,found) and not a349_matches(root,found) and not a350_matches(root,found):
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


# A341 — site-consistent luminous waves + links to existing PUBLIC reels.
# Keep the actual family/video data intact; preserve private UI source A340 for recovery.
A341_REL=A340_REL
A341_ROLLBACK=Path('/data/release_packages/BODYMIND_A341_PREUI_A340.py')
A341_STYLE_PATH=Path('/opt/bodymind/family_a341.css')
A341_LINKS_PATH=Path('/opt/bodymind/family_a341.js')
A341_STYLE_ANCHOR=b'</style>\n</head>'
A341_MEDIA_ANCHOR=b'</div></div></section>\n<section class="section"><div class="panel personal">'

def a341_source_from_a340(old:bytes)->tuple[bytes,str]:
    if not A340_BACKUP.is_file() or A340_BACKUP.is_symlink():
        raise RuntimeError('A341 original A337 UI backup missing')
    _,a340_sha=a340_expected_source(A340_BACKUP.read_bytes())
    if hashlib.sha256(old).hexdigest()!=a340_sha:
        raise RuntimeError('A341 A340 source checksum mismatch')
    if old.count(A341_STYLE_ANCHOR)!=1 or old.count(A341_MEDIA_ANCHOR)!=1:
        raise RuntimeError('A341 expected template anchors missing')
    style=A341_STYLE_PATH.read_bytes()
    links=A341_LINKS_PATH.read_bytes()
    if not (b'.bodymind-media-outbound' in style and b'familyMediaTrack' in links and b'noopener noreferrer' in links):
        raise RuntimeError('A341 expected visual/link assets missing')
    if b'</style>' in style or b'</script>' in links or b"'''" in links:
        raise RuntimeError('A341 unsafe style or link assets')
    new=old.replace(A341_STYLE_ANCHOR,b'\n'+style+b'\n'+A341_STYLE_ANCHOR,1)
    new=new.replace(A341_MEDIA_ANCHOR,
        b'</div></div></section>\n<script id="bodymind-media-links">\n'+links+b'\n</script>\n<section class="section"><div class="panel personal">',1)
    compile(new,A341_REL,'exec')
    return new,hashlib.sha256(new).hexdigest()

def a341_matches(root:Path,found:dict[str,str])->bool:
    if len(found)!=214 or A341_REL not in found or not A341_ROLLBACK.is_file() or A341_ROLLBACK.is_symlink():
        return False
    old=A341_ROLLBACK.read_bytes()
    _,expected_sha=a341_source_from_a340(old)
    if found[A341_REL]!=expected_sha:
        return False
    prior=dict(found)
    prior[A341_REL]=hashlib.sha256(old).hexdigest()
    return a340_matches(root,prior)

def maybe_apply_a341_family_ui(root:Path,db:Path)->None:
    found=source_inventory(root)
    if a341_matches(root,found):
        return
    if not a340_matches(root,found):
        return
    sqlite_readonly_check(db)
    target=root/A341_REL
    if target.is_symlink() or not target.is_file():
        raise RuntimeError('A341 unsafe source path')
    old=target.read_bytes()
    new,new_sha=a341_source_from_a340(old)
    if A341_ROLLBACK.exists():
        if A341_ROLLBACK.is_symlink() or A341_ROLLBACK.read_bytes()!=old:
            raise RuntimeError('A341 previous source backup mismatch')
    else:
        if not A341_ROLLBACK.parent.is_dir() or A341_ROLLBACK.parent.is_symlink():
            raise RuntimeError('A341 protected backup directory missing')
        with open(A341_ROLLBACK,'xb') as fh:
            fh.write(old)
            fh.flush()
            os.fsync(fh.fileno())
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(prefix='.a341_family_',suffix='.py',dir=str(target.parent),delete=False) as fh:
            tmp=Path(fh.name)
            fh.write(new)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp,stat.S_IMODE(target.stat().st_mode))
        os.replace(str(tmp),str(target))
        tmp=None
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    final=source_inventory(root)
    if not a341_matches(root,final) or final[A341_REL]!=new_sha:
        raise RuntimeError('A341 post-write manifest mismatch')
    print('BODYMIND A341 WAVES AND PUBLIC MEDIA LINKS APPLIED; previous source preserved; SQLite unchanged',flush=True)


# A342 — moving luminous waves. Source-only UI overlay; authenticated A341 tree and SQLite.
A342_REL=A341_REL
A342_BACKUP=Path('/data/release_packages/BODYMIND_A342_PREUI_A341.py')
A342_STYLE_PATH=Path('/opt/bodymind/family_a342_motion.css')

def a342_source_from_a341(old:bytes)->tuple[bytes,str]:
    if not A341_ROLLBACK.is_file() or A341_ROLLBACK.is_symlink():
        raise RuntimeError('A342 signed A340 source backup missing')
    _,a341_sha=a341_source_from_a340(A341_ROLLBACK.read_bytes())
    if hashlib.sha256(old).hexdigest()!=a341_sha:
        raise RuntimeError('A342 unexpected A341 source checksum')
    anchor=b'</style>\n</head>'
    if old.count(anchor)!=1:
        raise RuntimeError('A342 stylesheet anchor mismatch')
    css=A342_STYLE_PATH.read_bytes()
    if b'bmWaveFloat' not in css or b'prefers-reduced-motion' not in css or b'</style>' in css:
        raise RuntimeError('A342 motion stylesheet invalid')
    new=old.replace(anchor,b'\n'+css+b'\n'+anchor,1)
    compile(new,A342_REL,'exec')
    return new,hashlib.sha256(new).hexdigest()

def a342_matches(root:Path,found:dict[str,str])->bool:
    if len(found)!=214 or A342_REL not in found or not A342_BACKUP.is_file() or A342_BACKUP.is_symlink():
        return False
    old=A342_BACKUP.read_bytes()
    _,expected_sha=a342_source_from_a341(old)
    if found[A342_REL]!=expected_sha:
        return False
    prior=dict(found)
    prior[A342_REL]=hashlib.sha256(old).hexdigest()
    return a341_matches(root,prior)

def maybe_apply_a342_family_ui(root:Path,db:Path)->None:
    found=source_inventory(root)
    if a342_matches(root,found):
        return
    if not a341_matches(root,found):
        return
    sqlite_readonly_check(db)
    target=root/A342_REL
    if target.is_symlink() or not target.is_file():
        raise RuntimeError('A342 unsafe target source path')
    old=target.read_bytes()
    new,new_sha=a342_source_from_a341(old)
    if A342_BACKUP.exists():
        if A342_BACKUP.is_symlink() or A342_BACKUP.read_bytes()!=old:
            raise RuntimeError('A342 source backup conflict')
    else:
        if not A342_BACKUP.parent.is_dir() or A342_BACKUP.parent.is_symlink():
            raise RuntimeError('A342 safe rollback directory unavailable')
        with open(A342_BACKUP,'xb') as fh:
            fh.write(old)
            fh.flush()
            os.fsync(fh.fileno())
    temp=None
    try:
        with tempfile.NamedTemporaryFile(prefix='.a342_motion_',suffix='.py',dir=str(target.parent),delete=False) as fh:
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
    if not a342_matches(root,final) or final[A342_REL]!=new_sha:
        raise RuntimeError('A342 post-write source verification failed')
    print('BODYMIND A342 MOVING WAVES INSTALLED; SQLite and personal files unchanged',flush=True)


# A343 — stronger visible waves. Only visual CSS is changed; A342 source tree is authenticated.
A343_REL=A342_REL
A343_BACKUP=Path('/data/release_packages/BODYMIND_A343_PREUI_A342.py')
A343_STYLE_PATH=Path('/opt/bodymind/family_a343_visible_waves.css')
A343_CSS_SHA256='8e99376e6ce7ee8f59f7f1f53106633261204b7d66cb80492b95f1b1c8c19e97'

def a343_source_from_a342(old:bytes)->tuple[bytes,str]:
    if not A342_BACKUP.is_file() or A342_BACKUP.is_symlink():
        raise RuntimeError('A343 certified A341 source backup unavailable')
    _,prior_sha=a342_source_from_a341(A342_BACKUP.read_bytes())
    if hashlib.sha256(old).hexdigest()!=prior_sha:
        raise RuntimeError('A343 A342 source checksum mismatch')
    css=A343_STYLE_PATH.read_bytes()
    if hashlib.sha256(css).hexdigest()!=A343_CSS_SHA256:
        raise RuntimeError('A343 visible style checksum mismatch')
    if b'</style>' in css or b"'''" in css:
        raise RuntimeError('A343 unsafe style bytes')
    anchor=b'</style>\n</head>'
    if old.count(anchor)!=1:
        raise RuntimeError('A343 stylesheet anchor mismatch')
    new=old.replace(anchor,b'\n'+css+b'\n'+anchor,1)
    compile(new,A343_REL,'exec')
    return new,hashlib.sha256(new).hexdigest()

def a343_matches(root:Path,found:dict[str,str])->bool:
    if len(found)!=214 or A343_REL not in found or not A343_BACKUP.is_file() or A343_BACKUP.is_symlink():
        return False
    old=A343_BACKUP.read_bytes()
    _,expected=a343_source_from_a342(old)
    if found[A343_REL]!=expected:
        return False
    preceding=dict(found)
    preceding[A343_REL]=hashlib.sha256(old).hexdigest()
    return a342_matches(root,preceding)

def maybe_apply_a343_family_ui(root:Path,db:Path)->None:
    found=source_inventory(root)
    if a343_matches(root,found):
        return
    if not a342_matches(root,found):
        return
    sqlite_readonly_check(db)
    target=root/A343_REL
    if target.is_symlink() or not target.is_file():
        raise RuntimeError('A343 unsafe source path')
    old=target.read_bytes()
    new,new_sha=a343_source_from_a342(old)
    if A343_BACKUP.exists():
        if A343_BACKUP.is_symlink() or A343_BACKUP.read_bytes()!=old:
            raise RuntimeError('A343 backup conflict; no application write')
    else:
        if not A343_BACKUP.parent.is_dir() or A343_BACKUP.parent.is_symlink():
            raise RuntimeError('A343 protected source backup directory unavailable')
        with open(A343_BACKUP,'xb') as fh:
            fh.write(old)
            fh.flush()
            os.fsync(fh.fileno())
    temp=None
    try:
        with tempfile.NamedTemporaryFile(prefix='.a343_waves_',suffix='.py',dir=str(target.parent),delete=False) as fh:
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
    if not a343_matches(root,final) or final[A343_REL]!=new_sha:
        raise RuntimeError('A343 post-write manifest mismatch')
    print('BODYMIND A343 VISIBLE WAVES APPLIED; photo links retained; SQLite unchanged',flush=True)

# A344 — boutique editorial finish, verified over active A343; no DB/route/media changes.
A344_REL=A343_REL
A344_BACKUP=Path('/data/release_packages/BODYMIND_A344_PREUI_A343.py')
A344_STYLE_PATH=Path('/opt/bodymind/family_a344_luxury.css')
A344_CSS_SHA256='896a7bbfe4c58caee6c85f9ef50409ed675f6ca76d995a6d6d57c9f8e25799eb'

def a344_source_from_a343(old:bytes)->tuple[bytes,str]:
    if not A343_BACKUP.is_file() or A343_BACKUP.is_symlink():
        raise RuntimeError('A344 verified A342 rollback unavailable')
    _,prior_sha=a343_source_from_a342(A343_BACKUP.read_bytes())
    if hashlib.sha256(old).hexdigest()!=prior_sha:
        raise RuntimeError('A344 A343 source checksum mismatch')
    css=A344_STYLE_PATH.read_bytes()
    if hashlib.sha256(css).hexdigest()!=A344_CSS_SHA256:
        raise RuntimeError('A344 boutique style checksum mismatch')
    if b'</style>' in css or b"'''" in css:
        raise RuntimeError('A344 unsafe style delimiter')
    anchor=b'</style>\n</head>'
    if old.count(anchor)!=1:
        raise RuntimeError('A344 stylesheet anchor mismatch')
    new=old.replace(anchor,b'\n'+css+b'\n'+anchor,1)
    compile(new,A344_REL,'exec')
    return new,hashlib.sha256(new).hexdigest()

def a344_matches(root:Path,found:dict[str,str])->bool:
    if len(found)!=214 or A344_REL not in found or not A344_BACKUP.is_file() or A344_BACKUP.is_symlink():
        return False
    old=A344_BACKUP.read_bytes()
    _,expected=a344_source_from_a343(old)
    if found[A344_REL]!=expected:
        return False
    preceding=dict(found)
    preceding[A344_REL]=hashlib.sha256(old).hexdigest()
    return a343_matches(root,preceding)

def maybe_apply_a344_family_ui(root:Path,db:Path)->None:
    found=source_inventory(root)
    if a344_matches(root,found):
        return
    if not a343_matches(root,found):
        return
    sqlite_readonly_check(db)
    target=root/A344_REL
    if target.is_symlink() or not target.is_file():
        raise RuntimeError('A344 unsafe target source path')
    old=target.read_bytes()
    new,new_sha=a344_source_from_a343(old)
    if A344_BACKUP.exists():
        if A344_BACKUP.is_symlink() or A344_BACKUP.read_bytes()!=old:
            raise RuntimeError('A344 rollback conflict, no source write')
    else:
        if not A344_BACKUP.parent.is_dir() or A344_BACKUP.parent.is_symlink():
            raise RuntimeError('A344 protected rollback directory unavailable')
        with open(A344_BACKUP,'xb') as fh:
            fh.write(old)
            fh.flush()
            os.fsync(fh.fileno())
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(prefix='.a344_boutique_',suffix='.py',dir=str(target.parent),delete=False) as fh:
            tmp=Path(fh.name)
            fh.write(new)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp,stat.S_IMODE(target.stat().st_mode))
        os.replace(str(tmp),str(target))
        tmp=None
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    final=source_inventory(root)
    if not a344_matches(root,final) or final[A344_REL]!=new_sha:
        raise RuntimeError('A344 post-write manifest mismatch')
    print('BODYMIND A344 BOUTIQUE VISUAL APPLIED; links and video retained; SQLite unchanged',flush=True)

# Emergency rollback switch: A344 image can restore its verified A343 source
# without touching SQLite or the other 213 protected application sources.
def maybe_recover_a344_to_a343(root:Path,db:Path)->bool:
    if os.environ.get('BODYMIND_A344_RECOVER_A343')!='1':
        return False
    found=source_inventory(root)
    if a343_matches(root,found):
        print('BODYMIND A344 RECOVERY: verified A343 already active; database unchanged',flush=True)
        return True
    if not a344_matches(root,found):
        raise RuntimeError('A344 recovery declined: source not exactly A344')
    sqlite_readonly_check(db)
    target=root/A344_REL
    if target.is_symlink() or not target.is_file():
        raise RuntimeError('A344 recovery unsafe target')
    old=A344_BACKUP.read_bytes()
    temp=None
    try:
        with tempfile.NamedTemporaryFile(prefix='.a344_recover_',suffix='.py',dir=str(target.parent),delete=False) as fh:
            temp=Path(fh.name)
            fh.write(old)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(temp,stat.S_IMODE(target.stat().st_mode))
        os.replace(str(temp),str(target))
        temp=None
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
    if not a343_matches(root,source_inventory(root)):
        raise RuntimeError('A344 recovery did not restore verified A343')
    print('BODYMIND A344 RECOVERY SUCCESS: verified A343 restored; SQLite and documents unchanged',flush=True)
    return True

# A345 — real mobile full-frame hero; checked over exact protected A344 source.
A345_REL=A344_REL
A345_BACKUP=Path('/data/release_packages/BODYMIND_A345_PREUI_A344.py')
A345_CSS_PATH=Path('/opt/bodymind/family_a345_fullframe.css')
A345_JS_PATH=Path('/opt/bodymind/family_a345_fullframe.js')
A345_CSS_SHA256='3c915aae2b019c0cc495a47dd28f2dd18b3c06cea1fbe9f719e7e21ae0b8e5fc'
A345_JS_SHA256='b9580e4586893226471cf07c4dbee0ffa61a369f893622b4847326278c942ab3'
A345_SCRIPT_ANCHOR=b'\n</script>\n<section class="section"><div class="panel personal">'

def a345_source_from_a344(old:bytes)->tuple[bytes,str]:
    if not A344_BACKUP.is_file() or A344_BACKUP.is_symlink():
        raise RuntimeError('A345 protected A343 source backup missing')
    _,previous_sha=a344_source_from_a343(A344_BACKUP.read_bytes())
    if hashlib.sha256(old).hexdigest()!=previous_sha:
        raise RuntimeError('A345 unexpected A344 source digest')
    css=A345_CSS_PATH.read_bytes()
    js=A345_JS_PATH.read_bytes()
    if hashlib.sha256(css).hexdigest()!=A345_CSS_SHA256 or hashlib.sha256(js).hexdigest()!=A345_JS_SHA256:
        raise RuntimeError('A345 public asset checksum mismatch')
    if b'</style>' in css or b"'''" in css or b'</script>' in js or b"'''" in js:
        raise RuntimeError('A345 unsafe template delimiter')
    anchor=b'</style>\n</head>'
    if old.count(anchor)!=1 or old.count(A345_SCRIPT_ANCHOR)!=1:
        raise RuntimeError('A345 unique template anchors absent')
    new=old.replace(anchor,b'\n'+css+b'\n'+anchor,1)
    replacement=b'\n</script>\n<script id="bodymind-a345-video">\n'+js+b'\n</script>\n<section class="section"><div class="panel personal">'
    new=new.replace(A345_SCRIPT_ANCHOR,replacement,1)
    compile(new,A345_REL,'exec')
    return new,hashlib.sha256(new).hexdigest()

def a345_matches(root:Path,found:dict[str,str])->bool:
    if len(found)!=214 or A345_REL not in found or not A345_BACKUP.is_file() or A345_BACKUP.is_symlink():
        return False
    old=A345_BACKUP.read_bytes()
    _,expected_sha=a345_source_from_a344(old)
    if found[A345_REL]!=expected_sha:
        return False
    previous=dict(found)
    previous[A345_REL]=hashlib.sha256(old).hexdigest()
    return a344_matches(root,previous)

def maybe_apply_a345_family_ui(root:Path,db:Path)->None:
    found=source_inventory(root)
    if a345_matches(root,found):
        return
    if not a344_matches(root,found):
        return
    sqlite_readonly_check(db)
    target=root/A345_REL
    if target.is_symlink() or not target.is_file():
        raise RuntimeError('A345 unsafe target')
    old=target.read_bytes()
    new,new_sha=a345_source_from_a344(old)
    if A345_BACKUP.exists():
        if A345_BACKUP.is_symlink() or A345_BACKUP.read_bytes()!=old:
            raise RuntimeError('A345 rollback source conflict')
    else:
        if not A345_BACKUP.parent.is_dir() or A345_BACKUP.parent.is_symlink():
            raise RuntimeError('A345 protected rollback directory missing')
        with open(A345_BACKUP,'xb') as fh:
            fh.write(old)
            fh.flush()
            os.fsync(fh.fileno())
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(prefix='.a345_video_',suffix='.py',dir=str(target.parent),delete=False) as fh:
            tmp=Path(fh.name)
            fh.write(new)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp,stat.S_IMODE(target.stat().st_mode))
        os.replace(str(tmp),str(target))
        tmp=None
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    final=source_inventory(root)
    if not a345_matches(root,final) or final[A345_REL]!=new_sha:
        raise RuntimeError('A345 post-write source verification failed')
    print('BODYMIND A345 FULL FRAME HERO APPLIED; SQLite and personal documents unchanged',flush=True)

def maybe_recover_a345_to_a344(root:Path,db:Path)->bool:
    if os.environ.get('BODYMIND_A345_RECOVER_A344')!='1':
        return False
    found=source_inventory(root)
    if a344_matches(root,found):
        print('BODYMIND A345 RECOVERY: A344 already active',flush=True)
        return True
    if not a345_matches(root,found):
        raise RuntimeError('A345 recovery declined: source not exact A345')
    sqlite_readonly_check(db)
    target=root/A345_REL
    if target.is_symlink() or not target.is_file():
        raise RuntimeError('A345 recovery unsafe target')
    old=A345_BACKUP.read_bytes()
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(prefix='.a345_recover_',suffix='.py',dir=str(target.parent),delete=False) as fh:
            tmp=Path(fh.name)
            fh.write(old)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp,stat.S_IMODE(target.stat().st_mode))
        os.replace(str(tmp),str(target))
        tmp=None
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    if not a344_matches(root,source_inventory(root)):
        raise RuntimeError('A345 rollback verification failed')
    print('BODYMIND A345 RECOVERY PASS: A344 verified; SQLite unchanged',flush=True)
    return True

# A346 — proofed full-frame mobile + boutique editorial finish on exact A345.
A346_REL=A345_REL
A346_BACKUP=Path('/data/release_packages/BODYMIND_A346_PREUI_A345.py')
A346_CSS_PATH=Path('/opt/bodymind/family_a346_editorial.css')
A346_CSS_SHA256='d3f105233e1496dded3aaea599c7361e513dcc4987fa3b662d330a8df1d566ab'

def a346_source_from_a345(old:bytes)->tuple[bytes,str]:
    if not A345_BACKUP.is_file() or A345_BACKUP.is_symlink():
        raise RuntimeError('A346 requires protected A344 source backup')
    _,prior_sha=a345_source_from_a344(A345_BACKUP.read_bytes())
    if hashlib.sha256(old).hexdigest()!=prior_sha:
        raise RuntimeError('A346 A345 exact source checksum mismatch')
    css=A346_CSS_PATH.read_bytes()
    if hashlib.sha256(css).hexdigest()!=A346_CSS_SHA256:
        raise RuntimeError('A346 visual stylesheet checksum mismatch')
    if b'</style>' in css or b"'''" in css:
        raise RuntimeError('A346 unsafe template delimiter')
    anchor=b'</style>\n</head>'
    if old.count(anchor)!=1:
        raise RuntimeError('A346 stylesheet insertion anchor unavailable')
    new=old.replace(anchor,b'\n'+css+b'\n'+anchor,1)
    compile(new,A346_REL,'exec')
    return new,hashlib.sha256(new).hexdigest()

def a346_matches(root:Path,found:dict[str,str])->bool:
    if len(found)!=214 or A346_REL not in found or not A346_BACKUP.is_file() or A346_BACKUP.is_symlink():
        return False
    old=A346_BACKUP.read_bytes()
    _,expected_sha=a346_source_from_a345(old)
    if found[A346_REL]!=expected_sha:
        return False
    preceding=dict(found)
    preceding[A346_REL]=hashlib.sha256(old).hexdigest()
    return a345_matches(root,preceding)

def maybe_apply_a346_family_ui(root:Path,db:Path)->None:
    found=source_inventory(root)
    if a346_matches(root,found):
        return
    if not a345_matches(root,found):
        return
    sqlite_readonly_check(db)
    target=root/A346_REL
    if target.is_symlink() or not target.is_file():
        raise RuntimeError('A346 unsafe source target')
    old=target.read_bytes()
    new,new_sha=a346_source_from_a345(old)
    if A346_BACKUP.exists():
        if A346_BACKUP.is_symlink() or A346_BACKUP.read_bytes()!=old:
            raise RuntimeError('A346 source rollback conflict')
    else:
        if not A346_BACKUP.parent.is_dir() or A346_BACKUP.parent.is_symlink():
            raise RuntimeError('A346 protected backup directory unavailable')
        with open(A346_BACKUP,'xb') as fh:
            fh.write(old)
            fh.flush()
            os.fsync(fh.fileno())
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(prefix='.a346_editorial_',suffix='.py',dir=str(target.parent),delete=False) as fh:
            tmp=Path(fh.name)
            fh.write(new)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp,stat.S_IMODE(target.stat().st_mode))
        os.replace(str(tmp),str(target))
        tmp=None
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    final=source_inventory(root)
    if not a346_matches(root,final) or final[A346_REL]!=new_sha:
        raise RuntimeError('A346 post-apply source verification failed')
    print('BODYMIND A346 EDITORIAL FAMILY UI APPLIED; A345 video intact; DB unchanged',flush=True)

def maybe_recover_a346_to_a345(root:Path,db:Path)->bool:
    if os.environ.get('BODYMIND_A346_RECOVER_A345')!='1':
        return False
    found=source_inventory(root)
    if a345_matches(root,found):
        print('BODYMIND A346 RECOVERY: A345 already active',flush=True)
        return True
    if not a346_matches(root,found):
        raise RuntimeError('A346 recovery declined: source mismatch')
    sqlite_readonly_check(db)
    target=root/A346_REL
    if target.is_symlink() or not target.is_file():
        raise RuntimeError('A346 unsafe recovery target')
    old=A346_BACKUP.read_bytes()
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(prefix='.a346_recover_',suffix='.py',dir=str(target.parent),delete=False) as fh:
            tmp=Path(fh.name)
            fh.write(old)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp,stat.S_IMODE(target.stat().st_mode))
        os.replace(str(tmp),str(target))
        tmp=None
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    if not a345_matches(root,source_inventory(root)):
        raise RuntimeError('A346 recovery failed source verification')
    print('BODYMIND A346 RECOVERY SUCCESS: verified A345 restored; DB unchanged',flush=True)
    return True

# A347 — cinematic personal greeting over uncut family video, visual-only.
A347_REL=A346_REL
A347_BACKUP=Path('/data/release_packages/BODYMIND_A347_PREUI_A346.py')
A347_CSS_PATH=Path('/opt/bodymind/family_a347_overlay.css')
A347_CSS_SHA256='df14c0503d1a7f85a4f0680f7c7583c9c83753f487c0943941b6218d2ec5870e'

def a347_source_from_a346(old:bytes)->tuple[bytes,str]:
    if not A346_BACKUP.is_file() or A346_BACKUP.is_symlink():
        raise RuntimeError('A347 required A345 source backup missing')
    _,prior_sha=a346_source_from_a345(A346_BACKUP.read_bytes())
    if hashlib.sha256(old).hexdigest()!=prior_sha:
        raise RuntimeError('A347 A346 exact source digest mismatch')
    css=A347_CSS_PATH.read_bytes()
    if hashlib.sha256(css).hexdigest()!=A347_CSS_SHA256:
        raise RuntimeError('A347 overlay asset checksum mismatch')
    if b'</style>' in css or b"'''" in css:
        raise RuntimeError('A347 unsafe CSS delimiter')
    anchor=b'</style>\n</head>'
    if old.count(anchor)!=1:
        raise RuntimeError('A347 unique style anchor unavailable')
    new=old.replace(anchor,b'\n'+css+b'\n'+anchor,1)
    compile(new,A347_REL,'exec')
    return new,hashlib.sha256(new).hexdigest()

def a347_matches(root:Path,found:dict[str,str])->bool:
    if len(found)!=214 or A347_REL not in found or not A347_BACKUP.is_file() or A347_BACKUP.is_symlink():
        return False
    old=A347_BACKUP.read_bytes()
    _,new_sha=a347_source_from_a346(old)
    if found[A347_REL]!=new_sha:
        return False
    previous=dict(found)
    previous[A347_REL]=hashlib.sha256(old).hexdigest()
    return a346_matches(root,previous)

def maybe_apply_a347_family_ui(root:Path,db:Path)->None:
    found=source_inventory(root)
    if a347_matches(root,found):
        return
    if not a346_matches(root,found):
        return
    sqlite_readonly_check(db)
    target=root/A347_REL
    if target.is_symlink() or not target.is_file():
        raise RuntimeError('A347 unsafe source target')
    old=target.read_bytes()
    new,new_sha=a347_source_from_a346(old)
    if A347_BACKUP.exists():
        if A347_BACKUP.is_symlink() or A347_BACKUP.read_bytes()!=old:
            raise RuntimeError('A347 rollback copy conflict')
    else:
        if not A347_BACKUP.parent.is_dir() or A347_BACKUP.parent.is_symlink():
            raise RuntimeError('A347 protected rollback path absent')
        with open(A347_BACKUP,'xb') as fh:
            fh.write(old)
            fh.flush()
            os.fsync(fh.fileno())
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(prefix='.a347_overlay_',suffix='.py',dir=str(target.parent),delete=False) as fh:
            tmp=Path(fh.name)
            fh.write(new)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp,stat.S_IMODE(target.stat().st_mode))
        os.replace(str(tmp),str(target))
        tmp=None
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    final=source_inventory(root)
    if not a347_matches(root,final) or final[A347_REL]!=new_sha:
        raise RuntimeError('A347 source post-write verification failed')
    print('BODYMIND A347 CINEMATIC GREETING OVER VIDEO APPLIED; SQLite untouched',flush=True)

def maybe_recover_a347_to_a346(root:Path,db:Path)->bool:
    if os.environ.get('BODYMIND_A347_RECOVER_A346')!='1':
        return False
    found=source_inventory(root)
    if a346_matches(root,found):
        print('BODYMIND A347 RECOVERY: verified A346 already active',flush=True)
        return True
    if not a347_matches(root,found):
        raise RuntimeError('A347 recovery declined: unexpected source digest')
    sqlite_readonly_check(db)
    target=root/A347_REL
    if target.is_symlink() or not target.is_file():
        raise RuntimeError('A347 recovery unsafe target')
    old=A347_BACKUP.read_bytes()
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(prefix='.a347_recover_',suffix='.py',dir=str(target.parent),delete=False) as fh:
            tmp=Path(fh.name)
            fh.write(old)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp,stat.S_IMODE(target.stat().st_mode))
        os.replace(str(tmp),str(target))
        tmp=None
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    if not a346_matches(root,source_inventory(root)):
        raise RuntimeError('A347 recovery did not restore exact A346')
    print('BODYMIND A347 RECOVERY PASS: A346 verified, SQLite unchanged',flush=True)
    return True

# A348 — restore mobile five-item dock geometry while preserving A347 cinema hero.
A348_REL=A347_REL
A348_BACKUP=Path('/data/release_packages/BODYMIND_A348_PREUI_A347.py')
A348_CSS_PATH=Path('/opt/bodymind/family_a348_navfix.css')
A348_CSS_SHA256='b12c5790a43972eb621ac8f42d2cc6b6ccae6e77ed6d4eca56dc793854a7a2fe'

def a348_source_from_a347(old:bytes)->tuple[bytes,str]:
    if not A347_BACKUP.is_file() or A347_BACKUP.is_symlink():
        raise RuntimeError('A348 requires exact protected A346 source')
    _,prior_sha=a347_source_from_a346(A347_BACKUP.read_bytes())
    if hashlib.sha256(old).hexdigest()!=prior_sha:
        raise RuntimeError('A348 current source is not exact A347')
    css=A348_CSS_PATH.read_bytes()
    if hashlib.sha256(css).hexdigest()!=A348_CSS_SHA256:
        raise RuntimeError('A348 dock CSS checksum mismatch')
    if b'</style>' in css or b"'''" in css:
        raise RuntimeError('A348 unsafe CSS delimiter')
    anchor=b'</style>\n</head>'
    if old.count(anchor)!=1:
        raise RuntimeError('A348 stylesheet anchor mismatch')
    new=old.replace(anchor,b'\n'+css+b'\n'+anchor,1)
    compile(new,A348_REL,'exec')
    return new,hashlib.sha256(new).hexdigest()

def a348_matches(root:Path,found:dict[str,str])->bool:
    if len(found)!=214 or A348_REL not in found or not A348_BACKUP.is_file() or A348_BACKUP.is_symlink():
        return False
    old=A348_BACKUP.read_bytes()
    _,expected_sha=a348_source_from_a347(old)
    if found[A348_REL]!=expected_sha:
        return False
    preceding=dict(found)
    preceding[A348_REL]=hashlib.sha256(old).hexdigest()
    return a347_matches(root,preceding)

def maybe_apply_a348_family_ui(root:Path,db:Path)->None:
    found=source_inventory(root)
    if a348_matches(root,found):
        return
    if not a347_matches(root,found):
        return
    sqlite_readonly_check(db)
    target=root/A348_REL
    if target.is_symlink() or not target.is_file():
        raise RuntimeError('A348 unsafe target')
    old=target.read_bytes()
    new,new_sha=a348_source_from_a347(old)
    if A348_BACKUP.exists():
        if A348_BACKUP.is_symlink() or A348_BACKUP.read_bytes()!=old:
            raise RuntimeError('A348 protected rollback collision')
    else:
        if not A348_BACKUP.parent.is_dir() or A348_BACKUP.parent.is_symlink():
            raise RuntimeError('A348 rollback directory unavailable')
        with open(A348_BACKUP,'xb') as fh:
            fh.write(old)
            fh.flush()
            os.fsync(fh.fileno())
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(prefix='.a348_dock_',suffix='.py',dir=str(target.parent),delete=False) as fh:
            tmp=Path(fh.name)
            fh.write(new)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp,stat.S_IMODE(target.stat().st_mode))
        os.replace(str(tmp),str(target))
        tmp=None
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    final=source_inventory(root)
    if not a348_matches(root,final) or final[A348_REL]!=new_sha:
        raise RuntimeError('A348 source post-write verification failed')
    print('BODYMIND A348 MOBILE NAV CORRECTED; 5 TABS; DATA UNCHANGED',flush=True)

def maybe_recover_a348_to_a347(root:Path,db:Path)->bool:
    if os.environ.get('BODYMIND_A348_RECOVER_A347')!='1':
        return False
    found=source_inventory(root)
    if a347_matches(root,found):
        print('BODYMIND A348 RECOVERY: A347 already active',flush=True)
        return True
    if not a348_matches(root,found):
        raise RuntimeError('A348 recovery declined: source mismatch')
    sqlite_readonly_check(db)
    target=root/A348_REL
    if target.is_symlink() or not target.is_file():
        raise RuntimeError('A348 recovery unsafe target')
    old=A348_BACKUP.read_bytes()
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(prefix='.a348_recover_',suffix='.py',dir=str(target.parent),delete=False) as fh:
            tmp=Path(fh.name)
            fh.write(old)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp,stat.S_IMODE(target.stat().st_mode))
        os.replace(str(tmp),str(target))
        tmp=None
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    if not a347_matches(root,source_inventory(root)):
        raise RuntimeError('A348 recovery did not restore exact A347')
    print('BODYMIND A348 RECOVERY SUCCESS: verified A347 restored, SQLite untouched',flush=True)
    return True

# A349 — one curated UI layer replaces eight post-A340 CSS append-only patches.
# Existing JS playback and verified photo/social link script remain identical.
A349_REL=A348_REL
A349_BACKUP=Path('/data/release_packages/BODYMIND_A349_PREUI_A348.py')
A349_CSS_PATH=Path('/opt/bodymind/family_a349_atelier.css')
A349_CSS_SHA256='2363a2ba8f2f343d82846cddff4fe084a5ffa4e0c01623acd72715fb6b3ebc06'
A349_JS_PATH=Path('/opt/bodymind/family_a349_native_ratio.js')
A349_JS_SHA256='64d1871b0deb7a7c17f41dd725c2e9d7f17f8c2fb94a0917891b986da16b13c9'

def a349_consolidate_styles(old:bytes,layers:list[bytes],curated:bytes)->bytes:
    # Source is already verified as exact A348 before use. Each CSS span must occur once.
    if len(layers)!=8 or any(not layer for layer in layers):
        raise RuntimeError('A349 expected eight complete legacy CSS layers')
    if b'</style>' in curated or b"'''" in curated:
        raise RuntimeError('A349 stylesheet has unsafe delimiter')
    new=old
    for layer in layers:
        needle=b'\n'+layer+b'\n'
        if new.count(needle)!=1:
            raise RuntimeError('A349 CSS inventory mismatch, source preserved')
        new=new.replace(needle,b'\n',1)
    anchor=b'</style>\n</head>'
    if new.count(anchor)!=1:
        raise RuntimeError('A349 missing unique style anchor')
    # A341 contains working verified media link styles and waves;
    # A342 contains accessible motion. Both become part of ONE curated insertion.
    consolidated=b'\n/* BODYMIND A349 CONSOLIDATED STYLE */\n'+layers[0]+b'\n'+layers[1]+b'\n'+curated+b'\n'
    new=new.replace(anchor,consolidated+anchor,1)
    return new

def a349_source_from_a348(old:bytes)->tuple[bytes,str]:
    if not A348_BACKUP.is_file() or A348_BACKUP.is_symlink():
        raise RuntimeError('A349 requires protected A347 rollback source')
    _,prior_sha=a348_source_from_a347(A348_BACKUP.read_bytes())
    if hashlib.sha256(old).hexdigest()!=prior_sha:
        raise RuntimeError('A349 unexpected A348 source checksum')
    curated=A349_CSS_PATH.read_bytes()
    if hashlib.sha256(curated).hexdigest()!=A349_CSS_SHA256:
        raise RuntimeError('A349 studio stylesheet checksum mismatch')
    layers=[p.read_bytes() for p in (
        A341_STYLE_PATH,A342_STYLE_PATH,A343_STYLE_PATH,A344_STYLE_PATH,
        A345_CSS_PATH,A346_CSS_PATH,A347_CSS_PATH,A348_CSS_PATH
    )]
    new=a349_consolidate_styles(old,layers,curated)
    js=A349_JS_PATH.read_bytes()
    if hashlib.sha256(js).hexdigest()!=A349_JS_SHA256 or b'</script>' in js or b"'''" in js:
        raise RuntimeError('A349 native ratio helper verification failed')
    script_anchor=b'</script>\n<section class="section"><div class="panel personal">'
    if new.count(script_anchor)!=1:
        raise RuntimeError('A349 unique video script anchor absent')
    script=b'</script>\n<script id="bodymind-a349-native-ratio">\n'+js+b'\n</script>\n<section class="section"><div class="panel personal">'
    new=new.replace(script_anchor,script,1)
    compile(new,A349_REL,'exec')
    return new,hashlib.sha256(new).hexdigest()

def a349_matches(root:Path,found:dict[str,str])->bool:
    if len(found)!=214 or A349_REL not in found or not A349_BACKUP.is_file() or A349_BACKUP.is_symlink():
        return False
    old=A349_BACKUP.read_bytes()
    _,new_sha=a349_source_from_a348(old)
    if found[A349_REL]!=new_sha:
        return False
    prior=dict(found)
    prior[A349_REL]=hashlib.sha256(old).hexdigest()
    return a348_matches(root,prior)

def maybe_apply_a349_family_ui(root:Path,db:Path)->None:
    found=source_inventory(root)
    if a349_matches(root,found):
        return
    if not a348_matches(root,found):
        return
    sqlite_readonly_check(db)
    target=root/A349_REL
    if target.is_symlink() or not target.is_file():
        raise RuntimeError('A349 protected source path invalid')
    old=target.read_bytes()
    new,new_sha=a349_source_from_a348(old)
    if A349_BACKUP.exists():
        if A349_BACKUP.is_symlink() or A349_BACKUP.read_bytes()!=old:
            raise RuntimeError('A349 protected rollback source conflict')
    else:
        if not A349_BACKUP.parent.is_dir() or A349_BACKUP.parent.is_symlink():
            raise RuntimeError('A349 rollback directory absent')
        with open(A349_BACKUP,'xb') as fh:
            fh.write(old)
            fh.flush()
            os.fsync(fh.fileno())
    temp=None
    try:
        with tempfile.NamedTemporaryFile(prefix='.a349_atelier_',suffix='.py',dir=str(target.parent),delete=False) as fh:
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
    if not a349_matches(root,final) or final[A349_REL]!=new_sha:
        raise RuntimeError('A349 post-install source lock mismatch')
    print('BODYMIND A349 BOUTIQUE CURATED UI APPLIED; OLD CSS LAYERS CONSOLIDATED; SQLITE UNCHANGED',flush=True)

def maybe_recover_a349_to_a348(root:Path,db:Path)->bool:
    if os.environ.get('BODYMIND_A349_RECOVER_A348')!='1':
        return False
    found=source_inventory(root)
    if a348_matches(root,found):
        print('BODYMIND A349 RECOVERY: already verified A348',flush=True)
        return True
    if not a349_matches(root,found):
        raise RuntimeError('A349 recovery declined: source digest unexpected')
    sqlite_readonly_check(db)
    target=root/A349_REL
    if target.is_symlink() or not target.is_file():
        raise RuntimeError('A349 recovery unsafe target')
    old=A349_BACKUP.read_bytes()
    temp=None
    try:
        with tempfile.NamedTemporaryFile(prefix='.a349_recover_',suffix='.py',dir=str(target.parent),delete=False) as fh:
            temp=Path(fh.name)
            fh.write(old)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(temp,stat.S_IMODE(target.stat().st_mode))
        os.replace(str(temp),str(target))
        temp=None
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
    if not a348_matches(root,source_inventory(root)):
        raise RuntimeError('A349 recovery failed to verify exact A348')
    print('BODYMIND A349 RECOVERY PASS: A348 restored, no data changes',flush=True)
    return True

# A350 - verified media mapping + scoped accessibility layer.
# This is a surgical UI-only patch of the exact A349 source on the volume.
# All administrative routes, IDs, SQLite, attachments and private files are untouched.
A350_REL=A349_REL
A350_BACKUP=Path('/data/release_packages/BODYMIND_A350_PREUI_A349.py')
A350_CSS_PATH=Path('/opt/bodymind/family_a350_signature.css')
A350_JS_PATH=Path('/opt/bodymind/family_a350_verified_gallery.js')
A350_CSS_BLOB='1d1d073b36af36a0027ad33be2d17f18b07251cd'
A350_JS_BLOB='8c9d90257a3a4793b4c5ba627536195745207e8f'

def a350_git_blob(data:bytes)->str:
    return hashlib.sha1(b'blob '+str(len(data)).encode('ascii')+b'\x00'+data).hexdigest()

def a350_assets()->tuple[bytes,bytes]:
    css=A350_CSS_PATH.read_bytes()
    js=A350_JS_PATH.read_bytes()
    if a350_git_blob(css)!=A350_CSS_BLOB or a350_git_blob(js)!=A350_JS_BLOB:
        raise RuntimeError('A350 asset fingerprint mismatch')
    if b'</style>' in css or b"'''" in css or b'</script>' in js or b"'''" in js:
        raise RuntimeError('A350 unsafe template delimiter')
    if b'verifiedImageLinks' not in js or b'bm350-gallery-footer' not in css:
        raise RuntimeError('A350 required public gallery components unavailable')
    return css,js

def a350_transform_html(old:bytes,old_js:bytes,css:bytes,js:bytes)->bytes:
    # The A341 guesswork must be REMOVED, not shadowed by another handler.
    marker=b'<script id="bodymind-media-links">\n'+old_js+b'\n</script>'
    style_anchor=b'</style>\n</head>'
    if old.count(marker)!=1 or old.count(style_anchor)!=1:
        raise RuntimeError('A350 expected verified template anchors absent')
    new=old.replace(marker,
        b'<script id="bodymind-media-links-a350">\n'+js+b'\n</script>',1)
    new=new.replace(style_anchor,b'\n/* BODYMIND A350 SIGNATURE */\n'+css+b'\n'+style_anchor,1)
    compile(new,A350_REL,'exec')
    return new

# A350 backend privacy guard based on verified A349 production module SHA.
# Pure transform: no database writes, no document access, no changes to business rules.
A350_A349_LIVE_MODULE_SHA='12391e9f3fdc3dd92f91325c26f7e695cab28cbc771a721165708c2dfc4c9021'

def a350_secure_document_route(source:bytes,expected_sha:str=A350_A349_LIVE_MODULE_SHA)->bytes:
    if hashlib.sha256(source).hexdigest()!=expected_sha:
        raise RuntimeError('A350 protected family source SHA mismatch')
    import ast
    text=source.decode('utf-8')
    tree=ast.parse(text)
    nodes=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='bodymind_doc']
    if len(nodes)!=1:
        raise RuntimeError('A350 document route missing or duplicated')
    original=ast.get_source_segment(text,nodes[0])
    if not original or text.count(original)!=1:
        raise RuntimeError('A350 document route anchor ambiguous')
    needle='if not d: abort(404)'
    if original.count(needle)!=1 or 'visibile' in original:
        raise RuntimeError('A350 unexpected document access implementation')
    line=next(x for x in original.splitlines() if needle in x)
    indent=line[:line.index(needle)]
    guard=needle+'\n'+indent+"if 'visibile' in dcols and int(d['visibile'] or 0) != 1: abort(404)"
    text=text.replace(original,original.replace(needle,guard,1),1)
    false_success="{% if request.args.get('upload')=='ok' %}"
    if text.count(false_success)!=1:
        raise RuntimeError('A350 misleading upload banner anchor unavailable')
    start=text.index(false_success)
    stop=text.find('{% endif %}',start)
    if stop<0 or stop-start>500:
        raise RuntimeError('A350 unexpected upload confirmation template')
    text=text[:start]+text[stop+len('{% endif %}'):]
    result=text.encode('utf-8')
    compile(result,A350_REL,'exec')
    return result

def a350_expected_from_a349(old:bytes)->tuple[bytes,str]:
    if not A349_BACKUP.is_file() or A349_BACKUP.is_symlink():
        raise RuntimeError('A350 required A349 protected backup missing')
    _,prior_sha=a349_source_from_a348(A349_BACKUP.read_bytes())
    if hashlib.sha256(old).hexdigest()!=prior_sha:
        raise RuntimeError('A350 source differs from exact A349')
    css,js=a350_assets()
    guarded=a350_secure_document_route(old)
    new=a350_transform_html(guarded,A341_LINKS_PATH.read_bytes(),css,js)
    return new,hashlib.sha256(new).hexdigest()

def a350_matches(root:Path,found:dict[str,str])->bool:
    if len(found)!=214 or A350_REL not in found or not A350_BACKUP.is_file() or A350_BACKUP.is_symlink():
        return False
    old=A350_BACKUP.read_bytes()
    _,expected=a350_expected_from_a349(old)
    if found[A350_REL]!=expected:
        return False
    previous=dict(found)
    previous[A350_REL]=hashlib.sha256(old).hexdigest()
    return a349_matches(root,previous)

def maybe_apply_a350_family_ui(root:Path,db:Path)->None:
    found=source_inventory(root)
    if a350_matches(root,found):
        return
    if not a349_matches(root,found):
        return
    # Database validation is strictly read-only; not even a schema migration.
    sqlite_readonly_check(db)
    target=root/A350_REL
    if target.is_symlink() or not target.is_file():
        raise RuntimeError('A350 unsafe source target')
    old=target.read_bytes()
    new,new_sha=a350_expected_from_a349(old)
    if A350_BACKUP.exists():
        if A350_BACKUP.is_symlink() or A350_BACKUP.read_bytes()!=old:
            raise RuntimeError('A350 rollback copy conflict')
    else:
        if not A350_BACKUP.parent.is_dir() or A350_BACKUP.parent.is_symlink():
            raise RuntimeError('A350 protected backup directory unavailable')
        with open(A350_BACKUP,'xb') as fh:
            fh.write(old)
            fh.flush()
            os.fsync(fh.fileno())
    temp=None
    try:
        with tempfile.NamedTemporaryFile(prefix='.a350_signature_',suffix='.py',
                                          dir=str(target.parent),delete=False) as fh:
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
    if not a350_matches(root,final) or final[A350_REL]!=new_sha:
        raise RuntimeError('A350 post-install source fingerprint mismatch')
    print('BODYMIND A350 SIGNATURE UI APPLIED; EXISTING SQLITE AND PRIVATE DATA UNCHANGED',flush=True)

def maybe_recover_a350_to_a349(root:Path,db:Path)->bool:
    if os.environ.get('BODYMIND_A350_RECOVER_A349')!='1':
        return False
    found=source_inventory(root)
    if a349_matches(root,found):
        print('BODYMIND A350 RECOVERY: A349 already active',flush=True)
        return True
    if not a350_matches(root,found):
        raise RuntimeError('A350 recovery declined: nonmatching source')
    sqlite_readonly_check(db)
    target=root/A350_REL
    if target.is_symlink() or not target.is_file():
        raise RuntimeError('A350 recovery unsafe target')
    old=A350_BACKUP.read_bytes()
    temp=None
    try:
        with tempfile.NamedTemporaryFile(prefix='.a350_recover_',suffix='.py',
                                          dir=str(target.parent),delete=False) as fh:
            temp=Path(fh.name)
            fh.write(old)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(temp,stat.S_IMODE(target.stat().st_mode))
        os.replace(str(temp),str(target))
        temp=None
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
    if not a349_matches(root,source_inventory(root)):
        raise RuntimeError('A350 rollback fingerprint failed')
    print('BODYMIND A350 RECOVERY PASS: A349 exact source restored, no data change',flush=True)
    return True


# A351 SUNRISE: strictly cosmetic additive layer over the *deployed* A350
# source. This never edits document records, user permissions or video files.
A351_REL=A350_REL
A351_A350_LIVE_SHA='8bbb503c24242e88aa97bc1eb973f92e69aa395df27c00d38f6809c9435532d1'
A351_BACKUP=Path('/data/release_packages/BODYMIND_A351_PREUI_A350.py')
A351_CSS_PATH=Path('/opt/bodymind/family_a351_sunrise.css')
A351_JS_PATH=Path('/opt/bodymind/family_a351_sunrise.js')
A351_CSS_BLOB='be65b405156905c772c3895e5210b32375da1530'
A351_JS_BLOB='8f91b985657d86142c7d95b673eb55ab905c3bb3'

def a351_assets()->tuple[bytes,bytes]:
    css=A351_CSS_PATH.read_bytes()
    js=A351_JS_PATH.read_bytes()
    if a350_git_blob(css)!=A351_CSS_BLOB or a350_git_blob(js)!=A351_JS_BLOB:
        raise RuntimeError('A351 design assets changed after review')
    if any(k in css for k in (b'</style>',b"'''")) or any(k in js for k in (b'</script>',b"'''")):
        raise RuntimeError('A351 unsafe inline template delimiter')
    return css,js

def a351_expected_from_a350(old:bytes)->tuple[bytes,str]:
    if hashlib.sha256(old).hexdigest()!=A351_A350_LIVE_SHA:
        raise RuntimeError('A351 source SHA not equal to deployed A350')
    css,js=a351_assets()
    # Never depend on globally ambiguous HTML closing tags. A350 contains
    # multiple independent HTML views; anchor to the single hashed CSS/JS payload
    # injected only into the authenticated family page in the exact A350 release.
    old_css=A350_CSS_PATH.read_bytes()
    old_js=A350_JS_PATH.read_bytes()
    if old.count(old_css)!=1 or old.count(old_js)!=1:
        raise RuntimeError('A351 verified family CSS/JS asset anchors missing or duplicated')
    if b'BODYMIND A351 SUNRISE' in old or b'BODYMIND A351 DOCK' in old:
        raise RuntimeError('A351 duplicate or premodified layout')
    new=old.replace(old_css,old_css+b'\n/* BODYMIND A351 SUNRISE */\n'+css,1)
    new=new.replace(old_js,old_js+b'\n/* BODYMIND A351 DOCK */\n'+js,1)
    # Attach private album routes at Python-module level only after all original
    # A350 Flask functions have been defined. No route/model changes to A350.
    album_loader=b"""
# A351 PRIVATE ATHLETE ALBUM
import importlib.util as _bm351_import
_bm351_spec=_bm351_import.spec_from_file_location(
    'bodymind_a351_private_album','/opt/bodymind/bodymind_a351_private_album.py')
if _bm351_spec is None or _bm351_spec.loader is None:
    raise RuntimeError('A351 album module missing')
_bm351_album=_bm351_import.module_from_spec(_bm351_spec)
_bm351_spec.loader.exec_module(_bm351_album)
_bm351_album.install_family_gallery(app, db)
"""
    if b'BODYMIND A351 PRIVATE ATHLETE ALBUM' in new:
        raise RuntimeError('A351 album injection conflict')
    new+=album_loader
    compile(new,A351_REL,'exec')
    return new,hashlib.sha256(new).hexdigest()

def a351_matches(root:Path,found:dict[str,str])->bool:
    if len(found)!=214 or A351_REL not in found or not A351_BACKUP.is_file() or A351_BACKUP.is_symlink():
        return False
    old=A351_BACKUP.read_bytes()
    if hashlib.sha256(old).hexdigest()!=A351_A350_LIVE_SHA:
        return False
    _,sha=a351_expected_from_a350(old)
    if found[A351_REL]!=sha:
        return False
    previous=dict(found)
    previous[A351_REL]=hashlib.sha256(old).hexdigest()
    return a350_matches(root,previous)

def maybe_apply_a351_sunrise(root:Path,db:Path)->None:
    found=source_inventory(root)
    if a351_matches(root,found):
        return
    if not a350_matches(root,found):
        return
    sqlite_readonly_check(db)
    target=root/A351_REL
    if not target.is_file() or target.is_symlink():
        raise RuntimeError('A351 unsafe route source')
    old=target.read_bytes()
    new,new_sha=a351_expected_from_a350(old)
    if A351_BACKUP.exists():
        if not A351_BACKUP.is_file() or A351_BACKUP.is_symlink() or A351_BACKUP.read_bytes()!=old:
            raise RuntimeError('A351 recovery copy conflict')
    else:
        if not A351_BACKUP.parent.is_dir() or A351_BACKUP.parent.is_symlink():
            raise RuntimeError('A351 protected backup directory unavailable')
        with open(A351_BACKUP,'xb') as fh:
            fh.write(old)
            fh.flush()
            os.fsync(fh.fileno())
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(prefix='.a351_sunrise_',suffix='.py',dir=str(target.parent),delete=False) as fh:
            tmp=Path(fh.name)
            fh.write(new)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp,stat.S_IMODE(target.stat().st_mode))
        os.replace(str(tmp),str(target))
        tmp=None
    finally:
        if tmp is not None: tmp.unlink(missing_ok=True)
    updated=source_inventory(root)
    if updated[A351_REL]!=new_sha or not a351_matches(root,updated):
        raise RuntimeError('A351 source verification failed after update')
    print('BODYMIND A351 SUNRISE UI APPLIED - DATABASE AND MEDIA UNCHANGED',flush=True)

def maybe_recover_a351_to_a350(root:Path,db:Path)->bool:
    if os.environ.get('BODYMIND_A351_RECOVER_A350')!='1':
        return False
    found=source_inventory(root)
    if a350_matches(root,found):
        return True
    if not a351_matches(root,found):
        raise RuntimeError('A351 cannot recover unknown source')
    sqlite_readonly_check(db)
    target=root/A351_REL
    original=A351_BACKUP.read_bytes()
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(prefix='.a351_recover_',suffix='.py',dir=str(target.parent),delete=False) as fh:
            tmp=Path(fh.name)
            fh.write(original)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp,stat.S_IMODE(target.stat().st_mode))
        os.replace(str(tmp),str(target))
        tmp=None
    finally:
        if tmp is not None: tmp.unlink(missing_ok=True)
    if not a350_matches(root,source_inventory(root)):
        raise RuntimeError('A351 recovery fingerprint mismatch')
    print('BODYMIND A351 RECOVERY COMPLETE - VERIFIED A350 CODE RESTORED',flush=True)
    return True

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
            maybe_apply_a341_family_ui(args.root,args.db)
            maybe_apply_a342_family_ui(args.root,args.db)
            maybe_apply_a343_family_ui(args.root,args.db)
            if not maybe_recover_a344_to_a343(args.root,args.db):
                maybe_apply_a344_family_ui(args.root,args.db)
            if not maybe_recover_a345_to_a344(args.root,args.db):
                maybe_apply_a345_family_ui(args.root,args.db)
            if not maybe_recover_a346_to_a345(args.root,args.db):
                maybe_apply_a346_family_ui(args.root,args.db)
            if not maybe_recover_a347_to_a346(args.root,args.db):
                maybe_apply_a347_family_ui(args.root,args.db)
            if not maybe_recover_a348_to_a347(args.root,args.db):
                maybe_apply_a348_family_ui(args.root,args.db)
            if not maybe_recover_a349_to_a348(args.root,args.db):
                maybe_apply_a349_family_ui(args.root,args.db)
            if not maybe_recover_a350_to_a349(args.root,args.db):
                maybe_apply_a350_family_ui(args.root,args.db)
            if not maybe_recover_a351_to_a350(args.root,args.db):
                maybe_apply_a351_sunrise(args.root,args.db)
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
