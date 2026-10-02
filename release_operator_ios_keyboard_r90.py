# -*- coding: utf-8 -*-
from __future__ import annotations
import py_compile, shutil, sqlite3
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
OP=APP/'asd_app/routes_operator_bodymind.py'
BACK=Path('/data/release_backups/20261002_r90_ios_keyboard')
BACK.mkdir(parents=True,exist_ok=True)

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')
if not OP.exists():
    raise RuntimeError('R90 operator module missing')

def counts():
    conn=sqlite3.connect(str(DB),timeout=20)
    try:
        return {
          'tesserati':int(conn.execute('SELECT COUNT(*) FROM tesserati').fetchone()[0]),
          'documenti':int(conn.execute('SELECT COUNT(*) FROM documenti').fetchone()[0]),
          'inbound_documents':int(conn.execute('SELECT COUNT(*) FROM inbound_documents').fetchone()[0]),
        }
    finally:
        conn.close()

before=counts()
s=OP.read_text(encoding='utf-8',errors='replace')

if 'BODYMIND_R90_IOS_KEYBOARD_COMPOSER' not in s:
    dst=BACK/'asd_app/routes_operator_bodymind.py'
    dst.parent.mkdir(parents=True,exist_ok=True)
    if not dst.exists():
        shutil.copy2(OP,dst)

    # R74 made the composer fixed and then moved it again by the keyboard height.
    # On iOS Safari fixed elements already follow the visual viewport in several states,
    # so the extra compensation can move the composer outside the usable viewport.
    # R90 restores the R52 flex architecture and resizes the whole app shell instead.
    marker='BODYMIND_R74_IPHONE_COMPOSER'
    pos=s.find(marker)
    if pos<0:
        raise RuntimeError('R90 requires R74 composer marker')
    style_end=s.find('</style>',pos)
    if style_end<0:
        raise RuntimeError('R90 operator style end missing')

    css=r'''
    /* BODYMIND_R90_IOS_KEYBOARD_COMPOSER */
    html.bmo-r90-operator,html.bmo-r90-operator body{{
      height:100%!important;overflow:hidden!important;overscroll-behavior:none!important;
    }}
    @media(max-width:800px){{
      .bmo{{
        position:fixed!important;left:0!important;right:0!important;
        top:var(--bmo-r90-vv-top,0px)!important;bottom:auto!important;
        width:100vw!important;height:var(--bmo-r90-vv-height,100dvh)!important;
        min-height:0!important;max-height:none!important;
        padding:0!important;margin:0!important;overflow:hidden!important;
      }}
      .bmo-hero{{
        flex:0 0 52px!important;height:52px!important;min-height:52px!important;
      }}
      .bmo-grid{{
        display:flex!important;flex:1 1 auto!important;height:auto!important;
        min-height:0!important;overflow:hidden!important;
      }}
      .bmo-chat{{
        display:flex!important;flex-direction:column!important;flex:1 1 auto!important;
        height:100%!important;min-height:0!important;max-height:none!important;
        overflow:hidden!important;
      }}
      .bmo-messages{{
        flex:1 1 auto!important;height:auto!important;min-height:0!important;max-height:none!important;
        overflow-y:auto!important;-webkit-overflow-scrolling:touch!important;
        overscroll-behavior:contain!important;padding-bottom:12px!important;
      }}
      .bmo-compose-shell{{
        position:relative!important;left:auto!important;right:auto!important;
        top:auto!important;bottom:auto!important;transform:none!important;
        flex:0 0 auto!important;width:100%!important;z-index:4!important;
        box-sizing:border-box!important;
        padding:7px 7px max(8px,env(safe-area-inset-bottom))!important;
        background:linear-gradient(180deg,rgba(23,23,23,0),#171717 18%)!important;
      }}
      .bmo-compose{{
        position:relative!important;left:auto!important;right:auto!important;
        top:auto!important;bottom:auto!important;transform:none!important;
        width:100%!important;max-width:800px!important;margin:0 auto!important;
      }}
      .bmo-compose textarea{{
        font-size:16px!important;
      }}
    }}
'''
    s=s[:style_end]+css+s[style_end:]

    call='      bodymindR74Viewport();\n'
    js_pos=s.find(call,s.find('function bodymindR74Viewport'))
    if js_pos<0:
        raise RuntimeError('R90 R74 viewport call anchor missing')
    insert_at=js_pos+len(call)
    js=r'''
      // BODYMIND_R90_IOS_KEYBOARD_COMPOSER
      function bodymindR90SyncViewport(){{
        try{{
          if(!(window.matchMedia&&window.matchMedia('(max-width:800px)').matches))return;
          const root=document.documentElement;
          root.classList.add('bmo-r90-operator');
          const vv=window.visualViewport;
          const vh=Math.max(260,Math.round(vv?vv.height:window.innerHeight));
          const vt=Math.max(0,Math.round(vv?vv.offsetTop:0));
          root.style.setProperty('--bmo-r90-vv-height',vh+'px');
          root.style.setProperty('--bmo-r90-vv-top',vt+'px');
          // R74's keyboard offset is intentionally neutralized: the flex shell follows visualViewport.
          root.style.setProperty('--bmo-r74-keyboard','0px');
          if(window.scrollY)window.scrollTo(0,0);
          if(document.activeElement===input){{
            requestAnimationFrame(()=>{{messages.scrollTop=messages.scrollHeight}});
          }}
        }}catch(e){{}}
      }}
      function bodymindR90SyncSoon(){{
        bodymindR90SyncViewport();
        [40,120,260,420].forEach(ms=>setTimeout(bodymindR90SyncViewport,ms));
      }}
      if(window.visualViewport){{
        window.visualViewport.addEventListener('resize',bodymindR90SyncViewport,{{passive:true}});
        window.visualViewport.addEventListener('scroll',bodymindR90SyncViewport,{{passive:true}});
      }}
      window.addEventListener('resize',bodymindR90SyncViewport,{{passive:true}});
      window.addEventListener('orientationchange',bodymindR90SyncSoon,{{passive:true}});
      input?.addEventListener('focus',bodymindR90SyncSoon);
      input?.addEventListener('blur',bodymindR90SyncSoon);
      document.addEventListener('visibilitychange',()=>{{if(!document.hidden)bodymindR90SyncSoon()}});
      bodymindR90SyncSoon();
'''
    s=s[:insert_at]+js+s[insert_at:]
    OP.write_text(s,encoding='utf-8')
    py_compile.compile(str(OP),doraise=True)
    print('[operator-r90] PASS flex-composer visualViewport-height no-double-keyboard-offset ios-body-lock',flush=True)
