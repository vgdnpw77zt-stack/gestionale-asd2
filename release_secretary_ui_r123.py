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
if False and 'BODYMIND_R127_HISTORY_CARD_NAMES_NAV' in _core_r129 and 'BODYMIND_R129_PAYMENT_MOBILE_VISIBILITY' not in _core_r129:
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

# BODYMIND_R130_PAYMENT_MOBILE_HARD_FIX
# Independent hard fix: do not depend on any prior R126/R127 markup migration.
core_r130=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R130_PAYMENT_MOBILE_HARD_FIX' not in core_r130:
    core_r130 += r'''

# BODYMIND_R130_PAYMENT_MOBILE_HARD_FIX
@app.after_request
def _bodymind_r130_payment_mobile_hard_fix(resp):
    try:
        if request.method!='GET' or request.path!='/pagamenti' or int(getattr(resp,'status_code',200) or 200)!=200:
            return resp
        if 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp
        html=resp.get_data(as_text=True)
        css="""<style id='bodymind-r130-payment-fix'>
        @media(max-width:900px){
          /* Historical payments already contain the athlete identity in the first
             td. Legacy responsive CSS hid only the strong/b name and left badges. */
          .card table tr td:first-child>strong,
          .card table tr td:first-child>b,
          .table-wrap table tr td:first-child>strong,
          .table-wrap table tr td:first-child>b{
            display:block!important;
            visibility:visible!important;
            opacity:1!important;
            position:static!important;
            transform:none!important;
            clip:auto!important;
            clip-path:none!important;
            width:auto!important;
            max-width:none!important;
            height:auto!important;
            max-height:none!important;
            overflow:visible!important;
            white-space:normal!important;
            font-size:18px!important;
            line-height:1.2!important;
            font-weight:950!important;
            color:#f8fafc!important;
            margin:0 0 9px!important;
            text-indent:0!important;
          }

          /* On /pagamenti the bottom navigation must visually select Pagamenti,
             never Presenze. These selectors override older page/theme rules. */
          nav.nav a[href^="/presenze"],
          .nav a[href^="/presenze"],
          [class*="bottom"] a[href^="/presenze"]{
            background:transparent!important;
            background-image:none!important;
            border-color:transparent!important;
            box-shadow:none!important;
            color:#dbe7f5!important;
          }
          nav.nav a[href^="/pagamenti"],
          .nav a[href^="/pagamenti"],
          [class*="bottom"] a[href^="/pagamenti"]{
            background:linear-gradient(180deg,rgba(14,165,233,.30),rgba(3,105,161,.24))!important;
            border:1px solid rgba(56,189,248,.70)!important;
            box-shadow:inset 0 0 0 1px rgba(56,189,248,.18)!important;
            color:#fff!important;
          }
        }</style>"""
        if "id='bodymind-r130-payment-fix'" not in html:
            html=html.replace('</head>',css+'</head>',1) if '</head>' in html else css+html
        resp.set_data(html)
    except Exception as exc:
        print('[r130-payment-fix-warning] '+repr(exc),flush=True)
    return resp
'''
    CORE.write_text(core_r130,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r130-payment-fix] PASS mobile historical names/nav hard fix installed',flush=True)
else:
    print('[r130-payment-fix] already present',flush=True)

# BODYMIND_R131_HISTORY_NAME_VISIBLE_DIV
# The history table already contains the correct name in <strong>, but the
# legacy mobile table CSS hides that element. Duplicate the text into a plain
# div inside EACH history row server-side, so mobile cannot lose the identity.
core_r131=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R131_HISTORY_NAME_VISIBLE_DIV' not in core_r131:
    core_r131 += r'''

# BODYMIND_R131_HISTORY_NAME_VISIBLE_DIV
@app.after_request
def _bodymind_r131_history_name_visible_div(resp):
    try:
        if request.method!='GET' or request.path!='/pagamenti' or int(getattr(resp,'status_code',200) or 200)!=200:
            return resp
        if 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp
        html=resp.get_data(as_text=True)
        if 'Elenco pagamenti' not in html:
            return resp

        import re as _r131_re
        head,sep,tail=html.partition('Elenco pagamenti')
        # Only touch the historical payments area. Each row already has the
        # authoritative athlete name as the first-cell <strong> value.
        pat=_r131_re.compile(r"(?is)(<tr[^>]*class=['\"][^'\"]*table-row-ok[^'\"]*['\"][^>]*>\s*<td>\s*)(<strong>(.*?)</strong>)")
        def _add_name(m):
            raw=m.group(3)
            plain=_r131_re.sub(r'<[^>]+>','',raw).strip()
            if not plain:
                return m.group(0)
            return m.group(1)+"<div class='r131-history-name'>"+raw+"</div>"+m.group(2)
        tail,count=pat.subn(_add_name,tail)
        html=head+sep+tail
        if count:
            css="""<style id='bodymind-r131-history-name'>
            .r131-history-name{
              display:block!important;visibility:visible!important;opacity:1!important;
              position:static!important;clip:auto!important;clip-path:none!important;
              width:auto!important;height:auto!important;overflow:visible!important;
              color:#f8fafc!important;font-size:20px!important;line-height:1.15!important;
              font-weight:950!important;letter-spacing:.01em!important;margin:8px 0 12px!important;
              text-transform:uppercase!important;
            }
            @media(max-width:600px){.r131-history-name{font-size:18px!important}}
            </style>"""
            html=html.replace('</head>',css+'</head>',1) if '</head>' in html else css+html
        resp.set_data(html)
    except Exception as exc:
        print('[r131-history-name-warning] '+repr(exc),flush=True)
    return resp
'''
    CORE.write_text(core_r131,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r131-history-name] PASS server-side visible name div installed',flush=True)
else:
    print('[r131-history-name] already present',flush=True)

# BODYMIND_R133_PRESENCE_TABS_FIX
# Safari-safe course-group switching with a distinct register for each group.
core_r133=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R133_PRESENCE_TABS_FIX' not in core_r133:
    conn=sqlite3.connect(str(DB),timeout=30); conn.row_factory=sqlite3.Row
    try:
        courses=conn.execute("SELECT id,nome FROM corsi ORDER BY id").fetchall()
        def _grp(v):
            z=' '.join(str(v or '').strip().lower().replace('_',' ').split())
            if any(x in z for x in ('pro','agon','elite','advanced')): return 'pro'
            if any(x in z for x in ('kid','baby','bambin','junior')): return 'kids'
            if any(x in z for x in ('adult','adulti')): return 'adult'
            if 'base' in z: return 'base'
            return ''
        if not any(_grp(r['nome'])=='base' for r in courses):
            bdir=BACK/'r133_pre_base_course.db'
            if not bdir.exists():
                srcdb=sqlite3.connect(str(DB),timeout=30); outdb=sqlite3.connect(str(bdir))
                try: srcdb.backup(outdb)
                finally: outdb.close(); srcdb.close()
            cols={str(x[1]) for x in conn.execute("PRAGMA table_info(corsi)").fetchall()}
            vals={'nome':'BASE','descrizione':'Registro presenze Base','orario':'','max_iscritti':0,'tenant_id':'default'}
            vals={k:v for k,v in vals.items() if k in cols}
            ks=list(vals)
            conn.execute("INSERT INTO corsi("+','.join(ks)+") VALUES("+','.join('?' for _ in ks)+")",[vals[k] for k in ks])
            conn.commit()
            print('[r133-presence] created BASE course',flush=True)
    finally:
        conn.close()

    old_tabs="""    tabs=''.join("<a class='r123-tab "+('active' if group==k else '')+"' href='/presenze-semplici?gruppo="+k+"&data="+e(day)+"'>"+label+"</a>" for k,label in [('base','Base'),('kids','Kids'),('adult','Adult'),('pro','Pro / Agoniste')])"""
    new_tabs="""    tabs=''.join("<form class='r123-tab-form' method='get' action='/presenze-semplici'><input type='hidden' name='data' value='"+e(day)+"'><button type='submit' name='gruppo' value='"+k+"' class='r123-tab "+('active' if group==k else '')+"' aria-pressed='"+('true' if group==k else 'false')+"'>"+label+"</button></form>" for k,label in [('base','Base'),('kids','Kids'),('adult','Adult'),('pro','Pro / Agoniste')])"""
    if old_tabs in core_r133:
        core_r133=core_r133.replace(old_tabs,new_tabs,1)
    elif "r123-tab-form" not in core_r133:
        raise RuntimeError('R133 tabs source anchor missing')

    old_nav="""      <nav class='r123-tabs'>{tabs}</nav>
      <form method='post' id='r123-presence-form'>"""
    new_nav="""      <nav class='r123-tabs'>{tabs}</nav>
      <div class='r133-selected'>Registro selezionato: <strong>{e(_r123_group_label(group))}</strong></div>
      <form method='post' id='r123-presence-form'>"""
    if old_nav in core_r133:
        core_r133=core_r133.replace(old_nav,new_nav,1)
    elif "r133-selected" not in core_r133:
        raise RuntimeError('R133 selected banner anchor missing')

    old_css=""".r123-tabs{{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin:10px 0}}.r123-tab{{padding:11px 6px;border-radius:12px;background:#12243a;color:#cbd5e1!important;text-decoration:none;text-align:center;font-weight:900;font-size:12px}}.r123-tab.active{{background:#2563eb;color:white!important}}"""
    new_css=""".r123-tabs{{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin:10px 0;position:relative;z-index:20;pointer-events:auto}}.r123-tab-form{{margin:0;padding:0;display:block;position:relative;z-index:21;pointer-events:auto}}.r123-tab{{appearance:none;-webkit-appearance:none;width:100%;min-height:48px;padding:11px 6px;border:1px solid rgba(148,163,184,.22);border-radius:12px;background:#12243a;color:#cbd5e1!important;text-align:center;font-weight:900;font-size:12px;position:relative;z-index:22;pointer-events:auto;touch-action:manipulation;cursor:pointer}}.r123-tab.active{{background:#2563eb!important;border-color:#60a5fa!important;color:white!important;box-shadow:0 0 0 2px rgba(96,165,250,.18)}}.r133-selected{{margin:8px 0 10px;padding:10px 12px;border-radius:12px;background:rgba(37,99,235,.14);border:1px solid rgba(96,165,250,.28);color:#dbeafe;font-size:13px}}.r133-selected strong{{color:#fff;font-size:15px}}"""
    if old_css in core_r133:
        core_r133=core_r133.replace(old_css,new_css,1)
    elif "touch-action:manipulation" not in core_r133:
        raise RuntimeError('R133 tabs css anchor missing')

    CORE.write_text(core_r133,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r133-presence] PASS native group buttons + selected banner + distinct base course',flush=True)
else:
    print('[r133-presence] already present',flush=True)

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
_group_pages={}
for _g in ("base","kids","adult","pro"):
    _rr=c.get("/presenze-semplici?gruppo="+_g)
    _tx=_rr.get_data(as_text=True)
    _group_pages[_g]=(_rr.status_code==200 and ("value='"+_g+"' class='r123-tab active'") in _tx and "r133-selected" in _tx)
group_switch_ok=all(_group_pages.values())
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
r129_css_ok=("bodymind-r130-payment-fix" in ph and 'a[href^="/pagamenti"]' in ph and 'td:first-child>strong' in ph)
r131_history_ok=("r131-history-name" in ph)
ok=(p.status_code==200 and group_switch_ok and "BODYMIND_R123_PAYMENT_MOBILE" in ph and premium_pay_ok and r127_script_ok and r129_css_ok and r131_history_ok and _identity_ok and a.status_code in (301,302,307,308) and "/presenze-semplici" in str(a.headers.get("Location","")) and b.status_code==200 and direct_ok and "Giornata operativa" not in bh and all(x in bh for x in ("Base","Kids","Adult","Pro / Agoniste")) and integrity.lower()=="ok" and fk==0)
print("[r123-selftest] group_switch_ok=%s groups=%s status_payment=%s premium_pay_ok=%s legacy_history_name_ok=%s r127_script_ok=%s r129_css_ok=%s r131_history_ok=%s identity_ok=%s presence_redirect=%s simple=%s db=%s fk=%s ok=%s"%(group_switch_ok,_group_pages,p.status_code,premium_pay_ok,history_name_ok,r127_script_ok,r129_css_ok,r131_history_ok,_identity_ok,a.status_code,b.status_code,integrity,fk,ok),flush=True)
if not ok: raise RuntimeError("R123 QA failed")
'''
proc=subprocess.run([sys.executable,'-c',qa],capture_output=True,text=True,timeout=120)
print((proc.stdout or '').strip(),flush=True)
if proc.returncode!=0: raise RuntimeError('R123 child QA failed '+((proc.stderr or '')+(proc.stdout or ''))[-4000:])


# BODYMIND_R123_PAYMENT_SPLIT_V2
# Replace duplicate payment dashboards with one split secretary surface.
_core_split=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R123_PAYMENT_SPLIT_V2' not in _core_split:
    _core_split += r'''

