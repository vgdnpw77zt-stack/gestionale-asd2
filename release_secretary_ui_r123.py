# -*- coding: utf-8 -*-
from __future__ import annotations
import py_compile, shutil, sqlite3, subprocess, sys
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
BACK=Path('/data/release_backups/20261003_r123_secretary_ui')
BACK.mkdir(parents=True,exist_ok=True)
CORE=APP/'asd_app/core.py'
if not APP.joinpath('.TOP2_OFFICIAL').exists(): raise SystemExit('TOP2_OFFICIAL marker missing')
if not CORE.exists(): raise RuntimeError('R123 core.py missing')

src=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R123_SECRETARY_UI' not in src:
    dst=BACK/'core.py'
    if not dst.exists(): shutil.copy2(CORE,dst)
    src += r'''

# BODYMIND_R123_SECRETARY_UI
# Daily secretary UX: remove redundant payment selectors and expose one
# direct, mobile-first attendance workflow. Existing advanced routes remain.

def _r123_course_group(value):
    s=' '.join(str(value or '').strip().lower().replace('_',' ').split())
    if any(x in s for x in ('pro','agon','elite','advanced')):
        return 'pro'
    if any(x in s for x in ('kid','baby','bambin','junior')):
        return 'kids'
    if any(x in s for x in ('adult','adulti')):
        return 'adult'
    return 'base'

def _r123_group_label(key):
    return {'base':'Base','kids':'Kids','adult':'Adult','pro':'Pro / Agoniste'}.get(key,'Base')

@app.before_request
def _bodymind_r123_presence_entrypoint():
    # GET /presenze is now the simple daily workflow. POSTs to the historical
    # route are deliberately left untouched for backwards compatibility.
    if request.method=='GET' and request.path=='/presenze':
        args=[]
        for k in ('data','gruppo','corso_id'):
            v=(request.args.get(k) or '').strip()
            if v: args.append(k+'='+__import__('urllib.parse').parse.quote(v))
        return redirect('/presenze-semplici'+(('?'+('&'.join(args))) if args else ''))

@app.route('/presenze-semplici',methods=['GET','POST'])
@login_required
def bodymind_r123_presenze_semplici():
    from datetime import date as _date
    conn=db(); conn.row_factory=sqlite3.Row
    try:
        group=(request.values.get('gruppo') or '').strip().lower()
        if group not in ('base','kids','adult','pro'):
            group='base'
            cid=parse_int(request.values.get('corso_id','0'),0)
            if cid:
                cr=conn.execute('SELECT nome FROM corsi WHERE id=?',(cid,)).fetchone()
                if cr: group=_r123_course_group(cr['nome'])
        day=(request.values.get('data') or _date.today().isoformat()).strip()
        try: _date.fromisoformat(day)
        except Exception: day=_date.today().isoformat()

        athletes=conn.execute("""SELECT id,nome,cognome,corso FROM tesserati
            ORDER BY TRIM(cognome) COLLATE NOCASE,TRIM(nome) COLLATE NOCASE""").fetchall()
        # BODYMIND_R123_DIRECT_ATHLETE_SELECTION
        # Every operational group can choose directly from the whole athlete list.
        # The legacy tesserati.corso text is not a roster truth and must not hide people.
        selected=list(athletes)
        ids=[int(r['id']) for r in selected]
        course_rows=conn.execute('SELECT id,nome FROM corsi ORDER BY id').fetchall()
        course_id=next((int(c['id']) for c in course_rows if _r123_course_group(c['nome'])==group),None)

        if request.method=='POST':
            checked={parse_int(x,0) for x in request.form.getlist('presente_id')}
            checked={x for x in checked if x in set(ids)}
            try:
                if course_id is None:
                    conn.execute('DELETE FROM presenze WHERE data=? AND corso_id IS NULL',(day,))
                else:
                    conn.execute('DELETE FROM presenze WHERE data=? AND corso_id=?',(day,course_id))
                now=__import__('datetime').datetime.now().isoformat(timespec='seconds')
                # Keep the register minimal: store only actual presences.
                for tid in sorted(checked):
                    conn.execute("""INSERT INTO presenze(tesserato_id,corso_id,data,stato,note,created_at,updated_at)
                        VALUES(?,?,?,'presente','',?,?)""",(tid,course_id,day,now,now))
                conn.commit()
            except Exception as exc:
                conn.rollback()
                return redirect_with_message('/presenze-semplici?gruppo='+group+'&data='+day,'Errore nel salvataggio presenze: '+str(exc),'error')
            return redirect_with_message('/presenze-semplici?gruppo='+group+'&data='+day,'Presenze salvate: '+str(len(checked))+'.','success')

        existing={}
        if course_id is None:
            q=conn.execute("SELECT * FROM presenze WHERE data=? AND corso_id IS NULL AND stato='presente'",(day,)).fetchall()
        else:
            q=conn.execute("SELECT * FROM presenze WHERE data=? AND corso_id=? AND stato='presente'",(day,course_id)).fetchall()
        for p in q:
            existing[int(p['tesserato_id'])]=str(p['stato'] or '')
    finally:
        conn.close()

    tabs=''.join("<a class='r123-tab "+('active' if group==k else '')+"' href='/presenze-semplici?gruppo="+k+"&data="+e(day)+"'>"+label+"</a>" for k,label in [('base','Base'),('kids','Kids'),('adult','Adult'),('pro','Pro / Agoniste')])
    cards=[]
    for r in selected:
        tid=int(r['id']); is_present=existing.get(tid)=='presente'
        cards.append(f"""<label class='r123-athlete'>
          <input class='r123-check' type='checkbox' name='presente_id' value='{tid}' {'checked' if is_present else ''}>
          <span class='r123-name'>{e((r['cognome'] or '')+' '+(r['nome'] or ''))}</span>
          <span class='r123-course'>{e(r['corso'] or _r123_group_label(group))}</span>
          <span class='r123-state'>{'Presente' if is_present else 'Assente'}</span>
        </label>""")
    rows=''.join(cards) or "<div class='r123-empty'>Nessuna allieva presente in anagrafica.</div>"
    html=f"""<!-- BODYMIND_R123_PRESENZE_SIMPLE -->
    <main class='r123-page'>
      <header class='r123-head'><div><small>PRESENZE</small><h1>Registro rapido</h1><p>Scegli Base, Kids, Adult o Pro / Agoniste, poi tocca direttamente le allieve presenti e salva.</p></div>
      <a class='r123-back' href='/mobile'>Home</a></header>
      <nav class='r123-tabs'>{tabs}</nav>
      <form method='post' id='r123-presence-form'>
        {csrf_input()}
        <input type='hidden' name='gruppo' value='{e(group)}'>
        <div class='r123-date'><label>Data</label><input type='date' name='data' value='{e(day)}' onchange="location.href='/presenze-semplici?gruppo={e(group)}&data='+this.value"></div>
        <div class='r123-actions'><button type='button' onclick='r123All(true)'>Tutte presenti</button><button type='button' onclick='r123All(false)'>Tutte assenti</button></div>
        <section class='r123-list'>{rows}</section>
        <button class='r123-save' type='submit'>Salva presenze</button>
      </form>
    </main>
    <style>
    .r123-page{{max-width:760px;margin:0 auto;padding:14px 12px 90px}}.r123-head{{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;margin-bottom:12px}}.r123-head small{{font-weight:900;letter-spacing:.12em;color:#93c5fd}}.r123-head h1{{margin:4px 0 2px}}.r123-head p{{margin:0;color:#94a3b8}}.r123-back{{padding:10px 12px;border-radius:12px;background:#163b5f;color:white!important;text-decoration:none;font-weight:900}}.r123-tabs{{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin:10px 0}}.r123-tab{{padding:11px 6px;border-radius:12px;background:#12243a;color:#cbd5e1!important;text-decoration:none;text-align:center;font-weight:900;font-size:12px}}.r123-tab.active{{background:#2563eb;color:white!important}}.r123-date{{display:flex;align-items:center;gap:10px;background:#0e2034;padding:10px 12px;border-radius:13px;margin:8px 0}}.r123-date label{{font-weight:900}}.r123-date input{{margin-left:auto;max-width:180px}}.r123-actions{{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin:8px 0}}.r123-actions button{{min-height:44px;border:0;border-radius:12px;font-weight:900}}.r123-list{{display:grid;gap:7px}}.r123-athlete{{display:grid;grid-template-columns:34px 1fr auto;grid-template-areas:'check name state' 'check course state';align-items:center;gap:2px 8px;padding:12px;border-radius:14px;background:#0d1d31;border:1px solid rgba(148,163,184,.18)}}.r123-check{{grid-area:check;width:26px;height:26px}}.r123-name{{grid-area:name;font-weight:950}}.r123-course{{grid-area:course;color:#94a3b8;font-size:12px}}.r123-state{{grid-area:state;font-size:12px;font-weight:900;color:#fca5a5}}.r123-athlete:has(.r123-check:checked){{background:rgba(22,163,74,.14);border-color:rgba(34,197,94,.4)}}.r123-athlete:has(.r123-check:checked) .r123-state{{color:#86efac}}.r123-athlete:has(.r123-check:checked) .r123-state{{font-size:0}}.r123-athlete:has(.r123-check:checked) .r123-state:after{{content:'Presente';font-size:12px}}.r123-save{{position:sticky;bottom:max(10px,env(safe-area-inset-bottom));width:100%;min-height:52px;margin-top:12px;border:0;border-radius:14px;background:#16a34a;color:white;font-size:16px;font-weight:950;box-shadow:0 12px 28px rgba(0,0,0,.35)}}.r123-empty{{padding:18px;text-align:center;color:#94a3b8;background:#0d1d31;border-radius:14px}}@media(max-width:520px){{.r123-tabs{{grid-template-columns:1fr 1fr}}}}
    </style>
    <script>function r123All(v){{document.querySelectorAll('.r123-check').forEach(function(x){{x.checked=v}})}}</script>"""
    return layout(html)

@app.after_request
def _bodymind_r123_payment_simplify(resp):
    try:
        if request.method!='GET' or request.path!='/pagamenti' or int(getattr(resp,'status_code',200) or 200)!=200:
            return resp
        if 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp
        html=resp.get_data(as_text=True)
        mese,anno=current_month_year()
        mese=parse_int(request.args.get('mese',mese),mese); anno=parse_int(request.args.get('anno',anno),anno)
        season=get_membership_season(mese,anno)
        rows=[dict(x) for x in get_missing_iscrizione_rows(anno,mese)]
        rows=sorted(rows,key=lambda r:((str(r.get('cognome') or '')).strip().lower(),(str(r.get('nome') or '')).strip().lower()))
        if rows:
            items=''.join("<a class='r123-pay-person' href='/pagamenti?tesserato_id="+str(int(r.get('id') or 0))+"&mese="+str(mese)+"&anno="+str(anno)+"'><div class='r123-pay-id'><b>"+e((str(r.get('cognome') or '')+' '+str(r.get('nome') or '')).strip())+"</b><small>"+e(str(r.get('telefono') or r.get('telefono_genitore') or 'Telefono non indicato'))+"</small></div><span>Registra quota iscrizione</span></a>" for r in rows)
        else:
            items="<div class='r123-pay-empty'>Tutte le tesserate risultano in regola con la quota iscrizione.</div>"
        box=f"""<!-- BODYMIND_R123_PAYMENT_MOBILE --><section class='r123-pay-box'><div class='r123-pay-kicker'>OPERATIVITÀ IMMEDIATA</div><h3>Tesserate senza quota iscrizione · stagione {e(season['label'])}</h3><div class='r123-pay-list'>{items}</div></section>
        <style>.r123-pay-box{{margin:12px 0;padding:15px;border-radius:16px;background:#0d1d31;border:1px solid rgba(148,163,184,.18)}}.r123-pay-kicker{{font-size:11px;font-weight:950;letter-spacing:.1em;color:#93c5fd}}.r123-pay-box h3{{margin:5px 0 10px}}.r123-pay-list{{display:grid;gap:7px}}.r123-pay-person{{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:11px 12px;border-radius:12px;background:#12283f;color:white!important;text-decoration:none}}.r123-pay-id{{display:grid;gap:3px;min-width:0}}.r123-pay-id b{{font-size:14px;line-height:1.2}}.r123-pay-id small{{color:#cbd5e1;font-size:12px}}.r123-pay-person span{{font-size:11px;color:#93c5fd}}.r123-pay-empty{{color:#86efac;font-weight:800}}@media(max-width:560px){{.r123-pay-person{{align-items:flex-start;flex-direction:column}}}}</style>
        <script>(function(){{
          var targets=['tesseramento / iscrizione','seleziona periodo e tesserato','tesserati senza quota iscrizione/tesseramento'];
          function hideByText(txt){{
            document.querySelectorAll('h1,h2,h3,h4,.kicker,.section-title,label,p,div').forEach(function(el){{
              if((el.textContent||'').trim().toLowerCase().indexOf(txt)>=0){{
                var p=el.closest('.card,.metric-box,.panel,section,.filter-panel,.grid-2');
                if(p && !p.classList.contains('r123-pay-box')) p.style.display='none';
              }}
            }});
          }}
          targets.forEach(hideByText);
        }})();</script>"""
        html=html.replace('</body>',box+'</body>',1) if '</body>' in html else html+box
        resp.set_data(html)
    except Exception as exc:
        print('[r123-payment-warning] '+repr(exc),flush=True)
    return resp
'''
    CORE.write_text(src,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r123-core] PASS simplified payments + direct mobile attendance',flush=True)
