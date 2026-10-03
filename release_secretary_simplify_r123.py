# -*- coding: utf-8 -*-
from __future__ import annotations
import py_compile, re, shutil, sqlite3, subprocess, sys
from datetime import datetime
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
CORE=APP/'asd_app/core.py'
BACK=Path('/data/release_backups/20261003_r123_secretary_simplify')
BACK.mkdir(parents=True,exist_ok=True)
if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

def backup_file(p):
    dst=BACK/p.name
    if p.exists() and not dst.exists(): shutil.copy2(p,dst)

src=CORE.read_text(encoding='utf-8',errors='replace')
changed=False

# ------------------------------------------------------------
# PAGAMENTI: remove redundant season/filter panels and make the
# two operational missing-payment lists readable on mobile.
# Backend POST/payment truth remains unchanged.
# ------------------------------------------------------------
if 'BODYMIND_R123_PAYMENT_SIMPLIFY' not in src:
    start=src.find('@app.route("/pagamenti", methods=["GET", "POST"])')
    end=src.find('\n@app.',start+10)
    if start<0 or end<0: raise RuntimeError('R123 pagamenti block not found')
    block=src[start:end]
    original=block

    # Remove the standalone season configuration card from daily payments UI.
    a=block.find("   <div class='card soft' style='margin:14px 0'>\n     <div class='kicker'>Stagione sportiva</div>")
    if a>=0:
        b=block.find('   """',a)
        if b<0: raise RuntimeError('R123 season card end missing')
        block=block[:a]+"   <!-- BODYMIND_R123_PAYMENT_SIMPLIFY -->\n"+block[b:]

    # Remove only the redundant GET filter card; keep "Nuovo pagamento".
    filter_start=block.find('       <div class="card form-panel card-elevated">\n           <div class="kicker">Filtro operativo</div>')
    if filter_start>=0:
        next_card=block.find('       <div class="card form-panel card-elevated">\n           <div class="kicker">Registrazione veloce</div>',filter_start)
        if next_card<0: raise RuntimeError('R123 payment new-payment card anchor missing')
        block=block[:filter_start]+block[next_card:]
        block=block.replace('<div class="grid-2">','<div class="grid-1 r123-payment-entry">',1)

    # Make option labels and operational names surname-first.
    block=block.replace("{e(u['nome'])} {e(u['cognome'])}{label_extra}","{e(u['cognome'])} {e(u['nome'])}{label_extra}")
    block=block.replace("<td><b>{e(row['nome'])} {e(row['cognome'])}</b>","<td><b>{e(row['cognome'])} {e(row['nome'])}</b>")

    # Convert quick monthly rows from table rows to self-contained cards.
    old_month='''           <tr class='{row_class}'>
               <td><b>{e(row['cognome'])} {e(row['nome'])}</b><div class='small-muted'>{e(row['telefono'] or 'Telefono non indicato')}</div><div class='small-muted'>{state['badges']} {render_member_status_badge(compute_member_status(row.get('id'), selected_mese, selected_anno, payment_status_alerts))}</div></td>
               <td>{selected_mese:02d}/{selected_anno}</td>
               <td>{_payment_quick_form(row, 'mensile', selected_mese, selected_anno)}</td>
           </tr>
'''
    new_month='''           <div class='r123-pay-item {row_class}'>
               <div class='r123-pay-person'><b>{e(row['cognome'])} {e(row['nome'])}</b><small>{e(row['telefono'] or 'Telefono non indicato')}</small><small>{state['badges']} {render_member_status_badge(compute_member_status(row.get('id'), selected_mese, selected_anno, payment_status_alerts))}</small></div>
               <div class='r123-pay-period'>{selected_mese:02d}/{selected_anno}</div>
               <div class='r123-pay-action'>{_payment_quick_form(row, 'mensile', selected_mese, selected_anno)}</div>
           </div>
'''
    if old_month in block: block=block.replace(old_month,new_month,1)

    old_enroll='''           <tr class='{row_class}'>
               <td><b>{e(row['cognome'])} {e(row['nome'])}</b><div class='small-muted'>{e(row['telefono'] or 'Telefono non indicato')}</div><div class='small-muted'>{state['badges']} {render_member_status_badge(compute_member_status(row.get('id'), selected_mese, selected_anno, payment_status_alerts))}</div></td>
               <td>Stagione {e(season['label'])}<div class='small-muted'>da {e(season['start_month_name'])}</div></td>
               <td>{_payment_quick_form(row, 'iscrizione', int(season['start_month']), int(season['start_year']))}</td>
           </tr>
'''
    new_enroll='''           <div class='r123-pay-item {row_class}'>
               <div class='r123-pay-person'><b>{e(row['cognome'])} {e(row['nome'])}</b><small>{e(row['telefono'] or 'Telefono non indicato')}</small><small>{state['badges']} {render_member_status_badge(compute_member_status(row.get('id'), selected_mese, selected_anno, payment_status_alerts))}</small></div>
               <div class='r123-pay-period'>Stagione {e(season['label'])}</div>
               <div class='r123-pay-action'>{_payment_quick_form(row, 'iscrizione', int(season['start_month']), int(season['start_year']))}</div>
           </div>
'''
    if old_enroll in block: block=block.replace(old_enroll,new_enroll,1)

    block=block.replace("<table><tr><th>Tesserato / Stato</th><th>Periodo</th><th>Azione rapida</th></tr>{quick_non_pagati_html}</table>","<div class='r123-pay-list'>{quick_non_pagati_html}</div>")
    block=block.replace("<table><tr><th>Tesserato / Stato</th><th>Stagione</th><th>Azione rapida</th></tr>{quick_iscrizioni_html}</table>","<div class='r123-pay-list'>{quick_iscrizioni_html}</div>")

    # Add small responsive styling once, without touching payment logic.
    style_anchor='   conn.close()\n   return layout(html_out)'
    style_insert='''   html_out += """<style id='bodymind-r123-payment-mobile'>
   .r123-payment-entry{display:block}.r123-pay-list{display:grid;gap:9px;margin-top:10px}.r123-pay-item{display:grid;grid-template-columns:minmax(180px,1fr) 150px minmax(220px,auto);gap:10px;align-items:center;padding:12px;border:1px solid rgba(148,163,184,.18);border-radius:14px;background:rgba(15,23,42,.50)}.r123-pay-person b,.r123-pay-person small{display:block}.r123-pay-person b{font-size:15px}.r123-pay-person small{margin-top:3px;color:#94a3b8}.r123-pay-period{font-weight:800}.r123-pay-action form{margin:0}
   @media(max-width:720px){.r123-pay-item{grid-template-columns:1fr}.r123-pay-period{font-size:12px;color:#94a3b8}.r123-pay-action,.r123-pay-action form,.r123-pay-action button,.r123-payment-entry form select,.r123-payment-entry form input,.r123-payment-entry form button{width:100%!important}.r123-pay-person b{font-size:17px}}
   </style>"""
   conn.close()
   return layout(html_out)'''
    if style_anchor not in block: raise RuntimeError('R123 payment return anchor missing')
    block=block.replace(style_anchor,style_insert,1)

    if block==original: raise RuntimeError('R123 payment block unchanged')
    src=src[:start]+block+src[end:]
    changed=True