# BODYMIND_R123_PAYMENT_SPLIT_V2
@app.after_request
def _bodymind_r123_payment_split_v2(resp):
    try:
        if request.method!='GET' or request.path!='/pagamenti' or int(getattr(resp,'status_code',200) or 200)!=200:
            return resp
        if 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp
        html=resp.get_data(as_text=True)
        if 'BODYMIND_R123_PAYMENT_SPLIT_V2_SURFACE' in html:
            return resp

        from datetime import date as _d
        today=_d.today()
        mese=parse_int(request.args.get('mese',today.month),today.month)
        anno=parse_int(request.args.get('anno',today.year),today.year)
        if mese<1 or mese>12: mese=today.month
        if anno<2020 or anno>2100: anno=today.year
        vista=(request.args.get('vista') or 'iscrizioni').strip().lower()
        if vista not in ('iscrizioni','mensili','tutti'): vista='iscrizioni'
        season=anno if mese>=7 else anno-1

        c=db(); c.row_factory=sqlite3.Row
        try:
            tcols={str(x[1]) for x in c.execute('PRAGMA table_info(tesserati)').fetchall()}
            athletes=[dict(x) for x in c.execute("SELECT * FROM tesserati WHERE COALESCE(attivo,1)=1 ORDER BY TRIM(cognome) COLLATE NOCASE,TRIM(nome) COLLATE NOCASE").fetchall()]
            payments=[dict(x) for x in c.execute("SELECT * FROM pagamenti ORDER BY id DESC").fetchall()] if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pagamenti'").fetchone() else []
            quote_rows=[dict(x) for x in c.execute("SELECT * FROM quote_mensili WHERE mese=? AND anno=? ORDER BY id DESC",(mese,anno)).fetchall()] if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='quote_mensili'").fetchone() else []
        finally:
            try:c.close()
            except Exception:pass

        def _paid(p):
            st=(str(p.get('stato') or '')+' '+str(p.get('online_status') or '')).lower()
            if any(x in st for x in ('pending','attesa','cancel','annull','failed','fallit','refunded','rimbors')): return False
            if any(x in st for x in ('paid','pagat','saldat','complet','incassat')): return True
            try: amount=float(p.get('importo') or 0)
            except Exception: amount=0
            return bool(p.get('data') or p.get('paid_at')) and amount>0

        enroll_pay={}
        month_pay={}
        all_paid=[]
        for p in payments:
            if not _paid(p): continue
            tid=int(p.get('tesserato_id') or 0)
            cause=str(p.get('causale') or '').strip().lower()
            yr=int(p.get('anno') or 0)
            mm=int(p.get('mese') or 0)
            all_paid.append(p)
            if cause in ('iscrizione','tesseramento') and yr in (season,season+1) and tid not in enroll_pay:
                enroll_pay[tid]=p
            if (cause=='mensile' or 'mensil' in cause or cause in ('quota','quota_mensile')) and mm==mese and yr==anno and tid not in month_pay:
                month_pay[tid]=p

        quote_paid={}
        for q in quote_rows:
            tid=int(q.get('tesserato_id') or 0)
            st=str(q.get('stato') or '').lower()
            if tid and any(x in st for x in ('pagat','saldat','paid','incassat','complet')) and tid not in quote_paid:
                quote_paid[tid]=q

        def _name(a):
            return ((str(a.get('cognome') or '')+' '+str(a.get('nome') or '')).strip()) or ('Tesserata #'+str(int(a.get('id') or 0)))
        def _money(v):
            try:return ('€ %.2f' % float(v or 0)).replace('.',',')
            except Exception:return ''
        def _card(a,kind):
            tid=int(a.get('id') or 0); name=e(_name(a)); phone=e(str(a.get('telefono') or a.get('telefono_genitore') or ''))
            href='/pagamenti?tesserato_id='+str(tid)+'&mese='+str(mese)+'&anno='+str(anno)+'&vista='+kind
            if kind=='iscrizioni':
                p=enroll_pay.get(tid)
                legacy=bool(int(a.get('iscrizione_pagata') or 0) if 'iscrizione_pagata' in a else 0) or bool(int(a.get('tesseramento_pagato') or 0) if 'tesseramento_pagato' in a else 0)
                ok=bool(p or legacy)
                detail=(_money(p.get('importo'))+' · '+str(p.get('data') or '')).strip(' ·') if p else ('Già registrata' if legacy else 'Da registrare')
                badge='PAGATA' if ok else 'DA PAGARE'
            else:
                p=month_pay.get(tid); q=quote_paid.get(tid); ok=bool(p or q)
                detail=(_money(p.get('importo'))+' · '+str(p.get('data') or '')).strip(' ·') if p else ((_money(q.get('importo_dovuto'))+' · già registrato').strip(' ·') if q else 'Da registrare')
                badge='PAGATO' if ok else 'DA PAGARE'
            cls='paid' if ok else 'due'
            return "<a class='bmps-card "+cls+"' href='"+href+"'><div><b>"+name+"</b>"+("<small>"+phone+"</small>" if phone else "")+"</div><span><strong>"+badge+"</strong><small>"+e(detail)+"</small></span></a>"

        if vista=='iscrizioni':
            cards=''.join(_card(a,'iscrizioni') for a in athletes)
            paid_n=sum(1 for a in athletes if int(a.get('id') or 0) in enroll_pay or bool(int(a.get('iscrizione_pagata') or 0) if 'iscrizione_pagata' in a else 0) or bool(int(a.get('tesseramento_pagato') or 0) if 'tesseramento_pagato' in a else 0))
            title='Iscrizioni · stagione '+str(season)+'/'+str(season+1)
        elif vista=='mensili':
            cards=''.join(_card(a,'mensili') for a in athletes)
            paid_n=sum(1 for a in athletes if int(a.get('id') or 0) in month_pay or int(a.get('id') or 0) in quote_paid)
            names=['','Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno','Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre']
            title='Mensili · '+names[mese]+' '+str(anno)
        else:
            rows=[]
            byid={int(a.get('id') or 0):a for a in athletes}
            for p in all_paid:
                a=byid.get(int(p.get('tesserato_id') or 0),{})
                cause=str(p.get('causale') or 'pagamento').strip().title()
                rows.append("<div class='bmps-history'><b>"+e(_name(a))+"</b><span>"+e(cause)+"</span><strong>"+e(_money(p.get('importo')))+"</strong><small>"+e(str(p.get('data') or ''))+"</small></div>")
            cards=''.join(rows) or "<div class='bmps-empty'>Nessun incasso canonico registrato.</div>"
            paid_n=len(all_paid); title='Tutti gli incassi'

        total=len(athletes)
        query='&mese='+str(mese)+'&anno='+str(anno)
        surface=f"""<!-- BODYMIND_R123_PAYMENT_SPLIT_V2_SURFACE -->
        <section class='bmps'>
          <div class='bmps-head'><div><span>PAGAMENTI BODYMIND</span><h2>{e(title)}</h2></div><div class='bmps-count'>{paid_n}{(' / '+str(total)) if vista!='tutti' else ''}</div></div>
          <nav class='bmps-tabs'>
            <a class='{'active' if vista=='iscrizioni' else ''}' href='/pagamenti?vista=iscrizioni{query}'>Iscrizioni</a>
            <a class='{'active' if vista=='mensili' else ''}' href='/pagamenti?vista=mensili{query}'>Mensili</a>
            <a class='{'active' if vista=='tutti' else ''}' href='/pagamenti?vista=tutti{query}'>Tutti</a>
          </nav>
          <div class='bmps-list'>{cards}</div>
        </section>
        <style id='bodymind-payment-split-v2'>
        .r123-pay-box,.r125-board{{display:none!important}}
        .bmps{{margin:12px 0 18px;padding:14px;border-radius:20px;background:#091524;border:1px solid rgba(148,163,184,.18);color:#f8fafc}}
        .bmps-head{{display:flex;justify-content:space-between;align-items:center;gap:10px}}.bmps-head span{{font-size:10px;letter-spacing:.13em;font-weight:950;color:#7dd3fc}}.bmps-head h2{{margin:3px 0 0;font-size:22px}}.bmps-count{{font-size:22px;font-weight:950}}
        .bmps-tabs{{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin:13px 0}}.bmps-tabs a{{padding:11px 7px;border-radius:12px;background:#12243a;color:#cbd5e1!important;text-align:center;text-decoration:none;font-weight:900}}.bmps-tabs a.active{{background:#2563eb;color:white!important}}
        .bmps-list{{display:grid;gap:8px}}.bmps-card{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center;padding:12px 13px;border-radius:15px;text-decoration:none!important;color:white!important;border:1px solid transparent}}.bmps-card>div,.bmps-card>span{{display:grid;gap:3px}}.bmps-card>span{{justify-items:end;text-align:right}}.bmps-card small{{font-size:11px;color:#cbd5e1}}.bmps-card strong{{font-size:11px;letter-spacing:.05em}}.bmps-card.paid{{background:rgba(20,83,45,.78);border-color:rgba(74,222,128,.38)}}.bmps-card.due{{background:rgba(127,29,29,.72);border-color:rgba(248,113,113,.36)}}.bmps-history{{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:8px;align-items:center;padding:11px;border-radius:13px;background:#102238}}.bmps-history small{{grid-column:1/-1;color:#94a3b8}}.bmps-empty{{padding:14px;color:#cbd5e1}}
        @media(max-width:600px){{.bmps{{padding:11px}}.bmps-head h2{{font-size:19px}}.bmps-card{{grid-template-columns:1fr}}.bmps-card>span{{justify-items:start;text-align:left}}.bmps-history{{grid-template-columns:1fr auto}}}}
        </style>"""
        marker="BODYMIND_R123_PAYMENT_MOBILE"
        idx=html.find(marker)
        if idx>=0:
            pos=html.rfind('<section',0,idx)
            html=html[:pos]+surface+html[pos:] if pos>=0 else surface+html
        else:
            html=html.replace('<main','<main',1)
            bodypos=html.find('>')
            html=html[:bodypos+1]+surface+html[bodypos+1:] if bodypos>=0 else surface+html
        resp.set_data(html)
    except Exception as exc:
        print('[payment-split-v2-warning] '+repr(exc),flush=True)
    return resp
'''
    CORE.write_text(_core_split,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r123-payment-split-v2] PASS split Iscrizioni/Mensili/Tutti installed',flush=True)
else:
    print('[r123-payment-split-v2] already installed',flush=True)


# BODYMIND_R123_PAYMENT_SPLIT_V3
# Desktop-first payment semantics: enrollment is annual/seasonal; monthly is
# strictly one calendar month at a time. Existing rows are preserved.
_core_split_v3=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R123_PAYMENT_SPLIT_V3' not in _core_split_v3:
    _core_split_v3 += r'''

# BODYMIND_R123_PAYMENT_SPLIT_V3
@app.after_request
def _bodymind_r123_payment_split_v3(resp):
    try:
        if request.method!='GET' or request.path!='/pagamenti' or int(getattr(resp,'status_code',200) or 200)!=200:
            return resp
        if 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp
        html=resp.get_data(as_text=True)
        if 'BODYMIND_R123_PAYMENT_SPLIT_V3_SURFACE' in html:
            return resp

        from datetime import date as _d
        today=_d.today()
        mese=parse_int(request.args.get('mese',today.month),today.month)
        anno=parse_int(request.args.get('anno',today.year),today.year)
        if mese<1 or mese>12: mese=today.month
        if anno<2020 or anno>2100: anno=today.year
        vista=(request.args.get('vista') or 'iscrizioni').strip().lower()
        if vista not in ('iscrizioni','mensili','tutti'): vista='iscrizioni'
        season_start=parse_int(request.args.get('stagione',anno if mese>=7 else anno-1),anno if mese>=7 else anno-1)

        # Add a semantic header immediately before the V2 board, without
        # altering the canonical payment POST route.
        months=['','Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno','Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre']
        month_opts=''.join("<option value='"+str(i)+"'"+(" selected" if i==mese else "")+">"+months[i]+"</option>" for i in range(1,13))
        year_opts=''.join("<option value='"+str(y)+"'"+(" selected" if y==anno else "")+">"+str(y)+"</option>" for y in range(today.year-1,today.year+3))
        season_opts=''.join("<option value='"+str(y)+"'"+(" selected" if y==season_start else "")+">"+str(y)+"/"+str(y+1)+"</option>" for y in range(today.year-2,today.year+3))

        if vista=='iscrizioni':
            expl=f"""<div class='bmps3-explain annual'>
              <div><span>ISCRIZIONE ANNUALE</span><h3>Stagione {season_start}/{season_start+1}</h3>
              <p>Una sola quota per stagione. Puoi incassarla ad agosto, settembre o in un altro mese: non diventa mai una quota mensile.</p></div>
              <form method='get' class='bmps3-period'><input type='hidden' name='vista' value='iscrizioni'>
                <label>Stagione<select name='stagione' onchange='this.form.submit()'>{season_opts}</select></label>
                <label>Mese incasso<select name='mese'>{month_opts}</select></label>
                <label>Anno incasso<select name='anno'>{year_opts}</select></label>
                <button type='submit'>Applica</button>
              </form>
            </div>"""
        elif vista=='mensili':
            expl=f"""<div class='bmps3-explain monthly'>
              <div><span>QUOTA MENSILE</span><h3>{months[mese]} {anno}</h3>
              <p>Ogni mese è indipendente. Un pagamento di ottobre non copre novembre e non sostituisce l'iscrizione annuale.</p></div>
              <form method='get' class='bmps3-period'><input type='hidden' name='vista' value='mensili'>
                <label>Mese<select name='mese' onchange='this.form.submit()'>{month_opts}</select></label>
                <label>Anno<select name='anno' onchange='this.form.submit()'>{year_opts}</select></label>
              </form>
            </div>"""
        else:
            expl="""<div class='bmps3-explain all'><div><span>STORICO INCASSI</span><h3>Tutti i pagamenti</h3><p>Elenco storico. La classificazione resta separata tra Iscrizione annuale e Mensile.</p></div></div>"""

        anchor="<!-- BODYMIND_R123_PAYMENT_SPLIT_V2_SURFACE -->"
        if anchor in html:
            html=html.replace(anchor,"<!-- BODYMIND_R123_PAYMENT_SPLIT_V3_SURFACE -->"+expl+anchor,1)
        else:
            html=expl+html

        # Force the existing payment form to the active semantic mode. This
        # prevents monthly registrations from accidentally being saved with
        # the legacy hidden causale=iscrizione.
        js=f"""<script id='bodymind-payment-split-v3-js'>(function(){{
          var vista={vista!r};
          var mese={int(mese)}, anno={int(anno)}, stagione={int(season_start)};
          function setField(form,name,value){{
            var el=form.querySelector('[name=\"'+name+'\"]');
            if(!el) return;
            el.value=String(value);
            try{{ el.dispatchEvent(new Event('change',{{bubbles:true}})); }}catch(e){{}}
          }}
          document.querySelectorAll('form').forEach(function(form){{
            var cause=form.querySelector('input[name=\"causale\"],select[name=\"causale\"]');
            if(!cause) return;
            var txt=(form.innerText||'').toLowerCase();
            var hasPaymentFields=form.querySelector('[name=\"tesserato_id\"],[name=\"importo\"]');
            if(!hasPaymentFields && txt.indexOf('importo')<0) return;
            var oldBadge=form.querySelector('.bmps4-mode');
            if(oldBadge) oldBadge.remove();
            var badge=document.createElement('div');
            badge.className='bmps4-mode';
            if(vista==='mensili'){{
              cause.value='mensile';
              setField(form,'mese',mese); setField(form,'anno',anno);
              badge.innerHTML='<b>Stai registrando: MENSILE</b><span>'+String(mese).padStart(2,'0')+'/'+anno+' · questa quota vale solo per questo mese</span>';
            }} else if(vista==='iscrizioni'){{
              cause.value='iscrizione';
              setField(form,'mese',mese);
              var payYear=(mese>=7)?stagione:(stagione+1);
              setField(form,'anno',payYear);
              badge.innerHTML='<b>Stai registrando: ISCRIZIONE ANNUALE</b><span>Stagione '+stagione+'/'+(stagione+1)+' · mese incasso '+String(mese).padStart(2,'0')+'/'+payYear+'</span>';
            }} else {{
              return;
            }}
            var first=form.firstElementChild;
            if(first) form.insertBefore(badge,first); else form.appendChild(badge);
            try{{
              cause.setAttribute('data-bodymind-locked-causale','1');
              if(cause.tagName==='SELECT') cause.style.pointerEvents='none';
              cause.setAttribute('aria-readonly','true');
            }}catch(e){{}}
          }});
        }})();</script>"""
        html=html.replace('</body>',js+'</body>',1) if '</body>' in html else html+js

        css="""<style id='bodymind-payment-split-v3-css'>
        .bmps3-explain{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:20px;align-items:center;margin:14px 0 12px;padding:20px 22px;border-radius:20px;color:#f8fafc;border:1px solid rgba(148,163,184,.18);box-shadow:0 18px 50px rgba(0,0,0,.18)}
        .bmps3-explain.annual{background:linear-gradient(135deg,#10233a,#16324d)}
        .bmps3-explain.monthly{background:linear-gradient(135deg,#122c24,#174733)}
        .bmps3-explain.all{background:linear-gradient(135deg,#211a38,#322653)}
        .bmps3-explain span{display:block;font-size:11px;font-weight:950;letter-spacing:.14em;color:#93c5fd}.bmps3-explain h3{font-size:26px;margin:4px 0 5px}.bmps3-explain p{margin:0;max-width:780px;color:#cbd5e1;line-height:1.5}
        .bmps3-period{display:flex;gap:8px;align-items:end;flex-wrap:wrap;justify-content:flex-end}.bmps3-period label{display:grid;gap:4px;font-size:11px;font-weight:900;color:#cbd5e1}.bmps3-period select,.bmps3-period button{min-height:42px;border-radius:11px;border:1px solid rgba(148,163,184,.28);background:#071426;color:#fff;padding:8px 10px;font-weight:800}.bmps3-period button{background:#2563eb;border-color:#60a5fa;cursor:pointer}.bmps4-mode{grid-column:1/-1;display:grid;gap:3px;margin:0 0 10px;padding:11px 13px;border-radius:12px;background:#071426;border:1px solid rgba(96,165,250,.35)}.bmps4-mode b{font-size:12px;letter-spacing:.04em;color:#fff}.bmps4-mode span{font-size:11px;color:#bfdbfe}
        @media(min-width:901px){.bmps{padding:20px!important}.bmps-head h2{font-size:28px!important}.bmps-tabs{max-width:680px}.bmps-card{padding:15px 17px!important}.bmps-card b{font-size:15px}}
        @media(max-width:900px){.bmps3-explain{grid-template-columns:1fr;padding:14px}.bmps3-period{justify-content:flex-start}.bmps3-explain h3{font-size:21px}}
        </style>"""
        html=html.replace('</head>',css+'</head>',1) if '</head>' in html else css+html
        resp.set_data(html)
    except Exception as exc:
        print('[payment-split-v3-warning] '+repr(exc),flush=True)
    return resp
'''
    CORE.write_text(_core_split_v3,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r123-payment-split-v3] PASS annual-enrollment monthly-period form-forcing desktop-clarity',flush=True)
else:
    print('[r123-payment-split-v3] already installed',flush=True)

# BODYMIND_R123_PAYMENT_FORM_CLARITY_V4
print('[r123-payment-form-clarity-v4] PASS explicit annual/monthly registration mode',flush=True)


# BODYMIND_R123_CANONICAL_PAYMENT_MODULE_V5
# Final convergence: one operational payment module, two modes only.
# Disable old V2/V3 renderers in persisted core before app import, then install
# one canonical surface. Historical rows stay untouched.
_core_v5=CORE.read_text(encoding='utf-8',errors='replace')
_changed_v5=False
for _old in (
    "@app.after_request\ndef _bodymind_r123_payment_split_v2(resp):",
    "@app.after_request\ndef _bodymind_r123_payment_split_v3(resp):",
):
    if _old in _core_v5:
        _core_v5=_core_v5.replace(_old,_old.replace("@app.after_request\n",""),1)
        _changed_v5=True

if 'BODYMIND_R123_CANONICAL_PAYMENT_MODULE_V5' not in _core_v5:
    _core_v5 += r'''

