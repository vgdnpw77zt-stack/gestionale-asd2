"""A264 staging-only integration of A262 finance with the A263 minimal dashboard.

Never runs on live server. Adds no SQL, DML, DDL or changes to payment methods.
"""
from __future__ import annotations
from pathlib import Path
import hashlib, json

MARKER='BODYMIND_A264_COMPACT_FINANCE'
FAIL_MARKER='BODYMIND_A264_FAIL_VISIBLE'

NEW='''    # BODYMIND_A264_COMPACT_FINANCE: A263 hides legacy panels, so put finance inside visible Segreteria oggi.
    if 'bodymind-secretariat-home' in doc and 'BODYMIND_A263_SIMPLE_SECRETARIAT' in doc:
        if 'a264-finance-details' in doc:
            return doc, False
        a264_anchor="      </section>\\n\\n      <section class='a3-command-hero a6-command-hero'"
        if doc.count(a264_anchor)!=1:
            raise ValueError('STOP: anchor dashboard A263 mancante o ambiguo')
        _esc=html.escape
        _kpi=''.join('<div class="a264-fin-stat"><span>'+_esc(label)+'</span><b>'+_esc(euros(value))+'</b></div>' for label,value in (
            ('Entrate',data['entrate']),('Uscite',data['uscite']),('Saldo dei registri',data['saldo'])))
        _kpi+='<div class="a264-fin-stat"><span>Movimenti attivi</span><b>'+str(int(data['movimenti_attivi']))+'</b></div>'
        _teaser=_a262.tiny(data['origini_entrate']).replace('href="#a262-origin-anchor"','href="#a264-finance-details"').replace('apri gli altri controlli','apri il dettaglio')
        _finance_css=r"""<style id="a264-finance-style">
        .a264-finance-wrap{margin:18px 0 0;padding-top:16px;border-top:1px solid #35495e;min-width:0}
        .a264-finance-wrap h3{font-size:18px;margin:0 0 6px;color:#f5f8fe}
        .a264-finance-wrap .a264-sub{font-size:12px;color:#b8c9d9;line-height:1.55}
        .a264-fin-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:12px}
        .a264-fin-stat{padding:11px 10px;background:#1e3145;border:1px solid #37516b;border-radius:11px;min-width:0}
        .a264-fin-stat span{display:block;font-size:11px;color:#c6d5e4}
        .a264-fin-stat b{display:block;font-size:clamp(15px,1.8vw,22px);color:#fff;margin-top:6px;font-variant-numeric:tabular-nums}
        .a264-finance-wrap>details{margin:13px 0 0}
        .a264-finance-wrap>details>summary{padding:11px 12px;background:#243d54;color:#d4ebfa;border:1px solid #42617e;border-radius:11px;font-weight:700;cursor:pointer}
        .a264-finance-wrap>details>.bodymind-a237-finance{margin:12px 0 0}
        @media(max-width:750px){.a264-fin-stats{grid-template-columns:repeat(2,minmax(0,1fr))}}
        @media(max-width:450px){.a264-finance-wrap{padding-top:13px}.a264-fin-stat{padding:9px 8px}}
        </style>"""
        _open="""<script id='a264-finance-link'>
        document.addEventListener('click',function(e){
            var a=e.target.closest('#a262-show-details');if(!a)return;
            var d=document.getElementById('a264-finance-details');if(!d)return;
            e.preventDefault();d.open=true;
            var sub=d.querySelector('.a262-analysis');if(sub)sub.open=true;
            d.scrollIntoView({behavior:'auto',block:'start'});
        },true);
        </script>"""
        _markup=(_finance_css+_a262.css()
                 +"<div class=\\\"a264-finance-wrap\\\" aria-label=\\\"Flussi e origine degli incassi\\\">"
                 +"<h3>Flussi e bilancio</h3><p class=\\\"a264-sub\\\">Totale storico dei registri, tutte le annualità. Il saldo non rappresenta il conto bancario.</p>"
                 +"<div class=\\\"a264-fin-stats\\\">"+_kpi+"</div>"+_teaser
                 +"<details id=\\\"a264-finance-details\\\"><summary>Metodi di incasso, iscrizioni, mensili e sconti</summary>"
                 +finance_panel(data)+"</details></div>"+_open)
        doc=doc.replace(a264_anchor,_markup+'\\n      </section>\\n\\n      <section class=\\'a3-command-hero a6-command-hero\\'',1)
        return doc, True
'''


def patch(root):
    root=Path(root)
    path=root/'bodymind_a237_finance_truth.py'
    src=path.read_text(encoding='utf-8')
    if MARKER in src:
        if FAIL_MARKER not in src:raise RuntimeError('STOP A264: incomplete patch, manual review')
        return {'changed':False,'sha256':hashlib.sha256(src.encode()).hexdigest()}
    marker='    doc,changed=inject_markup(doc,finance_panel(data))\n'
    if src.count(marker)!=1 or 'A262_ORIGIN_ACTIVE' not in src:
        raise RuntimeError('STOP A264: A262 finance source not recognized')
    src=src.replace(marker,NEW+marker,1)
    fail='''            try:
                doc,changed=inject_markup(original,accounting_unavailable_markup())
                if changed:'''
    visible=r'''            try:
                # BODYMIND_A264_FAIL_VISIBLE: no hidden failure warning in compact A263.
                if 'bodymind-secretariat-home' in original and 'BODYMIND_A263_SIMPLE_SECRETARIAT' in original:
                    anchor="      </section>\n\n      <section class='a3-command-hero a6-command-hero'"
                    if original.count(anchor)!=1:
                        raise ValueError('STOP: cannot show finance reconciliation failure')
                    doc=original.replace(anchor,accounting_unavailable_markup()+"\n      </section>\n\n      <section class='a3-command-hero a6-command-hero'",1)
                    changed=True
                else:
                    doc,changed=inject_markup(original,accounting_unavailable_markup())
                if changed:'''
    if src.count(fail)!=1:
        raise RuntimeError('STOP A264: failure handler anchor changed')
    src=src.replace(fail,visible,1)
    compile(src,str(path),'exec')
    path.write_text(src,encoding='utf-8')
    return {'changed':True,'sha256':hashlib.sha256(src.encode()).hexdigest()}

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--root',required=True)
 print(json.dumps(patch(p.parse_args().root),indent=2))
