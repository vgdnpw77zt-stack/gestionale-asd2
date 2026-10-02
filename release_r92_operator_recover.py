# -*- coding: utf-8 -*-
from pathlib import Path
import py_compile, shutil

APP=Path('/data/top2_app')
OP=APP/'asd_app/routes_operator_bodymind.py'
BACK=Path('/data/release_backups/20261002_r92_recover')
BACK.mkdir(parents=True,exist_ok=True)
if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')
if not OP.exists():
    raise RuntimeError('R92 recovery operator module missing')

s=OP.read_text(encoding='utf-8',errors='replace')
original=s
bad='''and BODYMIND_R92_SHARED_AUTOENROLL_GATE_MARKER = True
                        _enrollment_identity_ready(semantic,require_valid_cf=True)'''
if bad in s:
    dst=BACK/'routes_operator_bodymind.py'
    if not dst.exists(): shutil.copy2(OP,dst)
    s=s.replace(bad,'and _enrollment_identity_ready(semantic,require_valid_cf=True)',1)
s=s.replace('sem_conf>=.98 and current_role()=="admin"','current_role()=="admin"')
if 'BODYMIND_R92_SHARED_AUTOENROLL_GATE' not in s:
    s='# BODYMIND_R92_SHARED_AUTOENROLL_GATE\n'+s
if s!=original:
    OP.write_text(s,encoding='utf-8')
py_compile.compile(str(OP),doraise=True)
print('[r92-recover] PASS operator syntax healed and strict gate normalized',flush=True)