# BODYMIND_R123_CANONICAL_PAYMENT_MODULE_V5
@app.after_request
def _bodymind_r123_canonical_payment_module_v5(resp):
    try:
        if request.method!='GET' or request.path!='/pagamenti' or int(getattr(resp,'status_code',200) or 200)!=200:
            return resp
        if 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp
        html=resp.get_data(as_text=True)
        from datetime import date as _d
        today=_d.today()
        mese=parse_int(request.args.get('mese',today.month),today.month)
        anno=parse_int(request.args.get('anno',today.year),today.year)
        if mese<1 or mese>12: mese=today.month
        if anno<2020 or anno>2100: anno=today.year
        vista=(request.args.get('vista') or 'iscrizioni').strip().lower()
        if vista not in ('iscrizioni','mensili'): vista='iscrizioni'
        season=parse_int(request.args.get('stagione',anno if mese>=7 else anno-1),anno if mese>=7 else anno-1)
        selected_tid=parse_int(request.args.get('tesserato_id',0),0)

        c=db(); c.row_factory=sqlite3.Row
        try:
            athletes=[dict(x) for x in c.execute(
                "SELECT * FROM tesserati WHERE COALESCE(attivo,1)=1 ORDER BY TRIM(cognome) COLLATE NOCASE,TRIM(nome) COLLATE NOCASE"
            ).fetchall()]
            payments=[dict(x) for x in c.execute("SELECT * FROM pagamenti ORDER BY id DESC").fetchall()] if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pagamenti'").fetchone() else []
            qrows=[dict(x) for x in c.execute("SELECT * FROM quote_mensili WHERE mese=? AND anno=? ORDER BY id DESC",(mese,anno)).fetchall()] if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='quote_mensili'").fetchone() else []
        finally:
            try:c.close()
            except Exception:pass

        def _paid(p):
            st=(str(p.get('stato') or '')+' '+str(p.get('online_status') or '')).lower()
            if any(x in st for x in ('pending','attesa','cancel','annull','failed','fallit','refunded','rimbors')): return False
            if any(x in st for x in ('paid','pagat','saldat','complet','incassat')): return True
            try: amount=float(p.get('importo') or 0)
            except Exception: amount=0
            return bool(p.get('data') or p.get('paid_at')) and amount>0

        enroll={}; monthly={}
        for p in payments:
            if not _paid(p): continue
            tid=int(p.get('tesserato_id') or 0)
            cause=str(p.get('causale') or '').strip().lower()
            pm=int(p.get('mese') or 0); py=int(p.get('anno') or 0)
            if (cause in ('iscrizione','tesseramento') or 'iscrizion' in cause) and py in (season,season+1) and tid not in enroll:
                enroll[tid]=p
            if (cause=='mensile' or 'mensil' in cause or cause in ('quota','quota_mensile')) and pm==mese and py==anno and tid not in monthly:
                monthly[tid]=p
        qpaid=set()
        for q in qrows:
            st=str(q.get('stato') or '').lower()
            if any(x in st for x in ('pagat','saldat','paid','incassat','complet')):
                qpaid.add(int(q.get('tesserato_id') or 0))

        months=['','Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno','Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre']
        def _name(a):
            return ((str(a.get('cognome') or '')+' '+str(a.get('nome') or '')).strip()) or ('Tesserata #'+str(int(a.get('id') or 0)))
        def _money(v):
            try:return ('€ %.2f' % float(v or 0)).replace('.',',')
            except Exception:return ''

        cards=[]
        paid_n=0
        for a in athletes:
            tid=int(a.get('id') or 0)
            if selected_tid and tid!=selected_tid: continue
            ep=enroll.get(tid)
            elegacy=bool(int(a.get('iscrizione_pagata') or 0)) if 'iscrizione_pagata' in a else False
            elegacy=elegacy or (bool(int(a.get('tesseramento_pagato') or 0)) if 'tesseramento_pagato' in a else False)
            enroll_ok=bool(ep or elegacy)
            mp=monthly.get(tid)
            month_ok=bool(mp or tid in qpaid)

            if vista=='iscrizioni':
                ok=enroll_ok
                detail=(_money(ep.get('importo'))+' · '+str(ep.get('data') or '')).strip(' ·') if ep else ('Già registrata' if elegacy else 'Iscrizione da registrare')
            else:
                ok=month_ok
                detail=(_money(mp.get('importo'))+' · '+str(mp.get('data') or '')).strip(' ·') if mp else ('Già registrato' if tid in qpaid else ('Mensile '+months[mese]+' da registrare'))
            if ok: paid_n+=1

            enroll_href=f"/pagamenti?vista=iscrizioni&stagione={season}&mese={mese}&anno={anno}&tesserato_id={tid}&azione=registra"
            monthly_href=f"/pagamenti?vista=mensili&mese={mese}&anno={anno}&tesserato_id={tid}&azione=registra"
            actions=(
                "<a class='bmpv5-act "+("done" if enroll_ok else "primary")+"' href='"+enroll_href+"'>"+("Iscrizione ✓" if enroll_ok else "Registra iscrizione")+"</a>"
                +"<a class='bmpv5-act "+("done" if month_ok else "secondary")+"' href='"+monthly_href+"'>"+(("Mensile "+months[mese]+" ✓") if month_ok else ("Registra mensile "+months[mese]))+"</a>"
            )
            cards.append("<div class='bmpv5-card "+("paid" if ok else "due")+"'><div class='bmpv5-person'><b>"+e(_name(a))+"</b><small>"+e(detail)+"</small></div><strong>"+("PAGATO" if ok else "DA PAGARE")+"</strong><div class='bmpv5-actions'>"+actions+"</div></div>")

        total_visible=len(cards)
        mode_title=("Iscrizione · stagione "+str(season)+"/"+str(season+1)) if vista=='iscrizioni' else ("Mensile · "+months[mese]+" "+str(anno))
        selector=""
        if vista=='iscrizioni':
            selector=f"""<form class='bmpv5-period' method='get'>
              <input type='hidden' name='vista' value='iscrizioni'>
              <label>Stagione<input name='stagione' type='number' value='{season}' min='2020' max='2100'></label>
              <label>Mese incasso<select name='mese'>{''.join("<option value='"+str(i)+"'"+(" selected" if i==mese else "")+">"+months[i]+"</option>" for i in range(1,13))}</select></label>
              <label>Anno<input name='anno' type='number' value='{anno}' min='2020' max='2100'></label>
              <button>Mostra</button>
            </form>"""
        else:
            selector=f"""<form class='bmpv5-period' method='get'>
              <input type='hidden' name='vista' value='mensili'>
              <label>Mese<select name='mese'>{''.join("<option value='"+str(i)+"'"+(" selected" if i==mese else "")+">"+months[i]+"</option>" for i in range(1,13))}</select></label>
              <label>Anno<input name='anno' type='number' value='{anno}' min='2020' max='2100'></label>
              <button>Mostra</button>
            </form>"""

        surface=f"""<!-- BODYMIND_R123_CANONICAL_PAYMENT_MODULE_V5 -->
        <section class='bmpv5'>
          <div class='bmpv5-head'>
            <div><span>PAGAMENTI BODYMIND</span><h1>{e(mode_title)}</h1><p>Un solo modulo. Gli stessi dati valgono ovunque.</p></div>
            <div class='bmpv5-count'>{paid_n}/{total_visible}</div>
          </div>
          <nav class='bmpv5-tabs'>
            <a class='{'active' if vista=='iscrizioni' else ''}' href='/pagamenti?vista=iscrizioni&stagione={season}&mese={mese}&anno={anno}'>ISCRIZIONE</a>
            <a class='{'active' if vista=='mensili' else ''}' href='/pagamenti?vista=mensili&mese={mese}&anno={anno}'>MENSILE</a>
          </nav>
          {selector}
          {("<div class='bmpv5-entry' id='bmpv5Entry'><div class='bmpv5-entry-head'><b>REGISTRA "+("ISCRIZIONE" if vista=="iscrizioni" else "MENSILE "+months[mese].upper())+"</b><span>Completa importo, metodo e data, poi salva.</span></div><div id='bmpv5EntrySlot'></div></div>" if selected_tid and (request.args.get('azione') or '')=='registra' else "")}
          <div class='bmpv5-list'>{''.join(cards) if cards else "<div class='bmpv5-empty'>Nessuna tesserata trovata.</div>"}</div>
        </section>
        <style id='bodymind-payment-module-v5'>
        /* Hide every superseded payment dashboard/surface; keep real POST forms/history available below. */
        .r123-pay-box,.r125-board,.bmps,.bmps3-explain{{display:none!important}}
        .bmpv5{{margin:14px 0 18px;padding:20px;border-radius:22px;background:#091728;border:1px solid rgba(96,165,250,.24);color:#f8fafc}}
        .bmpv5-head{{display:flex;justify-content:space-between;gap:16px;align-items:center}}.bmpv5-head span{{font-size:10px;letter-spacing:.14em;font-weight:950;color:#7dd3fc}}.bmpv5-head h1{{margin:4px 0;font-size:28px}}.bmpv5-head p{{margin:0;color:#b7c6d9}}.bmpv5-count{{font-size:26px;font-weight:950}}
        .bmpv5-tabs{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:14px 0}}.bmpv5-tabs a{{padding:14px;border-radius:14px;background:#10243b;color:#cbd5e1!important;text-decoration:none;text-align:center;font-weight:950}}.bmpv5-tabs a.active{{background:#2563eb;color:white!important}}
        .bmpv5-period{{display:flex;gap:8px;align-items:end;flex-wrap:wrap;margin-bottom:12px;padding:11px;border-radius:14px;background:#0c2035}}.bmpv5-period label{{display:grid;gap:4px;font-size:11px;font-weight:900;color:#cbd5e1}}.bmpv5-period input,.bmpv5-period select,.bmpv5-period button{{min-height:42px;border-radius:10px;border:1px solid rgba(148,163,184,.25);background:#06111f;color:#fff;padding:8px 10px}}.bmpv5-period button{{background:#2563eb;font-weight:900}}
        .bmpv5-entry{{margin:0 0 14px;padding:14px;border-radius:16px;background:#071426;border:1px solid rgba(96,165,250,.42);box-shadow:0 10px 30px rgba(2,6,23,.28)}}.bmpv5-entry-head{{display:grid;gap:3px;margin-bottom:10px}}.bmpv5-entry-head b{{font-size:13px;letter-spacing:.05em;color:#fff}}.bmpv5-entry-head span{{font-size:12px;color:#bfdbfe}}#bmpv5EntrySlot>form{{margin:0!important;max-width:none!important;width:100%!important;display:block!important;visibility:visible!important;opacity:1!important}}#bmpv5EntrySlot form [type=submit],#bmpv5EntrySlot form button[type=submit]{{min-height:44px!important;background:#2563eb!important;color:#fff!important;font-weight:950!important}}
        .bmpv5-list{{display:grid;gap:8px}}.bmpv5-card{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px 14px;align-items:center;padding:13px 15px;border-radius:14px;color:#fff;border:1px solid transparent}}.bmpv5-person{{display:grid;gap:3px}}.bmpv5-card small{{color:#cbd5e1}}.bmpv5-card.paid{{background:rgba(20,83,45,.78);border-color:rgba(74,222,128,.35)}}.bmpv5-card.due{{background:rgba(127,29,29,.70);border-color:rgba(248,113,113,.32)}}.bmpv5-card>strong{{font-size:11px}}.bmpv5-actions{{grid-column:1/-1;display:flex;gap:8px;flex-wrap:wrap}}.bmpv5-act{{display:inline-flex;align-items:center;justify-content:center;min-height:40px;padding:9px 12px;border-radius:11px;text-decoration:none!important;font-size:12px;font-weight:950}}.bmpv5-act.primary{{background:#2563eb;color:#fff!important}}.bmpv5-act.secondary{{background:#0f766e;color:#fff!important}}.bmpv5-act.done{{background:rgba(15,23,42,.55);color:#d1fae5!important;border:1px solid rgba(74,222,128,.28)}}
        @media(max-width:700px){{.bmpv5{{padding:13px}}.bmpv5-head{{align-items:flex-start}}.bmpv5-head h1{{font-size:21px}}.bmpv5-period{{display:grid;grid-template-columns:1fr 1fr}}.bmpv5-period button{{grid-column:1/-1}}.bmpv5-card{{grid-template-columns:1fr}}.bmpv5-actions{{display:grid;grid-template-columns:1fr}}}}
        </style>
        <script id='bodymind-payment-mode-v5'>(function(){{
          var vista={vista!r}, mese={mese}, anno={anno}, stagione={season}, selectedTid={selected_tid};
          document.querySelectorAll('form').forEach(function(form){{
            var cause=form.querySelector('input[name="causale"],select[name="causale"]');
            if(!cause) return;
            var has=form.querySelector('[name="tesserato_id"],[name="importo"]');
            if(!has && (form.innerText||'').toLowerCase().indexOf('importo')<0) return;
            cause.value=(vista==='mensili'?'mensile':'iscrizione');
            var m=form.querySelector('[name="mese"]'), y=form.querySelector('[name="anno"]'), t=form.querySelector('[name="tesserato_id"]');
            if(m) m.value=String(mese);
            if(y) y.value=String(vista==='mensili'?anno:(mese>=7?stagione:stagione+1));
            if(t && selectedTid) {{
              t.value=String(selectedTid);
              try{{ t.dispatchEvent(new Event('change',{{bubbles:true}})); }}catch(e){{}}
            }}
            var badge=form.querySelector('.bmpv5-formbadge');
            if(!badge){{badge=document.createElement('div');badge.className='bmpv5-formbadge';form.insertBefore(badge,form.firstElementChild);}}
            badge.innerHTML=vista==='mensili'
              ? '<b>MENSILE</b><span>'+String(mese).padStart(2,'0')+'/'+anno+'</span>'
              : '<b>ISCRIZIONE</b><span>Stagione '+stagione+'/'+(stagione+1)+'</span>';
            if(selectedTid && new URLSearchParams(location.search).get('azione')==='registra') {{
              form.setAttribute('data-bodymind-active-payment-form','1');
            }}
          }});
          if(selectedTid && new URLSearchParams(location.search).get('azione')==='registra') {{
            var active=document.querySelector('form[data-bodymind-active-payment-form="1"]');
            var slot=document.getElementById('bmpv5EntrySlot');
            if(active && slot) {{
              active.style.outline='none';
              active.style.outlineOffset='0';
              active.style.display='block';
              active.style.visibility='visible';
              active.style.opacity='1';
              slot.appendChild(active);
              var amount=active.querySelector('[name="importo"]');
              if(amount) {{
                try{{amount.focus({{preventScroll:true}})}}catch(e){{}}
              }}
            }} else if(slot) {{
              slot.innerHTML='<div style="padding:10px;border-radius:10px;background:#3f1d1d;color:#fecaca;font-weight:800">Form di registrazione non trovato: nessun dato è stato modificato.</div>';
            }}
          }}
        }})();</script>
        <style>.bmpv5-formbadge{{display:flex;justify-content:space-between;gap:10px;margin-bottom:10px;padding:10px 12px;border-radius:11px;background:#07182a;border:1px solid rgba(96,165,250,.32)}}.bmpv5-formbadge span{{color:#bfdbfe}}</style>"""

        # Insert once at the top of the active page.
        m=re.search(r'<main\b[^>]*>',html,re.I)
        if m: html=html[:m.end()]+surface+html[m.end():]
        else:
            b=re.search(r'<body\b[^>]*>',html,re.I)
            html=html[:b.end()]+surface+html[b.end():] if b else surface+html
        resp.set_data(html)
    except Exception as exc:
        print('[payment-module-v5-warning] '+repr(exc),flush=True)
    return resp
