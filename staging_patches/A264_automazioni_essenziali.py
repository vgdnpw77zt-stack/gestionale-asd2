"""A264 STAGING: compact settings UI for existing automation engine; does NOT schedule messages."""
from pathlib import Path
import hashlib, json

MARKER='BODYMIND_A264_AUTOMATION_UI'
ADDITIONAL_CSS=r'''
/* BODYMIND_A264_AUTOMATION_UI: compact form with native disclosure. */
.motor-page.a264-automations {max-width:1150px;margin:auto;gap:13px!important;color:#eef5ff}
.motor-page.a264-automations .motor-hero {background:#162334;border:1px solid #34465b;box-shadow:none;border-radius:18px;padding:18px 20px}
.motor-page.a264-automations .motor-hero h1 {font-size:clamp(23px,2.5vw,32px);letter-spacing:-.025em;margin-bottom:5px}
.motor-page.a264-automations .motor-hero p {font-size:14px;line-height:1.4;margin:0;max-width:680px}
.motor-page.a264-automations .motor-grid {grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:10px!important}
.motor-page.a264-automations .motor-card {padding:13px!important;border-radius:14px!important;min-height:auto!important;gap:6px!important;box-shadow:none}
.motor-page.a264-automations .motor-card b {font-size:14px!important}
.motor-page.a264-automations .motor-card small {font-size:12px!important;line-height:1.4}
.motor-page.a264-automations .motor-ico {width:36px!important;height:36px!important;font-size:18px!important;background:#244157!important;border-radius:11px!important}
.motor-page.a264-automations .a264-automation-group {background:#141f2d;border:1px solid #34485c;border-radius:15px;overflow:hidden}
.motor-page.a264-automations .a264-automation-group > summary {display:flex;align-items:center;justify-content:space-between;gap:12px;cursor:pointer;padding:15px 17px;min-height:54px;font-weight:750;list-style:none;color:#f3f7fc}
.motor-page.a264-automations .a264-automation-group > summary::after {content:'⌄';font-size:22px;color:#a4bfd6}
.motor-page.a264-automations .a264-automation-group[open] > summary::after {transform:rotate(180deg)}
.motor-page.a264-automations .a264-automation-group:not([open]) > .motor-section {display:none!important}
.motor-page.a264-automations .a264-automation-group > summary small {font-size:12px;color:#c4d4e2;font-weight:400;max-width:60%;line-height:1.35}
.motor-page.a264-automations .a264-automation-group > summary:focus-visible {outline:3px solid #7dc9ff;outline-offset:-3px}
.motor-page.a264-automations .motor-section {margin:0;border:0;border-radius:0;background:#17273a;box-shadow:none;padding:13px}
.motor-page.a264-automations .motor-hero-actions .pro-cta {min-height:44px;display:inline-flex;align-items:center;justify-content:center}
@media(max-width:760px) {
 .motor-page.a264-automations .motor-grid {grid-template-columns:1fr!important}
 .motor-page.a264-automations .a264-automation-group > summary {display:block;padding:13px}
 .motor-page.a264-automations .a264-automation-group > summary small {display:block;max-width:none;margin-top:4px}
 .motor-page.a264-automations .a264-automation-group > summary::after {position:absolute;right:16px;top:10px}
 .motor-page.a264-automations .a264-automation-group > summary {position:relative;padding-right:44px}
 .motor-page.a264-automations .motor-hero {padding:15px}
}
'''
def exact(s,a,b,label):
    n=s.count(a)
    if n!=1:raise RuntimeError(f'STOP {label}: anchor count {n}')
    return s.replace(a,b,1)