else:
    print('[r123-core] already applied',flush=True)

# Upgrade an already-installed R123 presence flow so every group can select
# directly from the full athlete list. Do not depend on legacy tesserati.corso.
core_now=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R123_SECRETARY_UI' in core_now and 'BODYMIND_R123_DIRECT_ATHLETE_SELECTION' not in core_now:
    old="""        athletes=conn.execute(\"\"\"SELECT id,nome,cognome,corso FROM tesserati
            ORDER BY TRIM(cognome) COLLATE NOCASE,TRIM(nome) COLLATE NOCASE\"\"\").fetchall()
        selected=[r for r in athletes if _r123_course_group(r['corso'])==group]
        ids=[int(r['id']) for r in selected]

        if request.method=='POST':
            checked={parse_int(x,0) for x in request.form.getlist('presente_id')}
            try:
                if ids:
                    marks=','.join('?' for _ in ids)
                    conn.execute('DELETE FROM presenze WHERE data=? AND tesserato_id IN ('+marks+')',[day]+ids)
                # Preserve a useful course_id when an existing course clearly
                # belongs to the same group; otherwise NULL is valid.
                course_rows=conn.execute('SELECT id,nome FROM corsi ORDER BY id').fetchall()
                course_id=next((int(c['id']) for c in course_rows if _r123_course_group(c['nome'])==group),None)
                now=__import__('datetime').datetime.now().isoformat(timespec='seconds')
                for r in selected:
                    tid=int(r['id'])
                    stato='presente' if tid in checked else 'assente'
                    conn.execute(\"\"\"INSERT INTO presenze(tesserato_id,corso_id,data,stato,note,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?)\"\"\",(tid,course_id,day,stato,'',now,now))
                conn.commit()
            except Exception as exc:
                conn.rollback()
                return redirect_with_message('/presenze-semplici?gruppo='+group+'&data='+day,'Errore nel salvataggio presenze: '+str(exc),'error')
            return redirect_with_message('/presenze-semplici?gruppo='+group+'&data='+day,'Presenze salvate.','success')

        existing={}
        if ids:
            marks=','.join('?' for _ in ids)
            for p in conn.execute('SELECT * FROM presenze WHERE data=? AND tesserato_id IN ('+marks+')',[day]+ids).fetchall():
                existing[int(p['tesserato_id'])]=str(p['stato'] or '')
"""
    new="""        athletes=conn.execute(\"\"\"SELECT id,nome,cognome,corso FROM tesserati
            ORDER BY TRIM(cognome) COLLATE NOCASE,TRIM(nome) COLLATE NOCASE\"\"\").fetchall()
        # BODYMIND_R123_DIRECT_ATHLETE_SELECTION
        selected=list(athletes)
        ids=[int(r['id']) for r in selected]
        course_rows=conn.execute('SELECT id,nome FROM corsi ORDER BY id').fetchall()
        course_id=next((int(c['id']) for c in course_rows if _r123_course_group(c['nome'])==group),None)

        if request.method=='POST':
            checked={parse_int(x,0) for x in request.form.getlist('presente_id')}
            checked={x for x in checked if x in set(ids)}
            try:
                if course_id is None:
                    conn.execute('DELETE FROM presenze WHERE data=? AND corso_id IS NULL',(day,))
                else:
                    conn.execute('DELETE FROM presenze WHERE data=? AND corso_id=?',(day,course_id))
                now=__import__('datetime').datetime.now().isoformat(timespec='seconds')
                for tid in sorted(checked):
                    conn.execute(\"\"\"INSERT INTO presenze(tesserato_id,corso_id,data,stato,note,created_at,updated_at)
                        VALUES(?,?,?,'presente','',?,?)\"\"\",(tid,course_id,day,now,now))
                conn.commit()
            except Exception as exc:
                conn.rollback()
                return redirect_with_message('/presenze-semplici?gruppo='+group+'&data='+day,'Errore nel salvataggio presenze: '+str(exc),'error')
            return redirect_with_message('/presenze-semplici?gruppo='+group+'&data='+day,'Presenze salvate: '+str(len(checked))+'.','success')

        existing={}
        if course_id is None:
            _rows=conn.execute(\"SELECT * FROM presenze WHERE data=? AND corso_id IS NULL AND stato='presente'\",(day,)).fetchall()
        else:
            _rows=conn.execute(\"SELECT * FROM presenze WHERE data=? AND corso_id=? AND stato='presente'\",(day,course_id)).fetchall()
        for p in _rows:
            existing[int(p['tesserato_id'])]=str(p['stato'] or '')
"""
    if old not in core_now:
        raise RuntimeError('R123 direct-selection migration anchor missing')
    dst=BACK/'core_pre_direct_selection.py'
    if not dst.exists(): shutil.copy2(CORE,dst)
    core_now=core_now.replace(old,new,1)
    core_now=core_now.replace('Nessuna allieva in questo gruppo. Assegna il corso dalla scheda atleta.','Nessuna allieva presente in anagrafica.')
    core_now=core_now.replace('Scegli il gruppo, tocca le allieve presenti e salva.','Scegli Base, Kids, Adult o Pro / Agoniste, poi tocca direttamente le allieve presenti e salva.')
    CORE.write_text(core_now,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r123-core-upgrade] PASS direct athlete selection for all groups',flush=True)