'''
    _changed_v5=True

if _changed_v5:
    CORE.write_text(_core_v5,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
print('[r123-payment-module-v5] PASS one-module two-modes-only old-surfaces-disabled',flush=True)


# BODYMIND_R123_PAYMENT_OPERATIVITY_V6
_core_v6=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R123_CANONICAL_PAYMENT_MODULE_V5' in _core_v6 and 'BODYMIND_R123_PAYMENT_OPERATIVITY_V6' not in _core_v6:
    anchor="""        cards=[]
        paid_n=0
"""
    inject="""        # BODYMIND_R123_PAYMENT_OPERATIVITY_V6
        _miss_enroll=[]; _miss_month=[]
        for _a in athletes:
            _tid=int(_a.get('id') or 0)
            _ep=enroll.get(_tid)
            _legacy=(bool(int(_a.get('iscrizione_pagata') or 0)) if 'iscrizione_pagata' in _a else False) or (bool(int(_a.get('tesseramento_pagato') or 0)) if 'tesseramento_pagato' in _a else False)
            if not (_ep or _legacy):
                _h=f"/pagamenti?vista=iscrizioni&stagione={season}&mese={mese}&anno={anno}&tesserato_id={_tid}&azione=registra"
                _miss_enroll.append("<div class='bmpv6-miss'><b>"+e(_name(_a))+"</b><a href='"+_h+"'>Registra iscrizione</a></div>")
            _mp=monthly.get(_tid)
            if not (_mp or _tid in qpaid):
                _h=f"/pagamenti?vista=mensili&mese={mese}&anno={anno}&tesserato_id={_tid}&azione=registra"
                _miss_month.append("<div class='bmpv6-miss'><b>"+e(_name(_a))+"</b><a href='"+_h+"'>Registra mensile "+e(months[mese])+"</a></div>")
        immediate=f\"\"\"<section class='bmpv6-immediate'>
          <div class='bmpv6-head'><div><span>OPERATIVITÀ IMMEDIATA</span><h2>Da registrare</h2></div><small>Unica verità per tutto il gestionale</small></div>
          <div class='bmpv6-cols'>
            <div><div class='bmpv6-colhead'><b>SENZA ISCRIZIONE</b><strong>{len(_miss_enroll)}</strong></div>{''.join(_miss_enroll) if _miss_enroll else "<p class='bmpv6-ok'>Nessuna iscrizione mancante.</p>"}</div>
            <div><div class='bmpv6-colhead'><b>SENZA MENSILE · {e(months[mese])} {anno}</b><strong>{len(_miss_month)}</strong></div>{''.join(_miss_month) if _miss_month else "<p class='bmpv6-ok'>Nessun mensile mancante.</p>"}</div>
          </div>
        </section><div id='bmpv5-form-mount'></div>
        <script id='bmpv6-form-mounter'>(function(){{
          var tid={selected_tid}, mode={vista!r}, mm={mese}, yy={anno}, ss={season};
          if(!tid || new URLSearchParams(location.search).get('azione')!=='registra') return;
          var forms=[].slice.call(document.querySelectorAll('form'));
          var active=forms.find(function(form){{
            return form.querySelector('[name="tesserato_id"]') && (form.querySelector('[name="importo"]') || (form.innerText||'').toLowerCase().indexOf('importo')>=0);
          }});
          if(!active) return;
          var t=active.querySelector('[name="tesserato_id"]'), c=active.querySelector('[name="causale"]'), m=active.querySelector('[name="mese"]'), y=active.querySelector('[name="anno"]');
          if(t) t.value=String(tid);
          if(c) c.value=(mode==='mensili'?'mensile':'iscrizione');
          if(m) m.value=String(mm);
          if(y) y.value=String(mode==='mensili'?yy:(mm>=7?ss:ss+1));
          var mount=document.getElementById('bmpv5-form-mount');
          if(mount && active.parentNode!==mount) mount.appendChild(active);
        }})();</script>\"\"\"

        cards=[]
        paid_n=0
"""
    if anchor not in _core_v6: raise RuntimeError('V6 cards anchor missing')
    _core_v6=_core_v6.replace(anchor,inject,1)
    surf="""          {selector}
          <div class='bmpv5-list'>"""
    if surf not in _core_v6: raise RuntimeError('V6 surface anchor missing')
    _core_v6=_core_v6.replace(surf,"""          {selector}
          {immediate}
          <div class='bmpv5-list'>""",1)
    css=""".bmpv5-period button{{background:#2563eb;font-weight:900}}
        .bmpv5-list"""
    css2=""".bmpv5-period button{{background:#2563eb;font-weight:900}}
        .bmpv6-immediate{{margin:14px 0;padding:14px;border-radius:16px;background:#071321;border:1px solid rgba(148,163,184,.18)}}.bmpv6-head{{display:flex;justify-content:space-between;gap:12px;align-items:end;margin-bottom:10px}}.bmpv6-head span{{font-size:10px;font-weight:950;letter-spacing:.12em;color:#fbbf24}}.bmpv6-head h2{{margin:3px 0 0;font-size:20px}}.bmpv6-head small{{color:#94a3b8}}.bmpv6-cols{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}.bmpv6-cols>div{{padding:10px;border-radius:13px;background:#0c2035}}.bmpv6-colhead{{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}}.bmpv6-colhead b{{font-size:11px}}.bmpv6-colhead strong{{min-width:28px;height:28px;display:grid;place-items:center;border-radius:999px;background:#7f1d1d}}.bmpv6-miss{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:center;padding:8px 9px;margin-top:6px;border-radius:10px;background:#111f31}}.bmpv6-miss b{{font-size:12px}}.bmpv6-miss a{{padding:8px 10px;border-radius:9px;background:#2563eb;color:white!important;text-decoration:none;font-size:11px;font-weight:950}}.bmpv6-ok{{padding:9px;border-radius:9px;background:#14532d;color:#dcfce7;font-size:12px}}#bmpv5-form-mount:not(:empty){{margin:14px 0;padding:14px;border-radius:16px;background:#0b1d31;border:2px solid rgba(96,165,250,.55)}}
        .bmpv5-list"""
    if css not in _core_v6: raise RuntimeError('V6 css anchor missing')
    _core_v6=_core_v6.replace(css,css2,1)
    mover="""              active.style.outlineOffset='6px';
            }}"""
    mover2="""              active.style.outlineOffset='6px';
              var mount=document.getElementById('bmpv5-form-mount');
              if(mount && active.parentNode!==mount) mount.appendChild(active);
            }}"""
    if mover in _core_v6:
        _core_v6=_core_v6.replace(mover,mover2,1)
    _core_v6=_core_v6.replace("@media(max-width:700px){{.bmpv5{{padding:13px}}","@media(max-width:700px){{.bmpv6-cols{{grid-template-columns:1fr}}.bmpv6-head{{align-items:flex-start;flex-direction:column}}.bmpv6-miss{{grid-template-columns:1fr}}.bmpv5{{padding:13px}}",1)
    CORE.write_text(_core_v6,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r123-payment-operativity-v6] PASS immediate-missing-lists direct-register existing-form-mounted',flush=True)
else:
    print('[r123-payment-operativity-v6] already or waiting for V5',flush=True)

# BODYMIND_R123_INLINE_PAYMENT_ENTRY_V6
print('[r123-inline-payment-entry-v6] PASS real payment form moved into canonical module',flush=True)


# BODYMIND_R123_PAYMENT_FORM_CANONICAL_V7
# Replace the V5/V6 "move an existing form" behavior with one real canonical
# registration/edit form. One module, two modes, same write path everywhere.
_core_v7=CORE.read_text(encoding='utf-8',errors='replace')
_changed_v7=False

# Disable the old payment renderer if still registered.
_old_v5="@app.after_request\ndef _bodymind_r123_canonical_payment_module_v5(resp):"
if _old_v5 in _core_v7:
    _core_v7=_core_v7.replace(_old_v5,_old_v5.replace("@app.after_request\n",""),1)
    _changed_v7=True

if 'BODYMIND_R123_PAYMENT_FORM_CANONICAL_V7' not in _core_v7:
    _core_v7 += r'''

# BODYMIND_R123_PAYMENT_FORM_CANONICAL_V7
@app.route('/pagamenti/registra-unico',methods=['POST'])
@login_required
def _bodymind_payment_register_v7():
    from datetime import date as _date, datetime as _dt
    tid=parse_int(request.form.get('tesserato_id'),0)
    tipo=(request.form.get('tipo') or '').strip().lower()
    mese=parse_int(request.form.get('mese'),0)
    anno=parse_int(request.form.get('anno'),0)
    stagione=parse_int(request.form.get('stagione'),0)
    data=(request.form.get('data') or '').strip()
    metodo=(request.form.get('metodo_pagamento') or '').strip()
    note=(request.form.get('note_pagamento') or '').strip()[:1000]
    payment_id=parse_int(request.form.get('payment_id'),0)
    try:
        importo=float(str(request.form.get('importo') or '').replace(',','.'))
    except Exception:
        importo=-1

    if tipo not in ('iscrizione','mensile') or tid<=0 or mese<1 or mese>12 or anno<2020 or anno>2100 or importo<0:
        return redirect('/pagamenti?errore=dati_non_validi',302)
    try:
        _date.fromisoformat(data)
    except Exception:
        data=_date.today().isoformat()
    if not metodo:
        metodo='contanti'
    if tipo=='iscrizione' and not stagione:
        stagione=anno if mese>=7 else anno-1

    c=db(); c.row_factory=sqlite3.Row
    try:
        athlete=c.execute("SELECT * FROM tesserati WHERE id=?",(tid,)).fetchone()
        if not athlete:
            return redirect('/pagamenti?errore=tesserato_non_trovato',302)

        existing=None
        if payment_id:
            existing=c.execute("SELECT * FROM pagamenti WHERE id=? AND tesserato_id=?",(payment_id,tid)).fetchone()
        if not existing:
            if tipo=='mensile':
                existing=c.execute(
                    "SELECT * FROM pagamenti WHERE tesserato_id=? AND mese=? AND anno=? AND lower(coalesce(causale,'')) LIKE '%mensil%' ORDER BY id DESC LIMIT 1",
                    (tid,mese,anno)
                ).fetchone()
            else:
                existing=c.execute(
                    "SELECT * FROM pagamenti WHERE tesserato_id=? AND anno IN (?,?) AND (lower(coalesce(causale,''))='iscrizione' OR lower(coalesce(causale,''))='tesseramento' OR lower(coalesce(causale,'')) LIKE '%iscrizion%') ORDER BY id DESC LIMIT 1",
                    (tid,stagione,stagione+1)
                ).fetchone()

        now=_dt.now().isoformat(timespec='seconds')
        if existing:
            pid=int(existing['id'])
            c.execute("""
                UPDATE pagamenti
                   SET mese=?,anno=?,importo=?,data=?,causale=?,
                       metodo_pagamento=?,note_pagamento=?,
                       stato='paid_manual',online_status='paid_manual',
                       paid_at=COALESCE(paid_at,?),updated_at=?
                 WHERE id=?
            """,(mese,anno,importo,data,tipo,metodo,note,now,now,pid))
        else:
            cur=c.execute("""
                INSERT INTO pagamenti(
                    tesserato_id,mese,anno,importo,data,causale,
                    online_status,stato,metodo_pagamento,note_pagamento,
                    tenant_id,paid_at,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,'paid_manual','paid_manual',?,?, 'default',?,?,?)
            """,(tid,mese,anno,importo,data,tipo,metodo,note,now,now,now))
            pid=int(cur.lastrowid)

        nome=((str(athlete['cognome'] or '')+' '+str(athlete['nome'] or '')).strip())
        desc=('Quota iscrizione stagione '+str(stagione)+'/'+str(stagione+1)) if tipo=='iscrizione' else ('Quota mensile '+str(mese).zfill(2)+'/'+str(anno))
        receipt=c.execute("SELECT * FROM ricevute WHERE pagamento_id=? ORDER BY id DESC LIMIT 1",(pid,)).fetchone()
        if receipt:
            rid=int(receipt['id'])
            c.execute("""
                UPDATE ricevute
                   SET nome=?,descrizione=?,importo=?,data=?,metodo_pagamento=?,updated_at=?
                 WHERE id=?
            """,(nome,desc,importo,data,metodo,now,rid))
        else:
            prog=int(c.execute("SELECT COALESCE(MAX(numero_progressivo),0)+1 FROM ricevute WHERE anno_progressivo=?",(anno,)).fetchone()[0] or 1)
            cur=c.execute("""
                INSERT INTO ricevute(
                    nome,descrizione,importo,data,pagamento_id,tenant_id,
                    created_at,updated_at,metodo_pagamento,
                    numero_progressivo,anno_progressivo,annullata
                ) VALUES(?,?,?,?,?,'default',?,?,?,?,?,0)
            """,(nome,desc,importo,data,pid,now,now,metodo,prog,anno))
            rid=int(cur.lastrowid)
        c.execute("UPDATE pagamenti SET ricevuta_id=? WHERE id=?",(rid,pid))

        if tipo=='iscrizione':
            c.execute("""
                UPDATE tesserati
                   SET iscrizione_pagata=1,tesseramento_pagato=1,updated_at=?
                 WHERE id=?
            """,(now,tid))
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='smart_alerts'").fetchone():
                c.execute("""
                    UPDATE smart_alerts
                       SET status='closed',closed_at=COALESCE(closed_at,?),updated_at=?
                     WHERE tesserato_id=? AND tipo='pagamento_mancante' AND status='open'
                """,(now,now,tid))
        else:
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='quote_mensili'").fetchone():
                q=c.execute("SELECT id FROM quote_mensili WHERE tesserato_id=? AND mese=? AND anno=? ORDER BY id DESC LIMIT 1",(tid,mese,anno)).fetchone()
                if q:
                    c.execute("""
                        UPDATE quote_mensili
                           SET importo_base=?,importo_dovuto=?,stato='pagato',
                               note=CASE WHEN ?<>'' THEN ? ELSE note END,
                               updated_at=?
                         WHERE id=?
                    """,(importo,importo,note,note,now,int(q['id'])))
                else:
                    c.execute("""
                        INSERT INTO quote_mensili(
                            tesserato_id,mese,anno,tariffa_codice,
                            importo_base,sconto,importo_dovuto,stato,note,created_at,updated_at
                        ) VALUES(?,?,?,'standard',?,0,?,'pagato',?,?,?)
                    """,(tid,mese,anno,importo,importo,note,now,now))
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='smart_alerts'").fetchone():
                token=str(mese).zfill(2)+'/'+str(anno)
                c.execute("""
                    UPDATE smart_alerts
                       SET status='closed',closed_at=COALESCE(closed_at,?),updated_at=?
                     WHERE tesserato_id=? AND tipo='quota_mese_mancante' AND status='open'
                       AND (message LIKE ? OR title LIKE ?)
                """,(now,now,tid,'%'+token+'%','%'+token+'%'))

        c.commit()
    except Exception as exc:
        try:c.rollback()
        except Exception:pass
        print('[payment-v7-save-warning] '+repr(exc),flush=True)
        return redirect('/pagamenti?errore=salvataggio',302)
    finally:
        try:c.close()
        except Exception:pass

    target='/pagamenti?vista='+('iscrizioni' if tipo=='iscrizione' else 'mensili')+'&mese='+str(mese)+'&anno='+str(anno)+'&tesserato_id='+str(tid)+'&salvato=1'
    if tipo=='iscrizione':
        target+='&stagione='+str(stagione)
    return redirect(target,303)


