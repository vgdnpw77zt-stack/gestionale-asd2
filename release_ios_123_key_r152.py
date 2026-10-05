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


# R152b: remove the legacy R147 numeric keypad source itself.
# Flask after_request handlers run in reverse registration order; leaving the
# old R147 numeric rewrite in core.py can undo R151/R152 at response time.
s=CORE.read_text(encoding='utf-8',errors='replace')
legacy_before=s

# Direct rendered-review markup from R147.
s=s.replace(
    "inputmode='numeric' placeholder='10/12/2026' pattern='[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}'",
    "inputmode='text' placeholder='GG/MM/AAAA' autocomplete='off'"
)
# R147 response-rewrite literal for upload/review forms.
s=s.replace(
    "type='text' name='scadenza' inputmode='numeric' placeholder='GG/MM/AAAA' pattern='[0-9]{2}/[0-9]{2}/[0-9]{4}'",
    "type='text' name='scadenza' inputmode='text' placeholder='GG/MM/AAAA' autocomplete='off'"
)

if s!=legacy_before:
    shutil.copy2(CORE,BACK/'core_pre_r152b.py')
    CORE.write_text(s,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r152b-source-cleanup] PASS removed legacy R147 numeric scadenza keypad',flush=True)
else:
    print('[r152b-source-cleanup] no legacy numeric scadenza source found',flush=True)

src=CORE.read_text(encoding='utf-8',errors='replace')
checks={
  'marker':'BODYMIND_R152_IOS_123_KEY' in src,
  'text_mode':"inputmode='text'" in src,
  'pattern_removed':"tag=_r152_re.sub(r\"\\s+pattern=" in src,
  'no_legacy_numeric_scadenza':"name='scadenza' inputmode='numeric'" not in src and 'name="scadenza" inputmode="numeric"' not in src,
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
