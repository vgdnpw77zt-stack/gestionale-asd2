"""A375: restore admin Uscite and shared SumUp; show unresolved ledger items, read-only."""
import re
from decimal import Decimal
from html import escape as e
from flask import request, redirect, make_response

SUMUP='/impostazioni/sumup-libero'
OUT='/pagamenti/uscite'
CHECK='/contabilita/verifica'


def euro(v):
    try:return f'{Decimal(str(v or 0)):.2f}'.replace('.',',')+' €'
    except Exception:return '—'


def nav_html(page,path):
    # Only the navigation inside the original, authenticated administrator shell.
    match=re.search(r'<aside\b[^>]*\bid=["\']app-sidebar["\'][^>]*>',page,re.I)
    if not match:return page
    end=page.find('</aside>',match.end())
    if end<0:return page
    chunk=page[match.end():end]
    chunk=re.sub(r'href=(["\'])/impostazioni/pagamenti-online\1',
                 lambda x:'href='+x.group(1)+SUMUP+x.group(1),chunk,flags=re.I)
    chunk=chunk.replace('Impostazioni SumUp e pagamenti online','SumUp · Link unico')
    chunk=chunk.replace('link individuali SumUp','link condiviso SumUp')
    if 'bm375-out-menu' not in chunk:
        target=re.search(r'<a\b[^>]*\bhref=["\']/ricevute["\']',chunk,re.I)
        links=('<a class="bm375-out-menu" href="/pagamenti/uscite" style="display:block;padding:11px 14px;'
               'margin:4px;border-radius:10px;background:#174762;border:1px solid #6ca5bb;'
               'font-weight:800;color:#eff9ff;text-decoration:none">🧾 Uscite · Giustificativi</a>'
               '<a class="bm375-out-menu" href="/contabilita/verifica" style="display:block;padding:11px 14px;'
               'margin:4px;border-radius:10px;background:#174762;border:1px solid #6ca5bb;'
               'font-weight:800;color:#eff9ff;text-decoration:none">🔎 Riconciliazione · Controllo</a>')
        chunk=chunk[:target.start()]+links+chunk[target.start():] if target else links+chunk
    page=page[:match.end()]+chunk+page[end:]
    if path in ('/','/pagamenti','/quote-incassi') and 'id="bm375-shortcuts"' not in page:
        bar=('<nav id="bm375-shortcuts" style="display:flex;gap:9px;flex-wrap:wrap;'
             'padding:14px;border-radius:14px;background:#153d58;border:1px solid #5792b0;margin:12px 0">'
             '<a href="/pagamenti/uscite" style="color:white;padding:9px">🧾 Uscite e allegati</a>'
             '<a href="/contabilita/verifica" style="color:white;padding:9px">🔎 Riconciliazione</a>'
             '<a href="/impostazioni/sumup-libero" style="color:white;padding:9px">🔗 SumUp unico</a></nav>')
        m=re.search(r'<main\b[^>]*class=["\'][^"\']*\bcontent\b[^"\']*["\'][^>]*>',page,re.I)
        if m:page=page[:m.end()]+bar+page[m.end():]
    return page


def pending_movements(conn):
    from asd_app.bodymind_a253_manual import methods
    mapped=methods(conn)
    return [dict(x) for x in conn.execute(
        """SELECT id,data,tipo,descrizione,importo,COALESCE(auto_generato,0) AS auto_generato
        FROM movimenti WHERE pagamento_id IS NULL AND tipo IN ('uscita','entrata')
        ORDER BY id DESC""")
        if int(x['id']) not in mapped or int(x['auto_generato'])!=0]