# ------------------------------------------------------------
# PRESENZE: one simple mobile-first register.
# Three existing operational groups only, direct athlete selection,
# no "Giornata operativa", DOCX, bookings, notes or duplicate register.
# Does not rewrite tesserati.corso.
# ------------------------------------------------------------
if 'BODYMIND_R123_PRESENZE_SIMPLE' not in src:
    start=src.find('@app.route("/presenze", methods=["GET", "POST"])')
    end=src.find('\n@app.',start+10)
    if start<0 or end<0: raise RuntimeError('R123 presenze block not found')
    new_pres=r'''@app.route("/presenze", methods=["GET", "POST"])
@login_required
def presenze():
    # BODYMIND_R123_PRESENZE_SIMPLE
    conn=db(); c=conn.cursor()
    all_courses=c.execute("SELECT id,nome,orario FROM corsi ORDER BY id").fetchall()

    def _group(row):
        n=str(row['nome'] or '').strip().lower()
        if 'kid' in n: return ('kids','Base Kids')
        if 'adult' in n: return ('adult','Adulti')
        if 'pro' in n or 'agon' in n: return ('pro','Pro / Agoniste')
        return (None,None)

    groups=[]
    for cr in all_courses:
        key,label=_group(cr)
        if key and not any(x['key']==key for x in groups):
            groups.append({'key':key,'label':label,'id':int(cr['id']),'orario':str(cr['orario'] or '')})
    order={'kids':0,'adult':1,'pro':2}
    groups.sort(key=lambda x:order.get(x['key'],99))

    selected_date=parse_date_input(request.values.get('data','').strip()) or now_iso_date()
    selected_course=parse_int(request.values.get('corso_id','0'),0)
    allowed_ids={x['id'] for x in groups}
    if selected_course not in allowed_ids:
        selected_course=groups[0]['id'] if groups else 0

    if request.method=='POST':
        try:
            data=require_valid_date(request.form.get('data','').strip(),'la data')
            corso_id=parse_int(request.form.get('corso_id','0'),0)
            if corso_id not in allowed_ids: raise ValueError('Seleziona Base Kids, Adulti o Pro / Agoniste.')
            valid_ids={int(x['id']) for x in c.execute("SELECT id FROM tesserati").fetchall()}
            present_ids={parse_int(x,0) for x in request.form.getlist('tesserato_id')}
            present_ids={x for x in present_ids if x in valid_ids}
            c.execute("DELETE FROM presenze WHERE corso_id=? AND data=?",(corso_id,data))
            for tid in sorted(present_ids):
                c.execute("""INSERT INTO presenze(tesserato_id,corso_id,data,stato,created_at,updated_at)
                             VALUES(?,?,?,'presente',?,?)""",(tid,corso_id,data,now_iso_dt(),now_iso_dt()))
            try: reconcile_package_usages(c,corso_id,data,present_ids)
            except Exception: pass
            conn.commit(); conn.close()
            return redirect_with_message(f"/presenze?data={data}&corso_id={corso_id}",f"Presenze salvate: {len(present_ids)} allieve presenti.",'success')
        except Exception as exc:
            conn.rollback(); conn.close()
            return redirect_with_message('/presenze',f"Errore presenze: {exc}",'error')

    athletes=c.execute("""SELECT id,nome,cognome,corso FROM tesserati
                          ORDER BY TRIM(cognome) COLLATE NOCASE,TRIM(nome) COLLATE NOCASE""").fetchall()
    present_ids=set()
    if selected_course:
        present_ids={int(x['tesserato_id']) for x in c.execute("""SELECT tesserato_id FROM presenze
                    WHERE corso_id=? AND data=? AND stato='presente'""",(selected_course,selected_date)).fetchall()}
    conn.close()

    tabs=''.join(f"<a class='r123-group {'active' if g['id']==selected_course else ''}' href='/presenze?data={e(selected_date)}&corso_id={g['id']}'>{e(g['label'])}</a>" for g in groups)
    cards=''.join(f"""<label class='r123-athlete {'on' if int(t['id']) in present_ids else ''}'>
      <input type='checkbox' name='tesserato_id' value='{int(t['id'])}' {'checked' if int(t['id']) in present_ids else ''}>
      <span class='r123-check'>✓</span><span><b>{e(t['cognome'])} {e(t['nome'])}</b></span>
    </label>""" for t in athletes)
    if not cards: cards="<div class='empty-state'>Nessuna atleta presente in anagrafica.</div>"
    return layout(f"""
    <main class='r123-pres'>
      <section class='app-section-hero'><div><div class='kicker'>Presenze</div><h2 class='section-title'>Registro rapido</h2><div class='small-muted'>Scegli gruppo e data, tocca direttamente le allieve presenti, salva. Fine.</div></div></section>
      <div class='r123-groups'>{tabs}</div>
      <form method='GET' class='r123-date'><input type='hidden' name='corso_id' value='{selected_course}'><input type='date' name='data' value='{e(selected_date)}'><button>Aggiorna data</button></form>
      <form method='POST' id='r123-pres-form'>
        {csrf_input()}<input type='hidden' name='corso_id' value='{selected_course}'><input type='hidden' name='data' value='{e(selected_date)}'>
        <div class='r123-tools'><strong><span id='r123-count'>{len(present_ids)}</span> presenti</strong><div><button type='button' onclick='r123All(true)'>Tutte</button><button type='button' onclick='r123All(false)'>Azzera</button></div></div>
        <div class='r123-athletes'>{cards}</div>
        <div class='r123-save'><button type='submit' {'disabled' if not selected_course else ''}>Salva presenze</button></div>
      </form>
    </main>
    <style id='bodymind-r123-presenze'>
    .r123-pres{{max-width:900px;margin:0 auto 60px}}.r123-groups{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0}}.r123-group{{padding:13px 10px;border-radius:14px;text-align:center;text-decoration:none!important;font-weight:900;background:rgba(15,23,42,.72);border:1px solid rgba(148,163,184,.18);color:#dbeafe!important}}.r123-group.active{{background:#1d4ed8;border-color:#60a5fa;color:white!important}}.r123-date{{display:flex;gap:8px;margin-bottom:10px}}.r123-date input{{flex:1}}.r123-tools{{display:flex;justify-content:space-between;align-items:center;gap:10px;margin:10px 0}}.r123-tools div{{display:flex;gap:6px}}.r123-athletes{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}}.r123-athlete{{display:grid;grid-template-columns:28px 28px 1fr;align-items:center;min-height:58px;padding:10px 12px;border-radius:14px;background:rgba(15,23,42,.64);border:1px solid rgba(148,163,184,.17);cursor:pointer}}.r123-athlete input{{width:22px!important;height:22px!important;min-width:22px!important;accent-color:#22c55e}}.r123-check{{opacity:.15;font-weight:950;color:#22c55e}}.r123-athlete.on{{background:rgba(22,101,52,.30);border-color:rgba(34,197,94,.5)}}.r123-athlete.on .r123-check{{opacity:1}}.r123-save{{position:sticky;bottom:max(8px,env(safe-area-inset-bottom));padding:10px 0;background:linear-gradient(transparent,rgba(2,6,23,.96) 35%)}}.r123-save button{{width:100%;min-height:50px;font-weight:950}}
    @media(max-width:680px){{.r123-pres{{padding:0 10px}}.r123-groups{{grid-template-columns:1fr 1fr 1fr;gap:5px}}.r123-group{{font-size:12px;padding:11px 5px}}.r123-athletes{{grid-template-columns:1fr}}.r123-date{{display:grid;grid-template-columns:1fr auto}}}}
    </style>
    <script>(function(){{
      function refresh(){{var n=0;document.querySelectorAll('.r123-athlete').forEach(function(l){{var c=l.querySelector('input');l.classList.toggle('on',!!c.checked);if(c.checked)n++;}});var out=document.getElementById('r123-count');if(out)out.textContent=n;}}
      document.querySelectorAll('.r123-athlete input').forEach(function(c){{c.addEventListener('change',refresh)}});window.r123All=function(v){{document.querySelectorAll('.r123-athlete input').forEach(function(c){{c.checked=!!v}});refresh()}};refresh();
    }})();</script>
    """)
'''
    src=src[:start]+new_pres+src[end:]
    changed=True

