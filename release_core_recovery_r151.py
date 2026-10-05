# -*- coding: utf-8 -*-
from __future__ import annotations
import py_compile, shutil
from pathlib import Path

CORE=Path('/data/top2_app/asd_app/core.py')
BACK=Path('/data/release_backups/20261005_r150_review_date_preview')
if not CORE.exists():
    raise SystemExit('R151 core.py missing')

try:
    py_compile.compile(str(CORE),doraise=True)
    print('[r151-core-recovery] core already valid',flush=True)
except Exception as exc:
    candidates=[BACK/'core.py']
    restored=False
    for src in candidates:
        if not src.exists():
            continue
        try:
            py_compile.compile(str(src),doraise=True)
        except Exception:
            continue
        bad=Path('/data/release_backups/20261005_r151_core_recovery')
        bad.mkdir(parents=True,exist_ok=True)
        try: shutil.copy2(CORE,bad/'core_invalid_r150.py')
        except Exception: pass
        shutil.copy2(src,CORE)
        py_compile.compile(str(CORE),doraise=True)
        print('[r151-core-recovery] restored valid pre-R150 core from '+str(src)+' after '+repr(exc),flush=True)
        restored=True
        break
    if not restored:
        raise SystemExit('R151 could not recover invalid core.py: '+repr(exc))