else:
    print('[operator-r90] already applied',flush=True)

src=OP.read_text(encoding='utf-8',errors='replace')
checks={
  'marker':'BODYMIND_R90_IOS_KEYBOARD_COMPOSER' in src,
  'visual_height':"--bmo-r90-vv-height" in src and 'vv.height' in src,
  'composer_in_flex':'.bmo-compose-shell{{\n        position:relative!important' in src,
  'r74_offset_neutralized':"setProperty('--bmo-r74-keyboard','0px')" in src,
  'focus_resync':"input?.addEventListener('focus',bodymindR90SyncSoon)" in src,
  'no_scroll_into_view':'scrollIntoView' not in src[src.find('BODYMIND_R90_IOS_KEYBOARD_COMPOSER'):],
}
after=counts()
conn=sqlite3.connect(str(DB),timeout=20)
try:
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:
    conn.close()
checks['business_counts_unchanged']=before==after
checks['db_integrity']=integrity.lower()=='ok' and fk==0
print('[r90-ios-keyboard] checks='+repr(checks)+' before='+repr(before)+' after='+repr(after)+' integrity='+integrity+' fk='+str(fk),flush=True)
failed=[k for k,v in checks.items() if not v]
if failed:
    raise RuntimeError('R90 QA failed '+repr(failed))
print('[r90-selftest] PASS iOS-keyboard composer-visible flex-layout visualViewport data-safe',flush=True)
