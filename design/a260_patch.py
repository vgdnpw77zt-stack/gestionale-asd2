"""BodyMind A260: progressive, additive redesign on the A259-reviewed clone.
NO network, database, production, or state mutations. Exact source SHA guards.
"""
from __future__ import annotations
from pathlib import Path
import hashlib

BASE = {
    'core.py': '2653a26d09b541d47ab681ec1e1fff4a6912c43151d902b82cb40de51aaf6b9f',
    'routes_dashboard.py': '58b131b3bc0f2ab16477693f3ca7507827659b6267e3e46b2c45575efedfea21',
    'routes_operator_bodymind.py': '08e82cffffc0812f2b218e784004fe8290780f138243c7145275e8c89b3d088d',
}
# Retain all interactive sections (including Autopilot) rather than visually hiding them.
DASH_CSS = r'''
/* A260 dashboard: three clear decisions before secondary instrumentation. */
html body .pro-dashboard.a62-topfix-dashboard {color:#edf3fa;max-width:1480px!important;margin:0 auto!important;min-width:0!important;}
html body .pro-dashboard.a62-topfix-dashboard .a260-today {margin:0 0 20px;padding:22px 24px 24px;border-radius:22px;background:#141f2e;border:1px solid #324457;box-shadow:none;}
html body .pro-dashboard.a62-topfix-dashboard .a260-today-head {display:flex;align-items:start;justify-content:space-between;gap:14px;flex-wrap:wrap;margin-bottom:20px;}
html body .pro-dashboard.a62-topfix-dashboard .a260-eyebrow {display:inline-flex;gap:7px;color:#a8c8dc;font-size:11px;font-weight:750;letter-spacing:.1em;text-transform:uppercase;}
html body .pro-dashboard.a62-topfix-dashboard .a260-today h2 {font-size:clamp(25px,2.6vw,34px);font-weight:760;line-height:1.15;letter-spacing:-.025em;color:#f5f7fb;margin:8px 0 5px;}
html body .pro-dashboard.a62-topfix-dashboard .a260-today-intro {font-size:14px;line-height:1.5;color:#aebed0;margin:0;max-width:650px;}
html body .pro-dashboard.a62-topfix-dashboard .a260-toolbar {display:flex;gap:8px;align-items:center;flex-wrap:wrap;}
html body .pro-dashboard.a62-topfix-dashboard .a260-action {min-height:43px;box-sizing:border-box;display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:9px 13px;border-radius:12px;border:1px solid #4e6380;color:#eaf3ff!important;background:#223348;text-decoration:none!important;font-size:13px;font-weight:700;box-shadow:none;white-space:nowrap;}
html body .pro-dashboard.a62-topfix-dashboard .a260-action.primary {background:#275e85;border-color:#4792c3;color:#fff!important;}
html body .pro-dashboard.a62-topfix-dashboard .a260-action:hover {background:#34506b;}
html body .pro-dashboard.a62-topfix-dashboard .a260-action:focus-visible,html body .pro-dashboard.a62-topfix-dashboard .a260-state:focus-visible {outline:3px solid #85c6ec;outline-offset:3px;}
html body .pro-dashboard.a62-topfix-dashboard .a260-state-grid {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;}
html body .pro-dashboard.a62-topfix-dashboard .a260-state {min-width:0;display:flex;flex-direction:column;gap:8px;padding:17px 18px;border:1px solid #384c62;border-radius:16px;color:#eef4fa!important;text-decoration:none!important;background:#1a2a3a;box-shadow:none;min-height:130px;box-sizing:border-box;}
html body .pro-dashboard.a62-topfix-dashboard .a260-state strong {color:inherit;font-size:14px;line-height:1.3;font-weight:750;}
html body .pro-dashboard.a62-topfix-dashboard .a260-state .a260-big {font-size:30px;line-height:1.05;letter-spacing:-.035em;font-weight:780;font-variant-numeric:tabular-nums;}
html body .pro-dashboard.a62-topfix-dashboard .a260-state small {font-size:12px;line-height:1.4;color:#bed0df;}
html body .pro-dashboard.a62-topfix-dashboard .a260-state.urgent {border-left:4px solid #f07a7c;}
html body .pro-dashboard.a62-topfix-dashboard .a260-state.soon {border-left:4px solid #e4b359;}
html body .pro-dashboard.a62-topfix-dashboard .a260-state.okay {border-left:4px solid #6ac59f;}
html body .pro-dashboard.a62-topfix-dashboard .a260-state:hover {background:#243749;border-color:#60829e;}
/* Legacy modules remain in the DOM: compact, not deleted. */
html body .pro-dashboard.a62-topfix-dashboard .a3-command-hero,html body .pro-dashboard.a62-topfix-dashboard .a6-command-hero {border-radius:18px!important;background:#162334!important;box-shadow:none!important;border:1px solid #334759!important;padding:17px!important;gap:15px!important;}
html body .pro-dashboard.a62-topfix-dashboard .a11-title-orbit,html body .pro-dashboard.a62-topfix-dashboard .hero-orbit {display:none!important;}
html body .pro-dashboard.a62-topfix-dashboard .a127-live-alert,html body .pro-dashboard.a62-topfix-dashboard .a3-focus-pill {box-shadow:none!important;border-radius:14px!important;}
html body .pro-dashboard.a62-topfix-dashboard .a9-action-tile {box-shadow:none!important;border-radius:14px!important;min-height:96px!important;}
html body .pro-dashboard.a62-topfix-dashboard .a9-action-tile small {display:none!important;}
html body .pro-dashboard.a62-topfix-dashboard .a129-kpi-command-card,html body .pro-dashboard.a62-topfix-dashboard .orchestra-card {box-shadow:none!important;border-radius:18px!important;}
html body .pro-dashboard.a62-topfix-dashboard :is(.a187-drag-handle,.a187-server-handle) {opacity:.38;}
@media (max-width:1100px) {
 html body .pro-dashboard.a62-topfix-dashboard .a260-today {padding:16px;}
 html body .pro-dashboard.a62-topfix-dashboard .a260-today-head {display:block;}
 html body .pro-dashboard.a62-topfix-dashboard .a260-toolbar {margin-top:13px;}
}
@media (max-width:730px) {
 html body .pro-dashboard.a62-topfix-dashboard .a260-today {margin:4px 0 12px;border-radius:16px;padding:15px;}
 html body .pro-dashboard.a62-topfix-dashboard .a260-state-grid {grid-template-columns:1fr!important;gap:8px;}
 html body .pro-dashboard.a62-topfix-dashboard .a260-state {min-height:0;padding:12px 14px;display:grid;grid-template-columns:1fr auto;column-gap:12px;align-items:center;}
 html body .pro-dashboard.a62-topfix-dashboard .a260-state strong {grid-column:1;grid-row:1;}
 html body .pro-dashboard.a62-topfix-dashboard .a260-state .a260-big {font-size:24px;grid-column:2;grid-row:1 / span 2;text-align:right;}
 html body .pro-dashboard.a62-topfix-dashboard .a260-state small {grid-column:1;grid-row:2;}
 html body .pro-dashboard.a62-topfix-dashboard .a260-toolbar {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;}
 html body .pro-dashboard.a62-topfix-dashboard .a260-action {min-width:0;white-space:normal;text-align:center;}
 html body .pro-dashboard.a62-topfix-dashboard .a260-today-intro {font-size:13px;}
 html body .pro-dashboard.a62-topfix-dashboard .a3-command-hero {padding:12px!important;}
}
@media (prefers-reduced-motion:reduce) {
 html body .pro-dashboard.a62-topfix-dashboard .a260-state,html body .pro-dashboard.a62-topfix-dashboard .a260-action {transition:none!important;animation:none!important;}
}
'''
OP_CSS = r'''
/* A260 chat refinement. Keeps audio, attachments, and AI tools functional. */
html body main.bmo {background:#101722!important;color:#edf3fa!important;}
html body main.bmo .bmo-hero {background:#172232!important;border-bottom:1px solid #334457!important;box-shadow:none!important;}
html body main.bmo .bmo-chat {background:#101722!important;box-shadow:none!important;border:0!important;}
html body main.bmo .bmo-messages {gap:15px!important;}
html body main.bmo .bmo-msg-row {align-items:flex-start!important;}
html body main.bmo .bmo-msg.bot {font-size:14.5px!important;line-height:1.55!important;letter-spacing:0!important;}
html body main.bmo .bmo-msg.me {border-radius:18px 18px 7px 18px!important;background:#29374a!important;box-shadow:none!important;font-weight:450!important;}
html body main.bmo .bmo-top-btn {border-radius:11px!important;background:#243448!important;border-color:#455b75!important;box-shadow:none!important;}
html body main.bmo .bmo-shortcuts {background:#162232!important;border-bottom:1px solid #35485e!important;gap:8px!important;}
html body main.bmo .bmo-shortcuts>a {border-radius:10px!important;white-space:nowrap!important;color:#deeaf5!important;}
html body main.bmo .bmo-shortcuts>a:first-child {background:#235d7d!important;color:#fff!important;}
html body main.bmo .bmo-compose-shell {background:#111b28!important;border-top:1px solid #324457!important;box-shadow:none!important;}
html body main.bmo .bmo-compose {background:#243144!important;border:1px solid #4a617d!important;box-shadow:none!important;}
html body main.bmo .bmo-compose #bmoInput {color:#fff!important;line-height:1.42!important;}
html body main.bmo .bmo-attach,html body main.bmo .bmo-mic {background:#30455e!important;border:1px solid #506c89!important;color:#fff!important;}
html body main.bmo .bmo-send {background:#dfeeff!important;color:#15354a!important;border:0!important;}
html body main.bmo a:focus-visible,html body main.bmo button:focus-visible,html body main.bmo textarea:focus-visible {outline:2px solid #8ad2ff!important;outline-offset:2px!important;}
/* Hide the underlying file control without an accessible overlay invading the composer. */
html body main.bmo #bmoAttachPicker {position:absolute!important;left:0!important;top:0!important;width:1px!important;height:1px!important;opacity:0!important;pointer-events:none!important;overflow:hidden!important;}
@media(max-width:800px) {
 html body main.bmo .bmo-hero {padding:7px 11px!important;min-height:56px!important;height:56px!important;flex:0 0 56px!important;}
 html body main.bmo .bmo-brand-title {font-size:15px!important;}
 html body main.bmo .bmo-shortcuts {padding:5px 8px!important;gap:5px!important;overflow-x:auto!important;scrollbar-width:none!important;}
 html body main.bmo .bmo-shortcuts>a {min-height:36px!important;display:inline-flex!important;align-items:center!important;padding:5px 10px!important;font-size:12px!important;}
 html body main.bmo .bmo-msg {max-width:calc(100% - 32px)!important;font-size:14px!important;}
 html body main.bmo .bmo-messages {padding:12px 12px 20px!important;gap:12px!important;}
 html body main.bmo .bmo-compose-shell {padding:6px 8px max(8px,env(safe-area-inset-bottom))!important;}
 html body main.bmo .bmo-compose {grid-template-columns:39px minmax(0,1fr) 39px 39px!important;gap:5px!important;min-width:0!important;min-height:55px!important;border-radius:18px!important;padding:6px!important;}
 html body main.bmo .bmo-compose>.bmo-attach,html body main.bmo .bmo-compose>.bmo-mic,html body main.bmo .bmo-compose>.bmo-send {width:39px!important;min-width:39px!important;max-width:39px!important;height:42px!important;border-radius:12px!important;}
 html body main.bmo .bmo-compose>#bmoInput {min-width:0!important;max-width:100%!important;width:100%!important;padding:9px 5px!important;font-size:16px!important;}
}
@media (min-width:801px) and (max-width:1366px) {
 html body main.bmo .bmo-grid {grid-template-columns:minmax(0,1fr)!important;}
 html body main.bmo .bmo-messages {max-width:900px!important;padding:20px 22px!important;}
}
'''