@app.after_request
def _bodymind_payment_module_v7(resp):
    try:
        if request.method!='GET' or request.path!='/pagamenti' or int(getattr(resp,'status_code',200) or 200)!=200:
            return resp
        if 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp
        html=resp.get_data(as_text=True)

        from datetime import date as _date
        today=_date.today()
        mese=parse_int(request.args.get('mese',today.month),today.month)
        anno=parse_int(request.args.get('anno',today.year),today.year)
        if mese<1 or mese>12:mese=today.month
        if anno<2020 or anno>2100:anno=today.year
        stagione=parse_int(request.args.get('stagione',anno if mese>=7 else anno-1),anno if mese>=7 else anno-1)
        vista=(request.args.get('vista') or 'iscrizioni').strip().lower()
        if vista not in ('iscrizioni','mensili'):vista='iscrizioni'
        selected_tid=parse_int(request.args.get('tesserato_id'),0)
        action=(request.args.get('azione') or '').strip().lower()
        action_tipo=(request.args.get('tipo') or '').strip().lower()
        if action_tipo not in ('iscrizione','mensile'):
            action_tipo='iscrizione' if vista=='iscrizioni' else 'mensile'

        c=db(); c.row_factory=sqlite3.Row
        try:
            athletes=[dict(x) for x in c.execute("SELECT * FROM tesserati WHERE COALESCE(attivo,1)=1 ORDER BY TRIM(cognome) COLLATE NOCASE,TRIM(nome) COLLATE NOCASE").fetchall()]
            payments=[dict(x) for x in c.execute("SELECT * FROM pagamenti ORDER BY id DESC").fetchall()]
            qrows=[dict(x) for x in c.execute("SELECT * FROM quote_mensili WHERE mese=? AND anno=? ORDER BY id DESC",(mese,anno)).fetchall()] if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='quote_mensili'").fetchone() else []
        finally:
            try:c.close()
            except Exception:pass

        def _paid(p):
            st=(str(p.get('stato') or '')+' '+str(p.get('online_status') or '')).lower()
            if any(x in st for x in ('pending','attesa','cancel','annull','failed','fallit','refunded','rimbors')):return False
            if any(x in st for x in ('paid','pagat','saldat','complet','incassat')):return True
            try:amount=float(p.get('importo') or 0)
            except Exception:amount=0
            return bool(p.get('data') or p.get('paid_at')) and amount>0

        enroll={}; monthly={}
        for p in payments:
            if not _paid(p):continue
            tid=int(p.get('tesserato_id') or 0)
            cause=str(p.get('causale') or '').lower()
            pm=int(p.get('mese') or 0); py=int(p.get('anno') or 0)
            if (cause in ('iscrizione','tesseramento') or 'iscrizion' in cause) and py in (stagione,stagione+1) and tid not in enroll:
                enroll[tid]=p
            if ('mensil' in cause or cause in ('quota','quota_mensile')) and pm==mese and py==anno and tid not in monthly:
                monthly[tid]=p

        qpaid=set()
        for q in qrows:
            st=str(q.get('stato') or '').lower()
            if any(x in st for x in ('pagat','saldat','paid','incassat','complet')):
                qpaid.add(int(q.get('tesserato_id') or 0))

        months=['','Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno','Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre']
        def _name(a):
            return ((str(a.get('cognome') or '')+' '+str(a.get('nome') or '')).strip()) or ('Tesserata #'+str(int(a.get('id') or 0)))
        def _money(v):
            try:return ('€ %.2f' % float(v or 0)).replace('.',',')
            except Exception:return ''

        rows=[]
        due_count=0
        for a in athletes:
            tid=int(a.get('id') or 0)
            ep=enroll.get(tid)
            legacy=(bool(int(a.get('iscrizione_pagata') or 0)) if 'iscrizione_pagata' in a else False) or (bool(int(a.get('tesseramento_pagato') or 0)) if 'tesseramento_pagato' in a else False)
            eok=bool(ep or legacy)
            mp=monthly.get(tid); mok=bool(mp or tid in qpaid)
            focus_ok=eok if vista=='iscrizioni' else mok
            if not focus_ok:due_count+=1
            eh=f"/pagamenti?vista=iscrizioni&stagione={stagione}&mese={mese}&anno={anno}&tesserato_id={tid}&azione=registra&tipo=iscrizione"
            mh=f"/pagamenti?vista=mensili&mese={mese}&anno={anno}&tesserato_id={tid}&azione=registra&tipo=mensile"
            rows.append((0 if not focus_ok else 1,
                "<div class='bmpv7-row "+("due" if not focus_ok else "paid")+"'>"
                +"<div class='bmpv7-person'><b>"+e(_name(a))+"</b><small>Iscrizione: "+("PAGATA" if eok else "da pagare")+" · "+months[mese]+": "+("PAGATO" if mok else "da pagare")+"</small></div>"
                +"<div class='bmpv7-actions'><a href='"+eh+"'>"+("Modifica iscrizione" if eok else "Registra iscrizione")+"</a><a href='"+mh+"'>"+("Modifica mensile "+months[mese] if mok else "Registra mensile "+months[mese])+"</a></div>"
                +"</div>"
            ))
        rows.sort(key=lambda x:x[0])

        form_html=''
        if selected_tid and action=='registra':
            athlete=next((a for a in athletes if int(a.get('id') or 0)==selected_tid),None)
            if athlete:
                existing=enroll.get(selected_tid) if action_tipo=='iscrizione' else monthly.get(selected_tid)
                pid=int(existing.get('id') or 0) if existing else 0
                amount=(str(existing.get('importo') or '') if existing else '')
                paydate=(str(existing.get('data') or today.isoformat()) if existing else today.isoformat())
                method=(str(existing.get('metodo_pagamento') or 'contanti') if existing else 'contanti')
                note=(str(existing.get('note_pagamento') or '') if existing else '')
                title=('ISCRIZIONE '+str(stagione)+'/'+str(stagione+1)) if action_tipo=='iscrizione' else ('MENSILE '+months[mese].upper()+' '+str(anno))
                form_html=f"""<form class='bmpv7-form' method='post' action='/pagamenti/registra-unico'>
                  <input type='hidden' name='csrf_token' value='{e(csrf_token())}'>
                  <input type='hidden' name='tesserato_id' value='{selected_tid}'>
                  <input type='hidden' name='tipo' value='{e(action_tipo)}'>
                  <input type='hidden' name='payment_id' value='{pid}'>
                  <input type='hidden' name='stagione' value='{stagione}'>
                  <div class='bmpv7-formhead'><div><span>{e(title)}</span><h2>{e(_name(athlete))}</h2></div><a href='/pagamenti?vista={vista}&mese={mese}&anno={anno}&stagione={stagione}'>Chiudi</a></div>
                  <div class='bmpv7-fields'>
                    <label>Importo €<input type='number' name='importo' step='0.01' min='0' required value='{e(amount)}' placeholder='es. 50,00'></label>
                    <label>Data<input type='date' name='data' required value='{e(paydate)}'></label>
                    <label>Mese<select name='mese'>{''.join("<option value='"+str(i)+"'"+(" selected" if i==mese else "")+">"+months[i]+"</option>" for i in range(1,13))}</select></label>
                    <label>Anno<input type='number' name='anno' min='2020' max='2100' required value='{anno}'></label>
                    <label>Metodo<select name='metodo_pagamento'>{''.join("<option"+(" selected" if method==x else "")+">"+x+"</option>" for x in ('contanti','bonifico','carta/SumUp','altro'))}</select></label>
                    <label class='wide'>Note / eccezione<textarea name='note_pagamento' rows='2' placeholder='Sconto, importo diverso, accordo particolare…'>{e(note)}</textarea></label>
                  </div>
                  <button class='bmpv7-save' type='submit'>{'Aggiorna pagamento' if pid else 'Salva pagamento'}</button>
                </form>"""

        saved="<div class='bmpv7-saved'>Pagamento salvato. Dashboard, Task e Centro operativo leggono ora lo stesso stato.</div>" if request.args.get('salvato')=='1' else ""
        error="<div class='bmpv7-error'>Il pagamento non è stato salvato. Controlla i dati e riprova.</div>" if request.args.get('errore') else ""

        selector=f"""<form class='bmpv7-period' method='get' action='/pagamenti'>
          <input type='hidden' name='vista' value='{e(vista)}'>
          <label>Mese<select name='mese'>{''.join("<option value='"+str(i)+"'"+(" selected" if i==mese else "")+">"+months[i]+"</option>" for i in range(1,13))}</select></label>
          <label>Anno<input type='number' name='anno' min='2020' max='2100' value='{anno}'></label>
          <input type='hidden' name='stagione' value='{stagione}'>
          <button type='submit'>Mostra</button>
        </form>"""

        surface=f"""<!-- BODYMIND_R123_PAYMENT_FORM_CANONICAL_V7 -->
        <section class='bmpv7'>
          <div class='bmpv7-head'><div><span>PAGAMENTI BODYMIND · MODULO UNICO</span><h1>{'ISCRIZIONE' if vista=='iscrizioni' else 'MENSILE '+months[mese].upper()}</h1><p>Prima chi deve pagare. Accanto a ogni atleta puoi registrare sia iscrizione sia mensile.</p></div><strong>{due_count} da pagare</strong></div>
          <nav class='bmpv7-tabs'><a class='{'on' if vista=='iscrizioni' else ''}' href='/pagamenti?vista=iscrizioni&stagione={stagione}&mese={mese}&anno={anno}'>ISCRIZIONE</a><a class='{'on' if vista=='mensili' else ''}' href='/pagamenti?vista=mensili&mese={mese}&anno={anno}'>MENSILE</a></nav>
          {selector}{saved}{error}{form_html}
          <div class='bmpv7-list'>{''.join(x[1] for x in rows)}</div>
        </section>
        <style id='bodymind-payment-v7'>
        .r123-pay-box,.r125-board,.bmps,.bmpv5,.bmpv6-immediate,.bmps3-explain{{display:none!important}}
        .bmpv7{{margin:14px 0 22px;padding:18px;border-radius:22px;background:#081626;border:1px solid rgba(96,165,250,.24);color:#f8fafc}}.bmpv7-head{{display:flex;justify-content:space-between;gap:14px;align-items:center}}.bmpv7-head span{{font-size:10px;letter-spacing:.14em;font-weight:950;color:#7dd3fc}}.bmpv7-head h1{{margin:4px 0;font-size:27px}}.bmpv7-head p{{margin:0;color:#b7c6d9}}.bmpv7-head>strong{{font-size:22px}}
        .bmpv7-tabs{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:14px 0}}.bmpv7-tabs a{{padding:14px;border-radius:13px;background:#10243a;color:#cbd5e1!important;text-decoration:none;text-align:center;font-weight:950}}.bmpv7-tabs a.on{{background:#2563eb;color:white!important}}
        .bmpv7-period{{display:flex;gap:8px;align-items:end;flex-wrap:wrap;margin-bottom:12px;padding:10px;border-radius:13px;background:#0c2035}}.bmpv7-period label{{display:grid;gap:4px;font-size:11px;font-weight:900}}.bmpv7-period input,.bmpv7-period select,.bmpv7-period button{{min-height:42px;border-radius:9px;border:1px solid rgba(148,163,184,.25);background:#06111f;color:#fff;padding:8px 10px}}.bmpv7-period button{{background:#2563eb;font-weight:900}}
        .bmpv7-form{{margin:12px 0 16px;padding:15px;border-radius:16px;background:#0d2138;border:2px solid rgba(96,165,250,.48)}}.bmpv7-formhead{{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:12px}}.bmpv7-formhead span{{font-size:10px;font-weight:950;color:#7dd3fc}}.bmpv7-formhead h2{{margin:3px 0;font-size:20px}}.bmpv7-formhead a{{color:#bfdbfe!important}}.bmpv7-fields{{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:9px}}.bmpv7-fields label{{display:grid;gap:5px;font-size:11px;font-weight:900;color:#cbd5e1}}.bmpv7-fields input,.bmpv7-fields select,.bmpv7-fields textarea{{width:100%;border-radius:9px;border:1px solid rgba(148,163,184,.25);background:#06111f;color:#fff;padding:9px;font-size:15px}}.bmpv7-fields .wide{{grid-column:1/-1}}.bmpv7-save{{margin-top:10px;min-height:45px;padding:10px 18px;border:0;border-radius:10px;background:#16a34a;color:#fff;font-weight:950}}
        .bmpv7-list{{display:grid;gap:8px}}.bmpv7-row{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px 14px;align-items:center;padding:12px 14px;border-radius:14px}}.bmpv7-row.due{{background:rgba(127,29,29,.66);border:1px solid rgba(248,113,113,.28)}}.bmpv7-row.paid{{background:rgba(20,83,45,.55);border:1px solid rgba(74,222,128,.24)}}.bmpv7-person{{display:grid;gap:3px}}.bmpv7-person small{{color:#cbd5e1}}.bmpv7-actions{{display:flex;gap:7px;flex-wrap:wrap}}.bmpv7-actions a{{padding:9px 11px;border-radius:9px;background:#2563eb;color:#fff!important;text-decoration:none;font-size:11px;font-weight:950}}.bmpv7-actions a+ a{{background:#0f766e}}.bmpv7-saved,.bmpv7-error{{margin:10px 0;padding:10px 12px;border-radius:10px;font-weight:850}}.bmpv7-saved{{background:#14532d;color:#dcfce7}}.bmpv7-error{{background:#7f1d1d;color:#fee2e2}}
        @media(max-width:780px){{.bmpv7{{padding:12px}}.bmpv7-head{{align-items:flex-start}}.bmpv7-head h1{{font-size:21px}}.bmpv7-fields{{grid-template-columns:1fr 1fr}}.bmpv7-fields .wide{{grid-column:1/-1}}.bmpv7-row{{grid-template-columns:1fr}}.bmpv7-actions{{display:grid;grid-template-columns:1fr}}}}
        </style>
        <script id='bodymind-payment-v7-clean'>(function(){{
          document.querySelectorAll('form').forEach(function(f){{
            if(!f.closest('.bmpv7') && !f.closest('header') && !f.closest('nav')) f.style.display='none';
          }});
        }})();</script>"""

        import re as _re
        m=_re.search(r'<main\b[^>]*>',html,_re.I)
        if m:html=html[:m.end()]+surface+html[m.end():]
        else:
            b=_re.search(r'<body\b[^>]*>',html,_re.I)
            html=html[:b.end()]+surface+html[b.end():] if b else surface+html
        resp.set_data(html)
    except Exception as exc:
        print('[payment-v7-render-warning] '+repr(exc),flush=True)
    return resp
'''
    _changed_v7=True

if _changed_v7:
    CORE.write_text(_core_v7,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
print('[r123-payment-v7] PASS real editable form no-loop same-write-path',flush=True)


# BODYMIND_R123_ADMIN_CONVERGENCE_V8
# Keep V7 as the single payment renderer/write path, enrich it with document
# verification + explicit cash-entry actions, restore desktop Collaboratori
# navigation, and expose Uscite without changing existing payment rows.
_core_v8=CORE.read_text(encoding='utf-8',errors='replace')
_changed_v8=False

# 1) Per-athlete actions in the canonical payment list.
_old_actions = """            eh=f"/pagamenti?vista=iscrizioni&stagione={stagione}&mese={mese}&anno={anno}&tesserato_id={tid}&azione=registra&tipo=iscrizione"
            mh=f"/pagamenti?vista=mensili&mese={mese}&anno={anno}&tesserato_id={tid}&azione=registra&tipo=mensile"
            rows.append((0 if not focus_ok else 1,
                "<div class='bmpv7-row "+("due" if not focus_ok else "paid")+"'>"
                +"<div class='bmpv7-person'><b>"+e(_name(a))+"</b><small>Iscrizione: "+("PAGATA" if eok else "da pagare")+" · "+months[mese]+": "+("PAGATO" if mok else "da pagare")+"</small></div>"
                +"<div class='bmpv7-actions'><a href='"+eh+"'>"+("Modifica iscrizione" if eok else "Registra iscrizione")+"</a><a href='"+mh+"'>"+("Modifica mensile "+months[mese] if mok else "Registra mensile "+months[mese])+"</a></div>"
                +"</div>"
            ))"""
_new_actions = """            eh=f"/pagamenti?vista=iscrizioni&stagione={stagione}&mese={mese}&anno={anno}&tesserato_id={tid}&azione=registra&tipo=iscrizione"
            mh=f"/pagamenti?vista=mensili&mese={mese}&anno={anno}&tesserato_id={tid}&azione=registra&tipo=mensile"
            dh=f"/documenti?tesserato_id={tid}"
            rows.append((0 if not focus_ok else 1,
                "<div class='bmpv7-row "+("due" if not focus_ok else "paid")+"'>"
                +"<div class='bmpv7-person'><b>"+e(_name(a))+"</b><small>Iscrizione: "+("PAGATA" if eok else "da pagare")+" · "+months[mese]+": "+("PAGATO" if mok else "da pagare")+"</small></div>"
                +"<div class='bmpv7-actions'><a class='doc' href='"+dh+"'>Verifica documento</a><a href='"+eh+"'>"+("Modifica incasso iscrizione" if eok else "Registra incasso iscrizione")+"</a><a href='"+mh+"'>"+("Modifica incasso "+months[mese] if mok else "Registra incasso "+months[mese])+"</a></div>"
                +"</div>"
            ))"""
if _old_actions in _core_v8:
    _core_v8=_core_v8.replace(_old_actions,_new_actions,1)
    _changed_v8=True

# 2) Add admin destinations to the canonical V7 surface.
_old_error = """        error="<div class='bmpv7-error'>Il pagamento non è stato salvato. Controlla i dati e riprova.</div>" if request.args.get('errore') else ""
"""
_new_error = """        error="<div class='bmpv7-error'>Il pagamento non è stato salvato. Controlla i dati e riprova.</div>" if request.args.get('errore') else ""
        collab_href=_bodymind_admin_route_v8('collaboratori') or '/collaboratori'
        collab_receipts_href=_bodymind_admin_route_v8('ricevute_collaboratori') or collab_href
        expense_href=_bodymind_admin_route_v8('uscite') or '/pagamenti/uscite'
"""
if _old_error in _core_v8:
    _core_v8=_core_v8.replace(_old_error,_new_error,1)
    _changed_v8=True

_old_nav = """          <nav class='bmpv7-tabs'><a class='{'on' if vista=='iscrizioni' else ''}' href='/pagamenti?vista=iscrizioni&stagione={stagione}&mese={mese}&anno={anno}'>ISCRIZIONE</a><a class='{'on' if vista=='mensili' else ''}' href='/pagamenti?vista=mensili&mese={mese}&anno={anno}'>MENSILE</a></nav>
          {selector}{saved}{error}{form_html}"""
_new_nav = """          <nav class='bmpv7-tabs'><a class='{'on' if vista=='iscrizioni' else ''}' href='/pagamenti?vista=iscrizioni&stagione={stagione}&mese={mese}&anno={anno}'>ISCRIZIONE</a><a class='{'on' if vista=='mensili' else ''}' href='/pagamenti?vista=mensili&mese={mese}&anno={anno}'>MENSILE</a></nav>
          <div class='bmpv8-admin'><a href='{e(expense_href)}'>USCITE</a><a href='{e(collab_href)}'>COLLABORATORI</a><a href='{e(collab_receipts_href)}'>RICEVUTE COLLABORATORI</a></div>
          {selector}{saved}{error}{form_html}"""
if _old_nav in _core_v8:
    _core_v8=_core_v8.replace(_old_nav,_new_nav,1)
    _changed_v8=True

_old_css = """.bmpv7-actions a{{padding:9px 11px;border-radius:9px;background:#2563eb;color:#fff!important;text-decoration:none;font-size:11px;font-weight:950}}.bmpv7-actions a+ a{{background:#0f766e}}"""
_new_css = """.bmpv7-actions a{{padding:9px 11px;border-radius:9px;background:#2563eb;color:#fff!important;text-decoration:none;font-size:11px;font-weight:950}}.bmpv7-actions a+ a{{background:#0f766e}}.bmpv7-actions a.doc{{background:#334155!important}}.bmpv8-admin{{display:flex;gap:8px;flex-wrap:wrap;margin:-4px 0 13px}}.bmpv8-admin a{{padding:9px 12px;border-radius:10px;background:#172554;color:#dbeafe!important;text-decoration:none;font-size:11px;font-weight:950;border:1px solid rgba(96,165,250,.26)}}"""
if _old_css in _core_v8:
    _core_v8=_core_v8.replace(_old_css,_new_css,1)
    _changed_v8=True

if 'BODYMIND_R123_ADMIN_CONVERGENCE_V8' not in _core_v8:
    _core_v8 += r'''

# BODYMIND_R123_ADMIN_CONVERGENCE_V8
def _bodymind_admin_route_v8(kind):
    """Resolve existing business routes at runtime instead of inventing URLs."""
    best=[]
    for rule in app.url_map.iter_rules():
        try:
            path=str(rule.rule); ep=str(rule.endpoint).lower()
            methods=set(rule.methods or set())
        except Exception:
            continue
        if 'GET' not in methods or '<' in path:
            continue
        low=(path+' '+ep).lower()
        score=0
        if kind=='collaboratori':
            if 'collabor' not in low: continue
            if 'ricevut' in low or 'pdf' in low or 'delete' in low or 'elimina' in low: continue
            score=20
            if path.rstrip('/')=='/collaboratori': score+=100
        elif kind=='ricevute_collaboratori':
            if 'collabor' not in low or 'ricevut' not in low: continue
            if 'pdf' in low or 'delete' in low or 'elimina' in low: continue
            score=30
        elif kind=='uscite':
            if path.rstrip('/')=='/pagamenti/uscite': continue
            words=('uscit','spes','prima-nota','prima_nota','moviment','cassa')
            if not any(w in low for w in words): continue
            # Avoid delete/PDF/detail routes.
            if any(w in low for w in ('delete','elimina','pdf','<')): continue
            score=20
            if 'uscit' in low or 'spes' in low: score+=40
        else:
            continue
        best.append((score,len(path),path))
    if not best:
        return ''
    best.sort(key=lambda x:(-x[0],x[1],x[2]))
    return best[0][2]


def _bodymind_uscite_schema_v8(conn):
    conn.execute("""
      CREATE TABLE IF NOT EXISTS bodymind_uscite(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT NOT NULL,
        descrizione TEXT NOT NULL,
        categoria TEXT,
        importo REAL NOT NULL,
        metodo TEXT,
        note TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      )
    """)