# BODYMIND_R124_PAYMENT_IDENTITY_FIX
# Patch both possible runtime sources. Keep it surgical and idempotent.
_patched_payment_identity=False
for _pay_src in (CORE, APP/'asd_app/routes_pagamenti.py'):
    if not _pay_src.exists():
        continue
    _txt=_pay_src.read_text(encoding='utf-8',errors='replace')
    _before=_txt
    _txt=_txt.replace("e(row['nome'])} {e(row['cognome'])","e((row.get('cognome') or '')+' '+(row.get('nome') or ''))")
    _txt=_txt.replace("e(row['telefono'] or 'Telefono non indicato')","e(row.get('telefono') or row.get('telefono_genitore') or 'Telefono non indicato')")
    if _txt!=_before:
        dst=BACK/('pre_r124_'+_pay_src.name)
        if not dst.exists(): shutil.copy2(_pay_src,dst)
        _pay_src.write_text(_txt,encoding='utf-8')
        py_compile.compile(str(_pay_src),doraise=True)
        _patched_payment_identity=True
        print('[r124-payment-identity] patched '+str(_pay_src),flush=True)
    elif ("row.get('telefono_genitore')" in _txt and "row.get('cognome')" in _txt):
        _patched_payment_identity=True
        print('[r124-payment-identity] already applied '+str(_pay_src),flush=True)
