"""A376 - retire obsolete WhatsApp scheduling wizard from daily BodyMind operations.

GET-only redirects preserve every original POST endpoint and all legacy records.
The single source of truth for SumUp is the existing A372 persistent configuration.
No automatic messages, tables, migrations, expense writes, or backups are triggered.
"""
from __future__ import annotations
import re
from html import escape
from flask import redirect, request


def remove_obsolete_links(page):
    """Keep one real communications entry; hide misleading old settings in sidebar."""
    m=re.search(r'<aside\b[^>]*\bid=(["\'])app-sidebar\1[^>]*>',page,re.I)
    if not m:
        return page
    end=page.find('</aside>',m.end())
    if end<0:
        return page
    side=page[m.end():end]
    for path in ('/segreteria/whatsapp','/motore-automazioni'):
        side=re.sub(
            r'<a\b(?=[^>]*\bhref=["\']'+re.escape(path)+r'["\'])[^>]*>.*?</a>',
            '',side,flags=re.I|re.S
        )
    side=side.replace('Invii e comunicazioni','Comunicazioni e promemoria')
    return page[:m.end()]+side+page[end:]


def shared_banner(link):
    if link:
        ref=escape(link,quote=True)
        status=('<p style="margin:8px 0 12px;color:#c8e7f4">'
                'Link SumUp unico già configurato. Nessuna impostazione per atleta, '
                'nessun calendario da attivare e nessun backup aggiuntivo richiesto per inviare un messaggio.</p>'
                f'<a href="{ref}" target="_blank" rel="noopener noreferrer nofollow" '
                'style="display:inline-block;padding:12px 15px;border-radius:11px;'
                'background:#9adecf;color:#073448;font-weight:800;text-decoration:none">'
                'Apri il link SumUp condiviso</a>')
    else:
        status=('<p style="margin:8px 0 12px;color:#c8e7f4">'
                'Nessun link SumUp condiviso attivato. Puoi configurarlo '
                '<a href="/impostazioni/sumup-libero">qui</a>.</p>')
    return ('<section id="bm376-comms" aria-label="Comunicazioni semplificate" '
            'style="max-width:1100px;margin:16px auto;padding:17px;border:1px solid #5d9eaf;'
            'border-radius:17px;background:linear-gradient(135deg,#153b54,#152a42);'
            'color:#fff">'
            '<h2 style="margin:0;font-size:21px;color:#fff">Comunicazioni semplici</h2>'
            '<p style="margin:9px 0;color:#d5eaf6;line-height:1.55">'
            'Seleziona soltanto le famiglie da contattare in questa pagina, '
            'controlla la quota e prepara il messaggio. Nessun SMS o WhatsApp '
            'viene inviato senza una tua azione.</p>'
            +status+
            '<p style="margin:10px 0 0;font-size:13px;color:#b5d7e6">'
            'I vecchi promemoria automatici con giorni -3, 2, 7, 11 e la coda '
            'con richiesta BACKUP_VERIFICATO non servono per il pagamento delle quote.'
            '</p></section>')


def install(app):
    from asd_app.core import auth, has_role, load_config
    from a372_sumup_shared import stored_link

    @app.before_request
    def remove_legacy_wizards_from_daily_flow():
        if request.method!='GET' or not auth() or not has_role('admin'):
            return None
        old_path=request.path.rstrip('/')
        if old_path in ('/segreteria/whatsapp','/pagamenti/online'):
            # Historical records may still be inspected intentionally; no POST altered.
            if request.args.get('storico')=='1':
                return None
            return redirect('/segreteria/comunicazioni',302)
        return None

    @app.after_request
    def clearer_admin_communications(response):
        if (request.method!='GET' or response.status_code!=200
            or response.mimetype!='text/html' or response.direct_passthrough
            or not auth() or not has_role('admin')):
            return response
        before=response.get_data(as_text=True)
        page=remove_obsolete_links(before)
        if request.path.rstrip('/')=='/segreteria/comunicazioni' and 'bm376-comms' not in page:
            link=stored_link(load_config())
            panel=shared_banner(link)
            m=re.search(r'<main\b[^>]*>',page,re.I)
            if m:
                page=page[:m.end()]+panel+page[m.end():]
        if page!=before:
            response.set_data(page)
            response.headers.pop('ETag',None)
            response.headers['Cache-Control']='private, no-store'
            response.headers['X-BodyMind-Communications']='A376'
        return response

    print('BODYMIND A376 COMMUNICATIONS SIMPLIFIED — old WhatsApp scheduling no longer entry point',flush=True)
