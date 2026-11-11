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



def owner_bilanci_html(conn, selected_month):
    """Owner-only read-only reporting. Source-level totals are never bank/cash balances."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from html import escape as h
    from decimal import Decimal
    from asd_app.bodymind_a237_finance_truth import payment_active
    month = selected_month if re.fullmatch(r'\d{4}-(?:0[1-9]|1[0-2])', selected_month or '') else datetime.now(ZoneInfo('Europe/Rome')).strftime('%Y-%m')
    def money(n):
        v=Decimal(str(n if n is not None else 0))
        return f'{v:,.2f}'.replace(',','_').replace('.',',').replace('_','.')+' €'
    def ym(value):
        t=str(value or '').strip()
        return t[:7].replace('/','-') if re.match(r'^\d{4}[-/](?:0[1-9]|1[0-2])',t) else None
    def paymonth(p):
        for key in ('data_pagamento','data_incasso','paid_at'):
            x=ym(p.get(key))
            if x:return x
        return None
    payments=[dict(r) for r in conn.execute('SELECT * FROM pagamenti ORDER BY id DESC')]
    expenses=[dict(r) for r in conn.execute('SELECT * FROM bodymind_uscite ORDER BY data DESC,id DESC')]
    active=[p for p in payments if payment_active(p)]
    monthly_payments=[p for p in active if paymonth(p)==month]
    unknown_paydates=sum(1 for p in active if not paymonth(p))
    expenses=[x for x in expenses if Decimal(str(x.get('importo') or 0))>0]
    monthly_expenses=[x for x in expenses if ym(x.get('data'))==month]
    unknown_expdates=sum(1 for x in expenses if not ym(x.get('data')))
    total_pay=sum((Decimal(str(p['importo'])) for p in monthly_payments),Decimal('0'))
    total_out=sum((Decimal(str(x['importo'])) for x in monthly_expenses),Decimal('0'))
    def pill(title,value,note):
        return ('<div class="bmbl-card"><span>'+h(title)+'</span><strong>'+h(value)+
                '</strong><small>'+h(note)+'</small></div>')
    pay_status=('Completo per le date registrate' if unknown_paydates==0 else
                f'{unknown_paydates} pagamenti attivi senza data utilizzabile')
    out_status=('Solo registro Uscite; non somma movimenti tecnici' if unknown_expdates==0 else
                f'{unknown_expdates} uscite senza data utilizzabile')
    cards=(pill('Incassi da pagamenti nel mese',money(total_pay) if not unknown_paydates else 'Non determinabile',pay_status)+
           pill('Uscite dal registro Uscite nel mese',money(total_out) if not unknown_expdates else 'Non determinabile',out_status)+
           pill('Saldo bancario','Non determinabile','Mancano saldo iniziale e movimenti bancari completi')+
           pill('Saldo fisico di cassa','Non determinabile','Richiede giacenza iniziale e trasferimenti')+
           pill('Risultato netto completo','Non determinabile','I registri devono distinguere ogni movimento tecnico da una nuova operazione'))
    ids=(10,134313)
    old_exp=next((x for x in expenses if int(x['id'])==ids[0]),None)
    old_mov=conn.execute('SELECT id,data,tipo,descrizione,importo,pagamento_id,auto_generato FROM movimenti WHERE id=?',(ids[1],)).fetchone()
    match=(old_exp is not None and old_mov is not None and
           Decimal(str(old_exp['importo']))==Decimal('520') and
           Decimal(str(old_mov['importo']))==Decimal('520') and
           str(old_exp.get('data') or '')==str(old_mov['data'] or ''))
    if match:
        notice=('Il registro Uscite conserva la registrazione #10 da 520 € e il registro Movimenti il riferimento #134313 '
                'della stessa data e dello stesso importo. In questa vista il movimento tecnico NON viene sommato '
                'nuovamente alle uscite. Questo controllo non modifica o convalida i collegamenti nel database.')
    else:
        notice=('La corrispondenza storica tra uscita #10 e movimento #134313 da 520 € non è confermata '
                'dai dati attuali: nessuna rettifica automatica è stata effettuata.')
    def exp_rows():
        return ''.join('<tr><td>'+h(str(x.get('data') or '—'))+'</td><td>'+h(str(x.get('descrizione') or '—'))+
                       '</td><td>'+h(str(x.get('metodo') or 'non indicato'))+'</td><td>'+h(money(x['importo']))+
                       '</td><td><a href="/pagamenti/uscite?modifica='+str(int(x['id']))+'">Apri #'+str(int(x['id']))+'</a></td></tr>'
                       for x in monthly_expenses[:150])
    def pay_rows():
        return ''.join('<tr><td>'+h(str(paymonth(p) or '—'))+'</td><td>'+h(str(p.get('causale') or 'Pagamento'))+
                       '</td><td>'+h(str(p.get('metodo_pagamento') or 'non indicato'))+'</td><td>'+h(money(p['importo']))+
                       '</td><td>#'+str(int(p['id']))+'</td></tr>' for p in monthly_payments[:150])
    return (
      '<main id="bm-owner-bilanci" class="bmbl"><style>'
      '.bmbl{max-width:1060px;margin:18px auto 80px;padding:12px;color:#edf5ff}'
      '.bmbl *{box-sizing:border-box}.bmbl h1,.bmbl h2{color:#fff}.bmbl a{color:#bceaff}'
      '.bmbl .bmbl-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:18px 0}'
      '.bmbl-card{background:#17344a;border:1px solid #5b7e98;border-radius:14px;padding:16px;min-width:0}'
      '.bmbl-card span,.bmbl-card small{display:block;color:#d1e0ef}.bmbl-card strong{display:block;font-size:20px;margin:8px 0;overflow-wrap:anywhere}'
      '.bmbl section{background:#10283d;border:1px solid #3f6880;border-radius:14px;padding:16px;margin:16px 0}'
      '.bmbl .bmbl-scroll{overflow-x:auto}.bmbl table{border-collapse:collapse;width:100%;min-width:640px}'
      '.bmbl td,.bmbl th{text-align:left;border-bottom:1px solid #35536b;padding:10px;font-size:13px;vertical-align:top}'
      '.bmbl input,.bmbl button{padding:10px;border-radius:8px}.bmbl .bmbl-note{line-height:1.6;color:#e0e8f2}'
      '@media(max-width:600px){.bmbl table{display:block;min-width:0}.bmbl thead{display:none}.bmbl tbody{display:block}'
      '.bmbl tr{display:block;border:1px solid #37566d;border-radius:10px;margin:9px 0;padding:8px}'
      '.bmbl td{display:block;border:0;padding:5px 3px;overflow-wrap:anywhere}.bmbl td:before{color:#a8c4d7;font-weight:600}'
      '.bmbl-exp td:nth-child(1):before,.bmbl-pay td:nth-child(1):before{content:"Data: "}'
      '.bmbl-exp td:nth-child(2):before{content:"Causale: "}.bmbl-exp td:nth-child(3):before,.bmbl-pay td:nth-child(3):before{content:"Metodo: "}'
      '.bmbl-exp td:nth-child(4):before,.bmbl-pay td:nth-child(4):before{content:"Importo: "}'
      '.bmbl-pay td:nth-child(2):before{content:"Causale: "}.bmbl-exp td:nth-child(5):before{content:"Dettaglio: "}'
      '.bmbl-pay td:nth-child(5):before{content:"ID: "}}'
      '</style><a href="/mobile">‹ Torna alla Home Owner</a><h1>Bilanci</h1>'
      '<p>Vista di sola lettura sui registri reali. Non genera né modifica pagamenti, giustificativi o riconciliazioni.</p>'
      '<form method="get" action="/owner/bilanci"><label for="bmbl-month">Periodo </label>'
      '<input id="bmbl-month" name="mese" type="month" value="'+h(month)+'"><button type="submit">Mostra</button></form>'
      '<div class="bmbl-grid">'+cards+'</div>'
      '<section><h2>Bonifico 520 € — verifica delle due registrazioni</h2><p class="bmbl-note">'+h(notice)+'</p>'
      '<p><a href="/pagamenti/uscite?modifica=10">Registro uscita #10</a> · '
      '<a href="/contabilita/verifica">Verifica movimenti esistenti</a></p></section>'
      '<section><h2>Uscite registrate del periodo ('+str(len(monthly_expenses))+')</h2>'
      '<p class="bmbl-note">Ogni uscita viene mostrata una volta per ID del registro spese. '
      'Non aggiungiamo automaticamente le registrazioni presenti anche in Movimenti.</p>'
      '<div class="bmbl-scroll"><table class="bmbl-exp"><thead><tr><th>Data</th><th>Descrizione</th><th>Metodo</th><th>Importo</th><th>Documento</th></tr></thead>'
      '<tbody>'+ (exp_rows() or '<tr><td colspan="5">Nessuna uscita con data nel periodo selezionato</td></tr>')+'</tbody></table></div></section>'
      '<section><h2>Pagamenti attivi del periodo ('+str(len(monthly_payments))+')</h2>'
      '<p class="bmbl-note">Sono inclusi solo gli incassi riconosciuti come attivi dal motore pagamenti; '
      'movimenti manuali distinti non vengono sommati senza un collegamento verificabile.</p>'
      '<div class="bmbl-scroll"><table class="bmbl-pay"><thead><tr><th>Data</th><th>Causale</th><th>Metodo</th><th>Importo</th><th>ID</th></tr></thead>'
      '<tbody>'+(pay_rows() or '<tr><td colspan="5">Nessun pagamento attivo con data nel periodo selezionato</td></tr>')+'</tbody></table></div></section>'
      '<p><a href="/pagamenti/uscite">Uscite e giustificativi</a> · '
      '<a href="/contabilita/verifica">Controllo movimenti</a> · '
      '<a href="/impostazioni/sumup-libero">Impostazioni SumUp</a></p></main>')



def install(app):
    from asd_app.core import admin_required, auth, has_role, db, layout
    @app.get('/owner/bilanci',endpoint='bm_owner_bilanci_readonly')
    @admin_required
    def owner_bilanci_readonly():
        if not auth() or not has_role('admin'):
            from flask import abort
            abort(403)
        conn=db()
        try:
            conn.execute('PRAGMA query_only=ON')
            page=owner_bilanci_html(conn,request.args.get('mese',''))
        finally:
            conn.close()
        res=make_response(layout(page))
        res.headers['Cache-Control']='private, no-store'
        res.headers['Vary']='Cookie'
        res.headers['X-BodyMind-Bilanci']='READONLY-20261111'
        return res

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
        # Footer Bilanci: use the existing accounting page without forcing reconciliation.
        # All other visits retain the original A375 reconciliation safeguard.
        if (request.method=='GET' and request.path=='/contabilita'
                and request.args.get('bm_owner_bilanci')!='1'):
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