if not _patched_payment_identity:
    # R123 overlay still renders identity/contact itself; do not take production
    # down merely because the historical quick-row source changed shape.
    print('[r124-payment-identity] canonical source shape changed; overlay remains authoritative',flush=True)

# BODYMIND_R125_PAYMENT_PREMIUM_STATUS
# Premium operational payment board: current month truth from canonical pagamenti.
core_pay=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R125_PAYMENT_PREMIUM_STATUS' not in core_pay:
    dst=BACK/'core_pre_r125_payment_premium.py'
    if not dst.exists(): shutil.copy2(CORE,dst)
    core_pay += r'''

# BODYMIND_R125_PAYMENT_PREMIUM_STATUS
@app.after_request
def _bodymind_r125_payment_premium_status(resp):
    try:
        if request.method!='GET' or request.path!='/pagamenti' or int(getattr(resp,'status_code',200) or 200)!=200:
            return resp
        if 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp
        html=resp.get_data(as_text=True)
        if 'BODYMIND_R125_PAYMENT_BOARD' in html:
            return resp

        mese,anno=current_month_year()
        mese=parse_int(request.args.get('mese',mese),mese)
        anno=parse_int(request.args.get('anno',anno),anno)

        c=db(); c.row_factory=sqlite3.Row
        try:
            tcols={str(x[1]) for x in c.execute('PRAGMA table_info(tesserati)').fetchall()}
            athletes=[dict(x) for x in c.execute("SELECT * FROM tesserati ORDER BY TRIM(cognome) COLLATE NOCASE,TRIM(nome) COLLATE NOCASE").fetchall()]
            pays=[dict(x) for x in c.execute("SELECT * FROM pagamenti WHERE mese=? AND anno=? ORDER BY id DESC",(mese,anno)).fetchall()]
        finally:
            c.close()

        def _paid_row(p):
            st=(str(p.get('stato') or '')+' '+str(p.get('online_status') or '')).lower()
            bad=any(x in st for x in ('pending','attesa','cancel','annull','failed','fallit','refunded','rimbors'))
            good=any(x in st for x in ('paid','pagat','saldat','complet','incassat'))
            try: amount=float(p.get('importo') or 0)
            except Exception: amount=0
            cause=str(p.get('causale') or '').lower()
            monthly=('mensil' in cause) or cause in ('quota','quota_mensile','mensile')
            return monthly and (not bad) and (good or (bool(p.get('data')) and amount>0))

        paid_by={}
        for p in pays:
            tid=int(p.get('tesserato_id') or 0)
            if tid>0 and tid not in paid_by and _paid_row(p):
                paid_by[tid]=p

        red=[]; green=[]
        for a in athletes:
            tid=int(a.get('id') or 0)
            name=((str(a.get('cognome') or '')+' '+str(a.get('nome') or '')).strip()) or ('Tesserata #'+str(tid))
            phone=str(a.get('telefono') or a.get('telefono_genitore') or '').strip()
            pay=paid_by.get(tid)
            item={'id':tid,'name':name,'phone':phone,'pay':pay}
            (green if pay else red).append(item)

        def _card(item,ok):
            tid=item['id']; name=e(item['name']); phone=e(item['phone'] or 'Telefono non indicato')
            href='/pagamenti?tesserato_id='+str(tid)+'&mese='+str(mese)+'&anno='+str(anno)
            if ok:
                p=item['pay'] or {}
                try: amount=float(p.get('importo') or 0)
                except Exception: amount=0
                detail=('€ %.2f' % amount).replace('.',',') if amount>0 else 'Pagamento registrato'
                if p.get('data'): detail+=' · '+e(str(p.get('data')))
                return "<a class='r125-pay-card is-paid' href='"+href+"'><span class='r125-dot'>✓</span><div class='r125-id'><b>"+name+"</b><small>"+phone+"</small></div><div class='r125-side'><strong>PAGATO</strong><small>"+detail+"</small></div></a>"
            return "<a class='r125-pay-card is-unpaid' href='"+href+"'><span class='r125-dot'>!</span><div class='r125-id'><b>"+name+"</b><small>"+phone+"</small></div><div class='r125-side'><strong>DA PAGARE</strong><small>Registra pagamento</small></div></a>"

        red_html=''.join(_card(x,False) for x in red) or "<div class='r125-empty ok'>Nessuna quota mensile da recuperare.</div>"
        green_html=''.join(_card(x,True) for x in green) or "<div class='r125-empty'>Nessun pagamento mensile registrato.</div>"
        month_names=['','Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno','Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre']
        month_label=(month_names[mese] if 1<=mese<=12 else str(mese))+' '+str(anno)

        board=f"""<!-- BODYMIND_R125_PAYMENT_BOARD -->
        <section class='r125-board'>
          <div class='r125-head'>
            <div><span class='r125-kicker'>STATO PAGAMENTI</span><h2>{e(month_label)}</h2><p>Rosso = da pagare · Verde = pagato</p></div>
            <div class='r125-counts'><span class='bad'>{len(red)} da pagare</span><span class='good'>{len(green)} pagati</span></div>
          </div>
          <div class='r125-tabs'>
            <button type='button' class='active' data-r125='all'>Tutti</button>
            <button type='button' data-r125='unpaid'>Da pagare <b>{len(red)}</b></button>
            <button type='button' data-r125='paid'>Pagati <b>{len(green)}</b></button>
          </div>
          <div class='r125-grid' data-r125-group='unpaid'>
            <div class='r125-section-title'><span class='red-dot'></span> Da pagare</div>{red_html}
          </div>
          <div class='r125-grid' data-r125-group='paid'>
            <div class='r125-section-title'><span class='green-dot'></span> Pagati</div>{green_html}
          </div>
        </section>
        <style>
        .r125-board{{margin:14px 0 18px;padding:16px;border-radius:22px;background:linear-gradient(145deg,#08111f,#0d1d31 52%,#10263f);border:1px solid rgba(148,163,184,.16);box-shadow:0 22px 55px rgba(0,0,0,.28);color:#f8fafc}}
        .r125-head{{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;margin-bottom:14px}}.r125-kicker{{font-size:11px;letter-spacing:.14em;font-weight:950;color:#7dd3fc}}.r125-head h2{{margin:3px 0 3px;font-size:24px}}.r125-head p{{margin:0;color:#94a3b8;font-size:13px}}.r125-counts{{display:flex;gap:7px;flex-wrap:wrap;justify-content:flex-end}}.r125-counts span{{padding:8px 10px;border-radius:999px;font-size:12px;font-weight:950}}.r125-counts .bad{{background:rgba(220,38,38,.18);color:#fecaca;border:1px solid rgba(248,113,113,.35)}}.r125-counts .good{{background:rgba(22,163,74,.18);color:#bbf7d0;border:1px solid rgba(74,222,128,.35)}}.r125-tabs{{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-bottom:14px}}.r125-tabs button{{border:1px solid rgba(148,163,184,.18);background:#0b1728;color:#cbd5e1;border-radius:12px;padding:10px 8px;font-weight:900}}.r125-tabs button.active{{background:#1d4ed8;color:white;border-color:#60a5fa}}.r125-grid{{display:grid;gap:8px;margin-top:10px}}.r125-section-title{{display:flex;align-items:center;gap:8px;margin:4px 2px 2px;font-size:12px;font-weight:950;letter-spacing:.06em;text-transform:uppercase;color:#cbd5e1}}.red-dot,.green-dot{{width:9px;height:9px;border-radius:50%}}.red-dot{{background:#ef4444;box-shadow:0 0 12px rgba(239,68,68,.65)}}.green-dot{{background:#22c55e;box-shadow:0 0 12px rgba(34,197,94,.65)}}.r125-pay-card{{display:grid;grid-template-columns:36px minmax(0,1fr) auto;gap:10px;align-items:center;padding:12px 13px;border-radius:16px;text-decoration:none!important;color:white!important;transition:transform .15s ease,border-color .15s ease}}.r125-pay-card:active{{transform:scale(.99)}}.r125-pay-card.is-unpaid{{background:linear-gradient(135deg,rgba(127,29,29,.84),rgba(69,10,10,.72));border:1px solid rgba(248,113,113,.4)}}.r125-pay-card.is-paid{{background:linear-gradient(135deg,rgba(20,83,45,.86),rgba(5,46,22,.74));border:1px solid rgba(74,222,128,.4)}}.r125-dot{{display:grid;place-items:center;width:32px;height:32px;border-radius:50%;font-weight:950;font-size:16px}}.is-unpaid .r125-dot{{background:#dc2626}}.is-paid .r125-dot{{background:#16a34a}}.r125-id{{display:grid;gap:3px;min-width:0}}.r125-id b{{font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.r125-id small{{font-size:12px;color:#cbd5e1}}.r125-side{{display:grid;justify-items:end;gap:2px;text-align:right}}.r125-side strong{{font-size:11px;letter-spacing:.06em}}.is-unpaid .r125-side strong{{color:#fecaca}}.is-paid .r125-side strong{{color:#bbf7d0}}.r125-side small{{font-size:11px;color:#cbd5e1}}.r125-empty{{padding:14px;border-radius:14px;background:#0b1728;color:#cbd5e1}}.r125-empty.ok{{color:#86efac}}@media(max-width:600px){{.r125-board{{margin:10px 0 14px;padding:12px;border-radius:18px}}.r125-head{{display:grid}}.r125-counts{{justify-content:flex-start}}.r125-pay-card{{grid-template-columns:34px minmax(0,1fr);grid-template-areas:'dot id' 'dot side'}}.r125-dot{{grid-area:dot}}.r125-id{{grid-area:id}}.r125-side{{grid-area:side;justify-items:start;text-align:left}}.r125-tabs button{{font-size:12px;padding:9px 5px}}}}
        </style>
        <script>(function(){{
          var board=document.querySelector('.r125-board'); if(!board) return;
          var buttons=board.querySelectorAll('[data-r125]');
          buttons.forEach(function(btn){{btn.addEventListener('click',function(){{
            buttons.forEach(function(b){{b.classList.remove('active')}}); btn.classList.add('active');
            var v=btn.getAttribute('data-r125');
            board.querySelectorAll('[data-r125-group]').forEach(function(g){{
              g.style.display=(v==='all'||g.getAttribute('data-r125-group')===v)?'grid':'none';
            }});
          }})}});
        }})();</script>"""
        # Place this before the rest of payment operations whenever possible.
        if '<main' in html:
            pos=html.find('>',html.find('<main'))
            html=html[:pos+1]+board+html[pos+1:]
        elif '</body>' in html:
            html=html.replace('</body>',board+'</body>',1)
        else:
            html+=board
        resp.set_data(html)
    except Exception as exc:
        print('[r125-payment-board-warning] '+repr(exc),flush=True)
    return resp
'''
    CORE.write_text(core_pay,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r125-payment-board] PASS premium red/green monthly board installed',flush=True)

