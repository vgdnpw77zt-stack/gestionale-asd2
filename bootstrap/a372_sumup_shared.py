"""A372 - one reusable SumUp open-amount link for every BodyMind family.

Only the administrator sets an already-created SumUp link. This module does not
create charge requests, claim that a payment was made, or reconcile money based
on entered amounts. Existing dues/receipts/finance remain authoritative.
"""
from __future__ import annotations
from html import escape as hx
from urllib.parse import urlsplit
import re

from flask import abort, make_response, redirect, request

KEY='bodymind_sumup_open_amount'
RELEASE='A372'
ALLOWED_ROOTS=('sumup.com','sumup.me','sumup.io','sumup.link')


def validate_url(raw):
    url=str(raw or '').strip()
    if not url:
        return ''
    if len(url)>850 or any(c in url for c in '\r\n\t <>\"\''):
        raise ValueError('Link SumUp non valido')
    u=urlsplit(url)
    host=(u.hostname or '').strip('.').lower()
    if (u.scheme!='https' or u.username or u.password or
        u.port not in (None,443) or not u.path or u.path=='/' or
        not any(host==h or host.endswith('.'+h) for h in ALLOWED_ROOTS)):
        raise ValueError('Utilizza il link HTTPS originale generato da SumUp, non un altro sito')
    return url


def stored_link(cfg):
    x=cfg.get(KEY,{})
    if not isinstance(x,dict) or not x.get('enabled'):
        return ''
    try:return validate_url(x.get('url',''))
    except ValueError:return ''


CSS="""<style id="bm372-style">
.bm372{margin:24px auto 80px;max-width:850px;padding:14px;color:#e9f4ff}
.bm372 h1{font-size:clamp(25px,5vw,35px);color:#fff}
.bm372 p,.bm372 small{color:#b7d4eb;line-height:1.6}
.bm372 .panel{padding:21px;background:#102c46;border:1px solid #587da1;border-radius:19px;margin:15px 0}
.bm372 label{display:block;font-weight:700;margin:12px 0;color:#fff}
.bm372 input[type=url]{display:block;width:100%;font-size:16px;border:1px solid #9fc1d6;border-radius:12px;padding:13px;background:#fff;color:#14304b;margin-top:8px}
.bm372 button{border:1px solid #a0e6e4;border-radius:12px;background:#206787;color:#fff;padding:12px 17px;font-weight:750;font-size:16px;cursor:pointer}
.bm372 a{color:#c5f2ff}
.bm372-ok{padding:14px;border-radius:12px;border:1px solid #4c8c78;background:#143e32;color:#c5ffe0!important}
.bm372-open{padding:19px!important;margin:16px 0!important;border-radius:17px!important;border:1px solid #70c6d7!important;
 background:linear-gradient(110deg,#173d56,#133148)!important;color:#eef9ff!important}
.bm372-open h3{font-size:20px!important;color:#fff!important;margin:0 0 8px!important}
.bm372-open p,.bm372-open small{color:#cfecf4!important;font-size:13px!important;line-height:1.6!important}
.bm372-open a{display:inline-block!important;background:#b6e8d7!important;color:#08283d!important;
 padding:12px 17px!important;border-radius:12px!important;text-decoration:none!important;
 font-size:15px!important;font-weight:800!important;margin:8px 0!important}
.bm372-admin-link{display:inline-block;padding:10px 15px;border:1px solid #6b9da9;border-radius:11px;
 color:#fff!important;background:#144a64;text-decoration:none!important;font-weight:760}
</style>"""


def admin_page(cfg,status=''):
    item=cfg.get(KEY,{}) if isinstance(cfg.get(KEY),dict) else {}
    url=str(item.get('url') or '').strip()
    ok=bool(item.get('enabled')) and bool(stored_link(cfg))
    badge='<p class="bm372-ok" role="status">Impostazione salvata e attiva.</p>' if status=='ok' else ''
    state=('Link condiviso attivo' if ok else 'Link non attivo')
    return (CSS+'<main class="bm372"><p><a href="/pagamenti">← Torna ai pagamenti</a></p>'
            '<h1>SumUp · Link unico a importo libero</h1>'
            '<p>Configura qui una sola volta il link riutilizzabile che hai già creato in SumUp. '
            'Il collegamento sarà lo stesso per tutte le famiglie con una quota da pagare.</p>'
            f'<section class="panel"><h2>{state}</h2>{badge}'
            '<form method="post" action="/impostazioni/sumup-libero">'
            '{{CSRF}}'
            f'<label>Link SumUp riutilizzabile<input type="url" name="url" placeholder="https://pay.sumup.com/..." value="{hx(url,quote=True)}" required maxlength="850"></label>'
            f'<label><input type="checkbox" name="abilitato" value="1" {"checked" if ok else ""}> Attiva il collegamento nelle Aree Famiglie</label>'
            '<button type="submit">Salva link unico</button></form></section>'
            '<section class="panel"><h2>Come riconciliare i versamenti</h2>'
            '<p>La famiglia sceglie l’importo. Dopo l’incasso, controlla la transazione in SumUp, '
            'l’identità della pagante, il mese di riferimento e la quota effettivamente dovuta. '
            'Solo la segreteria registra il pagamento nel gestionale e rende lo stato «Pagato».</p>'
            '<p>Nessun importo precompilato, nessuna creazione di link per singola atleta e '
            'nessuna registrazione automatica della quota dopo un semplice clic.</p></section>'
            '</main>')


