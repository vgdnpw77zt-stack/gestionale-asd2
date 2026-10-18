# -*- coding: utf-8 -*-
"""A262: audited read-only origins of ACTIVE financial movements, never receipt sums.

Purely presentation-oriented. The accounting total always comes from A237/A253.
Stored/current discounts are evidence, not a reconstruction of historical fee lists.
"""
from __future__ import annotations
from collections import defaultdict
from decimal import Decimal
from html import escape
import re
import unicodedata

CATEGORIES=(('iscrizioni','Iscrizioni'),('mensili','Quote mensili'),
            ('altri_pagamenti','Altri pagamenti'),('movimenti_manuali','Entrate manuali'))
METHODS=(('contanti','Contanti'),('bonifico','Bonifico'),
         ('carta_pos_sumup','Carta / SumUp / POS'),('addebito','Addebito'),
         ('altro','Altro dichiarato'),('non_classificato','Metodo non indicato'))
DISCOUNTS=(('iscr_sorelle','Iscrizioni: sorelle / fratelli'),
           ('iscr_meta_anno','Iscrizioni: metà anno'),
           ('iscr_altro','Iscrizioni: altre agevolazioni'),
           ('mens_sorelle','Mensili: sorelle / fratelli'),
           ('mens_meta_mese','Mensili: metà mese'),
           ('mens_altro','Mensili: altre agevolazioni'))
ZERO=Decimal('0.00')


def _amount(v):
    try:
        d=Decimal(str(v if v is not None else '0'))
        if not d.is_finite():raise ValueError('Importo non finito')
        return d.quantize(Decimal('0.01'))
    except Exception as err:
        raise ValueError('STOP: valore contabile non numerico') from err


def _simple(text):
    x=unicodedata.normalize('NFKD',str(text or '')).casefold()
    return ''.join(c for c in x if not unicodedata.combining(c))


def _category(causale):
    x=_simple(causale).replace('_',' ').strip()
    if 'iscrizion' in x or 'tesserament' in x:return 'iscrizioni'
    if 'mensil' in x or 'mensualit' in x or x in ('quota mensile','retta mensile'):
        return 'mensili'
    return 'altri_pagamenti'


def _discount_reason(text,category):
    x=_simple(text)
    if re.search(r'\b(?:nessun[oa]?|senza|no)\s+(?:sconto|riduzione|agevolazione)\b',x) or re.search(r'\bsconto\s*(?:=|:)\s*0(?:[,\.]00)?\b',x):
        return None
    if re.search(r'\b(sorell[aei]?|fratell[oiie]?|siblings?)\b',x):
        return 'iscr_sorelle' if category=='iscrizioni' else 'mens_sorelle'
    if category=='iscrizioni' and re.search(r'\b(meta|mezzo|mezza|1/2)\s*(?:di\s*)?(?:anno|stagione)\b',x):
        return 'iscr_meta_anno'
    if category=='mensili' and re.search(r'\b(meta|mezzo|mezza|1/2)\s*(?:di\s*)?mes[ei]\b',x):
        return 'mens_meta_mese'
    if re.search(r'\b(scont[oi]|riduzion[ei]|agevolazion[ei]|tariffa ridotta|quota ridotta|esenzion[ei])\b',x):
        return 'iscr_altro' if category=='iscrizioni' else 'mens_altro'
    return None