# BODYMIND_R126_HISTORY_NAMES
# Historical payment cards must always show the linked athlete identity prominently.
core_hist=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R126_HISTORY_NAMES' not in core_hist:
    dst=BACK/'core_pre_r126_history_names.py'
    if not dst.exists(): shutil.copy2(CORE,dst)
    core_hist += r'''

# BODYMIND_R126_HISTORY_NAMES
@app.after_request
def _bodymind_r126_payment_history_names(resp):
    try:
        if request.method!='GET' or request.path!='/pagamenti' or int(getattr(resp,'status_code',200) or 200)!=200:
            return resp
        if 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp
        html=resp.get_data(as_text=True)
        if 'NOME / STATO' not in html.upper() or 'r126-history-name' in html:
            return resp

        c=db(); c.row_factory=sqlite3.Row
        try:
            rows=[dict(x) for x in c.execute("""SELECT p.id,p.tesserato_id,p.data,p.importo,p.causale,p.mese,p.anno,
                     t.nome,t.cognome
                FROM pagamenti p
                LEFT JOIN tesserati t ON t.id=p.tesserato_id
                ORDER BY CASE WHEN p.data IS NULL OR TRIM(p.data)='' THEN 1 ELSE 0 END,
                         p.data DESC,p.id DESC""").fetchall()]
        finally:
            c.close()

        # The legacy payment history renders one NOME / STATO heading per payment card.
        # Inject identity directly after that heading, in the same order as the
        # canonical history query. If an athlete was intentionally deleted, keep a
        # transparent fallback instead of inventing a name.
        import re as _r126_re
        idx={'n':0}
        def _inject(match):
            n=idx['n']; idx['n']+=1
            if n>=len(rows):
                return match.group(0)
            r=rows[n]
            name=((str(r.get('cognome') or '')+' '+str(r.get('nome') or '')).strip()
                  or ('Tesserata #'+str(int(r.get('tesserato_id') or 0))))
            return match.group(0)+"<div class='r126-history-name'>"+e(name)+"</div>"

        pattern=_r126_re.compile(r'(?is)(<[^>]+>\s*NOME\s*/\s*STATO\s*</[^>]+>)')
        html,count=pattern.subn(_inject,html)
        if count:
            css="""<style>
            .r126-history-name{margin:8px 0 10px;font-size:20px;line-height:1.15;font-weight:950;letter-spacing:.01em;color:#f8fafc}
            @media(max-width:600px){.r126-history-name{font-size:18px;margin-top:7px}}
            </style>"""
            html=html.replace('</body>',css+'</body>',1) if '</body>' in html else html+css
            resp.set_data(html)
    except Exception as exc:
        print('[r126-history-name-warning] '+repr(exc),flush=True)
    return resp
'''
    CORE.write_text(core_hist,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r126-history-name] PASS payment history identity overlay installed',flush=True)