def patch(root):
    p=Path(root)/'routes_automation_pro.py'
    src=p.read_text(encoding='utf-8')
    if MARKER in src:return {'changed':False,'sha256':hashlib.sha256(src.encode()).hexdigest()}
    if "@app.route('/motore-automazioni'" not in src or 'def motore_automazioni_dashboard()' not in src:
        raise RuntimeError('STOP: unknown automation source')
    new=src
    old="section_html += f\"\"\"<section class='pro-panel motor-section'><div class='pro-panel-head'><div><span class='a3-eyebrow'>Come vuoi che lavori ASD Pro?</span><h2>{e(section_title)}</h2><p class='small-muted'>{e(section_desc)}</p></div></div><div class='motor-grid'>{cards}</div></section>\"\"\""
    replacement="section_html += f\"\"\"<details class='a264-automation-group' {'open' if section_title == 'Pagamenti' else ''}><summary><span>{e(section_title)}</span><small>{e(section_desc)}</small></summary><section class='pro-panel motor-section'><div class='motor-grid'>{cards}</div></section></details>\"\"\""
    new=exact(new,old,replacement,'native accordion')
    new=exact(new,"<div class='pro-dashboard motor-page'>","<div class='pro-dashboard motor-page a264-automations'>",'page class')
    new=exact(new,"<div><span class='a3-eyebrow'>Centro decisionale</span><h1>🧠 Motore Automazioni</h1>","<div><span class='a3-eyebrow'>Segreteria BodyMind</span><h1>Automazioni</h1>",'hero')
    new=exact(new,"Qui non vedi dettagli tecnici: scegli semplicemente <b>come vuoi che lavori ASD Pro</b>. Automatico se sicuro, anteprima con conferma o solo manuale. Il Motore decide, Risolvi esegue, il Cuore controlla.","Scegli cosa fare automaticamente, cosa preparare per la tua conferma e cosa lasciare manuale.",'intro')
    new=exact(new,"<a class='pro-cta ghost' href='/cuore-operativo'>Cuore Operativo</a>","<a class='pro-cta ghost' href='/comunicazioni-automatiche'>Storico invii</a>",'hero nav')
    start="      <section class='a144-flow-strip'>"
    end="      {saved_msg}"
    if new.count(start)!=1 or new.count(end)!=1:raise RuntimeError('STOP: process strip markers')
    before,rest=new.split(start,1);flow,after=rest.split(end,1)
    if '<b>Cuore = controllo</b>' not in flow: raise RuntimeError('STOP: unexpected old flow')
    new=before+end+after
    new=exact(new,"<a class='pro-cta ghost' href='/cuore-operativo'>Vai al Cuore Operativo</a>",'','save bar')
    new=exact(new,'risposte ambigue vanno nel Cuore Operativo come “Da verificare”.','risposte ambigue restano “Da verificare”.','warning copy')
    new=exact(new,"<a href='/cuore-operativo'>❤️ Cuore</a>",'','footer nav')
    new=exact(new,"Genera richiesta/link e segue la pratica nel Cuore Operativo.","Genera richiesta/link e monitora il pagamento verificato.",'payment copy')
    new=exact(new,"CAMPRET, deleghe, allergie e pagamenti devono entrare nel Cuore, non in un plugin separato.","CAMPRET, deleghe, allergie e pagamenti rimangono nello stesso flusso controllato.",'camp copy')
    new=exact(new,"Autorizzazioni e accompagnatori sempre visibili nel Cuore.","Autorizzazioni e accompagnatori sempre verificabili.",'minor copy')
    end_css='</style>\n    """\n    return layout(html)'
    if new.count(end_css)!=1:raise RuntimeError('STOP: automation CSS end marker ambiguous')
    new=new.replace(end_css,ADDITIONAL_CSS.replace('{','{{').replace('}','}}')+'</style>\n    """\n    return layout(html)',1)
    compile(new,str(p),'exec')
    p.write_text(new,encoding='utf-8')
    return {'changed':True,'sha256':hashlib.sha256(new.encode()).hexdigest()}

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument('--root',required=True)
    args=ap.parse_args()
    print(json.dumps(patch(args.root),indent=2))
