# -*- coding: utf-8 -*-
"""A238: read-only finance snapshot, payment methods, and truthful Home dashboard panel.

NO DML or DDL; historical transactions, receipts and expenses remain untouched.
"""
import html
import json
import re
import sqlite3
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path

DB = Path('/data/tenants/default/asd.db')
PAID = frozenset(('paid', 'paid_manual', 'closed_manual', 'pagato_online_verificato', 'pagato', 'incassato', 'saldato'))
VOID = frozenset(('annullato', 'annullata', 'cancelled', 'canceled', 'void', 'refunded', 'rimborsato', 'stornato'))
NOT_PAID = frozenset(('unpaid', 'pending', 'failed'))


def amount(v):
    try:
        return Decimal(str(v if v is not None else 0)).quantize(Decimal('0.01'))
    except (ValueError, InvalidOperation, TypeError):
        raise ValueError('STOP: valore contabile non numerico')


def payment_active(p):
    statuses = [str(p.get(k) or '').strip().lower() for k in ('stato', 'online_status')]
    statuses = [s for s in statuses if s]
    return bool(statuses) and amount(p.get('importo')) > 0 and any(s in PAID for s in statuses) and not any(s in VOID or s in NOT_PAID for s in statuses)


# A238: strict method classification. NEVER assume absent methods mean cash.
def payment_channel(raw):
    x = str(raw or '').strip().casefold().replace('_', ' ').replace('-', ' ')
    x = ' '.join(x.split())
    if x in ('contanti','contante','cash','in contanti','a mano','cash in hand'):
        return 'contanti'
    if x in ('bonifico','bonifico bancario','banca','bank transfer','sepa','iban'):
        return 'bonifico'
    # The stored option 'carta/SumUp' does not prove which processor settled it.
    if x in ('carta/sumup','carta / sumup','carta sumup','carta pos sumup','sumup','carta','pos','carta di credito','carta di debito','bancomat','card','circuito carta'):
        return 'carta_pos_sumup'
    if x in ('altro','other'):
        return 'altro'
    if x in ('addebito','sdd','rid','addebito diretto'):
        return 'addebito'
    return 'non_classificato'


def split_payment_channels(payments, expenses):
    keys=('contanti','bonifico','carta_pos_sumup','addebito','altro','non_classificato')
    income={k:Decimal('0.00') for k in keys}
    outgoing={k:Decimal('0.00') for k in keys}
    records={k:0 for k in keys}
    unknown_examples=set()
    for p in payments:
        k=payment_channel(p.get('metodo_pagamento'))
        income[k]+=amount(p.get('importo'));records[k]+=1
        if k=='non_classificato': unknown_examples.add(str(p.get('metodo_pagamento') or '(mancante)').strip()[:50])
    for e in expenses:
        val=amount(e.get('importo'))
        if val<=0:continue # documentary annexes of reimbursed expense, not another cash payment.
        k=payment_channel(e.get('metodo'))
        outgoing[k]+=val
        if k=='non_classificato':unknown_examples.add('Uscita: '+str(e.get('metodo') or '(mancante)').strip()[:40])
    return {'entrate_per_metodo':income,'uscite_per_metodo':outgoing,'movimenti_per_metodo':records,
            'etichette_non_riconosciute':sorted(unknown_examples)[:12]}


