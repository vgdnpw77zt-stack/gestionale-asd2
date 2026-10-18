"""A278 - deterministic, read-only explanation of due, suggestion, and open requests.
No CREATE/UPDATE/DELETE, no hidden default tariff, and no receipt mutations.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
from datetime import date
from .bodymind_a237_finance_truth import payment_active

ZERO=Decimal('0.00')
MONTHLY=('quota','quota mensile','quota_mensile','pagamento mensile')
EXEMPT=frozenset({'non_dovuto','non dovuto','esente','sospeso','sospesa'})
OPEN_REQUESTS=frozenset({'pending','queued','requested'})


def money(v):
    try:
        d=Decimal(str(0 if v is None else v))
        if not d.is_finite():raise ValueError('nonfinite')
        return d.quantize(Decimal('0.01'))
    except (ValueError,InvalidOperation,TypeError):
        raise ValueError('Importo non valido')

def table(conn,name):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())

def row(conn,sql,args=()):
    x=conn.execute(sql,args).fetchone()
    return dict(x) if x else None

def validate_period(year,month):
    year=int(year);month=int(month)
    if not (2020<=year<=2100 and 1<=month<=12):raise ValueError('Periodo non valido')
    return year,month

def fee_suggestion(conn, athlete_id, month, year):
    """Display-only prefill from exact saved dues, individual exception or listino.

    Not evidence of a legally owed amount; cannot silently materialize old months.
    """
    year,month=validate_period(year,month)
    if not table(conn,'tesserati'):return {'value':None,'source':'anagrafica_assente'}
    person=row(conn,'SELECT * FROM tesserati WHERE id=?',(int(athlete_id),))
    if not person:return {'value':None,'source':'atleta_inesistente'}
    if table(conn,'bodymind_a276_ingressi'):
        confirmed=row(conn,'SELECT data_inizio FROM bodymind_a276_ingressi WHERE tesserato_id=?',(int(athlete_id),))
        if confirmed and str(confirmed['data_inizio'])[:7]>f'{year:04d}-{month:02d}':
            return {'value':ZERO,'source':'prima_ingresso_confermato'}
    if table(conn,'bodymind_quota_decisioni'):
        dec=row(conn,'SELECT * FROM bodymind_quota_decisioni WHERE tesserato_id=? AND mese=? AND anno=?',
                (int(athlete_id),month,year))
        if dec:
            if str(dec.get('decisione') or '').lower() in EXEMPT:return {'value':ZERO,'source':'decisione_non_dovuto'}
            if str(dec.get('decisione') or '').lower() in ('dovuta','ridotta'):
                return {'value':money(dec['importo_dovuto']),'source':'decisione_motivata'}
            return {'value':None,'source':'decisione_da_verificare'}
    if table(conn,'quote_mensili'):
        q=row(conn,'SELECT * FROM quote_mensili WHERE tesserato_id=? AND mese=? AND anno=? ORDER BY id DESC LIMIT 1',
              (int(athlete_id),month,year))
        if q:
            status=str(q.get('stato') or '').strip().lower()
            if status in EXEMPT:return {'value':ZERO,'source':'mese_non_dovuto'}
            if status not in ('non_configurato','da_definire'):
                val=money(q.get('importo_dovuto'))
                if val>ZERO:return {'value':val,'source':'mensilita_salvata'}
                return {'value':None,'source':'importo_mensile_da_verificare'}
    kind=str(person.get('quota_tipo') or 'standard').lower().strip()
    if kind not in ('standard','sorelle','agonista','personalizzata'):kind='standard'
    if kind=='standard' and int(person.get('agonista') or 0)==1:kind='agonista'
    if kind=='personalizzata':
        custom=person.get('quota_personalizzata')
        if custom is None:return {'value':None,'source':'tariffa_personalizzata_non_configurata'}
        base=money(custom)
    else:
        if not table(conn,'quote_listino'):return {'value':None,'source':'listino_mancante'}
        item=row(conn,'SELECT * FROM quote_listino WHERE codice=? AND COALESCE(attivo,1)=1',(kind,))
        if not item:return {'value':None,'source':'tariffa_inattiva'}
        base=money(item.get('importo'))
    if base<=ZERO:return {'value':None,'source':'quota_base_da_configurare'}
    discount=money(person.get('quota_sconto_fisso'))
    if discount<ZERO or discount>base:return {'value':None,'source':'sconto_da_verificare'}
    return {'value':base-discount,'source':'anteprima_listino_'+kind,
            'base':base,'sconto':discount}

def recommended_for_form(db_func,tid,month,year):
    try:
        conn=db_func();conn.row_factory=__import__('sqlite3').Row
        try:
            conn.execute('PRAGMA query_only=ON')
            result=fee_suggestion(conn,tid,month,year)
            d=result['value']
            return {'amount_text':(f'{d:.2f}' if d is not None else ''),'source':result['source']}
        finally:conn.close()
    except (ValueError,KeyError,TypeError,__import__('sqlite3').DatabaseError):
        return {'amount_text':'','source':'da_verificare'}

def is_monthly(causale):
    t=str(causale or '').lower().strip()
    return ('mensil' in t or t in MONTHLY)

def monthly_explanation(conn,tid,month,year):
    """No obligation is invented. Credit/ambiguous request => no automated demand."""
    year,month=validate_period(year,month)
    suggestion=fee_suggestion(conn,tid,month,year)
    status=suggestion['source']
    due=(suggestion['value'] if status in {'mensilita_salvata','decisione_motivata','decisione_non_dovuto','mese_non_dovuto','prima_ingresso_confermato'} else None)
    qrow=(row(conn,'SELECT * FROM quote_mensili WHERE tesserato_id=? AND mese=? AND anno=? ORDER BY id DESC LIMIT 1',
          (int(tid),month,year)) if table(conn,'quote_mensili') else None)
    decision=(row(conn,'SELECT * FROM bodymind_quota_decisioni WHERE tesserato_id=? AND mese=? AND anno=?',
          (int(tid),month,year)) if table(conn,'bodymind_quota_decisioni') else None)
    if qrow is not None and decision is not None:
        expected=(ZERO if str(decision.get('decisione') or '').lower() in EXEMPT else money(decision.get('importo_dovuto')))
        stored=(ZERO if str(qrow.get('stato') or '').lower() in EXEMPT else money(qrow.get('importo_dovuto')))
        if expected!=stored:
            due=None;status='decisione_e_mensilita_in_conflitto'
    # A tariff row with an unexplained historical override cannot be declared a certain debt.
    if qrow is not None and decision is None and str(qrow.get('stato') or '').lower() not in EXEMPT:
        stored=money(qrow.get('importo_dovuto'))
        if stored>ZERO and not str(qrow.get('note') or '').strip():
            # Compare only where the athlete really inherits a standard listino,
            # without personalized tariff, fixed discount, or agonista/sisters category.
            p=row(conn,'SELECT * FROM tesserati WHERE id=?',(int(tid),))
            if p and str(p.get('quota_tipo') or 'standard').lower()=='standard' and not int(p.get('agonista') or 0) and not money(p.get('quota_sconto_fisso')):
                base=row(conn,'SELECT importo FROM quote_listino WHERE codice=?',('standard',)) if table(conn,'quote_listino') else None
                if base and money(base['importo'])>ZERO and (stored!=money(base['importo'])):
                    due=None;status='mensilita_diversa_dal_listino_senza_motivo'
    payments=[]
    if table(conn,'pagamenti'):
        for x in conn.execute('SELECT * FROM pagamenti WHERE tesserato_id=? AND mese=? AND anno=?',(int(tid),month,year)):
            p=dict(x)
            if is_monthly(p.get('causale')) and payment_active(p):payments.append(p)
    paid=sum((money(x.get('importo')) for x in payments), ZERO)
    request_total=ZERO; request_rows=[]
    if table(conn,'payment_requests'):
        columns={str(c[1]) for c in conn.execute('PRAGMA table_info(payment_requests)')}
        if {'status','amount','tesserato_id','mese','anno','id'} <= columns:
            for x in conn.execute('SELECT * FROM payment_requests WHERE tesserato_id=? AND mese=? AND anno=?',(int(tid),month,year)):
                q=dict(x)
                if str(q.get('status') or '').lower() in OPEN_REQUESTS and not q.get('deleted_at'):
                    request_rows.append(int(q['id']));request_total+=money(q.get('amount'))
    # A request is an administrative workflow, never an independent debt to add.
    if due is None:
        state='da_verificare';balance=None
    elif due==ZERO:
        state='non_dovuto' if paid==ZERO else 'incasso_su_periodo_non_dovuto_da_verificare';balance=ZERO
    elif paid>=due:
        state='pagato';balance=ZERO
    else:
        balance=due-paid
        state='parziale' if paid>ZERO else 'dovuto'
    if state in ('dovuto','parziale'):
        # Check earlier positive overpayments, including periods without configured dues.
        if table(conn,'pagamenti'):
            history=[dict(r) for r in conn.execute('SELECT * FROM pagamenti WHERE tesserato_id=? AND (anno<? OR (anno=? AND mese<?))',(int(tid),year,year,month))]
            prior_paid=sum((money(p['importo']) for p in history if is_monthly(p.get('causale')) and payment_active(p)),ZERO)
            previous_due=ZERO
            if table(conn,'quote_mensili'):
                qlist=[dict(q) for q in conn.execute('SELECT * FROM quote_mensili WHERE tesserato_id=? AND (anno<? OR (anno=? AND mese<?))',(int(tid),year,year,month))]
                previous_due=sum((ZERO if str(q.get('stato') or '').lower() in EXEMPT else money(q.get('importo_dovuto')) for q in qlist),ZERO)
                if prior_paid>previous_due:
                    state='da_verificare_crediti_precedenti'
            elif prior_paid>ZERO:
                state='da_verificare_crediti_precedenti'
    if due is not None and request_total>ZERO and request_total!=balance:
        request_note='richieste_non_coincidenti_con_residuo'
    elif request_total>ZERO:request_note='richieste_da_riconciliare_non_sommare'
    else:request_note='nessuna_richiesta_aperta'
    return {'tesserato_id':int(tid),'anno':year,'mese':month,'dovuto':due,'pagato':paid,
            'residuo':balance,'stato':state,'provenienza':status,'richieste_aperte':request_total,
            'richieste_ids':request_rows,'richieste_nota':request_note,'pagamenti_ids':[int(x['id']) for x in payments],
            'sollecito_automatico_sicuro':False}