@app.route('/pagamenti/uscite',methods=['GET','POST'])
@login_required
def _bodymind_uscite_v8():
    # Prefer an already existing accounting/expense module if the app has one.
    existing=_bodymind_admin_route_v8('uscite')
    if existing and existing!='/pagamenti/uscite' and request.method=='GET' and request.args.get('fallback')!='1':
        return redirect(existing,302)

    from datetime import date as _date, datetime as _dt
    conn=db(); conn.row_factory=sqlite3.Row
    _bodymind_uscite_schema_v8(conn)
    saved=False; err=''
    if request.method=='POST':
        data=(request.form.get('data') or _date.today().isoformat()).strip()
        descrizione=(request.form.get('descrizione') or '').strip()
        categoria=(request.form.get('categoria') or '').strip()
        metodo=(request.form.get('metodo') or '').strip()
        note=(request.form.get('note') or '').strip()[:1500]
        try: importo=float(str(request.form.get('importo') or '').replace(',','.'))
        except Exception: importo=-1
        try: _date.fromisoformat(data)
        except Exception: data=_date.today().isoformat()
        if not descrizione or importo<0:
            err='Inserisci descrizione e importo validi.'
        else:
            now=_dt.now().isoformat(timespec='seconds')
            conn.execute(
                "INSERT INTO bodymind_uscite(data,descrizione,categoria,importo,metodo,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (data,descrizione,categoria,importo,metodo,note,now,now)
            )
            conn.commit(); saved=True
    rows=conn.execute("SELECT * FROM bodymind_uscite ORDER BY data DESC,id DESC LIMIT 200").fetchall()
    total=float(conn.execute("SELECT COALESCE(SUM(importo),0) FROM bodymind_uscite").fetchone()[0] or 0)
    conn.close()
    items=''.join(
        "<tr><td>"+e(str(r['data']))+"</td><td><b>"+e(str(r['descrizione']))+"</b><br><small>"+e(str(r['categoria'] or ''))+"</small></td><td>€ "+e(("%.2f" % float(r['importo'] or 0)).replace('.',','))+"</td><td>"+e(str(r['metodo'] or ''))+"</td></tr>"
        for r in rows
    ) or "<tr><td colspan='4'>Nessuna uscita registrata.</td></tr>"
    msg="<div class='bmout-ok'>Uscita registrata.</div>" if saved else ("<div class='bmout-err'>"+e(err)+"</div>" if err else "")
    html=f"""
    <section class='bmout'>
      <div class='bmout-head'><div><span>AMMINISTRAZIONE</span><h1>Uscite</h1><p>Spese e uscite di cassa. Gli incassi di atlete restano nel modulo Pagamenti.</p></div><strong>Totale € {("%.2f" % total).replace('.',',')}</strong></div>
      <div class='bmout-links'><a href='/pagamenti'>Pagamenti</a><a href='{e(_bodymind_admin_route_v8("collaboratori") or "/collaboratori")}'>Collaboratori</a></div>
      {msg}
      <form method='post' class='bmout-form'>
        <input type='hidden' name='csrf_token' value='{e(csrf_token())}'>
        <label>Data<input type='date' name='data' value='{_date.today().isoformat()}' required></label>
        <label>Descrizione<input name='descrizione' required placeholder='Es. affitto sala'></label>
        <label>Categoria<input name='categoria' placeholder='Affitto, attrezzatura, utenze…'></label>
        <label>Importo €<input type='number' step='0.01' min='0' name='importo' required></label>
        <label>Metodo<select name='metodo'><option>contanti</option><option>bonifico</option><option>carta</option><option>altro</option></select></label>
        <label class='wide'>Note<textarea name='note' rows='2'></textarea></label>
        <button>Registra uscita</button>
      </form>
      <div class='bmout-table'><table><thead><tr><th>Data</th><th>Uscita</th><th>Importo</th><th>Metodo</th></tr></thead><tbody>{items}</tbody></table></div>
    </section>
    <style>
    .bmout{{padding:18px;border-radius:20px;background:#081626;color:#f8fafc}}.bmout-head{{display:flex;justify-content:space-between;gap:12px;align-items:center}}.bmout-head span{{font-size:10px;color:#7dd3fc;font-weight:950;letter-spacing:.14em}}.bmout-head h1{{margin:4px 0}}.bmout-head p{{margin:0;color:#cbd5e1}}.bmout-links{{display:flex;gap:8px;margin:13px 0}}.bmout-links a{{padding:9px 12px;border-radius:9px;background:#1d4ed8;color:white!important;text-decoration:none;font-weight:900}}.bmout-form{{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:9px;padding:13px;background:#0c2035;border-radius:14px}}.bmout-form label{{display:grid;gap:5px;font-size:11px;font-weight:900}}.bmout-form input,.bmout-form select,.bmout-form textarea{{width:100%;padding:9px;border-radius:9px;border:1px solid #334155;background:#06111f;color:#fff}}.bmout-form .wide{{grid-column:1/-1}}.bmout-form button{{min-height:43px;border:0;border-radius:9px;background:#dc2626;color:#fff;font-weight:950}}.bmout-table{{overflow:auto;margin-top:12px}}.bmout-table table{{width:100%;border-collapse:collapse}}.bmout-table th,.bmout-table td{{padding:9px;border-bottom:1px solid #1e293b;text-align:left}}.bmout-ok,.bmout-err{{padding:9px 11px;border-radius:9px;margin:8px 0}}.bmout-ok{{background:#14532d}}.bmout-err{{background:#7f1d1d}}
    @media(max-width:800px){{.bmout-form{{grid-template-columns:1fr 1fr}}.bmout-form .wide{{grid-column:1/-1}}}}
    </style>
    """
    return layout(html)


@app.after_request
def _bodymind_desktop_admin_nav_v8(resp):
    try:
        if request.method!='GET' or int(getattr(resp,'status_code',200) or 200)!=200:
            return resp
        if 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp
        html=resp.get_data(as_text=True)
        if 'BODYMIND_DESKTOP_ADMIN_NAV_V8' in html:
            return resp
        collab=_bodymind_admin_route_v8('collaboratori') or '/collaboratori'
        receipts=_bodymind_admin_route_v8('ricevute_collaboratori') or collab
        expense=_bodymind_admin_route_v8('uscite') or '/pagamenti/uscite'
        inject=f"""<!-- BODYMIND_DESKTOP_ADMIN_NAV_V8 -->
        <div id='bmAdminNavV8'>
          <span>AMMINISTRAZIONE</span>
          <a href='/pagamenti'>Pagamenti</a>
          <a href='{e(expense)}'>Uscite</a>
          <a href='{e(collab)}'>Collaboratori</a>
          <a href='{e(receipts)}'>Ricevute collaboratori</a>
        </div>
        <style>
        #bmAdminNavV8{{display:none}}
        @media(min-width:901px){{#bmAdminNavV8.bm-admin-mounted{{display:grid;gap:4px;margin:10px 8px;padding:9px;border-radius:12px;background:rgba(15,23,42,.62);border:1px solid rgba(148,163,184,.16)}}#bmAdminNavV8 span{{font-size:9px;letter-spacing:.13em;color:#94a3b8;font-weight:950}}#bmAdminNavV8 a{{padding:7px 8px;border-radius:8px;color:inherit!important;text-decoration:none;font-size:12px;font-weight:800}}#bmAdminNavV8 a:hover{{background:rgba(59,130,246,.14)}}}}
        </style>
        <script>(function(){{var box=document.getElementById('bmAdminNavV8');if(!box)return;var side=document.querySelector('aside nav,aside,.sidebar,[class*="sidebar"]');if(side){{side.appendChild(box);box.classList.add('bm-admin-mounted');}}else{{box.remove();}}}})();</script>"""
        if '</body>' in html: html=html.replace('</body>',inject+'</body>',1)
        else: html+=inject
        resp.set_data(html)
    except Exception as exc:
        print('[admin-nav-v8-warning] '+repr(exc),flush=True)
    return resp
'''
    _changed_v8=True

if _changed_v8:
    CORE.write_text(_core_v8,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)

# Read-only integrity check: existing payments/receipts must remain untouched here.
_c=sqlite3.connect(str(DB),timeout=20)
try:
    _integrity=str(_c.execute('PRAGMA integrity_check').fetchone()[0])
    _fk=len(_c.execute('PRAGMA foreign_key_check').fetchall())
    _pc=int(_c.execute('SELECT COUNT(*) FROM pagamenti').fetchone()[0]) if _c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pagamenti'").fetchone() else 0
    _rc=int(_c.execute('SELECT COUNT(*) FROM ricevute').fetchone()[0]) if _c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ricevute'").fetchone() else 0
finally:
    _c.close()
if _integrity.lower()!='ok' or _fk:
    raise RuntimeError('R123 V8 DB integrity guard failed')
print('[r123-admin-v8] PASS verify-doc + cash-entry + expenses + collaborators-nav payments='+str(_pc)+' receipts='+str(_rc)+' integrity='+_integrity+' fk='+str(_fk),flush=True)


# BODYMIND_R123_ADMIN_RESTORE_V9
# Restore business-critical administration without restoring stale duplicate UIs.
# Existing routes/data win; backups are audited, never blindly copied over newer core.
_core_v9=CORE.read_text(encoding='utf-8',errors='replace')
_changed_v9=False

# Payment row: real document review queue + archive access.
_old_doc="""            dh=f"/documenti?tesserato_id={tid}"
            rows.append((0 if not focus_ok else 1,
                "<div class='bmpv7-row "+("due" if not focus_ok else "paid")+"'>"
                +"<div class='bmpv7-person'><b>"+e(_name(a))+"</b><small>Iscrizione: "+("PAGATA" if eok else "da pagare")+" · "+months[mese]+": "+("PAGATO" if mok else "da pagare")+"</small></div>"
                +"<div class='bmpv7-actions'><a class='doc' href='"+dh+"'>Verifica documento</a><a href='"+eh+"'>"+("Modifica incasso iscrizione" if eok else "Registra incasso iscrizione")+"</a><a href='"+mh+"'>"+("Modifica incasso "+months[mese] if mok else "Registra incasso "+months[mese])+"</a></div>"
                +"</div>"
            ))"""
_new_doc="""            dh=f"/documenti/da-verificare?tesserato_id={tid}"
            ah=f"/documenti?tesserato_id={tid}"
            rows.append((0 if not focus_ok else 1,
                "<div class='bmpv7-row "+("due" if not focus_ok else "paid")+"'>"
                +"<div class='bmpv7-person'><b>"+e(_name(a))+"</b><small>Iscrizione: "+("PAGATA" if eok else "da pagare")+" · "+months[mese]+": "+("PAGATO" if mok else "da pagare")+"</small></div>"
                +"<div class='bmpv7-actions'><a class='doc' href='"+dh+"'>Verifica documento</a><a class='doc' href='"+ah+"'>Archivio</a><a href='"+eh+"'>"+("Modifica incasso iscrizione" if eok else "Registra incasso iscrizione")+"</a><a href='"+mh+"'>"+("Modifica incasso "+months[mese] if mok else "Registra incasso "+months[mese])+"</a></div>"
                +"</div>"
            ))"""
if _old_doc in _core_v9:
    _core_v9=_core_v9.replace(_old_doc,_new_doc,1); _changed_v9=True

# Preserve configured monthly amount/note when opening a new payment form.
_old_qpaid="""        qpaid=set()
        for q in qrows:
            st=str(q.get('stato') or '').lower()
            if any(x in st for x in ('pagat','saldat','paid','incassat','complet')):
                qpaid.add(int(q.get('tesserato_id') or 0))"""
_new_qpaid="""        qpaid=set(); quote_by_tid={}
        for q in qrows:
            qtid=int(q.get('tesserato_id') or 0)
            if qtid and qtid not in quote_by_tid: quote_by_tid[qtid]=q
            st=str(q.get('stato') or '').lower()
            if any(x in st for x in ('pagat','saldat','paid','incassat','complet')):
                qpaid.add(qtid)"""
if _old_qpaid in _core_v9:
    _core_v9=_core_v9.replace(_old_qpaid,_new_qpaid,1); _changed_v9=True

_old_amount="""                amount=(str(existing.get('importo') or '') if existing else '')
                paydate=(str(existing.get('data') or today.isoformat()) if existing else today.isoformat())
                method=(str(existing.get('metodo_pagamento') or 'contanti') if existing else 'contanti')
                note=(str(existing.get('note_pagamento') or '') if existing else '')"""
_new_amount="""                qsel=quote_by_tid.get(selected_tid) if action_tipo=='mensile' else None
                if existing:
                    amount=str(existing.get('importo') or '')
                    note=str(existing.get('note_pagamento') or '')
                else:
                    try:
                        qamount=float(qsel.get('importo_dovuto') or 0) if qsel else 0
                    except Exception:
                        qamount=0
                    amount=(str(qamount) if qamount>0 else '')
                    note=(str(qsel.get('note') or '') if qsel else '')
                paydate=(str(existing.get('data') or today.isoformat()) if existing else today.isoformat())
                method=(str(existing.get('metodo_pagamento') or 'contanti') if existing else 'contanti')"""
if _old_amount in _core_v9:
    _core_v9=_core_v9.replace(_old_amount,_new_amount,1); _changed_v9=True

# Expand the dynamic route resolver: prefer existing canonical business pages.
_old_resolver="""        elif kind=='uscite':
            if path.rstrip('/')=='/pagamenti/uscite': continue
            words=('uscit','spes','prima-nota','prima_nota','moviment','cassa')
            if not any(w in low for w in words): continue
            # Avoid delete/PDF/detail routes.
            if any(w in low for w in ('delete','elimina','pdf','<')): continue
            score=20
            if 'uscit' in low or 'spes' in low: score+=40
        else:
            continue"""
_new_resolver="""        elif kind=='contabilita':
            if 'contabil' not in low: continue
            if any(w in low for w in ('delete','elimina','pdf','<')): continue
            score=40
            if path.rstrip('/')=='/contabilita': score+=120
        elif kind=='ricevute':
            if 'ricevut' not in low or 'collabor' in low: continue
            if any(w in low for w in ('delete','elimina','pdf','<')): continue
            score=35
            if path.rstrip('/')=='/ricevute': score+=100
        elif kind=='lul':
            if not ('lul' in low or ('collabor' in low and 'ademp' in low) or 'uniemens' in low): continue
            if any(w in low for w in ('delete','elimina','pdf','<')): continue
            score=35
        elif kind=='documenti':
            if path.rstrip('/')!='/documenti': continue
            score=150
        elif kind=='document_review':
            if path.rstrip('/')!='/documenti/da-verificare': continue
            score=150
        elif kind=='centro':
            if path.rstrip('/') not in ('/cuore-operativo','/centro-operativo'): continue
            score=150
        elif kind=='uscite':
            if path.rstrip('/')=='/pagamenti/uscite': continue
            if path.rstrip('/')=='/contabilita':
                score=200
            else:
                words=('uscit','spes','prima-nota','prima_nota','moviment','cassa','contabil')
                if not any(w in low for w in words): continue
                if any(w in low for w in ('delete','elimina','pdf','<')): continue
                score=20
                if 'uscit' in low or 'spes' in low or 'contabil' in low: score+=40
        else:
            continue"""
if _old_resolver in _core_v9:
    _core_v9=_core_v9.replace(_old_resolver,_new_resolver,1); _changed_v9=True

# Payment page admin strip: compact gateways only; payment operations remain ISCRIZIONE/MENSILE.
_old_vars="""        collab_href=_bodymind_admin_route_v8('collaboratori') or '/collaboratori'
        collab_receipts_href=_bodymind_admin_route_v8('ricevute_collaboratori') or collab_href
        expense_href=_bodymind_admin_route_v8('uscite') or '/pagamenti/uscite'"""
_new_vars="""        collab_href=_bodymind_admin_route_v8('collaboratori') or '/collaboratori'
        collab_receipts_href=_bodymind_admin_route_v8('ricevute_collaboratori') or collab_href
        accounting_href=_bodymind_admin_route_v8('contabilita') or '/contabilita'
        receipts_href=_bodymind_admin_route_v8('ricevute') or '/ricevute'
        lul_href=_bodymind_admin_route_v8('lul') or collab_href
        documents_href=_bodymind_admin_route_v8('documenti') or '/documenti'
        review_href=_bodymind_admin_route_v8('document_review') or '/documenti/da-verificare'
        center_href=_bodymind_admin_route_v8('centro') or '/cuore-operativo'
        expense_href=_bodymind_admin_route_v8('uscite') or accounting_href"""
if _old_vars in _core_v9:
    _core_v9=_core_v9.replace(_old_vars,_new_vars,1); _changed_v9=True

_old_strip="""          <div class='bmpv8-admin'><a href='{e(expense_href)}'>USCITE</a><a href='{e(collab_href)}'>COLLABORATORI</a><a href='{e(collab_receipts_href)}'>RICEVUTE COLLABORATORI</a></div>"""
_new_strip="""          <div class='bmpv8-admin'><span>AMMINISTRAZIONE</span><a href='{e(accounting_href)}'>CONTABILITÀ / USCITE</a><a href='{e(receipts_href)}'>RICEVUTE</a><a href='{e(collab_href)}'>COLLABORATORI</a><a href='{e(lul_href)}'>LUL / ADEMPIMENTI</a><a href='{e(documents_href)}'>ARCHIVIO</a><a href='{e(review_href)}'>DA VERIFICARE</a></div>"""
if _old_strip in _core_v9:
    _core_v9=_core_v9.replace(_old_strip,_new_strip,1); _changed_v9=True

# Desktop admin nav restored as a stable business area.
_old_navvars="""        collab=_bodymind_admin_route_v8('collaboratori') or '/collaboratori'
        receipts=_bodymind_admin_route_v8('ricevute_collaboratori') or collab
        expense=_bodymind_admin_route_v8('uscite') or '/pagamenti/uscite'"""
_new_navvars="""        collab=_bodymind_admin_route_v8('collaboratori') or '/collaboratori'
        collab_receipts=_bodymind_admin_route_v8('ricevute_collaboratori') or collab
        accounting=_bodymind_admin_route_v8('contabilita') or '/contabilita'
        receipts=_bodymind_admin_route_v8('ricevute') or '/ricevute'
        lul=_bodymind_admin_route_v8('lul') or collab
        documents=_bodymind_admin_route_v8('documenti') or '/documenti'
        review=_bodymind_admin_route_v8('document_review') or '/documenti/da-verificare'
        center=_bodymind_admin_route_v8('centro') or '/cuore-operativo'
        expense=_bodymind_admin_route_v8('uscite') or accounting"""
if _old_navvars in _core_v9:
    _core_v9=_core_v9.replace(_old_navvars,_new_navvars,1); _changed_v9=True

_old_navlinks="""          <a href='/pagamenti'>Pagamenti</a>
          <a href='{e(expense)}'>Uscite</a>
          <a href='{e(collab)}'>Collaboratori</a>
          <a href='{e(receipts)}'>Ricevute collaboratori</a>"""
_new_navlinks="""          <a href='{e(center)}'>Centro operativo</a>
          <a href='/pagamenti'>Pagamenti</a>
          <a href='{e(accounting)}'>Contabilità / Uscite</a>
          <a href='{e(receipts)}'>Ricevute</a>
          <a href='{e(collab)}'>Collaboratori</a>
          <a href='{e(lul)}'>LUL / Adempimenti</a>
          <a href='{e(collab_receipts)}'>Ricevute collaboratori</a>
          <a href='{e(documents)}'>Archivio documentale</a>
          <a href='{e(review)}'>Documenti da verificare</a>"""
if _old_navlinks in _core_v9:
    _core_v9=_core_v9.replace(_old_navlinks,_new_navlinks,1); _changed_v9=True

if 'BODYMIND_R123_ADMIN_RESTORE_V9' not in _core_v9:
    _core_v9 += r'''