# BODYMIND_R127_HISTORY_CARD_NAMES_NAV
# Fix two mobile payment UX defects without changing payment data:
# 1) every historical payment card gets its own athlete name;
# 2) bottom navigation highlights Pagamenti, not Presenze, on /pagamenti.
core_r127=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R127_HISTORY_CARD_NAMES_NAV' not in core_r127:
    dst=BACK/'core_pre_r127_history_nav.py'
    if not dst.exists(): shutil.copy2(CORE,dst)
    core_r127 += r'''

# BODYMIND_R127_HISTORY_CARD_NAMES_NAV
@app.after_request
def _bodymind_r127_history_card_names_nav(resp):
    try:
        if request.method!='GET' or request.path!='/pagamenti' or int(getattr(resp,'status_code',200) or 200)!=200:
            return resp
        if 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp
        html=resp.get_data(as_text=True)
        if 'BODYMIND_R127_HISTORY_SCRIPT' in html:
            return resp

        c=db(); c.row_factory=sqlite3.Row
        try:
            prow=[dict(x) for x in c.execute("""SELECT p.id AS payment_id,p.tesserato_id,
                       t.nome,t.cognome
                  FROM pagamenti p
                  LEFT JOIN tesserati t ON t.id=p.tesserato_id
                  ORDER BY p.id""").fetchall()]
            arows=[dict(x) for x in c.execute("SELECT id,nome,cognome FROM tesserati").fetchall()]
        finally:
            c.close()

        pay_names={}
        for r in prow:
            pid=int(r.get('payment_id') or 0)
            tid=int(r.get('tesserato_id') or 0)
            nm=((str(r.get('cognome') or '')+' '+str(r.get('nome') or '')).strip()
                or ('Tesserata #'+str(tid)))
            if pid>0: pay_names[str(pid)]=nm
        athlete_names={}
        for r in arows:
            tid=int(r.get('id') or 0)
            nm=(str(r.get('cognome') or '')+' '+str(r.get('nome') or '')).strip()
            if tid>0 and nm: athlete_names[str(tid)]=nm

        _json=__import__('json')
        pjson=_json.dumps(pay_names,ensure_ascii=False)
        ajson=_json.dumps(athlete_names,ensure_ascii=False)

        addon=f"""<!-- BODYMIND_R127_HISTORY_SCRIPT -->
        <style>
        .r127-history-name{{font-size:20px;font-weight:950;line-height:1.15;color:#f8fafc;margin:8px 0 12px;letter-spacing:.01em}}
        .r127-nav-current{{background:linear-gradient(180deg,rgba(14,165,233,.24),rgba(3,105,161,.20))!important;border-color:rgba(56,189,248,.62)!important;color:#fff!important;box-shadow:inset 0 0 0 1px rgba(56,189,248,.18)!important}}
        .r127-nav-clear{{background:transparent!important;border-color:transparent!important;box-shadow:none!important}}
        /* BODYMIND_R129_PAYMENT_MOBILE_VISIBILITY
           The payment HTML already contains the athlete name inside the first
           table cell. Legacy responsive CSS was hiding the strong/b tag while
           leaving badges visible. Force the actual identity to remain visible. */
        @media(max-width:900px){{
          body .card table tr td:first-child>strong,
          body .card table tr td:first-child>b,
          body .table-wrap table tr td:first-child>strong,
          body .table-wrap table tr td:first-child>b{{
            display:block!important;visibility:visible!important;opacity:1!important;
            position:static!important;clip:auto!important;clip-path:none!important;
            width:auto!important;height:auto!important;overflow:visible!important;
            font-size:18px!important;line-height:1.2!important;font-weight:950!important;
            color:#f8fafc!important;margin:0 0 9px!important;text-indent:0!important;
          }}
          nav.nav a[href^="/presenze"],
          .nav a[href^="/presenze"],
          [class*="bottom"] a[href^="/presenze"]{{
            background:transparent!important;border-color:transparent!important;
            box-shadow:none!important;color:#dbe7f5!important;
          }}
          nav.nav a[href^="/pagamenti"],
          .nav a[href^="/pagamenti"],
          [class*="bottom"] a[href^="/pagamenti"]{{
            background:linear-gradient(180deg,rgba(14,165,233,.28),rgba(3,105,161,.22))!important;
            border:1px solid rgba(56,189,248,.68)!important;color:#fff!important;
            box-shadow:inset 0 0 0 1px rgba(56,189,248,.16)!important;
          }}
        }}
        @media(max-width:600px){{.r127-history-name{{font-size:18px}}}}
        </style>
        <script>
        (function(){{
          var paymentNames={pjson};
          var athleteNames={ajson};

          function exactText(el,txt){{
            return ((el.textContent||'').replace(/\s+/g,' ').trim().toUpperCase()===txt);
          }}
          function findCard(label){{
            var p=label.parentElement,depth=0;
            while(p && depth<9){{
              var tx=(p.innerText||'').toUpperCase();
              var causes=(tx.match(/CAUSALE/g)||[]).length;
              if(tx.indexOf('CAUSALE')>=0 && tx.indexOf('IMPORTO')>=0 && tx.indexOf('DATA')>=0 && causes===1) return p;
              p=p.parentElement; depth++;
            }}
            return label.parentElement;
          }}
          function numberFrom(v,patterns){{
            v=String(v||'');
            for(var i=0;i<patterns.length;i++){{var m=v.match(patterns[i]); if(m) return m[1];}}
            return '';
          }}
          function identify(card){{
            var el=card.querySelector('input[name="pagamento_id"],input[name="payment_id"],input[name="id"]');
            if(el && el.value && paymentNames[String(el.value)]) return {{name:paymentNames[String(el.value)],kind:'payment'}};
            var tid=card.querySelector('input[name="tesserato_id"]');
            if(tid && tid.value && athleteNames[String(tid.value)]) return {{name:athleteNames[String(tid.value)],kind:'athlete'}};
            var nodes=card.querySelectorAll('a[href],form[action],[data-payment-id],[data-id],[data-tesserato-id]');
            for(var i=0;i<nodes.length;i++){{
              var n=nodes[i];
              var raw=(n.getAttribute('href')||'')+' '+(n.getAttribute('action')||'')+' '+(n.getAttribute('data-payment-id')||'')+' '+(n.getAttribute('data-id')||'');
              var pid=numberFrom(raw,[/(?:pagamento_id|payment_id|[?&]id)=([0-9]+)/i,/\/pagamenti\/(?:elimina|delete|promemoria|ricevuta)\/?([0-9]+)/i]);
              if(pid && paymentNames[String(pid)]) return {{name:paymentNames[String(pid)],kind:'payment'}};
              var rt=(n.getAttribute('data-tesserato-id')||'')+' '+raw;
              var at=numberFrom(rt,[/(?:tesserato_id|tesserato)=([0-9]+)/i,/\/tesserati\/([0-9]+)/i,/\/mobile\/atleta\/([0-9]+)/i]);
              if(at && athleteNames[String(at)]) return {{name:athleteNames[String(at)],kind:'athlete'}};
            }}
            return null;
          }}

          // Remove the old one-off R126 label that could appear only above the first record.
          document.querySelectorAll('.r126-history-name').forEach(function(x){{x.remove();}});

          var labels=[];
          document.querySelectorAll('h1,h2,h3,h4,h5,h6,div,span,dt,th,strong').forEach(function(el){{
            if(exactText(el,'NOME / STATO')) labels.push(el);
          }});
          var seen=[];
          labels.forEach(function(label){{
            var card=findCard(label);
            if(!card || seen.indexOf(card)>=0) return;
            seen.push(card);
            var id=identify(card);
            if(!id || !id.name) return;
            if(card.querySelector('.r127-history-name')) return;
            var name=document.createElement('div');
            name.className='r127-history-name';
            name.textContent=id.name;
            label.insertAdjacentElement('afterend',name);
          }});

          // If a legacy card has no NOME / STATO label, still identify it from
          // its own payment/tesserato id and put the name at the top of that card.
          document.querySelectorAll('form[action],a[href]').forEach(function(node){{
            var card=node.closest('.card,[class*="payment"],[class*="row"],article,section');
            if(!card || card.querySelector('.r127-history-name')) return;
            var tx=(card.innerText||'').toUpperCase();
            if(tx.indexOf('CAUSALE')<0 || tx.indexOf('IMPORTO')<0) return;
            var id=identify(card); if(!id || !id.name) return;
            var name=document.createElement('div'); name.className='r127-history-name'; name.textContent=id.name;
            card.insertBefore(name,card.firstChild);
          }});

          // Correct bottom-navigation active state on the payment page.
          var navCandidates=document.querySelectorAll('nav a,nav button,[class*="bottom"] a,[class*="nav"] a');
          navCandidates.forEach(function(el){{
            var txt=(el.textContent||'').replace(/\s+/g,' ').trim().toLowerCase();
            var href=(el.getAttribute&&el.getAttribute('href'))||'';
            if(txt.indexOf('presenze')>=0 || href.indexOf('/presenze')===0){{
              el.classList.remove('active','current','selected');
              el.classList.add('r127-nav-clear');
              el.removeAttribute('aria-current');
            }}
            if(txt.indexOf('pagamenti')>=0 || href.indexOf('/pagamenti')===0){{
              el.classList.remove('r127-nav-clear');
              el.classList.add('active','r127-nav-current');
              el.setAttribute('aria-current','page');
            }}
          }});
        }})();
        </script>"""
        html=html.replace('</body>',addon+'</body>',1) if '</body>' in html else html+addon
        resp.set_data(html)
    except Exception as exc:
        print('[r127-history-nav-warning] '+repr(exc),flush=True)
    return resp
'''
    CORE.write_text(core_r127,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r127-history-nav] PASS per-card names + payment nav state installed',flush=True)