def snapshot(db_path=DB):
    db_path = Path(db_path)
    c = sqlite3.connect('file:'+str(db_path.resolve())+'?mode=ro', uri=True, timeout=20)
    c.row_factory = sqlite3.Row
    try:
        c.execute('PRAGMA query_only=ON')
        # Gate obvious corruption and schema drift instead of showing a convincing wrong sum.
        if str(c.execute('PRAGMA quick_check').fetchone()[0]) != 'ok':
            raise ValueError('STOP: database quick_check non OK')
        needed = {'pagamenti': {'id','importo','stato','online_status'},
                  'movimenti': {'id','importo','tipo','pagamento_id'},
                  'bodymind_uscite': {'id','importo','data'}}
        for t, keys in needed.items():
            columns = {str(r[1]) for r in c.execute('PRAGMA table_info("'+t+'")')}
            if not keys.issubset(columns): raise ValueError('STOP: schema inatteso '+t)
        ps = {int(r['id']):dict(r) for r in c.execute('SELECT * FROM pagamenti')}
        ledger = [dict(r) for r in c.execute('SELECT * FROM movimenti')]
        expenses = [dict(r) for r in c.execute('SELECT * FROM bodymind_uscite')]
        from .bodymind_a253_manual import methods as _a253_methods
        manual_methods = _a253_methods(c)
        manual_in={}
        manual_out={}

        receipts = {}
        rc = {str(x[1]) for x in c.execute('PRAGMA table_info("ricevute")')}
        if {'pagamento_id','annullata'}.issubset(rc):
            for r in c.execute('SELECT pagamento_id,annullata FROM ricevute WHERE pagamento_id IS NOT NULL'):
                pid = int(r['pagamento_id'])
                receipts.setdefault(pid,[]).append(int(r['annullata'] or 0))
        income=Decimal('0');cancelled=Decimal('0');unconfirmed=Decimal('0')
        live_count=0;cancelled_count=0;unknown_count=0;active_pids={};
        for m in ledger:
            kind = str(m.get('tipo') or '').strip().lower()
            if kind not in ('entrata','incasso','income'):
                # A235 found 0 old cash-out movements. Detect future ones; don't silently double count.
                if kind in ('uscita','spesa','expense') and amount(m.get('importo')) != 0:
                    if m.get('pagamento_id') is None and int(m.get('auto_generato') or 0)==0 and int(m['id']) in manual_methods:
                        manual_out[int(m['id'])]=dict(m, metodo=manual_methods[int(m['id'])])
                    else:
                        unknown_count += 1
                continue
            pid=m.get('pagamento_id');p=ps.get(int(pid)) if pid is not None else None
            val=amount(m.get('importo'))
            if pid is None and int(m.get('auto_generato') or 0)==0 and int(m['id']) in manual_methods:
                if val<=0:raise ValueError('STOP: movimento manuale A253 non positivo')
                manual_in[int(m['id'])]=dict(m, metodo_pagamento=manual_methods[int(m['id'])])
                income+=val;live_count+=1
            elif p and payment_active(p):
                if val != amount(p.get('importo')):
                    raise ValueError('STOP: incongruenza importo cassa/pagamento '+str(pid))
                active_pids[int(pid)] = active_pids.get(int(pid),0) + 1
                income += val;live_count += 1
            elif p and any(str(p.get(k) or '').strip().lower() in VOID for k in ('stato','online_status')):
                cancelled+=val;cancelled_count+=1
            else:
                unconfirmed+=val;unknown_count+=1
        if any(n!=1 for n in active_pids.values()):
            raise ValueError('STOP: duplicazione prima nota per un pagamento attivo')
        payment_ids={pid for pid,p in ps.items() if payment_active(p)}
        if active_pids.keys()!=payment_ids:
            raise ValueError('STOP: pagamenti attivi senza entrata o entrate non univoche')
        outgoing=sum((amount(x['importo']) for x in expenses),Decimal('0')) + sum((amount(x['importo']) for x in manual_out.values()),Decimal('0'))
        if outgoing<0:raise ValueError('STOP: uscita negativa da verificare')
        zero_attached=sum(1 for x in expenses if amount(x['importo'])==0)
        receipt_anomalies=sum(1 for pid in payment_ids if receipts and receipts.get(pid,[]).count(0)!=1)
        by_channel=split_payment_channels((ps[pid] for pid in sorted(payment_ids)),expenses)
        # Le scritture manuali A253 sono registrate separatamente e auditabili.
        for r in manual_in.values():
            k=payment_channel(r['metodo_pagamento']);val=amount(r['importo'])
            if k=='non_classificato':raise ValueError('STOP: metodo incasso manuale sconosciuto')
            by_channel['entrate_per_metodo'][k]+=val
            by_channel['movimenti_per_metodo'][k]+=1
        for r in manual_out.values():
            k=payment_channel(r['metodo']);val=amount(r['importo'])
            if k=='non_classificato':raise ValueError('STOP: metodo uscita manuale sconosciuto')
            by_channel['uscite_per_metodo'][k]+=val
        if sum(by_channel['entrate_per_metodo'].values(),Decimal('0.00'))!=income:
            raise ValueError('STOP: ripartizione per metodo non corrisponde agli incassi attivi')
        if sum(by_channel['uscite_per_metodo'].values(),Decimal('0.00'))!=outgoing:
            raise ValueError('STOP: ripartizione per metodo non corrisponde alle uscite registrate')
        # A262_ORIGIN_ACTIVE: counts derive from the SAME validated A237 rows.
        from . import bodymind_a262_income_origin as _a262
        origins=_a262.build(c,ps,active_pids,manual_in,income,
                             by_channel['entrate_per_metodo'],live_count)
        return {
            **by_channel,
            'origini_entrate':origins,
            'entrate':income,'uscite':outgoing,'saldo':income-outgoing,
            'movimenti_attivi':live_count,'movimenti_annullati':cancelled_count,
            'importo_escluso_annullati':cancelled,'da_verificare_senza_correlazione':unconfirmed,
            'a253_manual_income_count':len(manual_in),'a253_manual_outgoing_count':len(manual_out),
            'movimenti_non_classificati':unknown_count,'giustificativi_a_zero':zero_attached,
            'anomalie_ricevute':receipt_anomalies,
            'tabelle': {'pagamenti':len(ps),'movimenti':len(ledger),'bodymind_uscite':len(expenses)},
        }
    finally:
        c.close()


