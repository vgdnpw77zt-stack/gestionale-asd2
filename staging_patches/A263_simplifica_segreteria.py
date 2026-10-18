"""BodyMind A263 — minimal secretariat navigation, applied ONLY to reviewed staging sources.

Preserves all /cuore-operativo routes, post handlers, history and DB entries.
Makes the *normal UI* independent of the Core Operativo and timeline.
No Railway, no DB connections, no migration, no records removed.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

NAMES = ('core.py','routes_dashboard.py','routes_tesserati.py','routes_rc3_commercial_hardening.py')
MARKER='BODYMIND_A263_SIMPLE_SECRETARIAT'

A263_STYLE="""
/* BODYMIND_A263_SIMPLE_SECRETARIAT: one decision surface, no legacy second dashboard. */
html body #bodymind-secretariat-home.pro-dashboard > section:not(.a260-today) {{display:none!important;}}
html body .pro-dashboard.a62-topfix-dashboard .a260-today {{box-shadow:none!important;}}
html body .pro-dashboard.a62-topfix-dashboard .a260-today-intro {{max-width:52ch;}}
@media(max-width:730px) {{
 html body .pro-dashboard.a62-topfix-dashboard .a260-today {{padding:16px 14px!important;}}
 html body .pro-dashboard.a62-topfix-dashboard .a260-today h2 {{font-size:26px!important;}}
 html body .pro-dashboard.a62-topfix-dashboard .a260-today-intro {{font-size:13px!important;}}
}}
"""

def digest(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()

def exactly(source: str, old: str, new: str, label: str) -> str:
    if source.count(old)!=1:
        raise RuntimeError(f'STOP A263 {label}: expected one anchor, got {source.count(old)}')
    return source.replace(old,new,1)

def patch(root):
    root=Path(root)
    original={n:(root/n).read_text(encoding='utf-8') for n in NAMES}
    core=original['core.py']; dash=original['routes_dashboard.py']; ath=original['routes_tesserati.py']; analytics=original['routes_rc3_commercial_hardening.py']
    if MARKER in core and MARKER in dash:
        return {'changed':False,'shas':{n:digest(original[n]) for n in NAMES}}
    if MARKER in core or MARKER in dash:
        raise RuntimeError('STOP A263: partial previous patch; requires review')
    if 'BODYMIND A260 MENU' not in core or 'A260 accessible quick overview' not in dash or 'a261-progressive-dashboard' not in dash:
        raise RuntimeError('STOP A263: A259+A260+corrected A261 prerequisites absent')
    # Remove one redundant sidebar dropdown; keep functional admin routines and their URL routes.
    nav_begin="       + (nav_dropdown('Altri controlli', 'bolt',"
    nav_end="+ nav_dropdown('Persone', 'users',"
    if core.count(nav_begin)!=1 or core.count(nav_end)!=1:raise RuntimeError('STOP A263: sidebar anchors changed')
    head,tail=core.split(nav_begin,1)
    redundant,tail=tail.split(nav_end,1)
    if 'Cuore operativo' not in redundant or '/analytics-operative' not in redundant:raise RuntimeError('STOP A263: unexpected sidebar block')
    core=head+"       # BODYMIND_A263_SIMPLE_SECRETARIAT: redundant operational dropdown omitted from primary navigation.\n       "+nav_end+tail
    # Dock remains available on automation / resolver screens but without a "Cuore" tab.
    dock_line='      ("/cuore-operativo", "Cuore", "Cabina di controllo: stati, errori, da verificare, timeline"),\n'
    core=exactly(core,dock_line,'','quickdock Cuore')
    core=exactly(core,'<span class=\'a144-dock-title\'>Flusso operativo</span>',"<span class='a144-dock-title'>Automazioni</span>",'dock title')
    # Remove one misleading old UI success text; no business state logic changes.
    core=exactly(core,'Dashboard, Task e Centro operativo leggono ora lo stesso stato.','Dashboard e pagamenti leggono lo stesso stato.','payment confirmation copy')

    # A261's advanced toggle becomes unnecessary; the duplicate legacy sections are not rendered visually.
    css_first='/* A261: one lightweight work surface; advanced dashboard is always restorable. */'
    css_end='    </style>\n    <div class=\'pro-dashboard a2-dashboard'
    if dash.count(css_first)!=1 or dash.count(css_end)!=1:raise RuntimeError('STOP A263: dashboard CSS anchors missing')
    before,remaining=dash.split(css_first,1)
    old_css,after=remaining.split(css_end,1)
    if 'a261-compact' not in old_css:raise RuntimeError('STOP A263: A261 CSS not found')
    dash=before+A263_STYLE+'\n'+css_end+after
    toggle_begin='      <!-- A261 advanced controls toggle: all existing panels remain in the DOM. -->'
    toggle_end="      <section class='a3-command-hero a6-command-hero'"
    if dash.count(toggle_begin)!=1 or dash.count(toggle_end)!=1:raise RuntimeError('STOP A263: advanced toggle anchor ambiguous')
    before,remaining=dash.split(toggle_begin,1)
    button,after=remaining.split(toggle_end,1)
    if 'id=\'a261-more-button\'' not in button:raise RuntimeError('STOP A263: no A261 button')
    dash=before+toggle_end+after
    js_start='    <script id="a261-progressive-dashboard">'
    js_end='    </script>\n    """\n    return layout(html)'
    if dash.count(js_start)!=1 or dash.count(js_end)!=1:raise RuntimeError('STOP A263: script anchors ambiguous')
    before,remaining=dash.split(js_start,1)
    content,after=remaining.split(js_end,1)
    if 'bodymind_dashboard_advanced_open_v1' not in content:raise RuntimeError('STOP A263: wrong JS removed')
    dash=before+'    """\n    return layout(html)'+after
    root_markup="    <div class='pro-dashboard a2-dashboard a3-dashboard a5-dashboard a6-dashboard a7-dashboard a71-dashboard a8-dashboard a16-dashboard a18-dashboard a19-dashboard a62-topfix-dashboard a65-dashboard'>"
    dash=exactly(dash,root_markup,root_markup.replace("<div class=", "<div id='bodymind-secretariat-home' class="),'dashboard root ID')
    # Correct copy: there are no advanced panels in the primary UI.
    dash=exactly(dash,'Prima le cose importanti. Per i dettagli trovi ancora tutti i controlli nella pagina.',
       'Priorità chiare, meno schermate. Tutti gli strumenti di segreteria sono a portata di mano.','intro copy')
    # Public-facing application stays themed and consistent; no change to model figures.
    if "<strong>{'Tutto in regola' if total_actions == 0 else 'Consulta le schede'}</strong>" not in dash and "<strong>{'Tutto in regola' if total_actions == 0 else 'Stati in regola'}</strong>" not in dash:
        raise RuntimeError('STOP A263: conditional badge not found')

    # A tesserato already has document & payment shortcuts; discard a redundant portal to Core.
    old_ath="<a class='action-pill action-neutral' href='/cuore-operativo?tesserato_id={tesserato_id}'>♡ Pratiche aperte</a>"
    ath=exactly(ath,old_ath,'','tesserato actions')
    # Analytics route can still be visited if needed; replace its old cross-sell link with concrete tasks.
    old_analytics="<b>Apri il Cuore Operativo</b><small>Parti dagli alert aperti, non dai grafici.</small></div><a class='rc3-btn' href='/cuore-operativo'>Apri Cuore</a>"
    new_analytics="<b>Avvisi e scadenze</b><small>Apri soltanto le pratiche che richiedono attenzione.</small></div><a class='rc3-btn' href='/promemoria'>Apri avvisi</a>"
    analytics=exactly(analytics,old_analytics,new_analytics,'analytics action')
    result={'core.py':core,'routes_dashboard.py':dash,'routes_tesserati.py':ath,'routes_rc3_commercial_hardening.py':analytics}
    for name,body in result.items():
        compile(body,str(root/name),'exec')
    # Atomic local replace of files only after all checks succeed.
    import os
    for name,body in result.items():
        p=root/name
        if body==original[name]:continue
        tmp=p.with_suffix('.py.a263_tmp')
        tmp.write_text(body,encoding='utf-8')
        os.replace(tmp,p)
    return {'changed':True,'shas':{name:digest(body) for name,body in result.items()},
            'removed_visible_core_nav':True,'removed_legacy_dashboard_toggle':True,
            'kept_core_routes_and_audit':True}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',required=True)
    opt=p.parse_args()
    print(json.dumps(patch(opt.root),ensure_ascii=False,indent=2))
