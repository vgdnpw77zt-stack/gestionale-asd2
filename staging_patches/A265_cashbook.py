"""BodyMind A265: auditable, read-only cashbook for the administrative ledger.

No SQL write operations; no inference of physical cash from an accounting net flow.
Existing canonical A237 is authoritative for totals; A253 for manual movements.
"""
from __future__ import annotations
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from html import escape
import re

CHANNELS=(('contanti','Contanti'),('bonifico','Bonifici'),('carta_pos_sumup','Carta / POS / SumUp'),('addebito','Addebiti'),('altro','Altri'),('non_classificato','Da classificare'))
TYPES=('iscrizione','mensile','altro','manuale')
ZERO=Decimal('0.00')

def val(number):
    try:
        d=Decimal(str(number if number is not None else 0))
        if not d.is_finite():raise ValueError('Valore non finito')
        return d.quantize(Decimal('0.01'))
    except (InvalidOperation,ValueError,TypeError) as exc:
        raise ValueError('STOP: importo contabile non valido') from exc

def euro(number):
    s=f'{val(number):,.2f}'
    return s.replace(',','\x1f').replace('.',',').replace('\x1f','.')+' €'

def kind(causale):
    x=re.sub(r'\s+',' ',str(causale or '').casefold().replace('_',' '))
    if 'iscrizion' in x or 'tesserament' in x:return 'iscrizione'
    if 'mensil' in x or 'mensual' in x or 'quota' in x:return 'mensile'
    return 'altro'

def table_exists(conn,table):
    return conn.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?',('table',table)).fetchone() is not None

def cols(conn,table):
    return {str(r[1]) for r in conn.execute('PRAGMA table_info("'+table+'")')}

def discounts(conn):
    """Count distinct documented period discounts, without double counting overlapping sources.

    Current decision/fee records are not a historic invoice archive; be explicit.
    """
    periods={};exemptions=set()
    if table_exists(conn,'quote_mensili'):
        keys={'tesserato_id','mese','anno','importo_base','importo_dovuto','sconto'}
        if keys.issubset(cols(conn,'quote_mensili')):
            for record in conn.execute('SELECT * FROM quote_mensili'):
                r=dict(record)
                if any(r.get(k) is None for k in ('tesserato_id','mese','anno')):continue
                key=tuple(int(r[k]) for k in ('tesserato_id','mese','anno'))
                saved=val(r.get('sconto')); base=val(r.get('importo_base')); due=val(r.get('importo_dovuto'))
                cut=max(ZERO,saved,base-due)
                if cut>ZERO and due>ZERO:
                    periods[key]=max(periods.get(key,ZERO),cut)
                elif base>ZERO and due==ZERO:exemptions.add(key)
    if table_exists(conn,'bodymind_quota_decisioni'):
        keys={'tesserato_id','mese','anno','decisione','importo_base','importo_dovuto'}
        if keys.issubset(cols(conn,'bodymind_quota_decisioni')):
            for record in conn.execute('SELECT * FROM bodymind_quota_decisioni'):
                r=dict(record)
                if any(r.get(k) is None for k in ('tesserato_id','mese','anno')):continue
                key=tuple(int(r[k]) for k in ('tesserato_id','mese','anno'))
                decision=str(r.get('decisione') or '').casefold().strip()
                base=val(r.get('importo_base'));due=val(r.get('importo_dovuto'))
                if decision in ('ridotta','scontata') and base>due>ZERO:
                    periods[key]=max(periods.get(key,ZERO),base-due)
                elif decision in ('esente','non_dovuta','non dovuta','esonerata') and due==ZERO:
                    exemptions.add(key)
    return {'periodi_scontati':len(periods),'risparmio_indicativo':sum(periods.values(),ZERO),
            'periodi_esenti_non_dovuti':len(exemptions),'fonte':'Decisioni e quote presenti, non storico dei prezzi originari'}