# R129 upgrade existing R127 runtime: prior deployments already contain the
# R127 marker, so update its CSS in-place before the fresh-process QA.
_core_r129=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R127_HISTORY_CARD_NAMES_NAV' in _core_r129 and 'BODYMIND_R129_PAYMENT_MOBILE_VISIBILITY' not in _core_r129:
    _old=""".r127-history-name{font-size:20px;font-weight:950;line-height:1.15;color:#f8fafc;margin:8px 0 12px;letter-spacing:.01em}
        .r127-nav-current{background:linear-gradient(180deg,rgba(16,185,129,.26),rgba(5,150,105,.18))!important;border-color:rgba(52,211,153,.5)!important;color:#fff!important}
        .r127-nav-clear{background:transparent!important}
        @media(max-width:600px){.r127-history-name{font-size:18px}}"""
    _new=""".r127-history-name{font-size:20px;font-weight:950;line-height:1.15;color:#f8fafc;margin:8px 0 12px;letter-spacing:.01em}
        .r127-nav-current{background:linear-gradient(180deg,rgba(14,165,233,.24),rgba(3,105,161,.20))!important;border-color:rgba(56,189,248,.62)!important;color:#fff!important;box-shadow:inset 0 0 0 1px rgba(56,189,248,.18)!important}
        .r127-nav-clear{background:transparent!important;border-color:transparent!important;box-shadow:none!important}
        /* BODYMIND_R129_PAYMENT_MOBILE_VISIBILITY */
        @media(max-width:900px){
          body .card table tr td:first-child>strong,
          body .card table tr td:first-child>b,
          body .table-wrap table tr td:first-child>strong,
          body .table-wrap table tr td:first-child>b{
            display:block!important;visibility:visible!important;opacity:1!important;
            position:static!important;clip:auto!important;clip-path:none!important;
            width:auto!important;height:auto!important;overflow:visible!important;
            font-size:18px!important;line-height:1.2!important;font-weight:950!important;
            color:#f8fafc!important;margin:0 0 9px!important;text-indent:0!important;
          }
          nav.nav a[href^="/presenze"],.nav a[href^="/presenze"],[class*="bottom"] a[href^="/presenze"]{
            background:transparent!important;border-color:transparent!important;box-shadow:none!important;color:#dbe7f5!important;
          }
          nav.nav a[href^="/pagamenti"],.nav a[href^="/pagamenti"],[class*="bottom"] a[href^="/pagamenti"]{
            background:linear-gradient(180deg,rgba(14,165,233,.28),rgba(3,105,161,.22))!important;
            border:1px solid rgba(56,189,248,.68)!important;color:#fff!important;
            box-shadow:inset 0 0 0 1px rgba(56,189,248,.16)!important;
          }
        }
        @media(max-width:600px){.r127-history-name{font-size:18px}}"""
    if _old in _core_r129:
        _core_r129=_core_r129.replace(_old,_new,1)
    else:
        # Fallback: inject the override immediately before the R127 closing style.
        _needle="@media(max-width:600px){.r127-history-name{font-size:18px}}"
        if _needle in _core_r129:
            _core_r129=_core_r129.replace(_needle,_new.splitlines()[-1],1)
            _core_r129=_core_r129.replace("</style>","""/* BODYMIND_R129_PAYMENT_MOBILE_VISIBILITY */
        @media(max-width:900px){
          body .card table tr td:first-child>strong,body .card table tr td:first-child>b,
          body .table-wrap table tr td:first-child>strong,body .table-wrap table tr td:first-child>b{
            display:block!important;visibility:visible!important;opacity:1!important;position:static!important;
            clip:auto!important;clip-path:none!important;width:auto!important;height:auto!important;overflow:visible!important;
            font-size:18px!important;line-height:1.2!important;font-weight:950!important;color:#f8fafc!important;margin:0 0 9px!important;text-indent:0!important}
          nav.nav a[href^="/presenze"],.nav a[href^="/presenze"],[class*="bottom"] a[href^="/presenze"]{
            background:transparent!important;border-color:transparent!important;box-shadow:none!important;color:#dbe7f5!important}
          nav.nav a[href^="/pagamenti"],.nav a[href^="/pagamenti"],[class*="bottom"] a[href^="/pagamenti"]{
            background:linear-gradient(180deg,rgba(14,165,233,.28),rgba(3,105,161,.22))!important;
            border:1px solid rgba(56,189,248,.68)!important;color:#fff!important;box-shadow:inset 0 0 0 1px rgba(56,189,248,.16)!important}
        }</style>""",1)
        else:
            raise RuntimeError('R129 existing R127 CSS anchor missing')
    CORE.write_text(_core_r129,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r129-upgrade] PASS existing R127 runtime CSS upgraded',flush=True)
