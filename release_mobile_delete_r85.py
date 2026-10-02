# -*- coding: utf-8 -*-
from __future__ import annotations
import py_compile, shutil
from pathlib import Path

APP=Path('/data/top2_app')
P=APP/'asd_app/routes_document_coherence_r41.py'
BACK=Path('/data/release_backups/20261002_r85_mobile_delete/routes_document_coherence_r41.py')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')
if not P.exists():
    raise RuntimeError('R85 coherence module missing')

s=P.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R85_GLOBAL_MOBILE_DELETE' not in s:
    BACK.parent.mkdir(parents=True,exist_ok=True)
    if not BACK.exists(): shutil.copy2(P,BACK)
    old="        if request.path=='/mobile' or request.path.startswith('/tesserati'):\n"
    new="        # BODYMIND_R85_GLOBAL_MOBILE_DELETE\n        if 'BODYMIND_R73_MOBILE_DELETE_VISIBILITY' not in html:\n"
    if old not in s:
        raise RuntimeError('R85 mobile delete path gate anchor missing')
    s=s.replace(old,new,1)
    P.write_text(s,encoding='utf-8')
    py_compile.compile(str(P),doraise=True)
    print('[r85-mobile-delete] PASS mobile delete visibility no longer depends on route path',flush=True)
else:
    print('[r85-mobile-delete] already applied',flush=True)