TODAY = '''
      <!-- A260 accessible quick overview. Existing detailed panels below remain intact. -->
      <section class='a260-today' aria-labelledby='a260-today-title'>
        <div class='a260-today-head'>
          <div><span class='a260-eyebrow'>● BodyMind · Segreteria</span>
            <h2 id='a260-today-title'>Segreteria oggi</h2>
            <p class='a260-today-intro'>Prima le cose importanti. Per i dettagli trovi ancora tutti i controlli nella pagina.</p>
          </div>
          <nav class='a260-toolbar' aria-label='Azioni segreteria'>
            <a class='a260-action primary' href='/quote-incassi/incasso-rapido'>€ Registra contanti</a>
            <a class='a260-action' href='/tesserati/elenco-ordinato'>Tesserati</a>
            <a class='a260-action' href='/motore-automazioni'>Automazioni</a>
            <a class='a260-action' href='/documenti'>Documenti</a>
          </nav>
        </div>
        <div class='a260-state-grid' aria-label='Stato della segreteria'>
          <a class='a260-state urgent' href='/promemoria?mese={int(mese)}&anno={int(anno)}' aria-label='Da fare: {critical_count} criticità urgenti'>
            <strong>Da fare</strong><span class='a260-big'>{critical_count}</span><small>Criticità urgenti, apri e risolvi</small>
          </a>
          <a class='a260-state soon' href='/promemoria?mese={int(mese)}&anno={int(anno)}' aria-label='In scadenza e da verificare: {warning_count} avvisi'>
            <strong>In scadenza / da verificare</strong><span class='a260-big'>{warning_count}</span><small>Avvisi non bloccanti e controlli</small>
          </a>
          <a class='a260-state okay' href='/tesserati/elenco-ordinato'>
            <strong>Tutto in regola</strong><span class='a260-big' aria-hidden='true'>✓</span><small>Apri le schede e verifica gli stati aggiornati</small>
          </a>
        </div>
      </section>
'''