def review_html(conn):
    missing=pending_movements(conn)
    expenses=[dict(x) for x in conn.execute(
       """SELECT id,data,descrizione,importo,metodo,allegato_nome FROM bodymind_uscite
       ORDER BY data DESC,id DESC LIMIT 300""")]
    total=sum((Decimal(str(x['importo'] or 0)) for x in expenses),Decimal('0'))
    rows=[]
    duplicate_count=0
    for x in missing:
        duplicates=[y for y in expenses
                    if x['tipo']=='uscita' and y['data']==x['data']
                    and Decimal(str(x['importo'] or 0))==Decimal(str(y['importo'] or 0))]
        if duplicates: duplicate_count+=1
        detail=('Possibile duplicato tecnico del gestionale, NON un nuovo bonifico: '+', '.join(
               f'<a href="/pagamenti/uscite?modifica={int(y["id"])}">uscita #{int(y["id"])}</a>'
               for y in duplicates)+'. Non registrare nuovamente il pagamento.' ) if duplicates else 'Verificare metodo e prova del movimento'
        rows.append('<tr><td>#'+str(x['id'])+'</td><td>'+e(str(x['data']))+'</td>'
                    '<td>'+e(str(x['descrizione']))+'</td><td>'+euro(x['importo'])+'</td>'
                    '<td>'+detail+'</td></tr>')
    expense_rows=[]
    for x in expenses:
        expense_rows.append('<tr><td>'+e(str(x['data']))+'</td>'
          '<td>'+e(str(x['descrizione']))+'</td><td>'+euro(x['importo'])+'</td>'
          '<td>'+('Sì' if x['allegato_nome'] else 'No')+'</td>'
          f'<td><a href="/pagamenti/uscite?modifica={int(x["id"])}">Apri</a></td></tr>')
    table_css=('style="border-collapse:collapse;width:100%;min-width:680px"')
    td_css='<style>.bm375wrap{max-width:1100px;margin:18px auto 60px;padding:16px;color:#edf4fd}.bm375wrap h1,.bm375wrap h2{color:#fff}.bm375wrap p{line-height:1.6}.bm375wrap a{color:#aff1ff}.bm375wrap section{padding:20px;border-radius:15px;border:1px solid #5b809f;background:#14314b;margin:14px 0}.bm375wrap td,.bm375wrap th{border-bottom:1px solid #426b8b;padding:12px;text-align:left}.bm375wrap .scroll{overflow-x:auto}.bm375wrap .notice{color:#ffe4b3}</style>'
    return (td_css+'<main class="bm375wrap"><h1>Uscite · Verifica contabile</h1>'
      '<p><a href="/pagamenti/uscite">Apri registro Uscite e giustificativi</a> · '
      '<a href="/impostazioni/sumup-libero">SumUp link unico</a></p>'
      f'<section><h2>Uscite presenti: {len(expenses)}</h2><p>Totale delle uscite registrate: <strong>{euro(total)}</strong>. '
      'Gli importi dei movimenti in verifica non vengono aggiunti a questo totale.</p>'
      '<div class="scroll"><table '+table_css+'><thead><tr><th>Data</th><th>Descrizione</th>'
      '<th>Importo</th><th>Allegato</th><th>Apri</th></tr></thead><tbody>'
      +''.join(expense_rows)+'</tbody></table></div></section>'
      f'<section><h2>Movimenti da verificare: {len(missing)}</h2>'
      +((f'<p class="notice">{duplicate_count} movimento/i già presente/i come uscita, dello stesso giorno e importo. '
           'È una possibile doppia registrazione prodotta dai moduli del gestionale: '
           '<strong>non devi eseguire né registrare altri bonifici</strong>. '
           'Il movimento tecnico va verificato e rettificato mantenendo la traccia originale.</p>')
         if missing and duplicate_count==len(missing) else
        '<p class="notice">Questi movimenti non hanno un metodo contabile verificato. '
        'Prima di riconciliarli confronta conto corrente, giustificativo e registro Uscite. '
        'Non registrare nuovamente un pagamento già presente.</p>' if missing else
        '<p>Nessun movimento manuale in attesa nella verifica corrente.</p>')
      +('<div class="scroll"><table '+table_css+'><thead><tr><th>Movimento</th><th>Data</th>'
        '<th>Descrizione</th><th>Importo</th><th>Verifica</th></tr></thead><tbody>'
        +''.join(rows)+'</tbody></table></div>' if missing else '')
      +'</section><section><h2>Riconciliazione</h2>'
      '<p>Se un movimento ripete una spesa già registrata, bisogna rettificare il doppione '
      'mantenendone la tracciabilità; se è distinto, va classificato con il metodo corretto. '
      'Questo controllo non cancella, modifica o convalida automaticamente alcun movimento.</p>'
      '</section></main>')


def install(app):
    from asd_app.core import admin_required, auth, has_role, db, layout
    @app.get(CHECK,endpoint='bm375_manual_check')
    @admin_required
    def reconciliation():
        c=db()
        try:page=review_html(c)
        finally:c.close()
        res=make_response(layout(page))
        res.headers['Cache-Control']='private, no-store'
        res.headers['X-BodyMind-Accounting']='A375'
        return res

    @app.before_request
    def obsolete_payment_route():
        if not auth() or not has_role('admin'):return None
        if request.method=='GET' and request.path=='/impostazioni/pagamenti-online':
            return None if request.args.get('storico')=='1' else redirect(SUMUP,302)
        if request.method=='POST' and request.path=='/impostazioni/pagamenti-online/link':
            return layout('<main><h1>Link individuali disattivati</h1><p>BodyMind usa il link SumUp '
              'unico a importo libero. I precedenti restano conservati.</p>'
              '<a href="/impostazioni/sumup-libero">Apri SumUp link unico</a></main>'),409
        if request.method=='GET' and request.path=='/contabilita':
            c=db()
            try:
                pending=len(pending_movements(c))
            except Exception:
                return None
            finally:c.close()
            if pending:return redirect(CHECK,302)
        return None

    @app.after_request
    def navigation(response):
        if (request.method!='GET' or response.status_code!=200 or
            response.mimetype!='text/html' or response.direct_passthrough or
            not auth() or not has_role('admin')):return response
        old=response.get_data(as_text=True)
        new=nav_html(old,request.path.rstrip('/') or '/')
        if new!=old:
            response.set_data(new)
            response.headers.pop('ETag',None)
            response.headers['Cache-Control']='private, no-store'
        return response

    # Disable only the legacy A293 per-athlete offer insertion on Family Home.
    callbacks=app.after_request_funcs.get(None,[])
    old=[x for x in callbacks if getattr(x,'__name__','')=='bodymind_a293_family_sumup_offer']
    for x in old:callbacks.remove(x)
    print('BODYMIND A375 READY: Uscite visible, shared SumUp replaces individual, review screen active, legacy family CTA removed='+str(len(old)),flush=True)
