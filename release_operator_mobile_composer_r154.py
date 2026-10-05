from __future__ import annotations
import py_compile, shutil, sqlite3
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
OP=APP/'asd_app/routes_operator_bodymind.py'
BACK=Path('/data/release_backups/20261005_r154_operator_mobile_composer')
BACK.mkdir(parents=True,exist_ok=True)

if not OP.exists():
    raise RuntimeError('R154 operator module missing')

src=OP.read_text(encoding='utf-8',errors='replace')
marker='BODYMIND_R154_OPERATOR_MOBILE_COMPOSER_FINAL'
if marker not in src:
    shutil.copy2(OP,BACK/'routes_operator_bodymind.py')

    style_end=src.rfind('</style>')
    if style_end<0:
        raise RuntimeError('R154 final style tag missing; refusing blind patch')

    css=r'''
    /* BODYMIND_R154_OPERATOR_MOBILE_COMPOSER_FINAL
       Final mobile authority: one compact composer row, hidden native file input,
       flex-owned vertical layout, no giant floating panel. */
    @media(max-width:800px){{
      html.bmo-r90-operator,html.bmo-r90-operator body{{
        height:100%!important;
        min-height:0!important;
        overflow:hidden!important;
      }}
      .bmo{{
        position:fixed!important;
        inset:0!important;
        width:100vw!important;
        height:var(--bmo-r90-vv-height,100dvh)!important;
        min-height:0!important;
        max-height:none!important;
        overflow:hidden!important;
        display:flex!important;
        flex-direction:column!important;
      }}
      .bmo-hero{{
        flex:0 0 52px!important;
        height:52px!important;
        min-height:52px!important;
      }}
      .bmo-grid{{
        flex:1 1 auto!important;
        min-height:0!important;
        height:auto!important;
        overflow:hidden!important;
        display:flex!important;
      }}
      .bmo-chat{{
        flex:1 1 auto!important;
        min-height:0!important;
        height:100%!important;
        max-height:none!important;
        overflow:hidden!important;
        display:flex!important;
        flex-direction:column!important;
      }}
      .bmo-messages{{
        flex:1 1 auto!important;
        min-height:0!important;
        height:auto!important;
        max-height:none!important;
        overflow-y:auto!important;
        padding:14px 12px 10px!important;
      }}
      .bmo-compose-shell{{
        position:relative!important;
        inset:auto!important;
        left:auto!important;
        right:auto!important;
        top:auto!important;
        bottom:auto!important;
        transform:none!important;
        flex:0 0 auto!important;
        width:100%!important;
        height:auto!important;
        min-height:0!important;
        max-height:none!important;
        overflow:visible!important;
        margin:0!important;
        padding:7px 8px max(8px,env(safe-area-inset-bottom))!important;
        box-sizing:border-box!important;
        background:linear-gradient(180deg,rgba(23,23,23,0),#171717 18%)!important;
      }}
      .bmo-compose{{
        position:relative!important;
        inset:auto!important;
        left:auto!important;
        right:auto!important;
        top:auto!important;
        bottom:auto!important;
        transform:none!important;
        display:grid!important;
        grid-template-columns:40px minmax(0,1fr) 40px 40px!important;
        grid-template-rows:auto!important;
        align-items:end!important;
        gap:6px!important;
        width:100%!important;
        max-width:800px!important;
        min-height:56px!important;
        height:auto!important;
        margin:0 auto!important;
        padding:8px!important;
        box-sizing:border-box!important;
        overflow:hidden!important;
        border-radius:24px!important;
        background:#2f2f2f!important;
      }}
      #bmoAttachPicker.bmo-file-picker{{
        display:none!important;
        position:absolute!important;
        width:0!important;
        height:0!important;
        min-width:0!important;
        min-height:0!important;
        padding:0!important;
        margin:0!important;
        opacity:0!important;
        overflow:hidden!important;
        pointer-events:none!important;
      }}
      .bmo-hidden-tools,
      .bmo-side.bmo-hidden-tools{{
        display:none!important;
        width:0!important;
        height:0!important;
        overflow:hidden!important;
      }}
      .bmo-compose>.bmo-attach{{grid-column:1!important;grid-row:1!important}}
      .bmo-compose>#bmoInput{{grid-column:2!important;grid-row:1!important}}
      .bmo-compose>.bmo-mic{{grid-column:3!important;grid-row:1!important}}
      .bmo-compose>.bmo-send{{grid-column:4!important;grid-row:1!important}}
      .bmo-attach,.bmo-mic,.bmo-send{{
        display:grid!important;
        place-items:center!important;
        width:40px!important;
        min-width:40px!important;
        max-width:40px!important;
        height:40px!important;
        min-height:40px!important;
        max-height:40px!important;
        margin:0!important;
        padding:0!important;
        align-self:end!important;
        border-radius:50%!important;
        flex:none!important;
      }}
      .bmo-compose>#bmoInput{{
        display:block!important;
        width:100%!important;
        min-width:0!important;
        max-width:100%!important;
        min-height:40px!important;
        height:40px!important;
        max-height:112px!important;
        margin:0!important;
        padding:9px 8px!important;
        box-sizing:border-box!important;
        resize:none!important;
        overflow-y:auto!important;
        font-size:16px!important;
        line-height:22px!important;
        align-self:end!important;
      }}
      .bmo-compose-note{{display:none!important}}
    }}
'''
    src=src[:style_end]+css+src[style_end:]
    OP.write_text(src,encoding='utf-8')
    py_compile.compile(str(OP),doraise=True)
    print('[r154-install] final mobile composer authority installed',flush=True)
else:
    print('[r154-install] already applied',flush=True)

src=OP.read_text(encoding='utf-8',errors='replace')
checks={
    'marker': marker in src,
    'file_picker_hidden': '#bmoAttachPicker.bmo-file-picker' in src and 'display:none!important' in src,
    'single_row_grid': 'grid-template-columns:40px minmax(0,1fr) 40px 40px!important' in src,
    'composer_relative': '.bmo-compose-shell{{\n        position:relative!important' in src,
    'textarea_column': '.bmo-compose>#bmoInput{{grid-column:2!important' in src,
}
conn=sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True,timeout=20)
try:
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=conn.execute('PRAGMA foreign_key_check').fetchall()
finally:
    conn.close()
checks['db']=integrity.lower()=='ok' and not fk
print('[r154-selftest] '+repr(checks)+' integrity='+integrity+' fk='+str(len(fk)),flush=True)
if not all(checks.values()):
    raise RuntimeError('R154 QA failed '+repr(checks))
print('[r154-selftest-main] PASS compact-composer hidden-picker flex-layout db-readonly-ok',flush=True)
