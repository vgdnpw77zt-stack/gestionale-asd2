# -*- coding: utf-8 -*-
from __future__ import annotations
import py_compile, shutil, sqlite3, subprocess, sys, tempfile
from pathlib import Path

APP=Path('/data/top2_app')
CORE=APP/'asd_app/core.py'
DB=Path('/data/tenants/default/asd.db')
BACK=Path('/data/release_backups/20261005_r150_date_consolidation')
BACK.mkdir(parents=True,exist_ok=True)

def _strip_marked_block(src, marker):
    token='# '+marker
    idx=src.find(token)
    if idx<0:
        idx=src.find(marker)
        if idx<0:return src,False
    start=src.rfind('\n',0,idx)+1
    next_idx=src.find('\n# BODYMIND_',idx+len(marker))
    end=len(src) if next_idx<0 else next_idx+1
    return src[:start]+src[end:],True

s=CORE.read_text(encoding='utf-8',errors='replace')
before=s

# Canonical R147 parser: both 14/11/2026 and 14112026.
old_parser="""def _r147_parse_it_date(raw):
    from datetime import datetime as _r147_dt
    s=str(raw or '').strip()
    if not s:return ''
    for fmt in ('%d/%m/%Y','%d-%m-%Y','%Y-%m-%d','%Y/%m/%d'):
        try:return _r147_dt.strptime(s[:10],fmt).date().isoformat()
        except Exception:pass
    return ''"""
new_parser="""def _r147_parse_it_date(raw):
    from datetime import datetime as _r147_dt
    s=str(raw or '').strip()
    if not s:return ''
    digits=''.join(ch for ch in s if ch.isdigit())
    candidates=[('%d/%m/%Y',s),('%d-%m-%Y',s),('%Y-%m-%d',s),('%Y/%m/%d',s)]
    if len(digits)==8:candidates.append(('%d%m%Y',digits))
    for fmt,val in candidates:
        try:return _r147_dt.strptime(val,fmt).date().isoformat()
        except Exception:pass
    return ''"""
s=s.replace(old_parser,new_parser)

# R147 must render only /documenti/da-verificare. It must not rewrite the
# direct-athlete upload field after R144 has rendered it.
start=s.find("        if request.method!='GET' or p!='/documenti/da-verificare' or int(getattr(resp,'status_code',200) or 200) not in (200,301,302,303):")
end=s.find("        if not bool(session.get('logged')):return resp",start if start>=0 else 0)
if start>=0 and end>start:
    canonical_nonqueue="""        if request.method!='GET' or p!='/documenti/da-verificare' or int(getattr(resp,'status_code',200) or 200) not in (200,301,302,303):
            return resp
"""
    s=s[:start]+canonical_nonqueue+s[end:]

canonical_field="<label>Scadenza certificato · GG/MM/AAAA oppure 8 cifre<input type='text' name='scadenza' value='{e(current_exp)}' inputmode='text' autocomplete='off' placeholder='es. 14/11/2026 o 14112026'></label>"
for old in (
    "<label>Scadenza certificato · GG/MM/AAAA<input name='scadenza' value='{e(current_exp)}' inputmode='numeric' placeholder='10/12/2026' pattern='[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}'></label>",
    "<label>Scadenza certificato · GG/MM/AAAA<input name='scadenza' value='{e(current_exp)}' inputmode='text' placeholder='GG/MM/AAAA' autocomplete='off'></label>",
    "<label>Scadenza certificato · 8 cifre (GGMMYYYY)<input name='scadenza' value='{e(current_exp)}' inputmode='text' placeholder='GGMMYYYY · es. 27032027' autocomplete='off'></label>",
):
    s=s.replace(old,canonical_field)

s=s.replace(
    "        messages={'scadenza':'Per un certificato medico inserisci la scadenza in formato GG/MM/AAAA.','atleta':'Seleziona l’atleta.','materializza':'Il file non è materializzabile: resta da verificare.','tipo':'Seleziona il tipo documento.'}",
    "        messages={'scadenza':'Per un certificato medico inserisci GG/MM/AAAA oppure 8 cifre, ad esempio 14112026.','atleta':'Seleziona l’atleta.','materializza':'Il file non è materializzabile: resta da verificare.','tipo':'Seleziona il tipo documento.'}"
)

