# -*- coding: utf-8 -*-
from __future__ import annotations
import py_compile, shutil, subprocess, sys
from pathlib import Path

APP=Path('/data/top2_app')
CORE=APP/'asd_app/core.py'
BACK=Path('/data/release_backups/20261005_r150_review_date_preview')
BACK.mkdir(parents=True,exist_ok=True)

s=CORE.read_text(encoding='utf-8',errors='replace')
before=s

# 1) Server-side Italian date parser also accepts 8 compact digits.
old="""def _r147_parse_it_date(raw):
    from datetime import datetime as _r147_dt
    s=str(raw or '').strip()
    if not s:return ''
    for fmt in ('%d/%m/%Y','%d-%m-%Y','%Y-%m-%d','%Y/%m/%d'):
        try:return _r147_dt.strptime(s[:10],fmt).date().isoformat()
        except Exception:pass
    return ''
"""
new="""def _r147_parse_it_date(raw):
    from datetime import datetime as _r147_dt
    s=str(raw or '').strip()
    if not s:return ''
    digits=''.join(ch for ch in s if ch.isdigit())
    if len(digits)==8 and ('/' not in s and '-' not in s):
        s=digits[0:2]+'/'+digits[2:4]+'/'+digits[4:8]
    for fmt in ('%d/%m/%Y','%d-%m-%Y','%Y-%m-%d','%Y/%m/%d'):
        try:return _r147_dt.strptime(s[:10],fmt).date().isoformat()
        except Exception:pass
    return ''
"""
if old in s:
    s=s.replace(old,new,1)

# 2) Inbound preview uses the already-existing generic document opener.
s=s.replace(
    "preview_url=('/documenti/visualizza/'+str(rid)) if source=='documenti' else ('/documenti-automatici/file/'+str(rid))",
    "preview_url=('/documenti/visualizza/'+str(rid)) if source=='documenti' else ('/a172/documento/inbound_documents/'+str(rid))"
)

# 3) Safe response-time enhancement. Do NOT inject JavaScript into an f-string
# source block: previous candidate proved that braces/backslashes can corrupt
# persistent core.py. This after_request hook is ordinary Python source.
if 'BODYMIND_R150_DATE_AUTOFMT_SAFE' not in s:
    hook=r'''

# BODYMIND_R150_DATE_AUTOFMT_SAFE
@app.after_request
def _bodymind_r150_date_autofmt_safe(resp):
    try:
        import re as _r150_re
        p=request.path or ''
        if request.method!='GET' or int(getattr(resp,'status_code',200) or 200)!=200:
            return resp
        if p!='/documenti/da-verificare' and not _r150_re.fullmatch(r'/mobile/atleta/\d+/documenti/carica/?',p):
            return resp
        if 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp
        html=resp.get_data(as_text=True)
        html=html.replace("placeholder='10/12/2026'","placeholder='GG/MM/AAAA'")
        html=html.replace('Scadenza certificato (solo se nota)','Scadenza certificato · GG/MM/AAAA')
        js="""<script id="BODYMIND_R150_DATE_AUTOFMT">
document.addEventListener('DOMContentLoaded',function(){
  document.querySelectorAll("input[name='scadenza']").forEach(function(el){
    function fmt(){
      var d=(el.value||'').replace(/\D/g,'');
      if(d.length===8){el.value=d.slice(0,2)+'/'+d.slice(2,4)+'/'+d.slice(4,8);}
    }
    el.addEventListener('input',function(){
      var d=(el.value||'').replace(/\D/g,'');
      if(d.length===8){fmt();}
    });
    el.addEventListener('blur',fmt);
  });
});
</script>"""
        if 'BODYMIND_R150_DATE_AUTOFMT' not in html:
            html=html.replace('</body>',js+'</body>',1) if '</body>' in html else html+js
        resp.set_data(html)
    except Exception as exc:
        print('[r150-date-warning] '+repr(exc),flush=True)
    return resp
'''
    s += hook

if s!=before:
    backup=BACK/'core.py'
    if not backup.exists():
        shutil.copy2(CORE,backup)
    CORE.write_text(s,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r150-install] safe compact date + preview convergence installed',flush=True)
else:
    py_compile.compile(str(CORE),doraise=True)
    print('[r150-install] already current',flush=True)

qa=r"""
import sqlite3,sys
sys.path.insert(0,"/data/top2_app")
import app as _full
from asd_app.core import app,_r147_parse_it_date
app.config["TESTING"]=True
c=app.test_client()
with c.session_transaction() as sess:
    sess.update({"logged":True,"logged_in":True,"username":"admin","display_name":"R150 QA","role":"admin","tenant_slug":"default","user_id":1,"is_admin":True,"admin":True,"_csrf_token":"r150"})
q=c.get('/documenti/da-verificare')
h=q.get_data(as_text=True)
routes={str(r.rule) for r in app.url_map.iter_rules()}
conn=sqlite3.connect('/data/tenants/default/asd.db')
try:
    integ=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:conn.close()
src=open('/data/top2_app/asd_app/core.py',encoding='utf-8',errors='replace').read()
checks={
 'queue_200':q.status_code==200,
 'date_compact':_r147_parse_it_date('14112026')=='2026-11-14',
 'date_slash':_r147_parse_it_date('14/11/2026')=='2026-11-14',
 'autofmt_js':'BODYMIND_R150_DATE_AUTOFMT' in h,
 'preview_unified':"/a172/documento/inbound_documents/" in src,
 'generic_date':"GG/MM/AAAA" in h,
 'core_compiles':True,
 'db':integ.lower()=='ok' and fk==0,
}
print('[r150-selftest] '+repr(checks),flush=True)
if not all(checks.values()):
    raise RuntimeError('R150 QA failed '+repr(checks))
"""
p=subprocess.run([sys.executable,'-c',qa],capture_output=True,text=True,timeout=120)
print((p.stdout or '').strip(),flush=True)
if p.returncode!=0:
    raise RuntimeError('R150 child QA failed '+((p.stderr or '')+(p.stdout or ''))[-5000:])
print('[r150-selftest-main] PASS safe-date review-preview db-ok',flush=True)