def patch(root):
    root=Path(root)
    originals={name:(root/name).read_text(encoding='utf-8') for name in BASE}
    for name,expected in BASE.items():
        actual=hashlib.sha256(originals[name].encode()).hexdigest()
        markers={'core.py':'BODYMIND A260 MENU', 'routes_dashboard.py':'A260 accessible quick overview', 'routes_operator_bodymind.py':'A260 chat refinement'}
        if actual!=expected and markers[name] not in originals[name]:
            raise RuntimeError('STOP A260: differenza sorgente: '+name)
    dash=originals['routes_dashboard.py']
    if 'A260 accessible quick overview' not in dash:
        anchor="    <div class='pro-dashboard a2-dashboard"
        assert dash.count(anchor)==1
        # The overview belongs *inside* the existing dashboard wrapper.
        exact="    <div class='pro-dashboard a2-dashboard a3-dashboard a5-dashboard a6-dashboard a7-dashboard a71-dashboard a8-dashboard a16-dashboard a18-dashboard a19-dashboard a62-topfix-dashboard a65-dashboard'>"
        assert dash.count(exact)==1
        dash=dash.replace(exact,exact+TODAY,1)
    if 'A260 dashboard: three clear decisions' not in dash:
        anchor="    </style>\n    <div class='pro-dashboard a2-dashboard"
        assert dash.count(anchor)==1
        dash=dash.replace(anchor,DASH_CSS.replace('{','{{').replace('}','}}')+'\n'+anchor,1)
    op=originals['routes_operator_bodymind.py']
    if 'A260 chat refinement' not in op:
        # Last CSS appears in the template before the main bmo tag.
        anchor='\n</style>\n\n    <main class="bmo">'
        assert op.count(anchor)==1
        op=op.replace(anchor,'\n'+OP_CSS.replace('{','{{').replace('}','}}')+'\n'+anchor,1)
    core=originals['core.py']
    if 'BODYMIND A260 MENU' not in core:
        # Primary automation link; original advanced tools remain under accordion.
        anchor="       + nav_link('/operatore-bodymind', 'Operatore BodyMind', 'bolt', tier='core', title='Segreteria intelligente: parla, cerca, controlla e prepara azioni sul gestionale.')  # BODYMIND_R29_OPERATOR_NAV"
        assert core.count(anchor)==1
        core=core.replace(anchor,anchor+"\n       + (nav_link('/motore-automazioni', 'Automazioni', 'settings', tier='secondary', title='Gestisci regole e scadenze dal motore esistente.') if has_role('admin') else '')  # BODYMIND A260 MENU",1)
        core=core.replace("nav_dropdown('Operatività', 'bolt'","nav_dropdown('Altri controlli', 'bolt'",1)
        # Stop showing a duplicate automation nav link inside advanced tools.
        old="           + (nav_link('/motore-automazioni', 'Regole automazioni', 'settings', aliases=('/motore','/automation-engine','/automazioni-pro'), tier='secondary', title='Regole business semplici: quando sollecitare, bloccare, richiedere o chiudere.') if has_role('admin') else '')"
        assert core.count(old)==1
        core=core.replace(old,'',1)
    changed={'core.py':core,'routes_dashboard.py':dash,'routes_operator_bodymind.py':op}
    for name,content in changed.items():
        compile(content,str(root/name),'exec')
    for name,content in changed.items():
        if content!=originals[name]:
            (root/name).write_text(content,encoding='utf-8')
    return {name:{'sha_before':hashlib.sha256(originals[name].encode()).hexdigest(), 'sha_after':hashlib.sha256(changed[name].encode()).hexdigest()} for name in changed}

if __name__=='__main__':
    import sys,json
    print(json.dumps(patch(sys.argv[1]),ensure_ascii=False,indent=2))