# Remove every legacy response-time date/keyboard rewrite. R151 is reinstalled
# later as preview-close-only.
removed=[]
for marker in ('BODYMIND_R150_DATE_AUTOFMT_SAFE','BODYMIND_R152_IOS_123_KEY','BODYMIND_R151_KEYBOARD_PREVIEW_CLOSE','BODYMIND_R151_PREVIEW_CLOSE_ONLY'):
    s,done=_strip_marked_block(s,marker)
    if done:removed.append(marker)

if s!=before:
    fd,tmp_name=tempfile.mkstemp(prefix='bodymind_r150_candidate_',suffix='.py')
    import os as _r150_os
    _r150_os.close(fd)
    tmp=Path(tmp_name)
    try:
        tmp.write_text(s,encoding='utf-8')
        py_compile.compile(str(tmp),doraise=True)
        shutil.copy2(CORE,BACK/'core_before_consolidation.py')
        CORE.write_text(s,encoding='utf-8')
        py_compile.compile(str(CORE),doraise=True)
    finally:
        try:tmp.unlink()
        except Exception:pass
else:
    py_compile.compile(str(CORE),doraise=True)
print('[r150-consolidation] removed='+repr(removed)+' candidate_compile=ok',flush=True)

qa=r'''
import re,sqlite3,sys
sys.path.insert(0,"/data/top2_app")
import app as _full
from asd_app.core import app,_r147_parse_it_date
app.config["TESTING"]=True
c=app.test_client()
with c.session_transaction() as sess:
    sess.update({"logged":True,"logged_in":True,"username":"admin","display_name":"R150 QA","role":"admin","tenant_slug":"default","user_id":1,"is_admin":True,"admin":True,"_csrf_token":"r150"})
review=c.get("/documenti/da-verificare");h=review.get_data(as_text=True)
upload=c.get("/mobile/atleta/21/documenti/carica");uh=upload.get_data(as_text=True)
src=open("/data/top2_app/asd_app/core.py",encoding="utf-8",errors="replace").read()
def text_field(html):
    return bool(re.search(r"<input\b[^>]*\bname=['\"]scadenza['\"][^>]*\binputmode=['\"]text['\"][^>]*>",html,re.I))
checks={
 "review_200":review.status_code==200,
 "upload_200":upload.status_code==200,
 "review_native_text":text_field(h) and "inputmode='numeric'" not in h,
 "upload_native_text":text_field(uh) and "type='date' name='scadenza'" not in uh and "inputmode='numeric'" not in uh,
 "compact_parser":_r147_parse_it_date("14112026")=="2026-11-14",
 "slash_parser":_r147_parse_it_date("14/11/2026")=="2026-11-14",
 "legacy_hooks_absent":all(x not in src for x in ("BODYMIND_R150_DATE_AUTOFMT_SAFE","BODYMIND_R152_IOS_123_KEY","BODYMIND_R151_KEYBOARD_PREVIEW_CLOSE","BODYMIND_R151_PREVIEW_CLOSE_ONLY")),
 "no_orphan_legacy_js":"function fmt(){" not in src and 'BODYMIND_R150_DATE_AUTOFMT' not in src,
}
conn=sqlite3.connect("/data/tenants/default/asd.db",timeout=20)
try:
    integ=str(conn.execute("PRAGMA integrity_check").fetchone()[0]);fk=len(conn.execute("PRAGMA foreign_key_check").fetchall())
finally:conn.close()
checks["db"]=integ.lower()=="ok" and fk==0
print("[r150-selftest] "+repr(checks),flush=True)
if not all(checks.values()):raise RuntimeError("R150 QA failed "+repr(checks))
'''
p=subprocess.run([sys.executable,'-c',qa],capture_output=True,text=True,timeout=120)
print((p.stdout or '').strip(),flush=True)
if p.returncode!=0:
    raise RuntimeError('R150 child QA failed '+((p.stderr or '')+(p.stdout or ''))[-6000:])
print('[r150-selftest-main] PASS canonical-native-date compact-or-slash parser db-ok',flush=True)