def euros(value):
    s=f'{amount(value):,.2f}'
    return s.replace(',','\u00a7').replace('.',',').replace('\u00a7','.')+' €'


def finance_panel(data):
    esc=html.escape
    warning=('Sono presenti '+str(data['anomalie_ricevute'])+' pagamenti senza ricevuta valida unica. ' if data['anomalie_ricevute'] else '')
    if data['da_verificare_senza_correlazione'] or data['movimenti_non_classificati']:
        warning+='Movimenti di cassa non classificabili: verifica necessaria. '
    part=data.get('entrate_per_metodo') or {}
    exits=data.get('uscite_per_metodo') or {}
    methods=[('contanti','Contanti'),('bonifico','Bonifico'),('carta_pos_sumup','Carta / SumUp / POS'),('addebito','Addebito'),('altro','Altro dichiarato'),('non_classificato','Metodo non indicato')]
    from . import bodymind_a262_income_origin as _a262
    origin_markup=_a262.css()+_a262.render(data['origini_entrate'])
    partition=''.join('<div class="bm-method"><span>'+esc(label)+'</span><strong>'+esc(euros(part.get(k,0)))+'</strong><small>'+esc(str(data.get('movimenti_per_metodo',{}).get(k,0)))+' mov.</small></div>' for k,label in methods)
    out_details=' · '.join(esc(label)+': '+esc(euros(exits.get(k,0))) for k,label in methods if amount(exits.get(k,0))>0)
    unknown=(len(data.get('etichette_non_riconosciute',[]))>0)
    extra_warning=(' Esistono metodi di pagamento non indicati o non riconosciuti: NON sono conteggiati automaticamente come contanti.' if unknown else '')
    return '''<section class="bodymind-a237-finance" aria-label="Contabilit\u00e0 riconciliata">
<style>
.bodymind-a237-finance{background:#101c31;color:#edf5ff;border:1px solid #365471;border-radius:20px;padding:23px;margin:24px 0;box-sizing:border-box}
.bodymind-a237-finance *{box-sizing:border-box}.bodymind-a237-finance h2{font-size:24px;color:#fff;margin:8px 0 14px}
.bodymind-a237-finance .fin-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.bodymind-a237-finance .fin-kpis>div{background:#172b40;padding:15px;border-radius:14px;border:1px solid #31506a}
.bodymind-a237-finance .fin-kpis span{display:block;color:#cbd6e7;font-size:13px}.bodymind-a237-finance .fin-kpis strong{display:block;font-size:clamp(19px,2vw,31px);font-variant-numeric:tabular-nums;margin-top:8px;color:#d1e8ff}
.bodymind-a237-finance .method-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:9px;margin-top:12px}.bodymind-a237-finance .bm-method{background:#152b42;border:1px solid #2c4963;border-radius:9px;padding:10px;min-width:0}.bodymind-a237-finance .bm-method span{display:block;font-size:12px;color:#d7e4ee}.bodymind-a237-finance .bm-method strong{display:block;font-size:17px;margin-top:3px}.bodymind-a237-finance .bm-method small{display:block;color:#bed0df;margin-top:3px}
.bodymind-a237-finance .fin-note{color:#d9e4f0;font-size:13px;margin-top:12px;line-height:1.5}
@media(max-width:850px){.bodymind-a237-finance .fin-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.bodymind-a237-finance .method-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:450px){.bodymind-a237-finance .fin-kpis{grid-template-columns:1fr}}
</style>
<small>CONTABILIT\u00c0 REALE \u00b7 REGISTRI RICONCILIATI</small><h2>Flussi e bilancio</h2>
<div class="fin-kpis"><div><span>Entrate registrate valide</span><strong>'''+esc(euros(data['entrate']))+'''</strong></div>
<div><span>Uscite registrate</span><strong>'''+esc(euros(data['uscite']))+'''</strong></div>
<div><span>Saldo dei registri</span><strong>'''+esc(euros(data['saldo']))+'''</strong></div>
<div><span>Movimenti attivi</span><strong>'''+str(data['movimenti_attivi'])+'''</strong></div></div>
<div class="fin-note" style="margin-top:15px"><b>Incassi per metodo già registrato</b> (il campo carta/SumUp può non distinguere il circuito effettivo)</div>
<div class="method-grid">'''+partition+'''</div>'''+origin_markup+'''
<div class="fin-note">Uscite registrate per metodo: '''+(out_details or 'non classificato')+'''</div>
<p class="fin-note">Esclusi dai totali attivi: '''+str(data['movimenti_annullati'])+''' movimenti annullati per '''+esc(euros(data['importo_escluso_annullati']))+'''. 
Le '''+str(data['giustificativi_a_zero'])+''' righe a zero del modulo spese restano giustificativi e non vengono sommate nuovamente. 
Totali relativi ai registri presenti, non attestazione del saldo bancario. Per il saldo reale della cassa servono saldo iniziale, trasferimenti interni, prelievi e commissioni. '''+esc(warning+extra_warning)+'''</p>
</section>'''