def family_button(url, iban=''):
    safe=hx(url,quote=True)
    bank=''
    if iban:
        bank='<p>In alternativa puoi utilizzare il bonifico sul conto BodyMind (IBAN: <strong>'+hx(iban)+'</strong>). Indica nome, cognome dell’atleta e mese.</p>'
    return ('<section class="bm372-open" id="bm372-open-sumup" aria-label="Paga con SumUp a importo libero">'
            '<h3>Versa la quota con SumUp</h3>'
            '<p>Utilizza sempre questo stesso link. Inserisci tu l’importo concordato per il tuo corso: '
            '50 €, 70 € o 90 € secondo la categoria assegnata dalla segreteria, salvo accordi individuali.</p>'
            f'<a href="{safe}" target="_blank" rel="noopener noreferrer nofollow" referrerpolicy="no-referrer">'
            'Apri SumUp e inserisci l’importo ↗</a>'
            '<small>Per agevolare il riconoscimento del versamento, inserisci nome, cognome e mese nelle note '
            'se il pagamento lo consente. Il pagamento non cambia automaticamente lo stato della quota: '
            'la segreteria deve verificarlo in SumUp e registrarlo nel gestionale.</small>'
            +bank+'</section>')


def family_due(page):
    # A366 uses exactly this status chip only for an actually outstanding quote.
    return bool(re.search(r'class=["\\']status-chip\\s+unpaid["\\']\\s*>\\s*Da pagare',page,re.I))


def install(app):
    from asd_app.core import admin_required, auth, has_role, load_config, save_config, csrf_input, layout

    @app.route('/impostazioni/sumup-libero',methods=['GET','POST'],endpoint='bm372_sumup_shared')
    @admin_required
    def shared_config():
        if request.method=='POST':
            try:
                raw=validate_url(request.form.get('url'))
                if not raw:raise ValueError('Incolla il link SumUp che hai già creato')
                cfg=load_config()
                cfg[KEY]={'url':raw,'enabled':request.form.get('abilitato')=='1'}
                save_config(cfg)
            except (ValueError,OSError) as exc:
                return layout(CSS+'<main class="bm372"><h1>Link non salvato</h1><p>'+hx(str(exc))+'</p>'
                              '<a href="/impostazioni/sumup-libero">Riprova</a></main>'),400
            return redirect('/impostazioni/sumup-libero?esito=ok',303)
        cfg=load_config()
        html=admin_page(cfg,request.args.get('esito',''))
        return make_response(layout(html.replace('{{CSRF}}',csrf_input())))

    def attach(response):
        if (request.method!='GET' or response.status_code!=200 or
            response.mimetype!='text/html' or response.direct_passthrough):
            return response
        if request.endpoint=='app_tesserato':
            cfg=load_config()
            url=stored_link(cfg)
            if not url:return response
            page=response.get_data(as_text=True)
            if 'bm372-open-sumup' in page:return response
            if not family_due(page):return response
            # A366's named insertion point is deliberately preserved.
            slot='<!-- BODYMIND_SUMUP_SLOT -->'
            if page.count(slot)!=1:
                app.logger.warning('A372 SumUp slot missing on Family Home')
                return response
            iban=str(cfg.get('iban') or '').strip()
            page=page.replace(slot,family_button(url,iban)+slot,1)
            # Remove any old individual SumUp CTA in favor of one shared URL.
            page=re.sub(r'<a\\b[^>]*class="pay-cta"[^>]*>[^<]*SumUp[^<]*</a>','',page,flags=re.I)
            page=page.replace('</head>',CSS+'</head>',1)
            page=page.replace('Per il link SumUp o i dati del bonifico contatta la segreteria: non è disponibile un pagamento online già verificato per questa quota.','Puoi utilizzare il link SumUp condiviso qui sotto, oppure contattare la segreteria per il bonifico.')
            response.set_data(page)
            response.headers.pop('ETag',None)
            response.headers['Cache-Control']='private, no-store'
            response.headers['Referrer-Policy']='no-referrer'
            response.headers['X-BodyMind-Sumup']='A372'
            return response
        if request.path.rstrip('/') in ('/pagamenti','/impostazioni','/pagamenti-pro') and auth() and has_role('admin'):
            page=response.get_data(as_text=True)
            if 'bm372-admin-link' in page:return response
            match=re.search(r'<main\\b[^>]*>',page,re.I)
            if not match:return response
            btn='<div style="margin:10px 0 18px"><a class="bm372-admin-link" href="/impostazioni/sumup-libero">🔗 Configura SumUp · link unico a importo libero</a></div>'
            page=page[:match.end()]+CSS+btn+page[match.end():]
            response.set_data(page)
            response.headers.pop('ETag',None)
            return response
        return response

    app.after_request_funcs.setdefault(None,[]).insert(0,attach)
    print('BODYMIND A372 SHARED SUMUP READY — reusable open amount, manual verification',flush=True)
