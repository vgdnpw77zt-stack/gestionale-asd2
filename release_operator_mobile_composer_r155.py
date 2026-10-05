from __future__ import annotations
import py_compile, shutil, sqlite3, re
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
OP=APP/'asd_app/routes_operator_bodymind.py'
BACK=Path('/data/release_backups/20261005_r155_operator_composer_anchor')
BACK.mkdir(parents=True,exist_ok=True)

if not OP.exists():
    raise RuntimeError('R155 operator module missing')

src=OP.read_text(encoding='utf-8',errors='replace')
shutil.copy2(OP,BACK/'routes_operator_bodymind.py')

# Remove the old R154 block wherever it was injected. The previous installer used
# rfind('</style>') and could land in the /mobile entry style, not the operator page.
src=re.sub(
    r'\n\s*/\* BODYMIND_R154_OPERATOR_MOBILE_COMPOSER_FINAL.*?\n\s*\}\}\n(?=\s*</style>)',
    '\n',
    src,
    flags=re.S
)

marker='BODYMIND_R155_OPERATOR_COMPOSER_ANCHORED'
canonical='BODYMIND_OPERATOR_MOBILE_LAYOUT_CANONICAL'
anchor=src.find(canonical)
if anchor<0:
    raise RuntimeError('R155 canonical operator style marker missing; refusing blind patch')
style_end=src.find('</style>',anchor)
main_start=src.find('<main class="bmo">',anchor)
if style_end<0 or main_start<0 or not (style_end < main_start):
    raise RuntimeError('R155 operator style boundary invalid')

css=r'''
    /* BODYMIND_R155_OPERATOR_COMPOSER_ANCHORED
       Scoped ONLY to operator mobile style. Desktop is intentionally untouched. */
    @media(max-width:800px){{
      .bmo{{
        display:flex!important;
        flex-direction:column!important;
        height:var(--bmo-r90-vv-height,100dvh)!important;
        min-height:0!important;
        max-height:none!important;
        overflow:hidden!important;
      }}
      .bmo-grid{{
        display:flex!important;
        flex:1 1 auto!important;
        min-height:0!important;
        height:auto!important;
        overflow:hidden!important;
      }}
      .bmo-chat{{
        display:flex!important;
        flex-direction:column!important;
        flex:1 1 auto!important;
        min-height:0!important;
        height:100%!important;
        max-height:none!important;
        overflow:hidden!important;
      }}
      .bmo-messages{{
        flex:1 1 auto!important;
        min-height:0!important;
        height:auto!important;
        max-height:none!important;
        overflow-y:auto!important;
        padding-bottom:10px!important;
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
        grid-template-rows:40px!important;
        align-items:center!important;
        gap:6px!important;
        width:100%!important;
        max-width:800px!important;
        min-height:56px!important;
        height:56px!important;
        max-height:56px!important;
        margin:0 auto!important;
        padding:8px!important;
        box-sizing:border-box!important;
        overflow:hidden!important;
        border-radius:24px!important;
        background:#2f2f2f!important;
      }}
      #bmoAttachPicker{{
        display:none!important;
        position:absolute!important;
        width:0!important;
        height:0!important;
        min-width:0!important;
        min-height:0!important;
        max-width:0!important;
        max-height:0!important;
        padding:0!important;
        margin:0!important;
        opacity:0!important;
        overflow:hidden!important;
        appearance:none!important;
        -webkit-appearance:none!important;
        pointer-events:none!important;
      }}
      .bmo-hidden-tools,.bmo-side.bmo-hidden-tools{{
        display:none!important;
        position:absolute!important;
        width:0!important;
        height:0!important;
        overflow:hidden!important;
        visibility:hidden!important;
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
        align-self:center!important;
        border-radius:50%!important;
      }}
      .bmo-compose>#bmoInput{{
        display:block!important;
        width:100%!important;
        min-width:0!important;
        max-width:100%!important;
        min-height:40px!important;
        height:40px!important;
        max-height:40px!important;
        margin:0!important;
        padding:9px 8px!important;
        box-sizing:border-box!important;
        resize:none!important;
        overflow-y:auto!important;
        font-size:16px!important;
        line-height:22px!important;
        align-self:center!important;
      }}
      .bmo-compose-note{{display:none!important}}
    }}
'''
src=src[:style_end]+css+src[style_end:]

# Structural safety: legacy native file controls must never leak into the visible UI.
src=src.replace(
    '<input class="bmo-file-picker" type="file" id="bmoAttachPicker"',
    '<input class="bmo-file-picker" type="file" id="bmoAttachPicker" hidden style="display:none!important"',
    1
)
src=src.replace(
    '<aside class="bmo-side bmo-hidden-tools" aria-hidden="true">',
    '<aside class="bmo-side bmo-hidden-tools" aria-hidden="true" hidden style="display:none!important">',
    1
)

OP.write_text(src,encoding='utf-8')
py_compile.compile(str(OP),doraise=True)

verify=OP.read_text(encoding='utf-8',errors='replace')
a=verify.find(canonical)
m=verify.find(marker,a)
e=verify.find('</style>',a)
main=verify.find('<main class="bmo">',a)
checks={
  'marker_in_operator_style': a>=0 and m>a and e>m and main>e,
  'not_in_mobile_entry_style': verify.find(marker,main)<0,
  'single_row_height': 'height:56px!important' in verify[m:e],
  'single_row_grid': 'grid-template-columns:40px minmax(0,1fr) 40px 40px!important' in verify[m:e],
  'native_attach_hidden': 'id="bmoAttachPicker" hidden style="display:none!important"' in verify,
  'legacy_tools_hidden': 'aria-hidden="true" hidden style="display:none!important"' in verify,
}
conn=sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True,timeout=20)
try:
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=conn.execute('PRAGMA foreign_key_check').fetchall()
finally:
    conn.close()
checks['db']=integrity.lower()=='ok' and not fk
print('[r155-selftest] '+repr(checks)+' integrity='+integrity+' fk='+str(len(fk)),flush=True)
if not all(checks.values()):
    raise RuntimeError('R155 QA failed '+repr(checks))
print('[r155-selftest-main] PASS operator-style-anchor mobile-only compact-composer desktop-untouched',flush=True)
