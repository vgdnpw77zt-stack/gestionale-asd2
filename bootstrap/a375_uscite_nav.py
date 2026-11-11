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



def _audit_channel_readonly(conn):
    """Aggregate-only fiscal audit; no personal details, no SQL writes."""
    import json
    from collections import Counter, defaultdict
    from decimal import Decimal
    from asd_app.bodymind_a237_finance_truth import snapshot, payment_channel, payment_active
    from asd_app.bodymind_a253_manual import methods

    def v(x):return Decimal(str(x if x is not None else 0)).quantize(Decimal('0.01'))
    def sumstr(rows):return str(sum((v(r.get('importo')) for r in rows),Decimal('0.00')))
    ps=[dict(x) for x in conn.execute('SELECT * FROM pagamenti')]
    es=[dict(x) for x in conn.execute('SELECT * FROM bodymind_uscite')]
    ms=[dict(x) for x in conn.execute('SELECT * FROM movimenti')]
    active=[x for x in ps if payment_active(x)]
    remap=methods(conn)
    manual_in=[];manual_out=[]; unclassified=[]
    for m in ms:
        if m.get('pagamento_id') is not None or int(m.get('auto_generato') or 0):
            continue
        typ=str(m.get('tipo') or '').casefold()
        if typ not in ('entrata','incasso','income','uscita','spesa','expense'):continue
        if int(m['id']) not in remap:
            if v(m['importo']):unclassified.append(m)
            continue
        m=dict(m,metodo=remap[int(m['id'])])
        (manual_in if typ in ('entrata','incasso','income') else manual_out).append(m)
    methods_names=('contanti','bonifico','carta_pos_sumup','addebito','altro','non_classificato')
    report={}
    for name in methods_names:
        pays=[x for x in active if payment_channel(x.get('metodo_pagamento'))==name]
        expense=[x for x in es if v(x.get('importo'))>0 and payment_channel(x.get('metodo'))==name]
        manually_in=[x for x in manual_in if payment_channel(x.get('metodo'))==name]
        manually_out=[x for x in manual_out if payment_channel(x.get('metodo'))==name]
        report[name]={'pagamenti_n':len(pays),'pagamenti_euro':sumstr(pays),
                      'manuali_entrata_n':len(manually_in),'manuali_entrata_euro':sumstr(manually_in),
                      'uscite_n':len(expense),'uscite_euro':sumstr(expense),
                      'manuali_uscita_n':len(manually_out),'manuali_uscita_euro':sumstr(manually_out)}
    try:
        truth=snapshot()
        canonical={'status':'OK','entrate':str(truth['entrate']),'uscite':str(truth['uscite']),
                   'per_metodo':{k:{'entrate':str(truth['entrate_per_metodo'][k]),'uscite':str(truth['uscite_per_metodo'][k]),
                                    'n_incassi':truth['movimenti_per_metodo'][k]} for k in methods_names},
                   'da_verificare':str(truth['da_verificare_senza_correlazione']),
                   'non_classificati':truth['movimenti_non_classificati'],
                   'ricevute_anomale':truth['anomalie_ricevute']}
    except Exception as exc:
        canonical={'status':'BLOCK','reason':type(exc).__name__+': '+str(exc)[:160]}
    channel_mismatches=[]
    if canonical['status']=='OK':
        for name in methods_names:
            r=report[name]; ca=canonical['per_metodo'][name]
            recorded_in=v(r['pagamenti_euro'])+v(r['manuali_entrata_euro'])
            recorded_out=v(r['uscite_euro'])+v(r['manuali_uscita_euro'])
            if recorded_in!=v(ca['entrate']) or recorded_out!=v(ca['uscite']):
                channel_mismatches.append(name+':amount')
            if r['pagamenti_n']+r['manuali_entrata_n']!=int(ca['n_incassi']):
                channel_mismatches.append(name+':count')
    expense_match=[]
    for m in unclassified:
        hits=[int(x['id']) for x in es if v(x.get('importo'))==v(m['importo']) and
               str(x.get('data') or '')==str(m.get('data') or '')]
        expense_match.append({'movement_id':int(m['id']),'amount':str(v(m['importo'])),
                              'matches_expense_ids':hits})
    all_tables=[str(x['name']) for x in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    cash_tables=[name for name in all_tables if any(t in name.casefold() for t in
                  ('cassa','banca','cash','bank','trasfer','versament','preliev','saldo','deposit'))]
    doc={'status':'AGGREGATE_READONLY','canonical':canonical,'channels':report,
         'movimenti_non_mappati':len(unclassified),'unclassified_expense_crosscheck':expense_match,
         'possible_cash_transfer_tables':cash_tables,'income_mapped':len(manual_in),
         'expense_mapped':len(manual_out),'mismatches':channel_mismatches}
    print('BODYMIND CASH CHANNEL AUDIT '+json.dumps({
          'canonical':canonical['status'],'channels_ok':not channel_mismatches,
          'unknown_technical_count':len(unclassified),
          'unknown_matched_expenses':sum(bool(x['matches_expense_ids']) for x in expense_match),
          'cash_transfer_tables':len(cash_tables)},ensure_ascii=False),flush=True)
    return doc


def owner_bilanci_html(conn, selected_month):
    """Read-only Owner view of the EXISTING payments, expenses and A253 manual ledger.

    Uses the real ledger dates and original payment-activity classifier. Separately
    labelled bank/cash *flows* are never misrepresented as available balances.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from html import escape as h
    from collections import defaultdict
    from decimal import Decimal
    from asd_app.bodymind_a237_finance_truth import payment_active, payment_channel
    from asd_app.bodymind_a253_manual import methods as a253_methods

    ZERO = Decimal('0.00')
    period = selected_month if (selected_month == 'tutto' or
         re.fullmatch(r'\d{4}-(?:0[1-9]|1[0-2])', selected_month or '')) else datetime.now(ZoneInfo('Europe/Rome')).strftime('%Y-%m')
    def val(raw):
        d=Decimal(str(raw if raw is not None else 0))
        if not d.is_finite():
            raise ValueError('Importo non valido nel registro')
        return d.quantize(Decimal('0.01'))
    def money(raw):
        return f'{val(raw):,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')+' €'
    def ym(raw):
        s=str(raw or '').strip()
        a=re.match(r'^(\d{4})[-/](0[1-9]|1[0-2])(?:[-/]|T| |$)',s)
        if a:return a.group(1)+'-'+a.group(2)
        b=re.match(r'^\d{2}/(0[1-9]|1[0-2])/(\d{4})(?: |$)',s)
        return b.group(2)+'-'+b.group(1) if b else None
    def in_period(date):
        return period=='tutto' or ym(date)==period
    def fmt_date(value):
        return h(str(value or 'Data non indicata'))
    def channel(raw):
        c=payment_channel(raw)
        return c if c in ('contanti','bonifico','carta_pos_sumup','addebito','altro','non_classificato') else 'non_classificato'
    def card(title,amount,note):
        return ('<article class="bmbl-card"><span>'+h(title)+'</span><strong>'+money(amount)+
                '</strong><small>'+h(note)+'</small></article>')

    # Original source records. SQL SELECT only; the original payment engine decides active status.
    ps=[dict(r) for r in conn.execute('SELECT * FROM pagamenti ORDER BY id DESC')]
    es=[dict(r) for r in conn.execute('SELECT * FROM bodymind_uscite ORDER BY data DESC,id DESC')]
    ms=[dict(r) for r in conn.execute('SELECT id,data,tipo,descrizione,importo,pagamento_id,auto_generato FROM movimenti ORDER BY id DESC')]
    classified=a253_methods(conn)
    linked=defaultdict(list)
    for m in ms:
        if (m['pagamento_id'] is not None and
            str(m['tipo'] or '').strip().lower() in ('entrata','incasso','income') and ym(m['data'])):
            linked[int(m['pagamento_id'])].append(str(m['data']))
    def pay_date(p):
        dates=linked.get(int(p['id'])) or []
        if dates:return max(dates)
        for field in ('data_pagamento','data_incasso','paid_at','data'):
            if field in p and ym(p[field]):return str(p[field])
        return None

    valid_pay=[p for p in ps if payment_active(p)]
    dated_pay=[p for p in valid_pay if in_period(pay_date(p))]
    expenses=[x for x in es if val(x.get('importo'))>0]
    dated_exp=[x for x in expenses if in_period(x.get('data'))]
    missing_pay=sum(1 for x in valid_pay if not ym(pay_date(x)))
    missing_exp=sum(1 for x in expenses if not ym(x.get('data')))
    # A253-classified manual movements are separate from payments. Without that
    # marker, an orphan ledger movement is NOT automatically a new incasso/spesa.
    manual_income=[]; manual_out=[]; unclassified=[]
    for m in ms:
        if m['pagamento_id'] is not None or int(m['auto_generato'] or 0)!=0:
            continue
        t=str(m['tipo'] or '').strip().lower()
        if t not in ('entrata','incasso','income','uscita','spesa','expense'):
            continue
        if int(m['id']) not in classified:
            if val(m['importo'])!=0:unclassified.append(m)
            continue
        m=dict(m,metodo=classified[int(m['id'])])
        if t in ('entrata','incasso','income'):manual_income.append(m)
        else:manual_out.append(m)
    # A manually classified expense with the same date+amount as a documented
    # expense is NOT added again. The coincidence is shown for auditing.
    expense_keys={(ym(x.get('data')),val(x['importo'])) for x in expenses}
    manual_duplicates=[m for m in manual_out
                       if (ym(m['data']),val(m['importo'])) in expense_keys]
    # A253 is authoritative for manual transactions. Coincidence alone is NOT proof
    # of duplication: preserve each classified movement, and flag lookalikes for audit.
    distinct_manual_out=list(manual_out)
    entered_man_in=[m for m in manual_income if in_period(m['data'])]
    entered_man_out=[m for m in distinct_manual_out if in_period(m['data'])]
    incoming=dated_pay+entered_man_in
    outgoing=dated_exp+entered_man_out
    def inflow_method(p):
        return channel(p.get('metodo_pagamento') if 'metodo_pagamento' in p else p.get('metodo'))
    def outflow_method(x):
        return channel(x.get('metodo'))
    income=sum((val(p.get('importo')) for p in incoming),ZERO)
    expense=sum((val(x.get('importo')) for x in outgoing),ZERO)
    in_channels={k:ZERO for k in ('contanti','bonifico','carta_pos_sumup','addebito','altro','non_classificato')}
    out_channels={k:ZERO for k in in_channels}
    in_counts={k:0 for k in in_channels}
    out_counts={k:0 for k in in_channels}
    for p in incoming:
        k=inflow_method(p);in_channels[k]+=val(p.get('importo'));in_counts[k]+=1
    for x in outgoing:
        k=outflow_method(x);out_channels[k]+=val(x.get('importo'));out_counts[k]+=1
    total_pay=sum((val(p.get('importo')) for p in valid_pay),ZERO)
    total_man=sum((val(p.get('importo')) for p in manual_income),ZERO)
    total_exp=sum((val(x.get('importo')) for x in expenses),ZERO)
    total_extra=sum((val(x.get('importo')) for x in distinct_manual_out),ZERO)

    # Compare against the canonical finance snapshot when it can be evaluated.
    # A stale technical movement must not replace true payments with bogus zeros.
    canonical_status='Controllo di coerenza tra registri'
    if period=='tutto':
        try:
            from asd_app.bodymind_a237_finance_truth import snapshot
            truth=snapshot()
            if val(truth['entrate'])==income and val(truth['uscite'])==expense:
                canonical_status='Totali coerenti con il motore contabile A237'
            else:
                canonical_status='Totali del registro da confrontare con il motore A237'
        except (ValueError,RuntimeError,KeyError,TypeError,ImportError) as exc:
            canonical_status='Registri visibili; controllo tecnico A237 ancora da risolvere'
    missing_note=''
    if period!='tutto' and (missing_pay or missing_exp):
        missing_note=('<p class="bmbl-notice">Nel mese sono riportate soltanto le operazioni con data registrata. '
                      +h(str(missing_pay))+' pagamenti e '+h(str(missing_exp))+
                      ' uscite non hanno una data riconosciuta: sono comunque inclusi nei totali storici.</p>')
    header_cards=(
        card('Entrate registrate',income,'Tutti gli incassi attivi del periodo')+
        card('Uscite registrate',expense,'Uscite effettivamente registrate')+
        card('Risultato del periodo',income-expense,'Entrate meno uscite: non è un saldo bancario')+
        card('Contanti incassati',in_channels['contanti'],str(in_counts['contanti'])+' pagamenti registrati')+
        card('Contanti usciti',out_channels['contanti'],str(out_counts['contanti'])+' uscite registrate')+
        card('Bonifici ricevuti',in_channels['bonifico'],str(in_counts['bonifico'])+' incassi registrati')+
        card('Bonifici in uscita',out_channels['bonifico'],str(out_counts['bonifico'])+' pagamenti registrati')+
        card('Carta / POS / SumUp',in_channels['carta_pos_sumup'],str(in_counts['carta_pos_sumup'])+' incassi: circuito specifico non sempre distinto'))
    methods_table=[]
    for key,label in [('contanti','Contanti'),('bonifico','Bonifici'),('carta_pos_sumup','Carta / POS / SumUp'),('addebito','Addebiti'),('altro','Altro'),('non_classificato','Metodo non classificato')]:
        methods_table.append('<tr><td>'+h(label)+'</td><td>'+str(in_counts[key])+'</td><td>'+money(in_channels[key])+
            '</td><td>'+str(out_counts[key])+'</td><td>'+money(out_channels[key])+'</td><td>'+money(in_channels[key]-out_channels[key])+'</td></tr>')
    cash_box=('<section id="bmbl-cassa"><h2>Contanti: incassi e cassa fisica</h2>'
       '<p>Pagamenti registrati in contanti: <strong>'+str(in_counts['contanti'])+' per '+money(in_channels['contanti'])+'</strong>. '
       'Uscite in contanti registrate: <strong>'+str(out_counts['contanti'])+' per '+money(out_channels['contanti'])+'</strong>.</p>'
       '<p>Flusso contabile netto dei contanti nel periodo: <strong>'+money(in_channels['contanti']-out_channels['contanti'])+'</strong>. '
       'Questa differenza NON è il denaro che si trova fisicamente in cassa.</p>'
       '<p><strong>Giacenza fisica: non verificata.</strong> Per confrontarla servono la conta effettiva, '
       'la giacenza iniziale, eventuali versamenti contanti sul conto, prelievi e uscite non ancora annotate. '
       'I trasferimenti tra cassa e banca non sono nuovi ricavi o nuove spese.</p>'
       '<p class="bmbl-dim">Non sono state create operazioni, né spostati importi tra contanti e bonifici.</p></section>')
    def payment_rows():
        rows=[]
        for p in dated_pay[:200]:
            rows.append('<tr><td>'+fmt_date(pay_date(p))+'</td><td>#'+str(int(p['id']))+
                        ' · '+h(str(p.get('causale') or 'Pagamento'))+'</td><td>'+
                        h(str(p.get('metodo_pagamento') or '—'))+'</td><td>'+money(p['importo'])+'</td></tr>')
        for m in entered_man_in[:200]:
            rows.append('<tr><td>'+fmt_date(m['data'])+'</td><td>Entrata manuale #'+str(int(m['id']))+
                        ' · '+h(str(m.get('descrizione') or ''))+'</td><td>'+
                        h(str(m.get('metodo') or '—'))+'</td><td>'+money(m['importo'])+'</td></tr>')
        return ''.join(rows)
    def expense_rows():
        rows=[]
        for x in dated_exp[:200]:
            rows.append('<tr><td>'+fmt_date(x.get('data'))+'</td><td>'+
                       h(str(x.get('descrizione') or 'Uscita'))+'</td><td>'+
                       h(str(x.get('metodo') or '—'))+'</td><td>'+money(x['importo'])+
                       '</td><td><a href="/pagamenti/uscite?modifica='+str(int(x['id']))+'">#'+str(int(x['id']))+'</a></td></tr>')
        for m in entered_man_out[:200]:
            rows.append('<tr><td>'+fmt_date(m.get('data'))+'</td><td>Uscita manuale · '+
                       h(str(m.get('descrizione') or ''))+'</td><td>'+h(str(m.get('metodo') or '—'))+
                       '</td><td>'+money(m['importo'])+'</td><td>Movimento #'+str(int(m['id']))+'</td></tr>')
        return ''.join(rows)

    # Lifetime summary is computed from the SAME existing authenticated payment
    # classifier and original expense/manual registers, independently of period.
    life_in={k:ZERO for k in in_channels}
    life_out={k:ZERO for k in out_channels}
    life_in_count={k:0 for k in life_in}
    life_out_count={k:0 for k in life_out}
    for item in valid_pay+manual_income:
        kind=inflow_method(item)
        life_in[kind]+=val(item.get('importo'))
        life_in_count[kind]+=1
    for item in expenses+distinct_manual_out:
        kind=outflow_method(item)
        life_out[kind]+=val(item.get('importo'))
        life_out_count[kind]+=1
    life_income=sum(life_in.values(),ZERO)
    life_expense=sum(life_out.values(),ZERO)
    if (life_income!=total_pay+total_man or life_expense!=total_exp+total_extra):
        raise RuntimeError('Totali storici incoerenti con le registrazioni originali')
    misc=('addebito','altro','non_classificato')
    def misc_amount(src):return sum((src[key] for key in misc),ZERO)
    def misc_count(src):return sum(src[key] for key in misc)
    def life_card(label, amount, count, item_name):
        return card(label,amount,str(count)+' '+item_name+' registrati')
    lifetime_summary=(
        '<section id="bmbl-total-history" aria-label="Bilancio totale storico">'
        '<h2>Bilancio totale — dall’inizio delle registrazioni</h2>'
        '<p>Riepilogo complessivo sempre visibile, indipendente dal mese selezionato. '
        'Include soltanto registrazioni attive e movimenti manuali classificati, '
        'senza sommare due volte le scritture tecniche.</p>'
        '<h3>Entrate totali per metodo</h3><div class="bmbl-grid">'
        +life_card('Contanti incassati · totale',life_in['contanti'],life_in_count['contanti'],'incassi')
        +life_card('Bonifici incassati · totale',life_in['bonifico'],life_in_count['bonifico'],'incassi')
        +life_card('Carta / POS / SumUp · totale',life_in['carta_pos_sumup'],life_in_count['carta_pos_sumup'],'incassi')
        +life_card('Altri metodi · totale',misc_amount(life_in),misc_count(life_in_count),'incassi')
        +'</div><h3>Uscite totali per metodo</h3><div class="bmbl-grid">'
        +life_card('Bonifici in uscita · totale',life_out['bonifico'],life_out_count['bonifico'],'uscite')
        +life_card('Contanti in uscita · totale',life_out['contanti'],life_out_count['contanti'],'uscite')
        +life_card('Carta / POS / SumUp · uscite',life_out['carta_pos_sumup'],life_out_count['carta_pos_sumup'],'uscite')
        +life_card('Altri metodi · uscite',misc_amount(life_out),misc_count(life_out_count),'uscite')
        +'</div><h3>Totali complessivi</h3><div class="bmbl-grid">'
        +card('Entrate complessive',life_income,'Tutti gli incassi attivi registrati')
        +card('Uscite complessive',life_expense,'Tutte le uscite registrate')
        +card('Risultato complessivo',life_income-life_expense,'Entrate meno uscite: non equivale a un saldo bancario')
        +'</div><p class="bmbl-dim">Gli incassi Carta/POS/SumUp sono una categoria aggregata; '
        'non attribuiamo l’intera cifra al solo circuito SumUp. '
        'Il contante incassato non certifica la giacenza fisica: eventuali versamenti e '
        'trasferimenti tra cassa e banca richiedono verifica separata.</p></section>')
    historic_note=('Entrate storiche registrate: '+money(total_pay+total_man)+
                   ' · Uscite storiche registrate: '+money(total_exp+total_extra)+
                   ' · Risultato storico: '+money(total_pay+total_man-total_exp-total_extra))
    warning_parts=[]
    if unclassified:warning_parts.append(str(len(unclassified))+' movimento/i tecnici non classificati separati dagli incassi e dalle uscite ufficiali, senza conteggio aggiuntivo')
    if manual_duplicates:warning_parts.append(str(len(manual_duplicates))+' movimento/i manuale/i simili a giustificativi: possibili coincidenze da esaminare, mantenuti nel calcolo A237 senza cancellazioni')
    if any(len(d)>1 for d in linked.values()):warning_parts.append('Presenti pagamenti con più movimenti di entrata collegati: controllare la prima nota')
    warning='<p class="bmbl-notice">'+h('; '.join(warning_parts))+'. Nessun movimento è stato modificato.</p>' if warning_parts else ''
    references=''  # Entries are rendered from real records, never hardcoded recipients.

    css=(
      '<style>.bmbl{max-width:1080px;margin:18px auto 100px;padding:12px;color:#ecf5ff;box-sizing:border-box}'
      '.bmbl *{box-sizing:border-box}.bmbl h1,.bmbl h2{color:#fff}.bmbl a{color:#bef0ff}'
      '.bmbl .bmbl-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:20px 0}'
      '.bmbl-card{border:1px solid #537b94;background:#19364e;border-radius:14px;padding:18px;min-width:0}'
      '.bmbl-card span,.bmbl-card small{display:block;color:#cbdfea}.bmbl-card strong{display:block;font-size:clamp(20px,3vw,26px);margin:8px 0;overflow-wrap:anywhere}'
      '.bmbl section{background:#0f283d;border:1px solid #456983;border-radius:14px;margin:16px 0;padding:16px}'
      '.bmbl table{border-collapse:collapse;width:100%}.bmbl td,.bmbl th{text-align:left;vertical-align:top;border-bottom:1px solid #35546c;padding:10px;overflow-wrap:anywhere}'
      '.bmbl .bmbl-scroll{overflow-x:auto}.bmbl .bmbl-scroll table{min-width:640px}'
      '.bmbl-notice{line-height:1.6;border:1px solid #677785;border-radius:12px;padding:12px;background:#1b3346}'
      '.bmbl input,.bmbl select,.bmbl button{padding:10px;border-radius:9px;font:inherit}'
      '.bmbl p{line-height:1.55}.bmbl .bmbl-dim{color:#b7ccda;font-size:.92em}'
      '@media(max-width:640px){.bmbl .bmbl-grid{grid-template-columns:1fr 1fr;gap:8px}.bmbl-card{padding:12px}'
      '.bmbl-card strong{font-size:20px}.bmbl .bmbl-scroll table{min-width:0;display:block}'
      '.bmbl .bmbl-scroll thead{display:none}.bmbl .bmbl-scroll tbody{display:block}'
      '.bmbl .bmbl-scroll tr{display:block;margin:8px 0;padding:9px;border:1px solid #3d647c;border-radius:10px}'
      '.bmbl .bmbl-scroll td{display:block;padding:5px;border:0}.bmbl .bmbl-scroll td:before{color:#b4d1df;font-weight:700}'
      '.bmbl-in td:nth-child(1):before,.bmbl-out td:nth-child(1):before{content:"Data: "}'
      '.bmbl-in td:nth-child(2):before,.bmbl-out td:nth-child(2):before{content:"Operazione: "}'
      '.bmbl-in td:nth-child(3):before,.bmbl-out td:nth-child(3):before{content:"Metodo: "}'
      '.bmbl-in td:nth-child(4):before,.bmbl-out td:nth-child(4):before{content:"Importo: "}'
      '.bmbl-out td:nth-child(5):before{content:"Dettaglio: "}'
      '.bmbl-methods td:nth-child(1):before{content:"Metodo: "}.bmbl-methods td:nth-child(2):before{content:"N. incassi: "}'
      '.bmbl-methods td:nth-child(3):before{content:"Entrate: "}.bmbl-methods td:nth-child(4):before{content:"N. uscite: "}'
      '.bmbl-methods td:nth-child(5):before{content:"Uscite: "}.bmbl-methods td:nth-child(6):before{content:"Flusso netto: "}}'
      '</style>')
    return (
       '<main id="bm-owner-bilanci" class="bmbl">'+css+
       '<a href="/mobile">‹ Home Owner</a><h1>Bilanci</h1>'
       '<p>Incassi, uscite e movimenti del gestionale originale. Consulta i dati senza nuove registrazioni.</p>'
       '<form action="/owner/bilanci" method="get"><label for="bmbl-period">Periodo </label>'
       '<select id="bmbl-period" name="mese"><option value="tutto"'+(' selected' if period=='tutto' else '')+'>Tutto lo storico</option>'
       +''.join('<option value="'+h(k)+'"'+(' selected' if period==k else '')+'>'+h(k)+'</option>'
                 for k in sorted(set([datetime.now(ZoneInfo('Europe/Rome')).strftime('%Y-%m')]+
                                     [ym(pay_date(p)) for p in valid_pay if ym(pay_date(p))]+
                                     [ym(x.get('data')) for x in expenses if ym(x.get('data'))]+
                                     [ym(x['data']) for x in manual_income+manual_out if ym(x['data'])]),reverse=True))+
       '</select> <button type="submit">Mostra</button></form>'
       +'<div class="bmbl-grid">'+header_cards+'</div>'+cash_box+lifetime_summary
       +missing_note+'<p class="bmbl-dim">'+h(canonical_status)+'. '+h(historic_note)+
       '. I flussi bancari e contanti non attestano la giacenza effettiva del conto o della cassa.</p>'
       +warning+references+
       '<section><h2>Entrate e uscite per metodo</h2><div class="bmbl-scroll"><table class="bmbl-methods">'
       '<thead><tr><th>Metodo</th><th>N. incassi</th><th>Entrate</th><th>N. uscite</th><th>Uscite</th><th>Flusso netto</th></tr></thead><tbody>'+
       ''.join(methods_table)+'</tbody></table></div></section>'+
       '<section><h2>Entrate nel periodo ('+str(len(incoming))+')</h2><div class="bmbl-scroll">'
       '<table class="bmbl-in"><thead><tr><th>Data</th><th>Operazione</th><th>Metodo</th><th>Importo</th></tr></thead><tbody>'+
       (payment_rows() or '<tr><td colspan="4">Nessuna entrata nel periodo</td></tr>')+'</tbody></table></div></section>'+
       '<section><h2>Uscite nel periodo ('+str(len(outgoing))+')</h2><div class="bmbl-scroll">'
       '<table class="bmbl-out"><thead><tr><th>Data</th><th>Operazione</th><th>Metodo</th><th>Importo</th><th>Dettaglio</th></tr></thead><tbody>'+
       (expense_rows() or '<tr><td colspan="5">Nessuna uscita nel periodo</td></tr>')+'</tbody></table></div></section>'+
       '<p><a href="/pagamenti">Pagamenti</a> · <a href="/pagamenti/uscite">Uscite e giustificativi</a> · '
       '<a href="/contabilita/verifica">Verifica tecnica dei movimenti</a></p></main>')



def install(app):
    from asd_app.core import admin_required, auth, has_role, db, layout
    # Validate the private ledger in read-only mode. The optional Bilanci view
    # must NEVER prevent the original management app from booting.
    import sqlite3
    verify=None
    try:
        verify=sqlite3.connect('file:/data/tenants/default/asd.db?mode=ro',uri=True,timeout=20)
        verify.row_factory=sqlite3.Row
        verify.execute('PRAGMA query_only=ON')
        preview=owner_bilanci_html(verify,'')
        full=owner_bilanci_html(verify,'tutto')
        if (any(s not in preview for s in ('id="bm-owner-bilanci"','Entrate registrate','Uscite registrate','Risultato del periodo','Contanti incassati')) or
                'Non determinabile' in preview or 'Non determinabile' in full or
                'Tutto lo storico' not in full):
            raise RuntimeError('Bilanci template integrity check')
        cards_month=re.findall(r'<article class="bmbl-card"><span>(.*?)</span><strong>(.*?)</strong>',preview)
        cards_history=re.findall(r'<article class="bmbl-card"><span>(.*?)</span><strong>(.*?)</strong>',full)
        if len(cards_month)!=19 or len(cards_history)!=19:
            raise RuntimeError('Bilanci expected eight period cards and eleven lifetime cards')
        section_pattern=r'<section id="bmbl-total-history".*?</section>'
        current_total=re.search(section_pattern,preview,re.S)
        historical_total=re.search(section_pattern,full,re.S)
        if not current_total or not historical_total or current_total.group(0)!=historical_total.group(0):
            raise RuntimeError('Historical summary missing or changed with period selection')
        audit=_audit_channel_readonly(verify)
        if audit['canonical']['status']!='OK' or audit['mismatches']:
            raise RuntimeError('Bilanci totals do not match canonical accounting truth')
        print('BODYMIND OWNER BILANCI LIFETIME-AND-PERIOD PREFLIGHT PASS (19 CARDS, 6 CHANNELS)',flush=True)
    except Exception as exc:
        print('BODYMIND OWNER BILANCI PREFLIGHT WARNING: '+type(exc).__name__,flush=True)
    finally:
        if verify is not None:
            verify.close()

    @app.get('/owner/bilanci',endpoint='bm_owner_bilanci_readonly')
    @admin_required
    def owner_bilanci_readonly():
        if not auth() or not has_role('admin'):
            from flask import abort
            abort(403)
        conn=None
        invalid=False
        try:
            conn=db()
            conn.execute('PRAGMA query_only=ON')
            page=owner_bilanci_html(conn,request.args.get('mese',''))
        except Exception as exc:
            # Never invent balances and never disrupt other management routes.
            invalid=True
            print('BODYMIND OWNER BILANCI READ WARNING: '+type(exc).__name__,flush=True)
            page=('<main style="max-width:760px;margin:28px auto;padding:18px">'
                  '<h1>Bilanci: controllo dati necessario</h1>'
                  '<p>Non posso confermare i totali in questo momento. '
                  'Le registrazioni originali non sono state cambiate.</p>'
                  '<p><a href="/pagamenti">Apri Pagamenti</a> · '
                  '<a href="/pagamenti/uscite">Apri Uscite</a> · '
                  '<a href="/mobile">Torna alla Home Owner</a></p></main>')
        finally:
            if conn is not None:
                conn.close()
        res=make_response(layout(page),503 if invalid else 200)
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