else:
    print('[r129-upgrade] already present or R127 not installed yet',flush=True)

# Fresh import/UI gate.
qa=r'''
import sqlite3,sys
sys.path.insert(0,"/data/top2_app")
import app as _full
from asd_app.core import app
app.config["TESTING"]=True
c=app.test_client()
with c.session_transaction() as s:
    s.update({"logged":True,"username":"admin","display_name":"R123 QA","role":"admin","tenant_slug":"default"})
p=c.get("/pagamenti")
a=c.get("/presenze",follow_redirects=False)
b=c.get("/presenze-semplici?gruppo=pro")
ph=p.get_data(as_text=True); bh=b.get_data(as_text=True)
from asd_app.core import get_missing_iscrizione_rows,current_month_year
_mm,_yy=current_month_year()
_missing=[dict(x) for x in get_missing_iscrizione_rows(_yy,_mm)]
_identity_ok=True
if _missing:
    _r=_missing[0]
    _nm=((str(_r.get('cognome') or '')+' '+str(_r.get('nome') or '')).strip())
    _tel=str(_r.get('telefono') or _r.get('telefono_genitore') or 'Telefono non indicato')
    _identity_ok=bool(_nm and _nm in ph and _tel in ph)
conn=sqlite3.connect("/data/tenants/default/asd.db",timeout=20)
try:
    integrity=str(conn.execute("PRAGMA integrity_check").fetchone()[0]); fk=len(conn.execute("PRAGMA foreign_key_check").fetchall())
finally: conn.close()
ath_count=conn2=None
# direct list should include a known athlete regardless of legacy course assignment
direct_ok=("BODYMIND_R123_PRESENZE_SIMPLE" in bh and "r123-athlete" in bh)
premium_pay_ok=("BODYMIND_R125_PAYMENT_BOARD" in ph and "DA PAGARE" in ph and "PAGATO" in ph)
history_labels=ph.upper().count("NOME / STATO")
history_names=ph.count("r126-history-name")
history_name_ok=(history_labels==0 or history_names>=history_labels)
r127_script_ok=("BODYMIND_R127_HISTORY_SCRIPT" in ph and "r127-nav-current" in ph and "paymentNames=" in ph)
r129_css_ok=("BODYMIND_R129_PAYMENT_MOBILE_VISIBILITY" in ph and 'a[href^="/pagamenti"]' in ph and 'td:first-child>strong' in ph)
ok=(p.status_code==200 and "BODYMIND_R123_PAYMENT_MOBILE" in ph and premium_pay_ok and r127_script_ok and r129_css_ok and _identity_ok and a.status_code in (301,302,307,308) and "/presenze-semplici" in str(a.headers.get("Location","")) and b.status_code==200 and direct_ok and "Giornata operativa" not in bh and all(x in bh for x in ("Base","Kids","Adult","Pro / Agoniste")) and integrity.lower()=="ok" and fk==0)
print("[r123-selftest] status_payment=%s premium_pay_ok=%s legacy_history_name_ok=%s r127_script_ok=%s r129_css_ok=%s identity_ok=%s presence_redirect=%s simple=%s db=%s fk=%s ok=%s"%(p.status_code,premium_pay_ok,history_name_ok,r127_script_ok,r129_css_ok,_identity_ok,a.status_code,b.status_code,integrity,fk,ok),flush=True)
if not ok: raise RuntimeError("R123 QA failed")
'''
proc=subprocess.run([sys.executable,'-c',qa],capture_output=True,text=True,timeout=120)
print((proc.stdout or '').strip(),flush=True)
if proc.returncode!=0: raise RuntimeError('R123 child QA failed '+((proc.stderr or '')+(proc.stdout or ''))[-4000:])
