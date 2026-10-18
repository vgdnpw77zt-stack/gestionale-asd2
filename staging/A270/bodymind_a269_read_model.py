"""A269 staging: SQLite read-only *candidates* for approved manual reminders.

Only monthly quota rows with explicit due and reconciled, receipt-backed active
payments are eligible; absence or conflicting evidence means review, never send.
The A253 ledger remains accounting authority; this extractor does not change it.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from sqlite3 import Connection
from .bodymind_a269_reminders import MonthlyRecord, money

PAID={'paid','paid_manual','closed_manual','pagato_online_verificato','pagato','incassato','saldato'}
VOID={'annullato','annullata','cancelled','canceled','void','refunded','rimborsato','stornato'}
NONPAID={'unpaid','pending','failed','requested','test','pagato_test','paid_unverified','queued','deleted'}
WAIVED={'esente','sospeso','sospesa','non_dovuto','non dovuto'}
MONTHLY={'quota','quota mensile','quota_mensile','pagamento mensile'}


def _columns(conn: Connection, table: str) -> set[str]:
    return {str(r[1]) for r in conn.execute(f'PRAGMA table_info("{table}")')}


def _exists(conn: Connection, name: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def _month(row: dict) -> bool:
    cause=str(row.get('causale') or '').strip().casefold()
    return cause.startswith('mensil') or cause in MONTHLY


def _payment_state(row: dict) -> str:
    states=[str(row.get(k) or '').strip().lower() for k in ('stato','online_status')]
    values=[x for x in states if x]
    if any(x in VOID for x in values):return 'void'
    if any(x in NONPAID for x in values):return 'not_paid'
    if values and any(x in PAID for x in values):return 'paid'
    return 'ambiguous'


def collect(conn: Connection, *, year: int, month: int,
            contact_approvals: set[int] | None = None) -> list[MonthlyRecord]:
    """Pass an existing connection with PRAGMA query_only=ON; only SELECTs here.

    An upstream authenticated admin panel must supply approved recipient IDs.
    No contact approvals are inferred from simply having a phone number.
    """
    if not conn.execute('PRAGMA query_only').fetchone()[0]:
        raise RuntimeError('STOP: run with PRAGMA query_only=ON, never with writable connection')
    required={'tesserati':{'id','nome'},'quote_mensili':{'tesserato_id','mese','anno','importo_dovuto','stato'},
              'pagamenti':{'id','tesserato_id','mese','anno','causale','importo','stato','online_status'},
              'ricevute':{'id','pagamento_id','annullata','importo'}}
    for table,keys in required.items():
        if not _exists(conn,table) or not keys.issubset(_columns(conn,table)):
            raise RuntimeError(f'STOP: unverified schema {table}: missing {keys-_columns(conn,table)}')
    approvals=contact_approvals or set()
    personcols=_columns(conn,'tesserati')
    candidates=[k for k in ('telefono_genitore','cellulare_genitore','telefono_tutore','telefono','cellulare') if k in personcols]
    if not candidates: raise RuntimeError('STOP: no verified phone source')
    people={int(r['id']):dict(r) for r in conn.execute('SELECT * FROM tesserati')}
    periods=[dict(r) for r in conn.execute('SELECT * FROM quote_mensili WHERE anno=? AND mese=?',(year,month))]
    if not periods:return []
    decisions={}
    if _exists(conn,'bodymind_quota_decisioni'):
        for r in conn.execute('SELECT * FROM bodymind_quota_decisioni WHERE anno=? AND mese=?',(year,month)):
            decisions[int(r['tesserato_id'])]=dict(r)
    allpayments=defaultdict(list)
    receipts=defaultdict(list)
    for r in conn.execute('SELECT * FROM pagamenti WHERE anno=? AND mese=?',(year,month)):
        p=dict(r)
        if _month(p):allpayments[int(p['tesserato_id'])].append(p)
    pids=[int(p['id']) for group in allpayments.values() for p in group]
    if pids:
        for batch in (pids[i:i+400] for i in range(0,len(pids),400)):
            marks=','.join('?'*len(batch))
            for r in conn.execute('SELECT * FROM ricevute WHERE pagamento_id IN ('+marks+')',batch):
                receipts[int(r['pagamento_id'])].append(dict(r))
    out=[]
    for q in periods:
        tid=int(q['tesserato_id'])
        person=people.get(tid)
        if person is None:continue
        state=str(q.get('stato') or '').strip().lower()
        due=money(q.get('importo_dovuto'))
        dec=decisions.get(tid)
        decision_name=str((dec or {}).get('decisione') or '').strip().lower()
        consistent=True
        if decision_name in WAIVED:
            state='non_dovuto'
            due=Decimal('0.00')
        elif state in WAIVED and decision_name and decision_name not in WAIVED:
            consistent=False
        elif dec is not None:
            if 'importo_dovuto' in dec and money(dec['importo_dovuto'])!=due:
                consistent=False
        active=[]
        for p in allpayments.get(tid,[]):
            st=_payment_state(p)
            if st=='ambiguous':consistent=False
            elif st=='paid':
                if money(p['importo'])<=0:consistent=False
                recs=receipts.get(int(p['id']),[])
                if len(recs)!=1 or int(recs[0].get('annullata') or 0)!=0 or money(recs[0]['importo'])!=money(p['importo']):
                    consistent=False
                active.append(p)
        paid=sum((money(p['importo']) for p in active),Decimal('0.00'))
        if state in WAIVED and paid>0:consistent=False
        if due<=0 and state not in WAIVED:consistent=False
        if consistent and state not in WAIVED:
            state='pagato' if paid>=due else ('parziale' if paid>0 else 'da_pagare')
        else:
            state='da_verificare' if not consistent else state
        # Prior-month credits are an accounting input. Never ask for money
        # when a reconciled overpayment might cover the selected month.
        # Missing historic tariff rows make this *unknown*, not zero.
        credit_safe=True
        previous={}
        for old in conn.execute('SELECT * FROM quote_mensili WHERE tesserato_id=? AND (anno<? OR (anno=? AND mese<?))',
                                (tid,year,year,month)):
            r=dict(old);previous[(int(r['anno']),int(r['mese']))]=r
        previous_due=Decimal('0.00')
        for old in previous.values():
            prev_state=str(old.get('stato') or '').lower()
            if prev_state not in WAIVED:
                previous_due+=money(old['importo_dovuto'])
        previous_paid=Decimal('0.00')
        for oldp in conn.execute('SELECT * FROM pagamenti WHERE tesserato_id=? AND (anno<? OR (anno=? AND mese<?))',
                                 (tid,year,year,month)):
            old=dict(oldp)
            if not _month(old):continue
            st=_payment_state(old)
            if st=='ambiguous':credit_safe=False;continue
            if st!='paid':continue
            if (int(old['anno']),int(old['mese'])) not in previous:
                credit_safe=False  # Unconfigured historical period: credit unknown
            previous_paid+=money(old['importo'])
        if previous_paid>previous_due:
            credit_safe=False  # Carry-forward credit not applied; manual review
        telephone=next((str(person.get(col) or '').strip() for col in candidates if str(person.get(col) or '').strip()),'')
        out.append(MonthlyRecord(athlete_id=tid,year=year,month=month,state=state,due=due,paid=paid,
                  reconciled=consistent,credits_verified=credit_safe,waivers_verified=True,
                  contact_approved=tid in approvals,phone=telephone,given_name=str(person.get('nome') or '')))
    return out