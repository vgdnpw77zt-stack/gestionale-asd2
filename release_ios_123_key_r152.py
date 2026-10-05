from __future__ import annotations
import py_compile, shutil
from pathlib import Path

APP=Path('/data/top2_app')
CORE=APP/'asd_app/core.py'
BACK=Path('/data/release_backups/20261005_r152_ios_123')
BACK.mkdir(parents=True,exist_ok=True)

s=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R152_IOS_123_KEY' not in s:
    shutil.copy2(CORE,BACK/'core.py')
    s += r'''

# BODYMIND_R152_IOS_123_KEY
@app.after_request
def _bodymind_r152_ios_123_key(resp):
    try:
        import re as _r152_re
        p=request.path or ''
        if request.method!='GET' or int(getattr(resp,'status_code',200) or 200)!=200:
            return resp
        if 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp
        if p!='/documenti/da-verificare' and not _r152_re.fullmatch(r'/mobile/atleta/\d+/documenti/carica/?',p):
            return resp
        html=resp.get_data(as_text=True)

        # iOS can still switch to a restricted numeric layout when a numeric
        # pattern survives even if inputmode was rewritten. Force a plain text
        # field with no numeric pattern: this restores the standard Apple
        # alphabetic keyboard, whose lower-left "123" key opens numbers/symbols.
        def _fix(m):
            tag=m.group(0)
            if not _r152_re.search(r"\bname=['\"]scadenza['\"]",tag,_r152_re.I):
                return tag
            tag=_r152_re.sub(r"\btype=['\"][^'\"]*['\"]","type='text'",tag,flags=_r152_re.I)
            if not _r152_re.search(r"\btype=",tag,_r152_re.I):
                tag=tag[:-1]+" type='text'>"
            tag=_r152_re.sub(r"\binputmode=['\"][^'\"]*['\"]","inputmode='text'",tag,flags=_r152_re.I)
            if not _r152_re.search(r"\binputmode=",tag,_r152_re.I):
                tag=tag[:-1]+" inputmode='text'>"
            tag=_r152_re.sub(r"\s+pattern=['\"][^'\"]*['\"]","",tag,flags=_r152_re.I)
            tag=_r152_re.sub(r"\s+minlength=['\"][^'\"]*['\"]","",tag,flags=_r152_re.I)
            tag=_r152_re.sub(r"\s+maxlength=['\"][^'\"]*['\"]","",tag,flags=_r152_re.I)
            if 'autocomplete=' not in tag.lower():
                tag=tag[:-1]+" autocomplete='off'>"
            return tag

        html=_r152_re.sub(r"<input\b[^>]*>",_fix,html,flags=_r152_re.I)
        resp.set_data(html)
    except Exception as exc:
        print('[r152-warning] '+repr(exc),flush=True)
    return resp
'''
    CORE.write_text(s,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r152-install] PASS standard iOS text keyboard with 123/symbol switch enforced',flush=True)
else:
    print('[r152-install] already present',flush=True)

src=CORE.read_text(encoding='utf-8',errors='replace')
checks={
  'marker':'BODYMIND_R152_IOS_123_KEY' in src,
  'text_mode':"inputmode='text'" in src,
  'pattern_removed':"tag=_r152_re.sub(r\"\\s+pattern=" in src,
}
import sqlite3
conn=sqlite3.connect('/data/tenants/default/asd.db',timeout=20)
try:
    integ=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:conn.close()
checks['db']=integ.lower()=='ok' and fk==0
print('[r152-selftest] '+repr(checks),flush=True)
if not all(checks.values()):
    raise RuntimeError('R152 QA failed '+repr(checks))
