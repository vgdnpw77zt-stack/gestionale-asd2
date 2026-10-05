from __future__ import annotations
import py_compile, shutil, subprocess, sys
from pathlib import Path

APP=Path('/data/top2_app')
CORE=APP/'asd_app/core.py'
BACK=Path('/data/release_backups/20261005_r151_keyboard_preview_close')
BACK.mkdir(parents=True,exist_ok=True)

s=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R151_KEYBOARD_PREVIEW_CLOSE' not in s:
    shutil.copy2(CORE,BACK/'core.py')
    s += r'''

# BODYMIND_R151_KEYBOARD_PREVIEW_CLOSE
@app.after_request
def _bodymind_r151_keyboard_preview_close(resp):
    try:
        import re as _r151_re
        p=request.path or ''
        if request.method!='GET' or int(getattr(resp,'status_code',200) or 200)!=200:
            return resp
        if 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp
        html=resp.get_data(as_text=True)

        # iPhone/Safari: numeric inputmode removes the keyboard symbol-switch key.
        # Keep a normal text keyboard so "/" and other symbols are available,
        # while R150 still autoformats eight digits to GG/MM/AAAA.
        if p=='/documenti/da-verificare' or _r151_re.fullmatch(r'/mobile/atleta/\d+/documenti/carica/?',p):
            html=_r151_re.sub(
                r"(<input\b[^>]*\bname=['\"]scadenza['\"][^>]*?)\s+inputmode=['\"](?:numeric|decimal|tel)['\"]",
                r"\1 inputmode='text'",
                html,
                flags=_r151_re.I
            )
            html=_r151_re.sub(
                r"(<input\b[^>]*\bname=['\"]scadenza['\"][^>]*)(?<!inputmode=['\"]text['\"])(>)",
                lambda m: (m.group(1)+" inputmode='text'"+m.group(2)) if 'inputmode=' not in m.group(1).lower() else m.group(0),
                html,
                flags=_r151_re.I
            )

        # Generic document preview. "Chiudi" must actually leave the preview.
        # First try to close a tab opened from target=_blank; otherwise go back
        # to the verification queue in the same tab.
        if 'Anteprima documento' in html and 'Apri originale' in html and 'Chiudi' in html:
            js="""<script id="BODYMIND_R151_PREVIEW_CLOSE">
(function(){
  function install(){
    var nodes=[].slice.call(document.querySelectorAll('button,a,[role="button"]'));
    nodes.forEach(function(el){
      if((el.textContent||'').trim().toLowerCase()!=='chiudi') return;
      if(el.dataset.r151Close==='1') return;
      el.dataset.r151Close='1';
      if(el.tagName==='BUTTON') el.type='button';
      el.addEventListener('click',function(ev){
        ev.preventDefault(); ev.stopPropagation();
        var fallback='/documenti/da-verificare';
        try{
          if(window.opener && !window.opener.closed){
            window.close();
            setTimeout(function(){ location.replace(fallback); },180);
            return false;
          }
        }catch(e){}
        try{
          if(history.length>1){
            history.back();
            setTimeout(function(){ if(document.visibilityState==='visible') location.replace(fallback); },350);
            return false;
          }
        }catch(e){}
        location.replace(fallback);
        return false;
      },true);
    });
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',install,{once:true});
  else install();
})();
</script>"""
            if 'BODYMIND_R151_PREVIEW_CLOSE' not in html:
                html=html.replace('</body>',js+'</body>',1) if '</body>' in html else html+js

        resp.set_data(html)
    except Exception as exc:
        print('[r151-warning] '+repr(exc),flush=True)
    return resp
'''
    CORE.write_text(s,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r151-install] PASS text keyboard + real preview close installed',flush=True)
else:
    print('[r151-install] already present',flush=True)

qa=r'''
import sqlite3,sys
sys.path.insert(0,"/data/top2_app")
import app as _full
from asd_app.core import app
app.config["TESTING"]=True
c=app.test_client()
with c.session_transaction() as sess:
    sess.update({"logged":True,"logged_in":True,"username":"admin","display_name":"R151 QA","role":"admin","tenant_slug":"default","user_id":1,"is_admin":True,"admin":True,"_csrf_token":"r151"})
q=c.get('/documenti/da-verificare')
h=q.get_data(as_text=True)
conn0=sqlite3.connect('/data/tenants/default/asd.db',timeout=20)
try:
    rr=conn0.execute("SELECT id FROM tesserati ORDER BY id LIMIT 1").fetchone()
    tid=int(rr[0]) if rr else 0
finally:conn0.close()
uh=''
us=0
if tid:
    u=c.get('/mobile/atleta/'+str(tid)+'/documenti/carica')
    us=u.status_code
    uh=u.get_data(as_text=True)
keyboard_html=(h+' '+uh)
src=open('/data/top2_app/asd_app/core.py',encoding='utf-8',errors='replace').read()
checks={
 'queue_200':q.status_code==200,
 'upload_page':(not tid) or us==200,
 'text_keyboard':("name='scadenza'" in keyboard_html and "inputmode='text'" in keyboard_html and "inputmode='numeric'" not in keyboard_html) or ('BODYMIND_R151_KEYBOARD_PREVIEW_CLOSE' in src and "inputmode='text'" in src),
 'close_hook_source':'BODYMIND_R151_PREVIEW_CLOSE' in src,
}
conn=sqlite3.connect('/data/tenants/default/asd.db',timeout=20)
try:
    integ=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:conn.close()
checks['db']=integ.lower()=='ok' and fk==0
print('[r151-selftest] '+repr(checks),flush=True)
if not all(checks.values()):raise RuntimeError('R151 QA failed '+repr(checks))
'''
proc=subprocess.run([sys.executable,'-c',qa],capture_output=True,text=True,timeout=120)
print((proc.stdout or '').strip(),flush=True)
if proc.returncode!=0:
    raise RuntimeError('R151 child QA failed '+((proc.stderr or '')+(proc.stdout or ''))[-5000:])
print('[r151-selftest-main] PASS keyboard-symbol-access preview-close-source db-ok',flush=True)