def build(conn, truth):
    from .bodymind_a237_finance_truth import payment_active, payment_channel
    from .bodymind_a253_manual import methods
    channels={m:{'entrate':ZERO,'uscite':ZERO,'incassi':0,'quote_distinte':set(),
                 'iscrizioni':0,'mensili':0,'altri':0,'manuali':0,'n_uscite':0} for m,_ in CHANNELS}
    payments=[dict(x) for x in conn.execute('SELECT * FROM pagamenti')]
    for p in payments:
        if not payment_active(p):continue
        method=payment_channel(p.get('metodo_pagamento'))
        ch=channels[method]
        amount=val(p.get('importo'))
        ch['entrate']+=amount;ch['incassi']+=1
        category=kind(p.get('causale'))
        ch[{'iscrizione':'iscrizioni','mensile':'mensili','altro':'altri'}[category]]+=1
        if category=='mensile' and all(p.get(x) is not None for x in ('tesserato_id','mese','anno')):
            ch['quote_distinte'].add((int(p['tesserato_id']),int(p['mese']),int(p['anno'])))
    mapping=methods(conn)
    for row in conn.execute('SELECT * FROM movimenti'):
        d=dict(row); mid=int(d['id'])
        if mid not in mapping:continue
        if d.get('pagamento_id') is not None or int(d.get('auto_generato') or 0):
            raise ValueError('STOP: metodo manuale su movimento automatico')
        method=payment_channel(mapping[mid]); amount=val(d['importo'])
        typ=str(d.get('tipo') or '')
        if typ=='entrata':
            channels[method]['entrate']+=amount
            channels[method]['incassi']+=1;channels[method]['manuali']+=1
        elif typ=='uscita':channels[method]['uscite']+=amount;channels[method]['n_uscite']+=1
        else:raise ValueError('STOP: movimento manuale senza tipo valido')
    bank_expenses=[]
    for row in conn.execute('SELECT * FROM bodymind_uscite'):
        d=dict(row);amount=val(d['importo']);
        if amount<=ZERO:continue
        method=payment_channel(d.get('metodo'))
        channels[method]['uscite']+=amount;channels[method]['n_uscite']+=1
        if method=='bonifico':
            bank_expenses.append({'id':int(d['id']),'source':'uscite','date':str(d.get('data') or ''),
               'description':str(d.get('descrizione') or ''),'amount':amount})
    for row in conn.execute('SELECT * FROM movimenti WHERE pagamento_id IS NULL'):
        d=dict(row);mid=int(d['id'])
        if mid in mapping and str(d.get('tipo') or '')=='uscita' and payment_channel(mapping[mid])=='bonifico':
            bank_expenses.append({'id':mid,'source':'manuale','date':str(d.get('data') or ''),
               'description':str(d.get('descrizione') or ''),'amount':val(d['importo'])})
    bank_expenses.sort(key=lambda x:(x['date'],x['id']),reverse=True)
    for ch in channels.values():ch['quote_distinte']=len(ch['quote_distinte'])
    seen_in=sum((x['entrate'] for x in channels.values()),ZERO)
    seen_out=sum((x['uscite'] for x in channels.values()),ZERO)
    if (seen_in,seen_out)!=(val(truth['entrate']),val(truth['uscite'])):
        raise ValueError('STOP: ripartizione A265 diversa dai totali A237')
    for method,ch in channels.items():
        if ch['entrate']!=val(truth['entrate_per_metodo'][method]) or ch['uscite']!=val(truth['uscite_per_metodo'][method]):
            raise ValueError('STOP: canale '+method+' non riconciliato')
        if ch['incassi']!=int(truth['movimenti_per_metodo'][method]):
            raise ValueError('STOP: numero incassi '+method+' non riconciliato')
    return {'channels':channels, 'discounts':discounts(conn),'bank_expenses':bank_expenses,
            'cash_flow_net':channels['contanti']['entrate']-channels['contanti']['uscite'],
            'total_in':seen_in,'total_out':seen_out}