if changed:
    backup_file(CORE)
    CORE.write_text(src,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r123-source] PASS payments simplified + direct-presence register',flush=True)
else:
    print('[r123-source] already applied',flush=True)

# Read-only UI regression in a fresh process.
qa=r'''
import json,sqlite3,sys,re
sys.path.insert(0,"/data/top2_app")
import app as _full_app
from asd_app.core import app
app.config["TESTING"]=True
cl=app.test_client()
with cl.session_transaction() as s:
    s.update({"logged":True,"username":"admin","display_name":"R123 QA","role":"admin","tenant_slug":"default"})
pay=cl.get("/pagamenti")
ph=pay.get_data(as_text=True)
pres=cl.get("/presenze")
rh=pres.get_data(as_text=True)
checks={
 "payments_200":pay.status_code==200,
 "season_panel_removed":"Tesseramento / iscrizione: stagione" not in ph,
 "filter_removed":"Seleziona periodo e tesserato" not in ph,
 "missing_enrollment_names_visible":"Tesserati senza quota iscrizione/tesseramento" not in ph or "r123-pay-person" in ph,
 "presence_200":pres.status_code==200,
 "presence_three_groups":all(x in rh for x in ("Base Kids","Adulti","Pro / Agoniste")),
 "presence_no_giornata":"Giornata operativa" not in rh,
 "presence_no_docx":">DOCX<" not in rh,
 "presence_direct_athletes":"r123-athlete" in rh and "Salva presenze" in rh,
}
c=sqlite3.connect("/data/tenants/default/asd.db",timeout=20)
try:
    checks["db_ok"]=str(c.execute("PRAGMA integrity_check").fetchone()[0]).lower()=="ok" and len(c.execute("PRAGMA foreign_key_check").fetchall())==0
finally:c.close()
print("[r123-qa] "+json.dumps(checks,ensure_ascii=False),flush=True)
if not all(checks.values()): raise RuntimeError("R123 QA failed "+repr(checks))
'''
p=subprocess.run([sys.executable,'-c',qa],capture_output=True,text=True,timeout=120)
print((p.stdout or '').strip(),flush=True)
if p.returncode!=0: raise RuntimeError('R123 child QA failed '+((p.stderr or '')+(p.stdout or ''))[-4000:])
print('[r123-selftest] PASS payments-mobile-simplified direct-athlete-presences db-ok',flush=True)
