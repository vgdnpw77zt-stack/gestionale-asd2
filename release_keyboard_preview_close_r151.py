from __future__ import annotations
import py_compile, shutil, sqlite3
from pathlib import Path

APP=Path('/data/top2_app')
CORE=APP/'asd_app/core.py'
BACK=Path('/data/release_backups/20261005_r151_preview_close_only')
BACK.mkdir(parents=True,exist_ok=True)

def _strip_marked_function(src, marker):
    lines=src.splitlines(True)
    idx=next((i for i,x in enumerate(lines) if marker in x),-1)
    if idx<0:return src,False
    j=idx+1;seen_def=False
    while j<len(lines):
        line=lines[j]
        if line.startswith('def '):
            seen_def=True;j+=1;continue
        if seen_def and line.strip() and not line.startswith((' ','\t')):
            break
        j+=1
    return ''.join(lines[:idx]+lines[j:]),True

s=CORE.read_text(encoding='utf-8',errors='replace')
before=s
s,_=_strip_marked_function(s,'BODYMIND_R151_KEYBOARD_PREVIEW_CLOSE')
s,_=_strip_marked_function(s,'BODYMIND_R151_PREVIEW_CLOSE_ONLY')
s += r'''

# BODYMIND_R151_PREVIEW_CLOSE_ONLY
@app.after_request
def _bodymind_r151_preview_close_only(resp):
    try:
        if request.method!='GET' or int(getattr(resp,'status_code',200) or 200)!=200:
            return resp
        if 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp
        html=resp.get_data(as_text=True)
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
            resp.headers.pop('Content-Length',None)
    except Exception as exc:
        print('[r151-preview-warning] '+repr(exc),flush=True)
    return resp
'''
if s!=before:
    shutil.copy2(CORE,BACK/'core.py')
    CORE.write_text(s,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
print('[r151-install] preview-close-only installed',flush=True)

src=CORE.read_text(encoding='utf-8',errors='replace')
checks={
 'preview_only':"BODYMIND_R151_PREVIEW_CLOSE_ONLY" in src and "BODYMIND_R151_PREVIEW_CLOSE" in src,
 'old_keyboard_hook_absent':"BODYMIND_R151_KEYBOARD_PREVIEW_CLOSE" not in src,
}
conn=sqlite3.connect('/data/tenants/default/asd.db',timeout=20)
try:
    integ=str(conn.execute('PRAGMA integrity_check').fetchone()[0]);fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:conn.close()
checks['db']=integ.lower()=='ok' and fk==0
print('[r151-selftest] '+repr(checks),flush=True)
if not all(checks.values()):raise RuntimeError('R151 QA failed '+repr(checks))
print('[r151-selftest-main] PASS preview-close-only db-ok',flush=True)