# BODYMIND_R123_ADMIN_RESTORE_V9
@app.after_request
def _bodymind_payment_month_alerts_v9(resp):
    try:
        if request.method!='GET' or request.path!='/pagamenti' or int(getattr(resp,'status_code',200) or 200)!=200:
            return resp
        if 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp
        html=resp.get_data(as_text=True)
        if 'BODYMIND_PAYMENT_MONTH_ALERTS_V9_RENDERED' in html:
            return resp
        try:
            helper=bodymind_monthly_due_summary
        except Exception:
            return resp
        c=db(); c.row_factory=sqlite3.Row
        try: summary=helper(c)
        finally:
            try:c.close()
            except Exception:pass
        if not summary:
            return resp
        months=['','Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno','Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre']
        chips=''.join(
            "<a class='"+("ok" if int(x['mancanti'])==0 else "due")+"' href='/pagamenti?vista=mensili&mese="+str(x['mese'])+"&anno="+str(x['anno'])+"'><b>"+months[int(x['mese'])]+"</b><span>"+(str(x['mancanti'])+" da pagare" if int(x['mancanti']) else "completo")+"</span></a>"
            for x in summary
        )
        block="<!-- BODYMIND_PAYMENT_MONTH_ALERTS_V9_RENDERED --><div class='bmpv9-months'><strong>Mensili della stagione</strong><div>"+chips+"</div></div><style>.bmpv9-months{margin:9px 0 12px;padding:10px;border-radius:12px;background:#0b1d31}.bmpv9-months>strong{display:block;margin-bottom:7px;font-size:11px;color:#bfdbfe}.bmpv9-months>div{display:flex;gap:7px;flex-wrap:wrap}.bmpv9-months a{display:grid;gap:2px;min-width:110px;padding:8px 10px;border-radius:9px;color:white!important;text-decoration:none;font-size:11px}.bmpv9-months a.due{background:#7f1d1d}.bmpv9-months a.ok{background:#14532d}.bmpv9-months span{color:#e2e8f0}</style>"
        anchor="<div class='bmpv7-list'>"
        if 'BODYMIND_R123_PAYMENT_FORM_CANONICAL_V7' in html and anchor in html:
            html=html.replace(anchor,block+anchor,1)
            resp.set_data(html)
    except Exception as exc:
        print('[payment-month-alerts-v9-warning] '+repr(exc),flush=True)
    return resp
'''
    _changed_v9=True

if _changed_v9:
    CORE.write_text(_core_v9,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)

# Fresh-process read-only audit: prove business routes and preserved backups/data.
_audit_v9=r"""
import json,sqlite3,sys
from pathlib import Path
sys.path.insert(0,"/data/top2_app")
import app as _full
from asd_app.core import app
app.config["TESTING"]=True
client=app.test_client()
with client.session_transaction() as sess:
    sess.update({"logged":True,"logged_in":True,"username":"admin","display_name":"Admin Restore QA","role":"admin","tenant_slug":"default","user_id":1,"is_admin":True,"admin":True})
routes=[]
for rule in app.url_map.iter_rules():
    p=str(rule.rule); ep=str(rule.endpoint)
    low=(p+" "+ep).lower()
    if any(k in low for k in ("contabil","collabor","ricevut","lul","ademp","document-hub","documenti/da-verificare","cuore-operativo")):
        routes.append({"route":p,"endpoint":ep,"methods":sorted(m for m in (rule.methods or set()) if m not in ("HEAD","OPTIONS"))})
checks={}
for p in ("/contabilita","/documenti","/documenti/da-verificare","/cuore-operativo","/pagamenti"):
    rr=client.get(p,follow_redirects=False)
    checks[p]=rr.status_code
backs=[]
root=Path("/data/release_backups")
if root.exists():
    for x in sorted(root.iterdir()):
        n=x.name.lower()
        if any(k in n for k in ("r110","r115","r123","admin","collab","contab","document")):
            backs.append(x.name)
conn=sqlite3.connect("/data/tenants/default/asd.db",timeout=20)
try:
    counts={}
    for t in ("tesserati","pagamenti","ricevute","quote_mensili","documenti","inbound_documents"):
        counts[t]=int(conn.execute("SELECT COUNT(*) FROM "+t).fetchone()[0]) if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone() else None
    integrity=str(conn.execute("PRAGMA integrity_check").fetchone()[0]); fk=len(conn.execute("PRAGMA foreign_key_check").fetchall())
finally:conn.close()
print("[r123-admin-v9-audit] "+json.dumps({"routes":routes,"status":checks,"backups":backs[-40:],"counts":counts,"integrity":integrity,"fk":fk},ensure_ascii=False),flush=True)
if integrity.lower()!="ok" or fk or any(v not in (200,302) for v in checks.values()):
    raise RuntimeError("R123 V9 audit failed")
"""
_p=subprocess.run([sys.executable,"-c",_audit_v9],capture_output=True,text=True,timeout=120)
print((_p.stdout or "").strip(),flush=True)
if _p.returncode!=0:
    raise RuntimeError("R123 V9 child audit failed "+((_p.stderr or "")+(_p.stdout or ""))[-5000:])
print('[r123-admin-v9] PASS admin-functions-restored-via-live-routes backups-preserved data-intact',flush=True)


# BODYMIND_R123_ONBOARDING_PAYMENT_SYNC_V10
# A paid athlete/document truth must immediately reconcile the stale onboarding
# flags used by dashboard/tesserati. Monthly arrears remain operational tasks,
# but stale "pagamenti da verificare" is never allowed after canonical payment.
_core_v10=CORE.read_text(encoding='utf-8',errors='replace')
_changed_v10=False

if 'BODYMIND_R123_ONBOARDING_PAYMENT_SYNC_V10' not in _core_v10:
    _core_v10 += r'''

# BODYMIND_R123_ONBOARDING_PAYMENT_SYNC_V10
def _bodymind_reconcile_athlete_status_v10(conn, tid):
    from datetime import datetime as _bm_dt, date as _bm_date
    tid=int(tid or 0)
    if tid<=0: return False
    row=conn.execute("SELECT * FROM tesserati WHERE id=?",(tid,)).fetchone()
    if not row: return False
    try:
        from .document_sync_core_r143 import truth as _bm_doc_truth
        d=_bm_doc_truth(conn,row)
    except Exception as exc:
        print('[onboarding-sync-v10-doc-warning] '+repr(exc),flush=True)
        d={'mu':bool(row['iscrizione_firmata'] if 'iscrizione_firmata' in row.keys() else 0),
           'med_present':bool(row['certificato_scadenza'] if 'certificato_scadenza' in row.keys() else ''),
           'med_ok':False,'med_state':'Da verificare','tutela':True}

    today=_bm_date.today()
    p=bodymind_payment_truth(conn,tesserato_id=tid,mese=today.month,anno=today.year)
    pr=(p.get('rows') or [{}])[0] if (p.get('rows') or []) else {}
    enroll=bool(pr.get('iscrizione_pagata'))
    monthly=bool(pr.get('mensile_pagato'))

    mu=bool(d.get('mu'))
    med_present=bool(d.get('med_present'))
    med_ok=bool(d.get('med_ok'))
    tutela=bool(d.get('tutela'))
    docs_ok=bool(mu and med_ok and tutela)
    pay_ok=bool(enroll and monthly)
    overall=bool(docs_ok and pay_ok)

    reasons=[]
    if not mu: reasons.append('modulo unico da completare')
    if not med_present: reasons.append('certificato medico mancante')
    elif not med_ok:
        state=str(d.get('med_state') or '').strip().lower()
        reasons.append('certificato medico scaduto' if 'scadut' in state else 'certificato medico da verificare')
    if not tutela: reasons.append('tutela/consensi da completare')
    if not enroll: reasons.append('quota iscrizione non registrata')
    if not monthly: reasons.append('mensile '+str(today.month).zfill(2)+'/'+str(today.year)+' non registrato')

    if overall:
        status='active'; reason=''
    elif not docs_ok and not pay_ok:
        status='waiting_documents_payment'; reason='; '.join(reasons)
    elif not docs_ok:
        status='waiting_documents'; reason='; '.join(reasons)
    else:
        status='waiting_payment'; reason='; '.join(reasons)

    cols={str(x[1]) for x in conn.execute('PRAGMA table_info(tesserati)').fetchall()}
    changes={}
    desired={
        'blocco_tesseramento':0 if overall else 1,
        'onboarding_status':status,
        'onboarding_blocked_reason':reason,
    }
    for k,v in desired.items():
        if k not in cols: continue
        cur=row[k]
        if str(cur if cur is not None else '')!=str(v if v is not None else ''):
            changes[k]=v
    if not changes:
        return False
    if 'updated_at' in cols:
        changes['updated_at']=_bm_dt.now().isoformat(timespec='seconds')
    sets=','.join(k+'=?' for k in changes)
    conn.execute("UPDATE tesserati SET "+sets+" WHERE id=?",tuple(changes.values())+(tid,))
    return {'tid':tid,'status':status,'reason':reason,'overall':overall}


def bodymind_reconcile_all_athlete_statuses_v10(conn):
    ids=[int(x[0]) for x in conn.execute("SELECT id FROM tesserati WHERE COALESCE(attivo,1)=1 ORDER BY id").fetchall()]
    changed=[]
    for tid in ids:
        x=_bodymind_reconcile_athlete_status_v10(conn,tid)
        if x: changed.append(x)
    return changed
'''
    _changed_v10=True

# V7 write path: reconcile the same athlete before the transaction commits.
_old_commit="""        c.commit()
    except Exception as exc:
        try:c.rollback()"""
_new_commit="""        try:
            _bodymind_reconcile_athlete_status_v10(c,tid)
        except Exception as _sync_exc:
            print('[payment-v7-onboarding-sync-warning] '+repr(_sync_exc),flush=True)
        c.commit()
    except Exception as exc:
        try:c.rollback()"""
# Constrain replacement to the canonical V7 function region.
_v7a=_core_v10.find("def _bodymind_payment_register_v7():")
_v7b=_core_v10.find("@app.after_request\\ndef _bodymind_payment_module_v7",_v7a)
if _v7a>=0 and _v7b>_v7a:
    _region=_core_v10[_v7a:_v7b]
    if _old_commit in _region and "payment-v7-onboarding-sync-warning" not in _region:
        _region=_region.replace(_old_commit,_new_commit,1)
        _core_v10=_core_v10[:_v7a]+_region+_core_v10[_v7b:]
        _changed_v10=True

if _changed_v10:
    CORE.write_text(_core_v10,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)

# Backup before the one-time reconciliation of stale status flags.
_v10_backup=BACK/'pre_v10_onboarding_status.db'
if not _v10_backup.exists():
    shutil.copy2(DB,_v10_backup)

_v10_qa=r"""
import json,sqlite3,sys
sys.path.insert(0,"/data/top2_app")
import app as _full
from asd_app.core import app,db,bodymind_reconcile_all_athlete_statuses_v10,bodymind_monthly_due_summary
c=db(); c.row_factory=sqlite3.Row
try:
    changed=bodymind_reconcile_all_athlete_statuses_v10(c)
    c.commit()
    monthly=bodymind_monthly_due_summary(c)
    stale=[dict(x) for x in c.execute(
      "SELECT id,nome,cognome,onboarding_status,onboarding_blocked_reason FROM tesserati WHERE COALESCE(attivo,1)=1 AND lower(coalesce(onboarding_blocked_reason,'')) LIKE '%pagamenti da verificare%' ORDER BY id"
    ).fetchall()]
    integ=str(c.execute("PRAGMA integrity_check").fetchone()[0]); fk=len(c.execute("PRAGMA foreign_key_check").fetchall())
finally:c.close()
print("[r123-onboarding-v10-audit] "+json.dumps({"changed":changed,"monthly":monthly,"stale_generic_payment_reasons":stale,"integrity":integ,"fk":fk},ensure_ascii=False),flush=True)
if integ.lower()!="ok" or fk or stale:
    raise RuntimeError("V10 onboarding/payment sync failed")
"""
_v10p=subprocess.run([sys.executable,"-c",_v10_qa],capture_output=True,text=True,timeout=180)
print((_v10p.stdout or "").strip(),flush=True)
if _v10p.returncode!=0:
    raise RuntimeError("R123 V10 child audit failed "+((_v10p.stderr or "")+(_v10p.stdout or ""))[-6000:])
print('[r123-onboarding-v10] PASS payment+document truth reconciles tesseramento/dashboard status',flush=True)


# BODYMIND_R123_EXPENSE_ATTACHMENTS_V11
# Canonical Uscite module: one expense row, optional supporting document,
# preview/download, later attachment/update. Payment/enrollment rows are read-only here.
_v11_backup=BACK/'pre_v11_expense_attachments.db'
if not _v11_backup.exists():
    shutil.copy2(DB,_v11_backup)

_v11_conn=sqlite3.connect(str(DB),timeout=30)
try:
    _v11_before={}
    for _t in ('tesserati','pagamenti','ricevute'):
        _v11_before[_t]=int(_v11_conn.execute("SELECT COUNT(*) FROM "+_t).fetchone()[0]) if _v11_conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(_t,)).fetchone() else 0
    _v11_conn.execute("""
      CREATE TABLE IF NOT EXISTS bodymind_uscite(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT NOT NULL,
        descrizione TEXT NOT NULL,
        categoria TEXT,
        importo REAL NOT NULL,
        metodo TEXT,
        note TEXT,
        allegato_path TEXT,
        allegato_nome TEXT,
        allegato_mime TEXT,
        allegato_size INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      )
    """)
    _v11_cols={str(x[1]) for x in _v11_conn.execute("PRAGMA table_info(bodymind_uscite)").fetchall()}
    for _col,_typ in (
        ('allegato_path','TEXT'),('allegato_nome','TEXT'),
        ('allegato_mime','TEXT'),('allegato_size','INTEGER')
    ):
        if _col not in _v11_cols:
            _v11_conn.execute("ALTER TABLE bodymind_uscite ADD COLUMN "+_col+" "+_typ)
    _v11_conn.commit()
    _v11_after={}
    for _t in ('tesserati','pagamenti','ricevute'):
        _v11_after[_t]=int(_v11_conn.execute("SELECT COUNT(*) FROM "+_t).fetchone()[0]) if _v11_conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(_t,)).fetchone() else 0
    _v11_integrity=str(_v11_conn.execute("PRAGMA integrity_check").fetchone()[0])
    _v11_fk=len(_v11_conn.execute("PRAGMA foreign_key_check").fetchall())
finally:
    _v11_conn.close()
if _v11_before!=_v11_after or _v11_integrity.lower()!='ok' or _v11_fk:
    raise RuntimeError('V11 expense attachment schema guard failed before='+str(_v11_before)+' after='+str(_v11_after)+' integrity='+_v11_integrity+' fk='+str(_v11_fk))

_core_v11=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R123_EXPENSE_ATTACHMENTS_V11' not in _core_v11:
    _core_v11 += r'''

# BODYMIND_R123_EXPENSE_ATTACHMENTS_V11
def _bodymind_uscite_schema_v11(conn):
    conn.execute("""
      CREATE TABLE IF NOT EXISTS bodymind_uscite(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT NOT NULL,
        descrizione TEXT NOT NULL,
        categoria TEXT,
        importo REAL NOT NULL,
        metodo TEXT,
        note TEXT,
        allegato_path TEXT,
        allegato_nome TEXT,
        allegato_mime TEXT,
        allegato_size INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      )
    """)
    cols={str(x[1]) for x in conn.execute("PRAGMA table_info(bodymind_uscite)").fetchall()}
    for col,typ in (
        ('allegato_path','TEXT'),('allegato_nome','TEXT'),
        ('allegato_mime','TEXT'),('allegato_size','INTEGER')
    ):
        if col not in cols:
            conn.execute("ALTER TABLE bodymind_uscite ADD COLUMN "+col+" "+typ)


