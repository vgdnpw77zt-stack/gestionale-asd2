# -*- coding: utf-8 -*-
from __future__ import annotations
import py_compile, shutil
from pathlib import Path

APP=Path('/data/top2_app')
CORE=APP/'asd_app/core.py'
BACK=Path('/data/release_backups/20261005_r148_review_preview')
BACK.mkdir(parents=True,exist_ok=True)

s=CORE.read_text(encoding='utf-8',errors='replace')
before=s

s=s.replace("placeholder='10/12/2026'","placeholder='GG/MM/AAAA'")

needle="""            return f\"\"\"<article class='r147-card'><div class='r147-head'><div><b>{e(title)}</b><small>{e(who)}</small></div><span>DA VERIFICARE</span></div><p>{e(reason)}</p>
<form method='post' action='/documenti/da-verificare/r147/verifica'>"""
replacement="""            preview_url=('/documenti/visualizza/'+str(rid)) if source=='documenti' else ('/documenti-automatici/file/'+str(rid))
            return f\"\"\"<article class='r147-card'><div class='r147-head'><div><b>{e(title)}</b><small>{e(who)}</small></div><span>DA VERIFICARE</span></div><p>{e(reason)}</p>
<div class='r148-preview-actions'><a href='{preview_url}' target='_blank' rel='noopener'>👁 Anteprima documento</a></div>
<form method='post' action='/documenti/da-verificare/r147/verifica'>"""
if "r148-preview-actions" not in s:
    if needle not in s:
        raise RuntimeError('R148 card anchor missing')
    s=s.replace(needle,replacement,1)

css_anchor="""button{{width:100%;margin-top:14px;padding:13px;border:0;border-radius:12px;background:#166534;color:#fff;font-weight:950;font-size:16px}}a.back"""
css_new="""button{{width:100%;margin-top:14px;padding:13px;border:0;border-radius:12px;background:#166534;color:#fff;font-weight:950;font-size:16px}}.r148-preview-actions{{margin:12px 0}}.r148-preview-actions a{{display:block;padding:12px 13px;border-radius:12px;background:#1d4ed8;color:#fff!important;text-decoration:none;text-align:center;font-weight:950}}a.back"""
if ".r148-preview-actions{{" not in s:
    if css_anchor not in s:
        raise RuntimeError('R148 CSS anchor missing')
    s=s.replace(css_anchor,css_new,1)

if s!=before:
    shutil.copy2(CORE,BACK/'core.py')
    CORE.write_text(s,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r148-review-preview] installed',flush=True)
else:
    print('[r148-review-preview] already present',flush=True)
