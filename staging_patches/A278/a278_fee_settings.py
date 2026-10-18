"""A278: simple tariff editor (staging). Only future proposals change; no mass DML."""
from __future__ import annotations
from decimal import Decimal
from html import escape as h
import secrets
import sqlite3
from .a278_quote_rules import money,table

CODES=('standard','agonista','sorelle','personalizzata')

def update_tariff(conn, *,code,amount,expected,reason,operator):
    """Changes only quote_listino, auditable, atomic, optimistic precondition.

    No quote_mensili, pagamenti, movimenti, ricevute or PDFs touched.
    """
    code=str(code or '').strip().lower()
    if code not in CODES:raise ValueError('Categoria non valida')
    value_raw=Decimal(str(amount or '').replace(',','.'))
    previous_raw=Decimal(str(expected or '').replace(',','.'))
    if not value_raw.is_finite() or value_raw!=value_raw.quantize(Decimal('0.01')):
        raise ValueError('Importo con massimo due decimali')
    if not previous_raw.is_finite() or previous_raw!=previous_raw.quantize(Decimal('0.01')):
        raise ValueError('Confronto tariffa non valido')
    value=money(value_raw)
    previous=money(previous_raw)
    if value<Decimal('0') or value>Decimal('5000'):raise ValueError('Tariffa fuori intervallo')
    if not isinstance(reason,str) or len(reason.strip())<12:raise ValueError('Motivazione obbligatoria, almeno 12 caratteri')
    if not str(operator or '').strip():raise ValueError('Operatore non identificato')
    if conn.in_transaction:raise ValueError('Riapri il modulo: altra operazione contabile in corso')
    try:
        conn.execute('BEGIN IMMEDIATE')
        current=conn.execute('SELECT importo FROM quote_listino WHERE codice=?',(code,)).fetchone()
        if current is None:raise ValueError('Listino non inizializzato: intervento tecnico necessario')
        old=money(current[0])
        if old!=previous:raise ValueError('Prezzo modificato nel frattempo: ricarica la pagina')
        if old==value:raise ValueError('Nessuna variazione da registrare')
        conn.execute('''CREATE TABLE IF NOT EXISTS bodymind_a278_tariffe_audit(
          id INTEGER PRIMARY KEY AUTOINCREMENT,codice TEXT NOT NULL,
          precedente TEXT NOT NULL,nuovo TEXT NOT NULL,motivo TEXT NOT NULL,
          operatore TEXT NOT NULL,creato_il TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute('UPDATE quote_listino SET importo=?,updated_at=CURRENT_TIMESTAMP WHERE codice=?',(str(value),code))
        conn.execute('INSERT INTO bodymind_a278_tariffe_audit(codice,precedente,nuovo,motivo,operatore) VALUES(?,?,?,?,?)',
                     (code,str(old),str(value),reason.strip()[:500],str(operator)[:100]))
        conn.commit()
        return {'codice':code,'precedente':old,'nuovo':value,'frozen_months_unchanged':True}
    except Exception:
        conn.rollback()
        raise

def render_rates(rates,csrf,notice='',error=''):
    css="""<style>
    .a278{max-width:920px;margin:0 auto;padding:20px 13px 54px;font:15px system-ui;color:#eff7fd}
    .a278 *{box-sizing:border-box}.a278 h1{font-size:clamp(24px,3vw,31px);margin:7px 0}
    .a278 .intro{color:#c1d2df;max-width:70ch;line-height:1.48}
    .a278 .fees{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
    .a278 .fee{background:#102238;border:1px solid #334d66;border-radius:15px;padding:16px;box-shadow:none}
    .a278 .fee h2{margin:0 0 8px;font-size:18px}.a278 input,.a278 textarea{display:block;width:100%;min-height:44px;padding:9px;border:1px solid #8aa1b7;border-radius:9px;background:#081a2b;color:#fff;font:inherit;margin-top:4px}
    .a278 textarea{min-height:68px}.a278 label{display:block;margin:12px 0;font-weight:650}
    .a278 button{min-height:44px;width:100%;border:0;border-radius:10px;background:#317aad;color:#fff;font-weight:800;cursor:pointer}
    .a278 a{color:#a0d8fc}.a278 .notice{border-left:3px solid #edb76b;padding:10px 13px;margin:12px 0;background:#263242}
    @media(max-width:710px){.a278 .fees{grid-template-columns:1fr}}
    </style>"""
    result=css+"<main class='a278'><a href='/quote-incassi'>← Quote &amp; Incassi</a><h1>Tariffe e quote</h1>"
    result+="<p class='intro'>Imposta qui le tariffe generali. Il listino si applica come proposta alle quote nuove. <strong>Non modifica retroattivamente incassi, decisioni specifiche, ricevute o mensilità già salvate.</strong> Ogni eccezione va gestita nella scheda della tesserata o nella decisione del singolo mese.</p>"
    result+="<p class='intro'><a href='/pagamenti/decisione-quota?mese=10&anno=2026'>Eccezioni del mese (motivate)</a> · <a href='/segreteria/iscrizioni'>Date d'ingresso</a> · <a href='/segreteria/quote-verifica'>Spiegazione dei residui</a></p>"
    if notice:result+="<div class='notice'>"+h(notice)+"</div>"
    if error:result+="<div class='notice' role='alert'>"+h(error)+"</div>"
    result+="<div class='fees'>"
    for code in CODES:
        fee=rates.get(code)
        if fee is None:continue
        label={'standard':'Standard — quota ordinaria','agonista':'Agonista','sorelle':'Sorelle','personalizzata':'Personalizzata — base categoria'}[code]
        val=f'{money(fee):.2f}'
        result+="<section class='fee'><h2>"+h(label)+"</h2><form method='post'>"
        result+="<input type='hidden' name='csrf_token' value='"+h(csrf)+"'><input type='hidden' name='codice' value='"+h(code)+"'><input type='hidden' name='expected' value='"+h(val)+"'>"
        result+="<label>Quota mensile (€)<input name='importo' type='number' inputmode='decimal' min='0' max='5000' step='0.01' value='"+h(val)+"' required></label>"
        result+="<label>Motivo variazione<textarea name='motivo' minlength='12' maxlength='500' required placeholder='Es. nuovo listino dal 1° novembre'></textarea></label>"
        result+="<button type='submit' onclick=\"return confirm('Confermi la nuova tariffa senza modificare i mesi passati?')\">Salva tariffa</button></form></section>"
    return result+"</div><p class='intro'>Un valore 0 o una tariffa individuale non configurata non crea automaticamente un insoluto. Il controllo delle quote effettivamente dovute avviene per atleta, mese e data d’ingresso.</p></main>"

def report_for_period(conn,month,year):
    """One accounting view: owed amounts do NOT include open payment requests."""
    from .a278_quote_rules import monthly_explanation,validate_period
    year,month=validate_period(year,month)
    members=[]
    for person in conn.execute('SELECT id,nome,cognome FROM tesserati WHERE COALESCE(attivo,1)=1 ORDER BY cognome,nome'):
        rec=dict(person)
        explanation=monthly_explanation(conn,int(rec['id']),month,year)
        rec.update(explanation)
        members.append(rec)
    open_requests=[]
    if table(conn,'payment_requests'):
        cols={str(c[1]) for c in conn.execute('PRAGMA table_info(payment_requests)')}
        needed={'id','tesserato_id','status','amount','mese','anno'}
        if needed <= cols:
            for r in conn.execute('SELECT * FROM payment_requests'):
                x=dict(r)
                if str(x.get('status') or '').lower() not in ('pending','queued','requested') or x.get('deleted_at'):
                    continue
                open_requests.append({'id':int(x['id']),'tesserato_id':x.get('tesserato_id'),
                  'mese':x.get('mese'),'anno':x.get('anno'),'motivo':str(x.get('motivo') or '')[:100],
                  'importo':money(x.get('amount'))})
    verified=sum((x['residuo'] for x in members if x['stato'] in ('dovuto','parziale') and x['residuo'] is not None),Decimal('0.00'))
    ambiguous=sum(x['stato'] not in ('dovuto','parziale','pagato','non_dovuto') for x in members)
    pending_total=sum((x['importo'] for x in open_requests),Decimal('0.00'))
    return {'mese':month,'anno':year,'members':members,'residui_calcolati':verified,
      'quote_da_verificare':ambiguous,'richieste':open_requests,'richieste_aperte':pending_total}

def render_audit(data,csrf):
    css="""<style>.a278audit{max-width:1050px;margin:auto;padding:18px 12px;color:#f1f7fc;font:14px system-ui}
    .a278audit *{box-sizing:border-box}.a278audit h1{font-size:clamp(24px,3vw,30px)}
    .a278audit .muted{color:#c0d1df;line-height:1.5}.a278audit .cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px}
    .a278audit .cards article,.a278audit section{background:#10263a;border:1px solid #36536a;padding:14px;border-radius:14px;margin:9px 0}
    .a278audit .value{font-size:23px;font-weight:800}.a278audit table{border-collapse:collapse;width:100%}
    .a278audit th,.a278audit td{text-align:left;padding:9px 7px;border-bottom:1px solid #2b4a60}
    .a278audit a{color:#9cdeff}.a278audit form{display:flex;align-items:end;gap:8px;flex-wrap:wrap}
    .a278audit label{display:grid;gap:4px}.a278audit input,.a278audit button{padding:10px;border-radius:9px;border:1px solid #5b8aaa;background:#102b43;color:white;min-height:44px}
    @media(max-width:750px){.a278audit .cards{grid-template-columns:1fr}.a278audit table,.a278audit tr,.a278audit td,.a278audit tbody{display:block;width:100%}
      .a278audit thead{display:none}.a278audit tr{padding:11px 6px;border-bottom:1px solid #476078}.a278audit td{border:0;padding:4px}
      .a278audit td:before{content:attr(data-label) ': ';font-weight:750;color:#c8dfef}}</style>"""
    s=css+"<main class='a278audit'><a href='/impostazioni/quote'>← Impostazioni quote</a><h1>Spiegazione del da recuperare</h1>"
    s+="<p class='muted'>Le richieste online aperte NON sono nuovo denaro dovuto: vanno riconciliate, non sommate ai residui. Il totale dei residui calcolati NON è un saldo certificato se ci sono quote non configurate, crediti o date d’ingresso da verificare.</p>"
    s+="<form method='get'><label>Mese<input type='number' name='mese' min='1' max='12' value='"+str(data['mese'])+"'></label><label>Anno<input type='number' name='anno' min='2020' max='2100' value='"+str(data['anno'])+"'></label><button>Ricalcola</button></form>"
    s+="<div class='cards'><article>Residui documentati <div class='value'>€ "+h(f"{data['residui_calcolati']:.2f}")+"</div></article>"
    s+="<article>Richieste aperte, da riconciliare <div class='value'>€ "+h(f"{data['richieste_aperte']:.2f}")+"</div></article>"
    s+="<article>Situazioni dubbie <div class='value'>"+str(data['quote_da_verificare'])+"</div></article></div>"
    s+="<section><h2>Quote per atleta</h2><table><thead><tr><th>Atleta</th><th>Stato</th><th>Dovuto</th><th>Incassato</th><th>Residuo</th><th>Richieste</th><th>Apri</th></tr></thead><tbody>"
    for p in data['members']:
        fields=[h((str(p['cognome'] or '')+' '+str(p['nome'] or '')).strip()),h(p['stato']),
           '—' if p['dovuto'] is None else h(f"€ {p['dovuto']:.2f}"),h(f"€ {p['pagato']:.2f}"),
           'Da verificare' if p['residuo'] is None else h(f"€ {p['residuo']:.2f}"),
           h(f"€ {p['richieste_aperte']:.2f}"),"<a href='/quote-incassi/atleta/"+str(int(p['id']))+"'>Scheda</a>"]
        s+='<tr>'+''.join('<td data-label="'+lab+'">'+x+'</td>' for lab,x in zip(('Atleta','Stato','Dovuto','Incassato','Residuo','Richieste','Apri'),fields))+'</tr>'
    s+='</tbody></table></section><section><h2>Richieste da riconciliare</h2><p class="muted">Ogni richiesta è un promemoria/operazione, non un incasso né un ulteriore credito.</p><table><thead><tr><th>ID</th><th>Atleta ID</th><th>Periodo</th><th>Importo</th><th>Causale</th></tr></thead><tbody>'
    for x in data['richieste']:
        vals=[str(x['id']),h(str(x.get('tesserato_id') or 'non collegato')),
          h(f"{str(x.get('mese') or '?')}/{str(x.get('anno') or '?')}"),h(f"€ {x['importo']:.2f}"),h(x['motivo'])]
        s+='<tr>'+''.join('<td data-label="'+lab+'">'+v+'</td>' for lab,v in zip(('ID','Atleta','Periodo','Importo','Causale'),vals))+'</tr>'
    s+='</tbody></table></section></main>'
    return s

def install(ns):
    app=ns['app'];db=ns['db'];admin_required=ns['admin_required']
    request=ns['request'];csrf_token=ns['csrf_token'];layout=ns['layout'];session=ns['session'];redirect=ns['redirect']
    @app.route('/impostazioni/quote',methods=['GET','POST'],endpoint='bodymind_a278_tariffe')
    @admin_required
    def tariffe():
        error=''
        if request.method=='POST':
            if not secrets.compare_digest(str(request.form.get('csrf_token') or ''),csrf_token()):
                return layout(render_rates({},csrf_token(),error='Token non valido')),400
            conn=db();conn.row_factory=sqlite3.Row
            try:
                update_tariff(conn,code=request.form.get('codice'),amount=request.form.get('importo'),
                  expected=request.form.get('expected'),reason=request.form.get('motivo'),
                  operator=str(session.get('username') or session.get('user_id') or ''))
                return redirect('/impostazioni/quote?salvato=1',code=303)
            except (ValueError,sqlite3.DatabaseError) as exc:error=str(exc)
            finally:conn.close()
        conn=db();conn.row_factory=sqlite3.Row
        try:
            conn.execute('PRAGMA query_only=ON')
            if not table(conn,'quote_listino'):
                return layout(render_rates({},csrf_token(),error='Listino non presente: inizializzazione necessaria')),503
            rates={str(row['codice']):money(row['importo']) for row in conn.execute('SELECT codice,importo FROM quote_listino')}
        finally:conn.close()
        return layout(render_rates(rates,csrf_token(),notice='Tariffa salvata con storico. Mesi e pagamenti già registrati non alterati.' if request.args.get('salvato') else '',error=error))

    @app.route('/segreteria/quote-verifica',methods=['GET'],endpoint='bodymind_a278_quote_audit')
    @admin_required
    def quote_audit():
        from datetime import date
        now=date.today()
        try:
            month=int(request.args.get('mese') or now.month)
            year=int(request.args.get('anno') or now.year)
            conn=db();conn.row_factory=sqlite3.Row
            try:
                conn.execute('PRAGMA query_only=ON')
                result=report_for_period(conn,month,year)
            finally:conn.close()
            from flask import make_response
            response=make_response(layout(render_audit(result,csrf_token())))
            response.headers['Cache-Control']='no-store, max-age=0'
            return response
        except (ValueError,sqlite3.DatabaseError):
            return layout('<main><h1>Contabilità da verificare</h1><p>Il report è stato bloccato per evitare totali inattendibili.</p></main>'),503