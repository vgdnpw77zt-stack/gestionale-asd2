from __future__ import annotations
import py_compile, shutil, sqlite3
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
OP=APP/'asd_app/routes_operator_bodymind.py'
CORE=APP/'asd_app/core.py'
BACK=Path('/data/release_backups/20261005_r153_mobile_keyboard')
BACK.mkdir(parents=True,exist_ok=True)

for p in (OP,CORE):
    if not p.exists():
        raise RuntimeError('R153 missing '+str(p))

ops=OP.read_text(encoding='utf-8',errors='replace')
changed=False
if 'BODYMIND_R153_KEYBOARD_CONSOLIDATION' not in ops:
    shutil.copy2(OP,BACK/'routes_operator_bodymind.py')

    # R73 smooth scroll fights iOS keyboard viewport animation.
    old="""      function bodymindKeepComposerVisible(){
        try{
          messages.scrollTop=messages.scrollHeight;
          if(window.matchMedia&&window.matchMedia('(max-width:800px)').matches){
            const shell=document.querySelector('.bmo-compose-shell');
            if(shell) shell.scrollIntoView({block:'end',behavior:'smooth'});
          }
        }catch(e){}
      }
"""
    new="""      function bodymindKeepComposerVisible(){
        try{
          // BODYMIND_R153_KEYBOARD_CONSOLIDATION
          // Keep only the message pane pinned. Never scroll the page/composer while
          // iOS is animating the software keyboard.
          messages.scrollTop=messages.scrollHeight;
        }catch(e){}
      }
"""
    if old in ops:
        ops=ops.replace(old,new,1); changed=True

    # Do not force focus after async send completion; on iOS that races with taps,
    # blur, dictation/composition and viewport changes.
    old2="        }finally{send.disabled=false;input.focus();setTimeout(bodymindKeepComposerVisible,80)}"
    if old2 in ops:
        ops=ops.replace(old2,"        }finally{send.disabled=false;bodymindKeepComposerVisible()}",1); changed=True

    # R90 must resize the shell, but must not drive document scroll or schedule
    # a train of viewport writes from focus/blur events.
    repls=[
      ("          if(window.scrollY)window.scrollTo(0,0);","          // R153: never force page scroll while keyboard is opening."),
      ("        [40,120,260,420].forEach(ms=>setTimeout(bodymindR90SyncViewport,ms));","        setTimeout(bodymindR90SyncViewport,120);"),
      ("        window.visualViewport.addEventListener('scroll',bodymindR90SyncViewport,{passive:true});","        // R153: visualViewport scroll is noisy on iOS; resize is sufficient."),
      ("      input?.addEventListener('focus',bodymindR90SyncSoon);","      input?.addEventListener('focus',bodymindR90SyncViewport,{passive:true});"),
      ("      input?.addEventListener('blur',bodymindR90SyncSoon);","      input?.addEventListener('blur',bodymindR90SyncViewport,{passive:true});"),
    ]
    for a,b in repls:
        if a in ops:
            ops=ops.replace(a,b,1); changed=True

    # Preserve unsent draft across incidental rerenders/navigation restores.
    anchor="      bodymindR90SyncSoon();"
    draft=r'''
      // BODYMIND_R153_DRAFT_PRESERVE
      try{
        const draftKey='bodymind.operator.draft';
        const restoreDraft=()=>{ if(input && !input.value){ const v=sessionStorage.getItem(draftKey)||''; if(v) input.value=v; } };
        restoreDraft();
        input?.addEventListener('input',()=>{ try{ sessionStorage.setItem(draftKey,input.value||''); }catch(e){} },{passive:true});
        if(send){
          send.addEventListener('click',()=>{ setTimeout(()=>{ try{ if(input && !input.value) sessionStorage.removeItem(draftKey); }catch(e){} },0); },{passive:true});
        }
      }catch(e){}
'''
    if anchor in ops and 'BODYMIND_R153_DRAFT_PRESERVE' not in ops:
        ops=ops.replace(anchor,anchor+draft,1); changed=True

    if not changed:
        raise RuntimeError('R153 operator anchors not found; refusing blind patch')
    OP.write_text(ops,encoding='utf-8')
    py_compile.compile(str(OP),doraise=True)

core=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R153_NATIVE_MOBILE_INPUTS' not in core:
    shutil.copy2(CORE,BACK/'core.py')
    core += r'''

# BODYMIND_R153_NATIVE_MOBILE_INPUTS
@app.after_request
def _bodymind_r153_native_mobile_inputs(resp):
    try:
        if request.method!='GET' or int(getattr(resp,'status_code',200) or 200)!=200:
            return resp
        if 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp
        html=resp.get_data(as_text=True)
        if 'BODYMIND_R153_NATIVE_MOBILE_INPUTS_CSS' in html:
            return resp
        css="""<style id="BODYMIND_R153_NATIVE_MOBILE_INPUTS_CSS">
@media (max-width: 900px){
  input:not([type="hidden"]):not([disabled]),textarea:not([disabled]),select:not([disabled]),[contenteditable="true"]{
    pointer-events:auto!important;
    touch-action:manipulation!important;
    -webkit-user-select:text!important;
    user-select:text!important;
    -webkit-touch-callout:default!important;
  }
  input,textarea,select{font-size:max(16px,1em)}
}
</style>"""
        if '</head>' in html:
            html=html.replace('</head>',css+'</head>',1)
        else:
            html=css+html
        resp.set_data(html)
    except Exception as exc:
        print('[r153-warning] '+repr(exc),flush=True)
    return resp
'''
    CORE.write_text(core,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)

ops=OP.read_text(encoding='utf-8',errors='replace')
core=CORE.read_text(encoding='utf-8',errors='replace')
checks={
 'operator_marker':'BODYMIND_R153_KEYBOARD_CONSOLIDATION' in ops,
 'no_smooth_composer_scroll':"shell.scrollIntoView({block:'end',behavior:'smooth'})" not in ops,
 'no_forced_page_scroll':'if(window.scrollY)window.scrollTo(0,0);' not in ops,
 'no_async_forced_focus':'input.focus();setTimeout(bodymindKeepComposerVisible,80)' not in ops,
 'draft_preserve':'BODYMIND_R153_DRAFT_PRESERVE' in ops,
 'native_inputs':'BODYMIND_R153_NATIVE_MOBILE_INPUTS' in core and 'touch-action:manipulation' in core,
}
conn=sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True,timeout=20)
try:
    integ=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:
    conn.close()
checks['db']=integ.lower()=='ok' and fk==0
print('[r153-selftest] '+repr(checks)+' integrity='+integ+' fk='+str(fk),flush=True)
if not all(checks.values()):
    raise RuntimeError('R153 QA failed '+repr(checks))
print('[r153-selftest-main] PASS consolidated-ios-keyboard native-inputs draft-preserve db-readonly-ok',flush=True)