class _Candidates(HTMLParser):
    """Identify minimum HTML container with both section headings and finance labels."""
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.text=text;self.offsets=[0]
        for m in re.finditer('\n',text):self.offsets.append(m.end())
        self.stack=[];self.matches=[]
    def _at(self):
        line,col=self.getpos();return self.offsets[line-1]+col
    def handle_starttag(self,tag,attrs):
        if tag in ('div','section','article'):
            self.stack.append((tag,self._at()))
        elif tag not in ('br','meta','link','img','input','hr','source','path','use','wbr','area'):
            self.stack.append((tag,self._at()))
    def handle_startendtag(self,tag,attrs):pass
    def handle_endtag(self,tag):
        target=next((i for i in range(len(self.stack)-1,-1,-1) if self.stack[i][0]==tag),None)
        if target is None:return
        start=self.stack[target][1];end=self.text.find('>',self._at())+1
        if tag in ('div','section','article') and 0<end-start<40000:
            segment=self.text[start:end]
            if ('Contabilit' in segment and 'Flussi e bilancio' in segment and
                all(x in segment for x in ('Entrate','Uscite','Saldo','Movimenti'))):
                self.matches.append((start,end,tag))
        self.stack=self.stack[:target]


def replace_home_panel(doc,data):
    if 'BODYMIND_A237_FINANCE_ACTIVE' in doc:return doc,False
    if 'Flussi e bilancio' not in doc:return doc,False
    p=_Candidates(doc);p.feed(doc)
    if not p.matches:raise ValueError('Dashboard: impossibile isolare riquadro contabile esistente')
    start,end,_=min(p.matches,key=lambda x:x[1]-x[0])
    new='<!-- BODYMIND_A237_FINANCE_ACTIVE -->'+finance_panel(data)
    return doc[:start]+new+doc[end:],True