def _has_table(conn,name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() is not None


def _column_names(conn,table):
    return {str(row[1]) for row in conn.execute('PRAGMA table_info("'+table+'")')}


def _monthly_evidence(conn,paid_periods):
    """Only explicit period records, never the athlete's current profile alone."""
    if not paid_periods:return {}
    records={}
    if _has_table(conn,'quote_mensili'):
        required={'tesserato_id','mese','anno','importo_base','importo_dovuto','sconto','tariffa_codice','note'}
        if not required.issubset(_column_names(conn,'quote_mensili')):
            raise ValueError('STOP: schema quote_mensili incompleto')
        for raw in conn.execute('SELECT * FROM quote_mensili'):
            row=dict(raw);key=(int(row['tesserato_id']),int(row['mese']),int(row['anno']))
            if key in paid_periods:
                # A later update cannot become a proof of the historical tariff: label the evidence as current.
                prev=records.get(key)
                if prev is None or int(row.get('id') or 0)>int(prev.get('id') or 0):records[key]=row
    decisions={}
    if _has_table(conn,'bodymind_quota_decisioni'):
        required={'tesserato_id','mese','anno','decisione','importo_base','importo_dovuto','motivo'}
        if not required.issubset(_column_names(conn,'bodymind_quota_decisioni')):
            raise ValueError('STOP: schema decisioni quote incompleto')
        for raw in conn.execute('SELECT * FROM bodymind_quota_decisioni'):
            row=dict(raw);key=(int(row['tesserato_id']),int(row['mese']),int(row['anno']))
            if key in paid_periods:decisions[key]=row
    result={}
    for key in paid_periods:
        q=records.get(key);d=decisions.get(key)
        confirmed=False
        parts=[]
        if q:
            base=_amount(q['importo_base']);due=_amount(q['importo_dovuto']);discount=_amount(q['sconto'])
            if discount>0 or base>due>ZERO:
                confirmed=True
                parts.extend([str(q.get('tariffa_codice') or ''),str(q.get('note') or '')])
                if str(q.get('tariffa_codice') or '').strip().lower()=='sorelle':parts.append('sorelle')
        if d and str(d.get('decisione') or '').lower()=='ridotta':
            if _amount(d['importo_base'])>_amount(d['importo_dovuto'])>ZERO:
                confirmed=True;parts.append(str(d.get('motivo') or ''))
        if confirmed:result[key]=' '.join(parts)
    return result


def build(conn, payments, active_ids, manual_income, expected_total, expected_channels, expected_count):
    """Use the exact active A237 payment IDs, never a fresh independent SUM(receipts)."""
    from .bodymind_a237_finance_truth import payment_channel
    active_ids=set(active_ids)
    cat={k:{'count':0,'total':ZERO} for k,_ in CATEGORIES}
    matrix={k:{m:{'count':0,'total':ZERO} for m,_ in METHODS} for k,_ in CATEGORIES}
    discount_counts={k:0 for k,_ in DISCOUNTS}
    distinct_payers={k:set() for k,_ in CATEGORIES}
    docs=[]
    monthly_periods=defaultdict(list)
    for pid in active_ids:
        p=payments[pid]
        if 'causale' not in p or 'metodo_pagamento' not in p:
            raise ValueError('STOP: schema dettaglio entrate incompleto')
        kind=_category(p['causale'])
        if kind=='mensili':
            required=('tesserato_id','mese','anno')
            if any(p.get(n) is None for n in required):
                raise ValueError('STOP: identificazione quota mensile incompleta')
            key=(int(p['tesserato_id']),int(p['mese']),int(p['anno']))
            monthly_periods[key].append(pid)
        docs.append((pid,p,kind))
    evidence=_monthly_evidence(conn,set(monthly_periods))
    discounted_periods=set()
    discounted_enrollments=set()
    for pid,p,kind in docs:
        method=payment_channel(p['metodo_pagamento']);amount=_amount(p['importo'])
        cat[kind]['count']+=1;cat[kind]['total']+=amount
        if p.get('tesserato_id') is not None:
            distinct_payers[kind].add(int(p['tesserato_id']))
        matrix[kind][method]['count']+=1;matrix[kind][method]['total']+=amount
        notes=str(p.get('note_pagamento') or '')
        reason=_discount_reason(notes,kind) if kind in ('mensili','iscrizioni') else None
        if kind=='mensili':
            key=(int(p['tesserato_id']),int(p['mese']),int(p['anno']))
            if key in evidence:
                reason=_discount_reason(notes+' '+evidence[key],kind) or 'mens_altro'
                # 1 discounted month = 1 monthly-period decision, not 2 partial receipts.
                if key in discounted_periods:reason=None
                discounted_periods.add(key)
            elif reason:
                if key in discounted_periods:reason=None
                discounted_periods.add(key)
        if kind=='iscrizioni' and reason:
            # Two instalments of the same enrolment are not two discounts.
            key=(int(p['tesserato_id']),int(p.get('anno') or 0)) if p.get('tesserato_id') is not None else ('payment',pid)
            if key in discounted_enrollments:reason=None
            discounted_enrollments.add(key)
        if reason:discount_counts[reason]+=1
    for row in manual_income.values():
        method=payment_channel(row.get('metodo_pagamento'))
        amount=_amount(row['importo'])
        cat['movimenti_manuali']['count']+=1;cat['movimenti_manuali']['total']+=amount
        matrix['movimenti_manuali'][method]['count']+=1;matrix['movimenti_manuali'][method]['total']+=amount
    for k in distinct_payers:
        cat[k]['payers']=len(distinct_payers[k]) if k!='movimenti_manuali' else None
    cat['mensili']['periods']=len(monthly_periods)
    total=sum((item['total'] for item in cat.values()),ZERO)
    n=sum(item['count'] for item in cat.values())
    if total!=_amount(expected_total) or n!=int(expected_count):
        raise ValueError('STOP: origini entrate non riconciliate con A237')
    for method in expected_channels:
        observed=sum((matrix[k][method]['total'] for k in cat),ZERO)
        if observed!=_amount(expected_channels[method]):
            raise ValueError('STOP: origine per metodo non riconciliata: '+method)
    return {'categories':cat,'matrix':matrix,'discounts':discount_counts,
            'discounted_month_periods':len(discounted_periods),
            'note':'Sconti identificati dalle note dei pagamenti o dalle decisioni mensili presenti. Le tariffe mensili possono essere state aggiornate dopo l’incasso: i conteggi sono indicatori documentali, non attestazione del prezzo storico. Agevolazioni non documentate potrebbero non risultare.'}


def euros(val):
    s=f'{_amount(val):,.2f}'.replace(',','\x1f').replace('.',',').replace('\x1f','.')
    return s+' €'


def render(origin):
    e=escape
    cards=''.join('<div class="a262-origin-card"><span>'+e(label)+'</span><strong>'+e(euros(origin['categories'][k]['total']))+'</strong><small>'+str(origin['categories'][k]['count'])+' incassi' + ((' · '+str(origin['categories'][k]['payers'])+' tesserate/i') if origin['categories'][k]['payers'] is not None else '')+'</small></div>' for k,label in CATEGORIES)
    rows=[]
    for k,label in METHODS:
        cols=[]
        for cat,_ in CATEGORIES:
            cell=origin['matrix'][cat][k]
            cols.append('<td>'+e(euros(cell['total']))+' <small>('+str(cell['count'])+')</small></td>')
        rows.append('<tr><th scope="row">'+e(label)+'</th>'+''.join(cols)+'</tr>')
    discount_rows=''.join('<li><span>'+e(label)+'</span><b>'+str(origin['discounts'][k])+'</b></li>' for k,label in DISCOUNTS)
    return '''<section id="a262-origin-anchor" class="a262-finance-origin" aria-label="Origine riconciliata delle entrate"><h3>Da dove arrivano le entrate</h3>
<p>La somma coincide con le entrate del registro. Incassi e persone sono conteggi distinti.</p>
<div class="a262-origin-grid">'''+cards+'''</div>
<details class="a262-analysis"><summary>Dettaglio per metodo e agevolazioni</summary>
<div class="a262-table-wrap"><table><caption>Numero di incassi e importo per metodo e causale</caption><thead><tr><th>Metodo</th>'''+''.join('<th>'+e(label)+'</th>' for _,label in CATEGORIES)+'''</tr></thead><tbody>'''+''.join(rows)+'''</tbody></table></div>
<h4>Agevolazioni documentate</h4><ul class="a262-discount-grid">'''+discount_rows+'''</ul><p class="a262-caveat">'''+e(origin['note'])+''' Le quote esentate/non dovute non sono denaro incassato. Le riduzioni non si sommano alle entrate.</p>
</details></section>'''


def tiny(origin):
    vals=origin['categories'];s=escape
    return '''<div class="a262-teaser"><div class="a262-teaser-title">Origine degli incassi <small>registri riconciliati</small></div>
<div class="a262-teaser-grid">'''+''.join('<span>'+s(label)+'<b>'+s(euros(vals[key]['total']))+'</b><small>'+str(vals[key]['count'])+' incassi</small></span>' for key,label in CATEGORIES)+'''</div>
<small>Metodi e sconti: <a href="#a262-origin-anchor" id="a262-show-details">apri gli altri controlli</a></small></div>'''


def css():
    return '''<style id="a262-origin-style">
.a262-finance-origin{margin-top:20px;padding:16px;border:1px solid #38526b;border-radius:14px;background:#132437;color:#edf4fc}
.a262-finance-origin h3{font-size:20px;color:#fff;margin:0 0 7px}.a262-finance-origin p{color:#b9cfe0;font-size:13px}
.a262-origin-grid,.a262-teaser-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px}
.a262-origin-card,.a262-teaser-grid>span{min-width:0;background:#1b3248;border:1px solid #35516b;border-radius:11px;padding:12px;display:flex;flex-direction:column;gap:6px;color:#e5f0fa;font-size:12px}
.a262-origin-card strong,.a262-teaser-grid b{font-size:clamp(15px,1.7vw,22px);color:#fff;font-variant-numeric:tabular-nums}
.a262-origin-card small,.a262-teaser-grid small{font-size:11px;color:#b8cadb}
.a262-finance-origin details{margin-top:15px}.a262-finance-origin summary{cursor:pointer;color:#b3e1ff;font-weight:700;padding:11px 0}
.a262-table-wrap{overflow:auto}.a262-table-wrap table{border-collapse:collapse;width:100%;min-width:650px;font-size:12px}
.a262-table-wrap th,.a262-table-wrap td{padding:9px;border-bottom:1px solid #395067;text-align:left;color:#e9f1f9}
.a262-table-wrap td small{color:#b0bfce}.a262-discount-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;list-style:none;padding:0}
.a262-discount-grid li{display:flex;justify-content:space-between;gap:8px;background:#1c3449;border-radius:9px;padding:11px;font-size:12px}
.a262-caveat{font-size:12px;line-height:1.6}
.a262-teaser{margin-top:14px;padding:13px;background:#192c3c;border:1px solid #3b5369;border-radius:13px}
.a262-teaser-title{color:#eff8ff;font-size:14px;font-weight:750;margin-bottom:10px}.a262-teaser-title small{color:#b9cbd9;font-size:11px;font-weight:400;margin-left:9px}
.a262-teaser>small{display:block;margin-top:10px;color:#c2cfdd}.a262-teaser a{color:#9cdbff}
@media(max-width:850px){.a262-origin-grid,.a262-teaser-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:450px){.a262-origin-grid,.a262-teaser-grid,.a262-discount-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}.a262-origin-card,.a262-teaser-grid>span{padding:9px}.a262-teaser-grid b{font-size:17px}}
</style>'''
