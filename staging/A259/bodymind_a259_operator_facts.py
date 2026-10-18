# -*- coding: utf-8 -*-
"""A259: deterministici riepiloghi incassi per metodo, sola lettura.

Un filtro sul metodo non deve essere delegato al planner IA. Ogni importo
corrisponde a una entrata riconciliata A250/A253; gli annullati sono esclusi.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal
from datetime import date

METHODS = {
    'contanti': 'contanti',
    'bonifico': 'bonifico',
    'carta_pos_sumup': 'carta / POS / SumUp',
}
MONTHS = {
    'gennaio': 1, 'febbraio': 2, 'marzo': 3, 'aprile': 4,
    'maggio': 5, 'giugno': 6, 'luglio': 7, 'agosto': 8,
    'settembre': 9, 'ottobre': 10, 'novembre': 11, 'dicembre': 12,
}


def _norm(raw):
    s = unicodedata.normalize('NFKD', str(raw or ''))
    return ' '.join(''.join(c for c in s if not unicodedata.combining(c)).casefold().split())


def _money(v):
    s = f'{Decimal(str(v)):,.2f}'
    return s.replace(',', '#').replace('.', ',').replace('#', '.') + ' €'


def _requested_method(raw):
    n = _norm(raw)
    # Questions about action in cash must still reach the write/confirm workflow.
    if re.search(r'\b(registra|segna|incassa|incassami|salva|modifica|elimina|annulla|restituisci|rimborsa)\b', n):
        return None
    asking = ('?' in str(raw)) or bool(re.search(r'\b(quanti|quante|quanto|totale|numero|somma|dimmi|mostra|vedi|abbiamo|risultano|sono|trovo|trovi)\b', n))
    brief = len(n) <= 30 and bool(re.search(r'^(?:e |ma |solo |in |a |con )*(?:i |gli |le )?(?:contanti|contante|bonifici|bonifico|sumup|carta|pos|cash)\b', n))
    if not asking and not brief:
        return None
    if re.search(r'\b(contant\w*|cash)\b', n):
        return 'contanti'
    if re.search(r'\bbonific\w*\b', n):
        return 'bonifico'
    if re.search(r'\b(sumup|pos|carta|carte)\b', n):
        return 'carta_pos_sumup'
    return None


def _period(raw):
    n = _norm(raw)
    month = next((num for name, num in MONTHS.items() if re.search(r'\b' + name + r'\b', n)), None)
    match = re.search(r'\b(20\d{2})\b', n)
    year = int(match.group(1)) if match else (date.today().year if month else None)
    return month, year


def finance_reply(conn, question):
    """Return a factual chat response, or None when query isn't a method fact.

    Raises on incomplete/corrupt accounting: never invents a reassuring figure.
    """
    method = _requested_method(question)
    if method is None:
        return None

    from .bodymind_a237_finance_truth import payment_active, payment_channel, amount
    from .bodymind_a250_finance_view import movements_operational

    mm, yy = _period(question)
    payments = {int(p['id']): dict(p) for p in conn.execute('SELECT * FROM pagamenti')}
    rows, uncategorized = movements_operational(conn)
    if uncategorized:
        raise ValueError('movimenti manuali senza classificazione')
    active_ids = {pid for pid,p in payments.items() if payment_active(p)}
    live_ids = set()
    count = 0
    total = Decimal('0.00')
    memberships = monthly = other = manual = 0
    for row in rows:
        if str(row.get('tipo') or '').casefold() not in ('entrata','incasso','income'):
            continue
        pid = row.get('pagamento_id')
        if pid is not None:
            pid = int(pid)
            if pid not in active_ids:
                raise ValueError('movimento non riconciliato con pagamento attivo')
            if pid in live_ids:
                raise ValueError('pagamento ripetuto nel registro')
            live_ids.add(pid)
            p = payments[pid]
            chan = payment_channel(p.get('metodo_pagamento'))
            value = amount(p.get('importo'))
            if amount(row.get('importo')) != value:
                raise ValueError('importo del registro diverso dal pagamento')
            if mm is not None and int(p.get('mese') or 0) != mm:
                continue
            if yy is not None and int(p.get('anno') or 0) != yy:
                continue
            cause = str(p.get('causale') or '').casefold()
        else:
            # Solo le scritture manuali A253 classificate come contabilità effettiva.
            chan = payment_channel(row.get('_a253_metodo'))
            value = amount(row.get('importo'))
            day = str(row.get('data') or '')
            if mm is not None and not day.startswith(f'{yy:04d}-{mm:02d}'):
                continue
            if mm is None and yy is not None and not day.startswith(f'{yy:04d}'):
                continue
            cause = 'manuale'
        if chan != method:
            continue
        count += 1
        total += value
        if cause == 'manuale':
            manual += 1
        elif 'iscrizion' in cause or 'tesserament' in cause:
            memberships += 1
        elif 'mensil' in cause or cause == 'quota':
            monthly += 1
        else:
            other += 1

    if live_ids != active_ids:
        raise ValueError('non tutti gli incassi attivi risultano riconciliati')
    label = METHODS[method]
    period = (' per le quote di ' + next(k for k,v in MONTHS.items() if v == mm).title() + f' {yy}') if mm else (f' nell’anno {yy}' if yy else ' su tutti i periodi registrati')
    parts = [f'{count} movimento effettivo' if count == 1 else f'{count} movimenti effettivi', f'totale {_money(total)}']
    breakdown = []
    for num, key in ((memberships,'iscrizioni'),(monthly,'mensili'),(manual,'registrazioni manuali'),(other,'altre causali')):
        if num: breakdown.append(f'{num} ' + ('iscrizione' if key == 'iscrizioni' else 'mensile' if key == 'mensili' else 'registrazione manuale' if key == 'registrazioni manuali' else 'altra causale') if num == 1 else f'{num} {key}')
    text = f'Incassi con metodo {label}{period}: ' + ', '.join(parts) + '.'
    if breakdown:
        text += ' Dettaglio: ' + ', '.join(breakdown) + '.'
    text += ' Esclusi annullati, non pagati e storni.'
    return {
        'text': text, 'mode': 'finance_verified', 'cloud_ai': False,
        'method': method, 'count': count, 'amount': str(total),
        'links': [{'label':'Registro contanti','href':'/quote-incassi/cassa'}] if method == 'contanti' else [{'label':'Pagamenti','href':'/pagamenti'}],
    }