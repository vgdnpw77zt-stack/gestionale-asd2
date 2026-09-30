# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import compileall, shutil

APP=Path('/data/top2_app')
BACKUP=Path('/data/release_backups/20260930_cloud_native_r47')
APPP=APP/'app.py'
BRIDGE=APP/'asd_app/routes_operator_bridge.py'
MARKER=APP/'.BODYMIND_CLOUD_NATIVE_R47'

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')
BACKUP.mkdir(parents=True,exist_ok=True)

def backup(path, rel):
    if path.exists():
        dst=BACKUP/rel
        if not dst.exists():
            dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,dst)

backup(APPP,'app.py')
backup(BRIDGE,'asd_app/routes_operator_bridge.py')

text=APPP.read_text(encoding='utf-8',errors='replace')
lines=[]
for line in text.splitlines():
    if 'import asd_app.routes_operator_bridge' in line:
        continue
    lines.append(line)
new='\n'.join(lines)+'\n'
if new!=text:
    APPP.write_text(new,encoding='utf-8')

if BRIDGE.exists():
    BRIDGE.unlink()

for p in (APP/'asd_app/__pycache__').glob('routes_operator_bridge*.pyc'):
    try: p.unlink()
    except Exception: pass

for name in ('.BODYMIND_OPERATOR_BRIDGE_R36',):
    p=APP/name
    try:
        if p.exists(): p.unlink()
    except Exception: pass

if 'routes_operator_bridge' in APPP.read_text(encoding='utf-8',errors='replace'):
    raise RuntimeError('R47 bridge import still present')
if BRIDGE.exists():
    raise RuntimeError('R47 bridge runtime still present')
if not compileall.compile_file(str(APPP),quiet=1):
    raise RuntimeError('R47 app.py compile failed')

MARKER.write_text('BodyMind R47 cloud native: local Mac/Qwen bridge retired\n',encoding='utf-8')
print('[cloud-native-r47] removed local bridge import/runtime; historical DB audit preserved',flush=True)
print('[cloud-native-r47-selftest] PASS no-local-bridge cloud-only',flush=True)
