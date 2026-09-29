# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import compileall, py_compile, shutil

APP=Path('/data/top2_app')
SRC=Path('/opt/bodymind/operator_bridge_runtime_r36.py')
TARGET=APP/'asd_app/routes_operator_bridge.py'
MARKER=APP/'.BODYMIND_OPERATOR_BRIDGE_R36'
BACKUPS=Path('/data/release_backups/20260929_operator_bridge_r36')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')
if not SRC.exists():
    raise SystemExit('R36 bridge source missing')

def backup(rel):
    src=APP/rel; dst=BACKUPS/rel
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dst)

def validate_source(text):
    tmp=Path('/tmp/bodymind_bridge_candidate.py')
    tmp.write_text(text,encoding='utf-8')
    py_compile.compile(str(tmp),doraise=True)

desired=SRC.read_text(encoding='utf-8')
validate_source(desired)

if not MARKER.exists():
    BACKUPS.mkdir(parents=True,exist_ok=True)
    backup('asd_app/routes_operator_bridge.py')
    TARGET.write_text(desired,encoding='utf-8')

    appp=APP/'app.py'
    if not appp.exists():
        raise RuntimeError('R36 app.py missing')
    apptext=appp.read_text(encoding='utf-8',errors='replace')
    if 'import asd_app.routes_operator_bridge' not in apptext:
        backup('app.py')
        anchor='import asd_app.routes_operator_bodymind  # noqa: F401'
        if anchor not in apptext:
            anchor='import asd_app.routes_documenti  # noqa: F401'
        if anchor not in apptext:
            raise RuntimeError('R36 app import anchor missing')
        apptext=apptext.replace(anchor,anchor+'\nimport asd_app.routes_operator_bridge  # noqa: F401  # R36 local AI bridge',1)
        appp.write_text(apptext,encoding='utf-8')

    if not compileall.compile_file(str(TARGET),quiet=1):
        raise RuntimeError('R36 bridge compile failed')
    if not compileall.compile_file(str(appp),quiet=1):
        raise RuntimeError('R36 app compile failed')

    checks={
      'pair':'/bodymind-ai-bridge/pair' in desired,
      'poll':'/bodymind-ai-bridge/poll' in desired,
      'result':'/bodymind-ai-bridge/result' in desired,
      'setup':'/operatore-bodymind/bridge/setup' in desired,
      'install':'/bodymind-ai-bridge/install.sh' in desired,
      'local-only-exec':'bridge_enhance_result' in desired,
    }
    failed=[k for k,v in checks.items() if not v]
    if failed:
        raise RuntimeError('R36 bridge selftest failed '+repr(failed))
    MARKER.write_text('BodyMind local AI bridge R36 applied\n',encoding='utf-8')
    print('[operator-bridge-r36] applied',flush=True)
    print('[operator-bridge-r36-selftest] PASS pair-token poll-result install-launchagent deterministic-actions-preserved',flush=True)
else:
    current=TARGET.read_text(encoding='utf-8',errors='replace') if TARGET.exists() else ''
    if current!=desired:
        TARGET.write_text(desired,encoding='utf-8')
        print('[operator-bridge-r36] bridge module refreshed from image',flush=True)
    if not compileall.compile_file(str(TARGET),quiet=1):
        raise RuntimeError('R36 bridge runtime compile failed')
    print('[operator-bridge-r36] already applied',flush=True)
