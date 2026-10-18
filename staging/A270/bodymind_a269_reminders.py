"""BodyMind A269 (staging): deterministic reminder decisions, NO automatic sending.

Inputs MUST come from reconciled, read-only account/athlete states. A sent-message
record means an actual provider-acknowledged send, never a draft/preview/queue.
No DB schema changes, HTTP calls, SMTP calls, or external provider calls.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Iterable
from urllib.parse import quote, urlsplit
import re

FINAL_DELIVERY = frozenset({'sent','delivered','inviato','consegnato'})
STOP_STATES = frozenset({'pagato','non_dovuto','esente','sospeso','sospesa','non_configurato'})
ALLOW_STATES = frozenset({'da_pagare','parziale'})


def money(value) -> Decimal:
    try:
        n=Decimal(str(value))
        if not n.is_finite() or n<0:
            raise ValueError('Importo non valido')
        return n.quantize(Decimal('0.01'))
    except (InvalidOperation,TypeError) as exc:
        raise ValueError('Importo non numerico') from exc


@dataclass(frozen=True)
class Policy:
    # BodyMind ASD deadline confirmed by owner: monthly payments by the 10th.
    # A policy can still explicitly set None to stop reminders.
    due_day: int | None = 10
    before_days: int = 7
    repeat_days: int = 3
    max_attempts: int = 3
    enabled: bool = False
    whatsapp_enabled: bool = False
    sumup_url: str = ''

    def __post_init__(self):
        if self.due_day is not None and not 1<=self.due_day<=28:
            raise ValueError('Scadenza mensile: giorno da 1 a 28')
        if not 0<=self.before_days<=31 or not 1<=self.repeat_days<=31:
            raise ValueError('Intervalli promemoria non validi')
        if not 1<=self.max_attempts<=5:
            raise ValueError('Numero massimo di invii non valido')
        if self.sumup_url:
            parsed=urlsplit(self.sumup_url)
            if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password:
                raise ValueError('Il link SumUp deve essere HTTPS e senza credenziali')
            if parsed.hostname in ('localhost','127.0.0.1'):
                raise ValueError('URL di pagamento non pubblico')


@dataclass(frozen=True)
class MonthlyRecord:
    athlete_id: int
    year: int
    month: int
    state: str
    due: Decimal
    paid: Decimal
    # The source must have reconciled quote, formal decisions, payments and receipts.
    reconciled: bool
    credits_verified: bool
    waivers_verified: bool
    contact_approved: bool
    phone: str = ''
    given_name: str = ''

    @property
    def outstanding(self) -> Decimal:
        return max(Decimal('0.00'),money(self.due)-money(self.paid))

    def __post_init__(self):
        if not 1<=self.month<=12 or self.year<2000 or self.athlete_id<=0:
            raise ValueError('Periodo o tesserato non valido')
        money(self.due);money(self.paid)


@dataclass(frozen=True)
class Delivery:
    # Only provider-confirmed entries count. A queued, draft or preview does not.
    sent_at: date
    status: str
    year: int
    month: int
    athlete_id: int
    purpose: str = 'monthly_due'


@dataclass(frozen=True)
class Decision:
    action: str  # hold | none | manual_preview
    reason: str
    key: str
    outstanding: Decimal
    attempt: int = 0
    due_date: date | None = None
    whatsapp_url: str = ''
    message: str = ''


def normalized_phone(raw: str) -> str:
    p=''.join(re.findall(r'\d',str(raw or '')))
    if p.startswith('00'):
        p=p[2:]
    if len(p)==10 and p.startswith('3'):
        p='39'+p
    return p if p.startswith('39') and 11<=len(p)<=13 else ''


def build_message(record: MonthlyRecord, outstanding: Decimal, payment_url: str) -> str:
    # No urgency, debt threat, or sensitive diagnosis details in a WhatsApp preview.
    name=re.sub(r'[^\w\-\s]', '', record.given_name or '').strip()[:60]
    intro=f'Ciao {name},' if name else 'Buongiorno,'
    month=f'{record.month:02d}/{record.year}'
    text=f'{intro} BodyMind Aerial Studio ASD ti ricorda di verificare la quota {month} di {outstanding:.2f} €. Se hai già pagato, ignora questo promemoria e segnalacelo.'
    return text + (f' Link per il pagamento: {payment_url}' if payment_url else ' Per il pagamento contatta la segreteria.')


def decide(record: MonthlyRecord, policy: Policy, deliveries: Iterable[Delivery], *, today: date) -> Decision:
    key=f'mensile:{record.athlete_id}:{record.year:04d}-{record.month:02d}'
    outstanding=record.outstanding
    def stop(action: str, reason: str) -> Decision:
        return Decision(action,reason,key,outstanding)
    state=str(record.state or '').strip().casefold()
    if state in STOP_STATES:
        return stop('none','Quota pagata, esente, sospesa o non configurata')
    if state not in ALLOW_STATES or outstanding<=0:
        return stop('hold','Stato contabile ambiguo o saldo già coperto: verifica necessaria')
    if not all((record.reconciled,record.credits_verified,record.waivers_verified)):
        return stop('hold','Riconciliazione, credito precedente o esenzioni non verificati')
    if not policy.enabled or policy.due_day is None:
        return stop('hold','Regola di scadenza non abilitata/configurata')
    due_date=date(record.year,record.month,policy.due_day)
    if today<due_date-timedelta(days=policy.before_days):
        return stop('none','Non è ancora il momento del promemoria')
    prior=sorted((d for d in deliveries if d.athlete_id==record.athlete_id and d.year==record.year
                  and d.month==record.month and d.purpose=='monthly_due'
                  and d.status.strip().casefold() in FINAL_DELIVERY),key=lambda d:d.sent_at)
    if len(prior)>=policy.max_attempts:
        return stop('none','Numero massimo di promemoria raggiunto')
    if prior and today<(prior[-1].sent_at+timedelta(days=policy.repeat_days)):
        return stop('none','Promemoria già inviato: attendere intervallo di ripetizione')
    if prior and today==prior[-1].sent_at:
        return stop('none','Nessun doppio invio nella stessa giornata')
    if not record.contact_approved:
        return stop('hold','Recapito/consenso destinatario da verificare')
    phone=normalized_phone(record.phone)
    if not phone:
        return stop('hold','Numero destinatario non valido')
    msg=build_message(record,outstanding,policy.sumup_url)
    url='https://wa.me/'+phone+'?text='+quote(msg,safe='')
    # WhatsApp Business app only: never assert an API message was sent.
    # Even with API configured, actual sending requires approved templates and a separate adapter.
    return Decision('manual_preview','Bozza WhatsApp pronta, invio non eseguito',key,outstanding,
                    attempt=len(prior)+1,due_date=due_date,whatsapp_url=url,message=msg)