def _bodymind_uscita_attachment_save_v11(upload, expense_id):
    if not upload or not getattr(upload,'filename',''):
        return None
    from pathlib import Path as _Path
    from werkzeug.utils import secure_filename as _secure_filename
    import mimetypes as _mimetypes, uuid as _uuid

    original=_secure_filename(str(upload.filename or '').strip())
    if not original:
        raise ValueError('Nome allegato non valido.')
    suffix=_Path(original).suffix.lower()
    allowed={'.pdf','.png','.jpg','.jpeg','.webp','.heic','.heif','.doc','.docx','.xls','.xlsx'}
    if suffix not in allowed:
        raise ValueError('Formato allegato non supportato.')
    root=_Path('/data/tenants/default/media/uscite')
    root.mkdir(parents=True,exist_ok=True)
    saved_name=str(int(expense_id))+'_'+_uuid.uuid4().hex[:12]+suffix
    dest=root/saved_name
    upload.save(str(dest))
    size=int(dest.stat().st_size)
    if size>20*1024*1024:
        try:dest.unlink()
        except Exception:pass
        raise ValueError('Allegato troppo grande: massimo 20 MB.')
    mime=(getattr(upload,'mimetype','') or _mimetypes.guess_type(original)[0] or 'application/octet-stream')
    return {'path':str(dest),'name':original,'mime':mime,'size':size}


def _bodymind_uscite_v11_impl():
    from datetime import date as _date, datetime as _dt
    conn=db(); conn.row_factory=sqlite3.Row
    _bodymind_uscite_schema_v11(conn)
    saved=False; err=''
    edit_id=parse_int(request.args.get('modifica') or request.form.get('uscita_id'),0)

    if request.method=='POST':
        data=(request.form.get('data') or _date.today().isoformat()).strip()
        descrizione=(request.form.get('descrizione') or '').strip()
        categoria=(request.form.get('categoria') or '').strip()
        metodo=(request.form.get('metodo') or '').strip()
        note=(request.form.get('note') or '').strip()[:2000]
        try: importo=float(str(request.form.get('importo') or '').replace(',','.'))
        except Exception: importo=-1
        try:_date.fromisoformat(data)
        except Exception:data=_date.today().isoformat()

        if not descrizione or importo<0:
            err='Inserisci descrizione e importo validi.'
        else:
            now=_dt.now().isoformat(timespec='seconds')
            try:
                if edit_id:
                    current=conn.execute("SELECT * FROM bodymind_uscite WHERE id=?",(edit_id,)).fetchone()
                    if not current:
                        raise ValueError('Uscita non trovata.')
                    conn.execute("""
                      UPDATE bodymind_uscite
                         SET data=?,descrizione=?,categoria=?,importo=?,metodo=?,note=?,updated_at=?
                       WHERE id=?
                    """,(data,descrizione,categoria,importo,metodo,note,now,edit_id))
                    expense_id=edit_id
                else:
                    cur=conn.execute("""
                      INSERT INTO bodymind_uscite(data,descrizione,categoria,importo,metodo,note,created_at,updated_at)
                      VALUES(?,?,?,?,?,?,?,?)
                    """,(data,descrizione,categoria,importo,metodo,note,now,now))
                    expense_id=int(cur.lastrowid)

                upload=request.files.get('allegato')
                if upload and getattr(upload,'filename',''):
                    meta=_bodymind_uscita_attachment_save_v11(upload,expense_id)
                    conn.execute("""
                      UPDATE bodymind_uscite
                         SET allegato_path=?,allegato_nome=?,allegato_mime=?,allegato_size=?,updated_at=?
                       WHERE id=?
                    """,(meta['path'],meta['name'],meta['mime'],meta['size'],now,expense_id))
                conn.commit()
                saved=True
                edit_id=expense_id
            except Exception as exc:
                try:conn.rollback()
                except Exception:pass
                err=str(exc) or 'Errore nel salvataggio uscita.'

    editing=conn.execute("SELECT * FROM bodymind_uscite WHERE id=?",(edit_id,)).fetchone() if edit_id else None
    rows=conn.execute("SELECT * FROM bodymind_uscite ORDER BY data DESC,id DESC LIMIT 300").fetchall()
    total=float(conn.execute("SELECT COALESCE(SUM(importo),0) FROM bodymind_uscite").fetchone()[0] or 0)
    conn.close()

    def _val(row,key,default=''):
        try:return row[key] if row and key in row.keys() and row[key] is not None else default
        except Exception:return default

    def _eur(v):
        try:return ('%.2f' % float(v or 0)).replace('.',',')
        except Exception:return '0,00'

    form_data={
        'id':int(_val(editing,'id',0) or 0),
        'data':str(_val(editing,'data',_date.today().isoformat())),
        'descrizione':str(_val(editing,'descrizione','')),
        'categoria':str(_val(editing,'categoria','')),
        'importo':str(_val(editing,'importo','')),
        'metodo':str(_val(editing,'metodo','contanti') or 'contanti'),
        'note':str(_val(editing,'note','')),
        'allegato_nome':str(_val(editing,'allegato_nome','')),
    }

    items=[]
    for r in rows:
        rid=int(r['id'])
        an=str(_val(r,'allegato_nome',''))
        ap=str(_val(r,'allegato_path',''))
        att=''
        if an and ap:
            att=("<a class='bmout11-preview' target='_blank' href='/pagamenti/uscite/allegato/"+str(rid)+"'>Anteprima</a>"
                 +"<a class='bmout11-download' href='/pagamenti/uscite/allegato/"+str(rid)+"?download=1'>Scarica</a>"
                 +"<small>"+e(an)+"</small>")
        else:
            att="<span class='bmout11-none'>Nessun giustificativo</span>"
        items.append(
          "<tr><td>"+e(str(r['data']))+"</td>"
          +"<td><b>"+e(str(r['descrizione']))+"</b><br><small>"+e(str(r['categoria'] or ''))+"</small></td>"
          +"<td><b>€ "+e(_eur(r['importo']))+"</b></td>"
          +"<td>"+e(str(r['metodo'] or ''))+"</td>"
          +"<td><div class='bmout11-files'>"+att+"</div></td>"
          +"<td><a class='bmout11-edit' href='/pagamenti/uscite?modifica="+str(rid)+"'>Modifica / Allega</a></td></tr>"
        )
    table_rows=''.join(items) or "<tr><td colspan='6'>Nessuna uscita registrata.</td></tr>"

    msg="<div class='bmout11-ok'>Uscita salvata correttamente.</div>" if saved else ("<div class='bmout11-err'>"+e(err)+"</div>" if err else "")
    attached=''
    if form_data['id'] and form_data['allegato_nome']:
        attached=("<div class='bmout11-current'>Giustificativo attuale: <b>"+e(form_data['allegato_nome'])+"</b> · "
                  +"<a target='_blank' href='/pagamenti/uscite/allegato/"+str(form_data['id'])+"'>Anteprima</a> · "
                  +"<a href='/pagamenti/uscite/allegato/"+str(form_data['id'])+"?download=1'>Scarica</a></div>")

    html=f"""
    <!-- BODYMIND_R123_EXPENSE_ATTACHMENTS_V11 -->
    <section class='bmout11'>
      <div class='bmout11-head'>
        <div><span>AMMINISTRAZIONE · USCITE</span><h1>{'Modifica uscita' if form_data['id'] else 'Registra uscita'}</h1>
        <p>Ogni uscita può avere un giustificativo collegato: ricevuta, fattura, tessere ente, scontrino o altro documento.</p></div>
        <strong>Totale uscite € {e(_eur(total))}</strong>
      </div>
      <nav class='bmout11-nav'>
        <a href='/pagamenti'>Pagamenti</a>
        <a class='on' href='/pagamenti/uscite'>Uscite</a>
        <a href='/collaboratori'>Collaboratori</a>
        <a href='/collaboratori/ricevute'>Ricevute collaboratori</a>
      </nav>
      {msg}
      <form method='post' enctype='multipart/form-data' class='bmout11-form'>
        <input type='hidden' name='csrf_token' value='{e(csrf_token())}'>
        <input type='hidden' name='uscita_id' value='{form_data["id"]}'>
        <label>Data<input type='date' name='data' required value='{e(form_data["data"])}'></label>
        <label>Descrizione<input name='descrizione' required value='{e(form_data["descrizione"])}' placeholder='Es. Tessere ente sportivo'></label>
        <label>Categoria<input name='categoria' value='{e(form_data["categoria"])}' placeholder='Tesseramento, affitto, attrezzatura…'></label>
        <label>Importo €<input type='number' step='0.01' min='0' name='importo' required value='{e(form_data["importo"])}'></label>
        <label>Metodo<select name='metodo'>
          {''.join("<option"+(" selected" if form_data["metodo"]==x else "")+">"+x+"</option>" for x in ('contanti','bonifico','carta','addebito','altro'))}
        </select></label>
        <label class='wide'>Note<textarea name='note' rows='2' placeholder='Dettagli o eccezioni…'>{e(form_data["note"])}</textarea></label>
        <label class='wide bmout11-upload'>Giustificativo / ricevuta
          <input type='file' name='allegato' accept='.pdf,.png,.jpg,.jpeg,.webp,.heic,.heif,.doc,.docx,.xls,.xlsx'>
          <small>PDF, immagini, Word o Excel · massimo 20 MB. Se modifichi una spesa senza scegliere un nuovo file, il documento già presente resta collegato.</small>
        </label>
        {attached}
        <div class='bmout11-formactions'>
          <button type='submit'>{'Salva modifiche' if form_data['id'] else 'Registra uscita'}</button>
          {("<a href='/pagamenti/uscite'>Annulla modifica</a>" if form_data['id'] else "")}
        </div>
      </form>
      <div class='bmout11-table'><table>
        <thead><tr><th>Data</th><th>Uscita</th><th>Importo</th><th>Metodo</th><th>Giustificativo</th><th></th></tr></thead>
        <tbody>{table_rows}</tbody>
      </table></div>
    </section>
    <style id='bodymind-expense-v11-style'>
      .bmout11{{margin:14px 0 24px;padding:20px;border-radius:22px;background:#081626;border:1px solid rgba(96,165,250,.24);color:#f8fafc}}
      .bmout11-head{{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}}.bmout11-head span{{font-size:10px;letter-spacing:.14em;font-weight:950;color:#7dd3fc}}.bmout11-head h1{{margin:4px 0;font-size:28px}}.bmout11-head p{{margin:0;color:#cbd5e1;max-width:760px}}.bmout11-head>strong{{font-size:20px;white-space:nowrap}}
      .bmout11-nav{{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}}.bmout11-nav a{{padding:9px 12px;border-radius:10px;background:#10243a;color:#dbeafe!important;text-decoration:none;font-weight:900;font-size:12px}}.bmout11-nav a.on{{background:#2563eb;color:#fff!important}}
      .bmout11-form{{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:9px;padding:14px;border-radius:15px;background:#0c2035}}.bmout11-form label{{display:grid;gap:5px;font-size:11px;font-weight:900;color:#cbd5e1}}.bmout11-form input,.bmout11-form select,.bmout11-form textarea{{width:100%;padding:10px;border-radius:9px;border:1px solid #334155;background:#06111f;color:#fff;font-size:14px}}.bmout11-form .wide{{grid-column:1/-1}}.bmout11-upload small{{font-weight:600;color:#94a3b8}}.bmout11-current{{grid-column:1/-1;padding:9px 11px;border-radius:9px;background:#172554;color:#dbeafe}}.bmout11-current a{{color:#93c5fd!important}}
      .bmout11-formactions{{grid-column:1/-1;display:flex;gap:8px;align-items:center}}.bmout11-formactions button{{min-height:44px;border:0;border-radius:10px;background:#dc2626;color:white;font-weight:950;padding:10px 18px}}.bmout11-formactions a{{padding:10px 14px;border-radius:10px;background:#334155;color:white!important;text-decoration:none;font-weight:900}}
      .bmout11-table{{overflow:auto;margin-top:14px}}.bmout11-table table{{width:100%;border-collapse:collapse;min-width:900px}}.bmout11-table th,.bmout11-table td{{padding:10px;border-bottom:1px solid #1e293b;text-align:left;vertical-align:top}}.bmout11-files{{display:flex;gap:6px;flex-wrap:wrap;align-items:center}}.bmout11-files a,.bmout11-edit{{padding:7px 9px;border-radius:8px;color:white!important;text-decoration:none;font-size:11px;font-weight:900}}.bmout11-preview{{background:#2563eb}}.bmout11-download{{background:#0f766e}}.bmout11-edit{{background:#475569;display:inline-block}}.bmout11-files small{{width:100%;color:#94a3b8}}.bmout11-none{{color:#94a3b8}}
      .bmout11-ok,.bmout11-err{{margin:9px 0;padding:10px 12px;border-radius:10px;font-weight:850}}.bmout11-ok{{background:#14532d}}.bmout11-err{{background:#7f1d1d}}
      @media(max-width:800px){{.bmout11{{padding:12px}}.bmout11-head{{display:grid}}.bmout11-head h1{{font-size:22px}}.bmout11-form{{grid-template-columns:1fr 1fr}}.bmout11-form .wide{{grid-column:1/-1}}}}
    </style>
    """
    return layout(html)


@app.before_request
def _bodymind_expense_entry_v11():
    # One expense module for every legacy accounting/expense entry point.
    # Unauthenticated requests continue to the original protected endpoint.
    if request.path in ('/pagamenti/uscite','/contabilita') and request.method in ('GET','POST'):
        try:
            from flask import session as _session
            authenticated=bool(_session.get('logged') or _session.get('logged_in') or _session.get('user_id'))
        except Exception:
            authenticated=False
        if not authenticated:
            return None
        return _bodymind_uscite_v11_impl()


@app.route('/pagamenti/uscite/allegato/<int:expense_id>')
@login_required
def _bodymind_uscita_attachment_v11(expense_id):
    from pathlib import Path as _Path
    from flask import send_file as _send_file
    conn=db(); conn.row_factory=sqlite3.Row
    try:
        _bodymind_uscite_schema_v11(conn)
        row=conn.execute("SELECT * FROM bodymind_uscite WHERE id=?",(int(expense_id),)).fetchone()
    finally:
        try:conn.close()
        except Exception:pass
    if not row or not row['allegato_path']:
        return ('Giustificativo non presente.',404)
    root=_Path('/data/tenants/default/media/uscite').resolve()
    p=_Path(str(row['allegato_path'])).resolve()
    if root!=p and root not in p.parents:
        return ('Percorso allegato non valido.',403)
    if not p.exists() or not p.is_file():
        return ('File allegato non trovato.',404)
    mime=str(row['allegato_mime'] or 'application/octet-stream')
    name=str(row['allegato_nome'] or p.name)
    force=request.args.get('download')=='1'
    previewable=(mime=='application/pdf' or mime.startswith('image/'))
    return _send_file(str(p),mimetype=mime,as_attachment=(force or not previewable),download_name=name,conditional=True)
'''
    CORE.write_text(_core_v11,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)

_v11_qa=r"""
import json,sqlite3,sys
sys.path.insert(0,"/data/top2_app")
import app as _full
from asd_app.core import app
app.config["TESTING"]=True
routes=[(str(r.rule),str(r.endpoint),sorted(m for m in (r.methods or set()) if m not in ("HEAD","OPTIONS"))) for r in app.url_map.iter_rules()]
expense_file=[x for x in routes if x[0]=='/pagamenti/uscite/allegato/<int:expense_id>']
client=app.test_client()
with client.session_transaction() as sess:
    sess.update({"logged":True,"logged_in":True,"username":"admin","display_name":"Expense QA","role":"admin","tenant_slug":"default","user_id":1,"is_admin":True,"admin":True})
r1=client.get('/pagamenti/uscite',follow_redirects=False)
r2=client.get('/contabilita',follow_redirects=False)
body=r1.get_data(as_text=True)
conn=sqlite3.connect("/data/tenants/default/asd.db",timeout=20)
try:
    cols=[str(x[1]) for x in conn.execute("PRAGMA table_info(bodymind_uscite)").fetchall()]
    counts={t:int(conn.execute("SELECT COUNT(*) FROM "+t).fetchone()[0]) for t in ("tesserati","pagamenti","ricevute")}
    integrity=str(conn.execute("PRAGMA integrity_check").fetchone()[0]); fk=len(conn.execute("PRAGMA foreign_key_check").fetchall())
finally:conn.close()
out={"uscite_status":r1.status_code,"contabilita_status":r2.status_code,"marker":"BODYMIND_R123_EXPENSE_ATTACHMENTS_V11" in body,"multipart":"multipart/form-data" in body,"attachment_route":bool(expense_file),"columns":cols,"counts":counts,"integrity":integrity,"fk":fk}
print("[r123-expense-v11-audit] "+json.dumps(out,ensure_ascii=False),flush=True)
if r1.status_code!=200 or r2.status_code!=200 or not out["marker"] or not out["multipart"] or not expense_file or not all(x in cols for x in ("allegato_path","allegato_nome","allegato_mime","allegato_size")) or integrity.lower()!="ok" or fk:
    raise RuntimeError("V11 expense attachments audit failed")
"""
_v11p=subprocess.run([sys.executable,"-c",_v11_qa],capture_output=True,text=True,timeout=180)
print((_v11p.stdout or "").strip(),flush=True)
if _v11p.returncode!=0:
    raise RuntimeError("R123 V11 child audit failed "+((_v11p.stderr or "")+(_v11p.stdout or ""))[-6000:])
print('[r123-expense-v11] PASS one-expense-module attachments-preview-download payments-preserved before='+str(_v11_before)+' after='+str(_v11_after),flush=True)
