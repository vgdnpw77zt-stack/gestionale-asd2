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
                    conn.execute("""INSERT INTO presenze(tesserato_id,corso_id,data,stato,note,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?)""",(tid,course_id,day,stato,'',now,now))
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
    rows=''.join(cards) or "<div class='r123-empty'>Nessuna allieva in questo gruppo. Assegna il corso dalla scheda atleta.</div>"
    html=f"""<!-- BODYMIND_R123_PRESENZE_SIMPLE -->
    <main class='r123-page'>
      <header class='r123-head'><div><small>PRESENZE</small><h1>Registro rapido</h1><p>Scegli il gruppo, tocca le allieve presenti e salva.</p></div>
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
            items=''.join("<a class='r123-pay-person' href='/pagamenti?tesserato_id="+str(int(r.get('id') or 0))+"&mese="+str(mese)+"&anno="+str(anno)+"'><b>"+e((str(r.get('cognome') or '')+' '+str(r.get('nome') or '')).strip())+"</b><span>Registra quota iscrizione</span></a>" for r in rows)
        else:
            items="<div class='r123-pay-empty'>Tutte le tesserate risultano in regola con la quota iscrizione.</div>"
        box=f"""<!-- BODYMIND_R123_PAYMENT_MOBILE --><section class='r123-pay-box'><div class='r123-pay-kicker'>OPERATIVITÀ IMMEDIATA</div><h3>Tesserate senza quota iscrizione · stagione {e(season['label'])}</h3><div class='r123-pay-list'>{items}</div></section>
        <style>.r123-pay-box{{margin:12px 0;padding:15px;border-radius:16px;background:#0d1d31;border:1px solid rgba(148,163,184,.18)}}.r123-pay-kicker{{font-size:11px;font-weight:950;letter-spacing:.1em;color:#93c5fd}}.r123-pay-box h3{{margin:5px 0 10px}}.r123-pay-list{{display:grid;gap:7px}}.r123-pay-person{{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:11px 12px;border-radius:12px;background:#12283f;color:white!important;text-decoration:none}}.r123-pay-person span{{font-size:11px;color:#93c5fd}}.r123-pay-empty{{color:#86efac;font-weight:800}}@media(max-width:560px){{.r123-pay-person{{align-items:flex-start;flex-direction:column}}}}</style>
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
b=c.get("/presenze-semplici")
ph=p.get_data(as_text=True); bh=b.get_data(as_text=True)
conn=sqlite3.connect("/data/tenants/default/asd.db",timeout=20)
try:
    integrity=str(conn.execute("PRAGMA integrity_check").fetchone()[0]); fk=len(conn.execute("PRAGMA foreign_key_check").fetchall())
finally: conn.close()
ok=(p.status_code==200 and "BODYMIND_R123_PAYMENT_MOBILE" in ph and a.status_code in (301,302,307,308) and "/presenze-semplici" in str(a.headers.get("Location","")) and b.status_code==200 and "BODYMIND_R123_PRESENZE_SIMPLE" in bh and "Giornata operativa" not in bh and all(x in bh for x in ("Base","Kids","Adult","Pro / Agoniste")) and integrity.lower()=="ok" and fk==0)
print("[r123-selftest] status_payment=%s presence_redirect=%s simple=%s db=%s fk=%s ok=%s"%(p.status_code,a.status_code,b.status_code,integrity,fk,ok),flush=True)
if not ok: raise RuntimeError("R123 QA failed")
'''
proc=subprocess.run([sys.executable,'-c',qa],capture_output=True,text=True,timeout=120)
print((proc.stdout or '').strip(),flush=True)
if proc.returncode!=0: raise RuntimeError('R123 child QA failed '+((proc.stderr or '')+(proc.stdout or ''))[-4000:])