def client_replacement_script(panel_markup):
    """Replace possibly late-rendered accounting card without assuming one dashboard module."""
    # JSON escaping prevents early close of script, even if content changes later.
    encoded=json.dumps(panel_markup,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    js=r'''(function(){
"use strict";
var replacement=MARKUP;
var applied=false;
function update(){
 if(applied)return true;
 var els=document.querySelectorAll('h1,h2,h3,h4,h5');
 for(var i=0;i<els.length;i++){
  var h=els[i];
  if((h.textContent||'').trim().toLowerCase()!=='flussi e bilancio')continue;
  var ancestor=h;
  for(var k=0;k<9&&ancestor&&ancestor!==document.body;k++,ancestor=ancestor.parentElement){
   var t=ancestor.textContent||'';
   if(t.length>6500)break;
   if(t.indexOf('Contabilità reale')===-1 && t.indexOf('Contabilita reale')===-1)continue;
   if(['Entrate','Uscite','Saldo','Movimenti'].some(function(x){return t.indexOf(x)===-1}))continue;
   var host=document.createElement('div');
   host.innerHTML=replacement;
   var newPanel=host.firstElementChild;
   if(!newPanel)return false;
   ancestor.replaceWith(newPanel);
   applied=true;
   return true;
  }
 }
 return false;
}
if(!update()){
 var obs=new MutationObserver(function(){if(update())obs.disconnect()});
 obs.observe(document.documentElement,{childList:true,subtree:true});
 document.addEventListener('visibilitychange',function(){if(update())obs.disconnect()});
 window.addEventListener('load',function(){if(update())obs.disconnect()});
}
})();'''
    return '<script id="bodymind-a237-finance-client">'+js.replace('MARKUP',encoded,1)+'</script>'


def inject_markup(doc, panel):
    """Use server DOM replacement or a bounded client observer for asynchronous cards."""
    if 'BODYMIND_A237_FINANCE_ACTIVE' in doc or 'bodymind-a237-finance-client' in doc:
        return doc,False
    if 'Flussi e bilancio' in doc:
        p=_Candidates(doc);p.feed(doc)
        if p.matches:
            start,end,_=min(p.matches,key=lambda x:x[1]-x[0])
            return doc[:start]+'<!-- BODYMIND_A237_FINANCE_ACTIVE -->'+panel+doc[end:],True
    js=client_replacement_script(panel)
    idx=doc.lower().rfind('</body>')
    if idx>=0:return doc[:idx]+js+doc[idx:],True
    return doc+js,True


def inject_dashboard(doc, data):
    from . import bodymind_a262_income_origin as _a262
    doc,changed=inject_markup(doc,finance_panel(data))
    if 'A261 advanced controls toggle:' not in doc or 'a260-state-grid' not in doc:
        return doc,changed
    anchor="      </section>\n\n      <!-- A261 advanced controls toggle:"
    if doc.count(anchor)!=1:
        raise ValueError('STOP: dashboard A261 insertion anchor missing/ambiguous')
    teaser=_a262.css()+_a262.tiny(data['origini_entrate'])
    nav="""<script id='a262-origin-navigation'>
    document.addEventListener('click',function(event){
      var link=event.target.closest('#a262-show-details');
      if(!link)return;
      var box=document.querySelector('.pro-dashboard.a261-compact');
      if(box){var btn=box.querySelector('#a261-more-button');if(btn)btn.click();}
    },true);</script>"""
    doc=doc.replace(anchor,teaser+"\n      </section>\n\n      <!-- A261 advanced controls toggle:",1)
    pos=doc.lower().rfind('</body>')
    doc=doc[:pos]+nav+doc[pos:] if pos>=0 else doc+nav
    return doc,True


def accounting_unavailable_markup():
    return '<section class="bodymind-a237-finance" role="alert" style="background:#251d24;color:white;padding:24px;border-radius:16px"><h2>Contabilità da verificare</h2><p>La quadratura dei registri non è riuscita. Non mostrare importi come validi. Verificare Pagamenti e Uscite.</p></section>'


def install(globs):
    app=globs['app'];request=globs['request'];db_path=DB
    @app.after_request
    def _bodymind_a237_dashboard_response(resp):
        resp.headers['X-BodyMind-Finance-Flow']='A237'
        resp.headers['X-BodyMind-Cash-Methods']='A238'
        if request.path not in ('/','/dashboard') or request.method!='GET' or resp.status_code!=200:
            return resp
        if 'text/html' not in (resp.content_type or ''):return resp
        original=resp.get_data(as_text=True)
        try:
            panel_data=snapshot(db_path)
            changed,ok=inject_dashboard(original,panel_data)
            if ok:
                resp.set_data(changed)
                resp.headers['X-BodyMind-Finance-Panel']='reconciled'
                resp.headers['Cache-Control']='no-store'
        except Exception as exc:
            try:app.logger.error('A237 dashboard fail-closed: %s',repr(exc))
            except Exception:pass
            try:
                doc,changed=inject_markup(original,accounting_unavailable_markup())
                if changed:
                    resp.set_data(doc)
                    resp.headers['X-BodyMind-Finance-Panel']='review-needed'
                    resp.headers['Cache-Control']='no-store'
            except Exception as nested:
                try:app.logger.error('A237 cannot mask stale dashboard values: %s',repr(nested))
                except Exception:pass
        return resp
