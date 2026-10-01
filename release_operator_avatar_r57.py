# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import py_compile, shutil

APP=Path('/data/top2_app')
P=APP/'asd_app/routes_operator_bodymind.py'
BACK=Path('/data/release_backups/20261001_operator_r57/routes_operator_bodymind.py')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

s=P.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R57_CHAT_AVATAR' in s:
    print('[operator-r57] already applied',flush=True)
    raise SystemExit(0)

BACK.parent.mkdir(parents=True,exist_ok=True)
if not BACK.exists():
    shutil.copy2(P,BACK)

s=s.replace('OPERATOR_VERSION = "R56.0-fast-safe-dedupe"','OPERATOR_VERSION = "R57.0-fast-safe-dedupe-avatar"',1)
old="const av=document.createElement('img');av.className='bmo-msg-avatar';av.src='/bodymind-media/logo';av.alt='BodyMind';row.appendChild(av);"
new="/* BODYMIND_R57_CHAT_AVATAR */ const av=document.createElement('img');av.className='bmo-msg-avatar';av.src='https://bodymindaerialstudio.life/seed-media/logo?v=9';av.alt='BodyMind Aerial Studio';row.appendChild(av);"
if old not in s:
    raise RuntimeError('R57 chat avatar anchor missing')
s=s.replace(old,new,1)

P.write_text(s,encoding='utf-8')
py_compile.compile(str(P),doraise=True)
print('[operator-r57] PASS chat-avatar-bodymind-public-logo',flush=True)