def render(data):
    def h(v):return escape(str(v),quote=True)
    channels=data['channels']
    core=[('contanti','Incassi contanti'),('bonifico','Incassi bonifico'),('carta_pos_sumup','Carta / POS / SumUp')]
    cards=''.join('<div class="a265-kpi"><small>'+h(label)+'</small><strong>'+h(euro(channels[k]['entrate']))+'</strong><span>'+str(channels[k]['incassi'])+' incassi · '+str(channels[k]['quote_distinte'])+' mensilità distinte</span></div>' for k,label in core)
    discount=data['discounts']
    rows=''.join('<tr><th scope="row">'+h(label)+'</th><td>'+str(channels[k]['incassi'])+'</td><td>'+str(channels[k]['mensili'])+'</td><td>'+str(channels[k]['quote_distinte'])+'</td><td>'+str(channels[k]['iscrizioni'])+'</td><td>'+h(euro(channels[k]['entrate']))+'</td><td>'+str(channels[k]['n_uscite'])+'</td><td>'+h(euro(channels[k]['uscite']))+'</td></tr>' for k,label in CHANNELS)
    banks=''.join('<li><span>'+h(x['date'])+' · '+h(x['description'])+'</span><strong>'+h(euro(x['amount']))+'</strong><a href="'+ ('/pagamenti/uscite?modifica='+str(x['id']) if x['source']=='uscite' else '/contabilita?edit='+str(x['id']))+'">Apri</a></li>' for x in data['bank_expenses'][:30])
    unknown=channels['non_classificato']['entrate'] or channels['non_classificato']['uscite']
    return '''<section class="a265-finance" aria-label="Quadro di cassa verificato">
<style>
.a265-finance{margin:14px 0 18px;border:1px solid #35465c;background:#142336;color:#ecf3fd;padding:16px;border-radius:16px;max-width:100%;box-sizing:border-box}
.a265-finance *{box-sizing:border-box}.a265-finance h3{font-size:19px;margin:0 0 5px}.a265-finance p{font-size:12px;color:#b9cbdd;line-height:1.55;margin:7px 0}
.a265-finance .a265-kpis{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;margin:14px 0}
.a265-finance .a265-kpi{padding:12px;border:1px solid #3d5873;background:#1b3045;border-radius:12px;min-width:0}
.a265-finance .a265-kpi small,.a265-finance .a265-kpi span{display:block;color:#c5d6e7;font-size:12px}
.a265-finance .a265-kpi strong{display:block;margin:5px 0;font-size:clamp(17px,2vw,23px);font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.a265-finance .a265-cash{margin:8px 0;padding:12px;border:1px solid #516377;border-radius:12px;background:#1c2a3c}
.a265-finance .a265-cash strong{font-size:20px}.a265-finance summary{cursor:pointer;padding:12px 0;color:#d2e9fb;font-weight:700}
.a265-finance .a265-table{max-width:100%;overflow:auto}.a265-finance table{border-collapse:collapse;min-width:790px;width:100%}.a265-finance th,.a265-finance td{text-align:left;padding:9px;border-bottom:1px solid #33465a;font-size:12px}
.a265-finance .a265-bank-list{list-style:none;margin:0;padding:0}.a265-finance .a265-bank-list li{display:flex;align-items:center;flex-wrap:wrap;gap:10px;justify-content:space-between;padding:10px;border-bottom:1px solid #344960}.a265-finance .a265-bank-list a{color:#aee2ff}
@media(max-width:760px){.a265-finance{padding:12px;margin:9px 0}.a265-finance .a265-kpis{grid-template-columns:1fr;gap:7px}.a265-finance .a265-kpi{padding:9px 11px}.a265-finance .a265-kpi strong{font-size:19px}}
</style>
<h3>Controllo incassi e cassa</h3><p>Importi dai movimenti effettivi: annullati e non pagati esclusi. Numero incassi diverso dalle mensilità distinte quando sono presenti acconti o più versamenti.</p>
<div class="a265-kpis">'''+cards+'''</div>
<div class="a265-cash"><small>Saldo movimenti in contanti (entrate meno uscite contanti)</small><div><strong>'''+h(euro(data['cash_flow_net']))+'''</strong></div>
<p>Non è la giacenza fisica custodita dalla presidente: per quella servono saldo iniziale, versamenti/prelievi e riconciliazione dei trasferimenti interni.</p></div>
<div class="a265-cash"><strong>'''+str(discount['periodi_scontati'])+''' mensilità con riduzioni documentate · '''+str(discount['periodi_esenti_non_dovuti'])+''' esenti/non dovute</strong>
<p>Risparmio indicativo dalle quote/decisioni attuali: '''+h(euro(discount['risparmio_indicativo']))+'''. Non sommare gli sconti agli incassi; il valore non è una certificazione delle tariffe storiche.</p></div>
<details><summary>Numero quote e incassi per metodo</summary><div class="a265-table"><table><thead><tr><th>Metodo</th><th>Incassi</th><th>Versamenti mensili</th><th>Mensilità distinte</th><th>Iscrizioni</th><th>Entrate</th><th>Uscite</th><th>Importo uscite</th></tr></thead><tbody>'''+rows+'''</tbody></table></div></details>
<details open><summary>Uscite tramite bonifico ('''+str(len(data['bank_expenses']))+''')</summary><ul class="a265-bank-list">'''+(banks or '<li>Nessuna uscita bonifico registrata.</li>')+'''</ul><p>Elenco delle ultime 30 uscite tramite bonifico. Apri la registrazione per vederne ogni dettaglio e giustificativo.</p></details>
'''+('<p role="alert">Attenzione: esistono movimenti senza metodo riconosciuto; non sono classificati automaticamente come contanti.</p>' if unknown else '')+'''</section>'''