"""Staging-only A278 patch, run on isolated reviewed clone AFTER A277.
No production, database, receipts, PDFs or external services are accessed.
"""
from pathlib import Path
import ast, hashlib, json, shutil, tempfile, os

MARKER='BODYMIND_A278_LISTINO_UNICO'

def once(body,a,b,label):
    if body.count(a)!=1:raise RuntimeError(f'STOP A278: {label} anchor {body.count(a)}')
    return body.replace(a,b,1)

def patch(root,source=None):
    root=Path(root); source=Path(source or Path(__file__).parent)
    current={k:(root/k).read_text('utf-8') for k in ('core.py','routes_quote_incassi.py','routes_pagamenti.py')}
    core=current['core.py']; quote=current['routes_quote_incassi.py']; pay=current['routes_pagamenti.py']
    if MARKER in core:raise RuntimeError('STOP A278: already installed')
    if 'BODYMIND_A276_INGRESSO_VERIFICATO' not in core:
        raise RuntimeError('STOP A278: A277 / A276 verified enrollment baseline missing')
    bridge='''from . import route_a276 as _bodymind_a276_route
_bodymind_a276_route.install(globals())'''
    enhanced=bridge+'''\n\n# '''+MARKER+''': settings and single source of truth for monthly tariff suggestions.
from . import a278_fee_settings as _bodymind_a278_fee_settings
_bodymind_a278_fee_settings.install(globals())'''
    core=once(core,bridge,enhanced,'route bridge')
    old="""                    amount=('50.00' if action_tipo=='iscrizione' else ('70.00' if selected_tid not in bm_non_due and selected_tid not in bm_pre_entry else '0.00'))"""
    new="""                    # BODYMIND_A278_LISTINO_UNICO: never prefill 70 EUR from a string literal.
                    from .a278_quote_rules import recommended_for_form as _a278_recommend
                    _a278_form_suggestion=_a278_recommend(db,selected_tid,mese,anno)
                    amount=('50.00' if action_tipo=='iscrizione' else (
                        '0.00' if selected_tid in bm_non_due or selected_tid in bm_pre_entry
                        else _a278_form_suggestion['amount_text']))"""
    core=once(core,old,new,'70 EUR monthly hardcode')
    # Used only on existing/edit forms where _a278_form_suggestion would otherwise not be bound.
    old2="""                else:
                    form_html=f\"\"\"<form class='bmpv7-form' method='post' action='/pagamenti/registra-unico' data-bm-standard='{50 if action_tipo==\"iscrizione\" else 70}'"""
    new2="""                else:
                    from .a278_quote_rules import recommended_for_form as _a278_recommend
                    _a278_form_suggestion=_a278_recommend(db,selected_tid,mese,anno)
                    _a278_standard=('50.00' if action_tipo=='iscrizione' else _a278_form_suggestion['amount_text'])
                    form_html=f\"\"\"<form class='bmpv7-form' method='post' action='/pagamenti/registra-unico' data-bm-standard='{e(_a278_standard)}'"""
    core=once(core,old2,new2,'dynamic form comparison')
    core=once(core,"""<small class='bmpv8-instructions'>50 € iscrizione / 70 € mensile sono gli importi ordinari. Puoi inserire 0 € con motivo: non verrà emessa alcuna ricevuta né registrato denaro incassato.</small>""",
    """<small class='bmpv8-instructions'>L’importo mensile è proposto dal listino e dalle eventuali eccezioni salvate. Se manca, verifica la tariffa prima di registrare. Una quota non dovuta si documenta con motivazione, senza generare ricevute da 0 €. <a href='/impostazioni/quote'>Impostazioni tariffe</a>.</small>""",'fee help')
    core=once(core,"""<a href='/pagamenti'>Pagamenti</a>\n      </header>\n      <form class='bmqi-period'""", """<nav><a href='/pagamenti'>Pagamenti</a> · <a href='/impostazioni/quote'>Tariffe e quote</a> · <a href='/segreteria/quote-verifica'>Spiega i residui</a></nav>\n      </header>\n      <form class='bmqi-period'""",'quote menu')
    # Ensure the quote summary is explicitly marked as request workflow, not verified debt.
    # One audited tariff entrypoint: disable an older POST handler that bypassed history
    # and silently aligned unconfigured months after changing a price.
    legacy_start="""@app.post('/quote-incassi/listino')
@admin_required
def quote_listino_save():"""
    legacy_end="""@app.post('/quote-incassi/non-dovuto/<int:tid>')"""
    if quote.count(legacy_start)!=1 or quote.count(legacy_end)!=1:
        raise RuntimeError('STOP A278: legacy tariff handler anchors changed')
    before,tail=quote.split(legacy_start,1)
    discarded,after=tail.split(legacy_end,1)
    if 'UPDATE quote_listino' not in discarded or 'stato=CASE' not in discarded:
        raise RuntimeError('STOP A278: legacy tariff handler not recognized')
    quote=before+legacy_start+"""
    # A278: old endpoint no longer alters monthly dues or silently changes the listino.
    return redirect_with_message('/impostazioni/quote',
        'Per aggiornare la tariffa usa Impostazioni → Tariffe e quote: modifica motivata e verificabile.','error')

"""+legacy_end+after
    pay=once(pay,"""<div class='label'>Da recuperare online/link</div>""", """<div class='label'>Richieste aperte, non debito accertato</div>""", 'requests label')
    pay=once(pay,"""<div class='label'>Quote mese mancanti</div>""", """<div class='label'>Quote da verificare nel mese</div>""",'due label')
    files={'core.py':core,'routes_quote_incassi.py':quote,'routes_pagamenti.py':pay,
           'a278_fee_settings.py':(source/'a278_fee_settings.py').read_text('utf-8'),
           'a278_quote_rules.py':(source/'a278_quote_rules.py').read_text('utf-8')}
    for name,body in files.items():ast.parse(body,filename=name)
    # Copy ONLY to private staging clone, atomically after all anchors/syntax validated.
    for name,body in files.items():
        if (root/name).exists() and (root/name).read_text('utf-8')==body:continue
        tmp=root/(name+'.a278.tmp')
        tmp.write_text(body,'utf-8')
        os.replace(tmp,root/name)
    return {'changed':True,'files':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in files.items()},
            'no_db_changes':True,'no_pdf_changes':True}
if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('--root',required=True)
    print(json.dumps(patch(ap.parse_args().root),indent=2))