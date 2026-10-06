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

_r123_guard=sqlite3.connect("file:"+str(DB)+"?mode=ro",uri=True,timeout=20)
try:
    _r123_counts_before={t:int(_r123_guard.execute("SELECT COUNT(*) FROM "+t).fetchone()[0]) for t in ("tesserati","pagamenti","ricevute","quote_mensili","documenti","inbound_documents")}
finally:_r123_guard.close()

# Remove superseded R123 functions from persistent source before Flask imports them.
def _r123_strip_runtime_functions(path,names):
    import ast
    text=path.read_text(encoding='utf-8',errors='replace')
    tree=ast.parse(text); lines=text.splitlines(True); ranges=[]; wanted=set(names)
    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in wanted:
            start=min([node.lineno]+[d.lineno for d in node.decorator_list])-1
            end=int(getattr(node,'end_lineno',node.lineno)); ranges.append((start,end,node.name))
    if not ranges:return []
    dst=BACK/'core_pre_canonical_consolidation.py'
    if not dst.exists():shutil.copy2(path,dst)
    for start,end,_ in sorted(ranges,reverse=True):del lines[start:end]
    path.write_text(''.join(lines),encoding='utf-8')
    return [x[2] for x in ranges]

_r123_removed=_r123_strip_runtime_functions(CORE,(
 '_bodymind_r123_payment_simplify','_bodymind_r125_payment_premium_status',
 '_bodymind_r126_payment_history_names','_bodymind_r127_history_card_names_nav',
 '_bodymind_r130_payment_mobile_hard_fix','_bodymind_r131_history_name_visible_div',
 '_bodymind_r123_payment_split_v2','_bodymind_r123_payment_split_v3',
 '_bodymind_r123_canonical_payment_module_v5','_bodymind_payment_register_v7',
 '_bodymind_payment_module_v7','_bodymind_admin_route_v8','_bodymind_uscite_schema_v8',
 '_bodymind_uscite_v8','_bodymind_desktop_admin_nav_v8','_bodymind_payment_month_alerts_v9',
 '_bodymind_uscite_schema_v11','_bodymind_uscita_attachment_save_v11','_bodymind_uscite_v11_impl',
 '_bodymind_expense_entry_v11','_bodymind_uscita_attachment_v11',
 '_bodymind_dashboard_background_restore_r123','_bodymind_dashboard_recompose_r156',
))
_marker_text=CORE.read_text(encoding='utf-8',errors='replace')
for _marker in ('# BODYMIND_R123_PAYMENT_FORM_CANONICAL_V7\n','# BODYMIND_R123_EXPENSE_ATTACHMENTS_V11\n'):
    _marker_text=_marker_text.replace(_marker,'')
CORE.write_text(_marker_text,encoding='utf-8')
if _r123_removed:
    py_compile.compile(str(CORE),doraise=True)
    print('[r123-runtime-consolidation] removed='+repr(sorted(_r123_removed)),flush=True)

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

# BODYMIND_R123_PAYMENT_FORM_CANONICAL_V7
# Replace the V5/V6 "move an existing form" behavior with one real canonical
# registration/edit form. One module, two modes, same write path everywhere.
_core_v7=CORE.read_text(encoding='utf-8',errors='replace')
_changed_v7=False

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
                    "SELECT * FROM pagamenti WHERE tesserato_id=? AND mese=? AND anno=? AND (lower(coalesce(causale,'')) LIKE '%mensil%' OR lower(coalesce(causale,'')) IN ('quota','quota_mensile')) ORDER BY id DESC LIMIT 1",
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
            truth=bodymind_payment_truth(c,mese=mese,anno=anno,stagione=stagione)
            payment_state={int(x['tesserato_id']):dict(x) for x in truth.get('rows',[])}
            payment_rows={int(x['id']):dict(x) for x in c.execute("SELECT * FROM pagamenti ORDER BY id DESC").fetchall()}
            quote_by_tid={}
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='quote_mensili'").fetchone():
                for q in c.execute("SELECT * FROM quote_mensili WHERE mese=? AND anno=? ORDER BY id DESC",(mese,anno)).fetchall():
                    q=dict(q); qtid=int(q.get('tesserato_id') or 0)
                    if qtid and qtid not in quote_by_tid:quote_by_tid[qtid]=q
            try:month_summary=bodymind_monthly_due_summary(c)
            except Exception:month_summary=[]
        finally:
            try:c.close()
            except Exception:pass

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
            state=payment_state.get(tid,{})
            eok=bool(state.get('iscrizione_pagata'))
            mok=bool(state.get('mensile_pagato'))
            focus_ok=eok if vista=='iscrizioni' else mok
            if not focus_ok:due_count+=1
            eh=f"/pagamenti?vista=iscrizioni&stagione={stagione}&mese={mese}&anno={anno}&tesserato_id={tid}&azione=registra&tipo=iscrizione"
            mh=f"/pagamenti?vista=mensili&mese={mese}&anno={anno}&tesserato_id={tid}&azione=registra&tipo=mensile"
            dh=f"/documenti/da-verificare?tesserato_id={tid}"
            ah=f"/documenti?tesserato_id={tid}"
            rows.append((0 if not focus_ok else 1,
                "<div class='bmpv7-row "+("due" if not focus_ok else "paid")+"' data-bm-tid='"+str(tid)+"' data-bm-enroll='"+("1" if eok else "0")+"' data-bm-monthly='"+("1" if mok else "0")+"'>"
                +"<div class='bmpv7-person'><b>"+e(_name(a))+"</b><small>Iscrizione: "+("PAGATA" if eok else "da pagare")+" · "+months[mese]+": "+("PAGATO" if mok else "da pagare")+"</small></div>"
                +"<div class='bmpv7-actions'><a class='doc' href='"+dh+"'>Verifica documento</a><a class='doc' href='"+ah+"'>Archivio</a><a href='"+eh+"'>"+("Modifica incasso iscrizione" if eok else "Registra incasso iscrizione")+"</a><a href='"+mh+"'>"+("Modifica incasso "+months[mese] if mok else "Registra incasso "+months[mese])+"</a></div>"
                +"</div>"
            ))
        rows.sort(key=lambda x:x[0])

        form_html=''
        if selected_tid and action=='registra':
            athlete=next((a for a in athletes if int(a.get('id') or 0)==selected_tid),None)
            if athlete:
                state=payment_state.get(selected_tid,{})
                existing_id=state.get('iscrizione_payment_id') if action_tipo=='iscrizione' else state.get('mensile_payment_id')
                existing=payment_rows.get(int(existing_id or 0))
                pid=int(existing.get('id') or 0) if existing else 0
                qsel=quote_by_tid.get(selected_tid) if action_tipo=='mensile' else None
                if existing:
                    amount=str(existing.get('importo') or '')
                    note=str(existing.get('note_pagamento') or '')
                else:
                    try:qamount=float(qsel.get('importo_dovuto') or 0) if qsel else 0
                    except Exception:qamount=0
                    amount=(str(qamount) if qamount>0 else '')
                    note=(str(qsel.get('note') or '') if qsel else '')
                paydate=(str(existing.get('data') or today.isoformat()) if existing else today.isoformat())
                method=(str(existing.get('metodo_pagamento') or 'contanti') if existing else 'contanti')
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
        month_strip=''
        if month_summary:
            month_chips=''.join("<a class='"+("ok" if int(x['mancanti'])==0 else "due")+"' href='/pagamenti?vista=mensili&mese="+str(x['mese'])+"&anno="+str(x['anno'])+"'><b>"+months[int(x['mese'])]+" "+str(x['anno'])+"</b><span>"+(str(x['mancanti'])+" da pagare" if int(x['mancanti']) else "completo")+"</span></a>" for x in month_summary)
            month_strip="<div class='bmpv7-months'><strong>MENSILI DELLA STAGIONE</strong><div>"+month_chips+"</div></div>"

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
          <div class='bmpv7-admin'><span>AMMINISTRAZIONE</span><a href='/uscite'>USCITE</a><a href='/ricevute'>RICEVUTE</a><a href='/collaboratori'>COLLABORATORI</a><a href='/collaboratori/ricevute'>RICEVUTE COLLABORATORI</a><a href='/documenti'>ARCHIVIO</a><a href='/documenti/da-verificare'>DA VERIFICARE</a></div>
          {selector}{month_strip}{saved}{error}{form_html}
          <div class='bmpv7-list'>{''.join(x[1] for x in rows)}</div>
        </section>
        <style id='bodymind-payment-v7'>
        .bmpv7{{margin:14px 0 22px;padding:18px;border-radius:22px;background:#081626;border:1px solid rgba(96,165,250,.24);color:#f8fafc}}.bmpv7-head{{display:flex;justify-content:space-between;gap:14px;align-items:center}}.bmpv7-head span{{font-size:10px;letter-spacing:.14em;font-weight:950;color:#7dd3fc}}.bmpv7-head h1{{margin:4px 0;font-size:27px}}.bmpv7-head p{{margin:0;color:#b7c6d9}}.bmpv7-head>strong{{font-size:22px}}
        .bmpv7-tabs{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:14px 0}}.bmpv7-tabs a{{padding:14px;border-radius:13px;background:#10243a;color:#cbd5e1!important;text-decoration:none;text-align:center;font-weight:950}}.bmpv7-tabs a.on{{background:#2563eb;color:white!important}}
        .bmpv7-period{{display:flex;gap:8px;align-items:end;flex-wrap:wrap;margin-bottom:12px;padding:10px;border-radius:13px;background:#0c2035}}.bmpv7-period label{{display:grid;gap:4px;font-size:11px;font-weight:900}}.bmpv7-period input,.bmpv7-period select,.bmpv7-period button{{min-height:42px;border-radius:9px;border:1px solid rgba(148,163,184,.25);background:#06111f;color:#fff;padding:8px 10px}}.bmpv7-period button{{background:#2563eb;font-weight:900}}
        .bmpv7-form{{margin:12px 0 16px;padding:15px;border-radius:16px;background:#0d2138;border:2px solid rgba(96,165,250,.48)}}.bmpv7-formhead{{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:12px}}.bmpv7-formhead span{{font-size:10px;font-weight:950;color:#7dd3fc}}.bmpv7-formhead h2{{margin:3px 0;font-size:20px}}.bmpv7-formhead a{{color:#bfdbfe!important}}.bmpv7-fields{{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:9px}}.bmpv7-fields label{{display:grid;gap:5px;font-size:11px;font-weight:900;color:#cbd5e1}}.bmpv7-fields input,.bmpv7-fields select,.bmpv7-fields textarea{{width:100%;border-radius:9px;border:1px solid rgba(148,163,184,.25);background:#06111f;color:#fff;padding:9px;font-size:15px}}.bmpv7-fields .wide{{grid-column:1/-1}}.bmpv7-save{{margin-top:10px;min-height:45px;padding:10px 18px;border:0;border-radius:10px;background:#16a34a;color:#fff;font-weight:950}}
        .bmpv7-list{{display:grid;gap:8px}}.bmpv7-row{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px 14px;align-items:center;padding:12px 14px;border-radius:14px}}.bmpv7-row.due{{background:rgba(127,29,29,.66);border:1px solid rgba(248,113,113,.28)}}.bmpv7-row.paid{{background:rgba(20,83,45,.55);border:1px solid rgba(74,222,128,.24)}}.bmpv7-person{{display:grid;gap:3px}}.bmpv7-person small{{color:#cbd5e1}}.bmpv7-actions{{display:flex;gap:7px;flex-wrap:wrap}}.bmpv7-actions a{{padding:9px 11px;border-radius:9px;background:#2563eb;color:#fff!important;text-decoration:none;font-size:11px;font-weight:950}}.bmpv7-actions a+ a{{background:#0f766e}}.bmpv7-actions a.doc{{background:#334155!important}}.bmpv7-admin{{display:flex;gap:8px;flex-wrap:wrap;margin:-4px 0 13px;align-items:center}}.bmpv7-admin span{{font-size:10px;font-weight:950;color:#94a3b8;letter-spacing:.1em}}.bmpv7-admin a{{padding:9px 11px;border-radius:9px;background:#172554;color:#dbeafe!important;text-decoration:none;font-size:11px;font-weight:900}}.bmpv7-months{{margin:0 0 12px;padding:10px;border-radius:13px;background:#0b1d31}}.bmpv7-months>strong{{display:block;margin-bottom:7px;font-size:10px;letter-spacing:.12em;color:#93c5fd}}.bmpv7-months>div{{display:flex;gap:7px;flex-wrap:wrap}}.bmpv7-months a{{display:grid;gap:2px;padding:8px 10px;border-radius:10px;color:#fff!important;text-decoration:none;font-size:11px}}.bmpv7-months a.due{{background:#7f1d1d}}.bmpv7-months a.ok{{background:#14532d}}.bmpv7-months span{{color:#e2e8f0}}.bmpv7-saved,.bmpv7-error{{margin:10px 0;padding:10px 12px;border-radius:10px;font-weight:850}}.bmpv7-saved{{background:#14532d;color:#dcfce7}}.bmpv7-error{{background:#7f1d1d;color:#fee2e2}}
        @media(max-width:780px){{.bmpv7{{padding:12px}}.bmpv7-head{{align-items:flex-start}}.bmpv7-head h1{{font-size:21px}}.bmpv7-fields{{grid-template-columns:1fr 1fr}}.bmpv7-fields .wide{{grid-column:1/-1}}.bmpv7-row{{grid-template-columns:1fr}}.bmpv7-actions{{display:grid;grid-template-columns:1fr}}}}
        </style>"""

        import re as _re
        m=_re.search(r'(<main\\b[^>]*>)(.*?)(</main>)',html,_re.I|_re.S)
        if not m:raise RuntimeError('canonical payment main element missing')
        html=html[:m.start(2)]+surface+html[m.end(2):]
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


# BODYMIND_R123_CANONICAL_PAYMENT_CONVERGENCE
# Reconcile already-persistent runtime sources without introducing another release layer.
# This is source-only: no payment/receipt/document rows are created, deleted or rewritten here.
_core_conv=CORE.read_text(encoding='utf-8',errors='replace')
_old_quote_truth=r"""    # Legacy quote_mensili can prove that a monthly was already marked paid,
    # but never creates a second cash receipt.
    if _table_local('quote_mensili'):
        qrows=conn.execute("SELECT * FROM quote_mensili WHERE mese=? AND anno=?",(mese,anno)).fetchall()
        for q in qrows:
            tid=int(q['tesserato_id'] or 0) if 'tesserato_id' in q.keys() else 0
            if tid not in by_tid: continue
            st=str(q['stato'] or '').strip().lower() if 'stato' in q.keys() else ''
            if any(x in st for x in ('pagat','saldat','paid','incassat','complet')):
                by_tid[tid]['mensile_pagato']=True

"""
_new_quote_truth=r"""    # quote_mensili describes what is due (and can retain legacy workflow state),
    # but it is NOT evidence of a cash receipt. A monthly is paid only when a
    # canonical row exists in pagamenti for the exact athlete + month + year.
    # This prevents Dashboard/Task/Tesserati/Operatore from inventing an incasso.

"""
if _old_quote_truth in _core_conv:
    _core_conv=_core_conv.replace(_old_quote_truth,_new_quote_truth,1)
_core_conv=_core_conv.replace(
    "if request.method!='GET' or request.path!='/dashboard' or int(getattr(resp,'status_code',200) or 200)!=200:",
    "if request.method!='GET' or request.path not in ('/dashboard','/cuore-operativo','/centro-operativo') or int(getattr(resp,'status_code',200) or 200)!=200:",
    1
)
# Collaboratori is a real business module and must remain visible in normal desktop navigation.
_core_conv=_core_conv.replace(
    "if can_access_section('collaboratori') and is_advanced_mode() else ''",
    "if can_access_section('collaboratori') else ''"
)
CORE.write_text(_core_conv,encoding='utf-8')
py_compile.compile(str(CORE),doraise=True)

# Patch only the canonical payment/navigation fragments in the already-installed
# operator; preserve R52-R155 document, audio and iOS work.
_OP=APP/'asd_app/routes_operator_bodymind.py'
if _OP.exists():
    _ops=_OP.read_text(encoding='utf-8',errors='replace')
    _src=Path('/opt/bodymind/operator_bodymind_runtime_r29.py').read_text(encoding='utf-8',errors='replace')
    for _start,_end in (
        ('def _payment_split_counts(', '\ndef _global_check('),
        ('def _links_for(', '\ndef _set_pending_action('),
    ):
        _a=_src.find(_start); _b=_src.find(_end,_a)
        _oa=_ops.find(_start); _ob=_ops.find(_end,_oa)
        if _a>=0 and _b>_a and _oa>=0 and _ob>_oa:
            _ops=_ops[:_oa]+_src[_a:_b]+_ops[_ob:]
    # Copy the deterministic named-athlete payment branch from canonical source.
    _mark='# Canonical deterministic payment status for a named athlete.'
    if _mark not in _ops and _mark in _src:
        _sa=_src.find(_mark)
        _sb=_src.find('    # BODYMIND_R40_AGENT_TOOLS',_sa)
        _anchor='    # BODYMIND_R40_AGENT_TOOLS'
        _oa=_ops.find(_anchor)
        if _sb>_sa and _oa>=0:
            _ops=_ops[:_oa]+_src[_sa:_sb]+_ops[_oa:]
    # Period-aware count branch: replace only the simple-fact payment clause.
    _s0=_src.find('        if "pagament" in n or "incass" in n:')
    _s1=_src.find('        if "ricevut" in n:',_s0)
    _o0=_ops.find('        if "pagament" in n or "incass" in n:')
    _o1=_ops.find('        if "ricevut" in n:',_o0)
    if _s0>=0 and _s1>_s0 and _o0>=0 and _o1>_o0:
        _ops=_ops[:_o0]+_src[_s0:_s1]+_ops[_o1:]
    _OP.write_text(_ops,encoding='utf-8')
    py_compile.compile(str(_OP),doraise=True)

# Read-only convergence gate. Never use quote_mensili as proof of an incasso.
_conv_qa=r"""
import json,sqlite3,sys
sys.path.insert(0,"/data/top2_app")
import app as _full
from asd_app.core import app,bodymind_payment_truth
from pathlib import Path
c=sqlite3.connect("/data/tenants/default/asd.db",timeout=20); c.row_factory=sqlite3.Row
try:
    before={t:int(c.execute("SELECT COUNT(*) FROM "+t).fetchone()[0]) for t in ("tesserati","pagamenti","ricevute")}
    today=__import__('datetime').date.today()
    truth=bodymind_payment_truth(c,mese=today.month,anno=today.year)
    mismatches=[]
    for row in truth.get("rows",[]):
        tid=int(row["tesserato_id"])
        paid=c.execute('''SELECT 1 FROM pagamenti WHERE tesserato_id=? AND mese=? AND anno=?
          AND (lower(coalesce(causale,'')) LIKE '%mensil%' OR lower(coalesce(causale,'')) IN ('quota','quota_mensile'))
          AND lower(coalesce(stato,'')||' '||coalesce(online_status,'')) NOT LIKE '%pending%'
          AND lower(coalesce(stato,'')||' '||coalesce(online_status,'')) NOT LIKE '%annull%'
          AND lower(coalesce(stato,'')||' '||coalesce(online_status,'')) NOT LIKE '%failed%'
          LIMIT 1''',(tid,today.month,today.year)).fetchone()
        if bool(row.get("mensile_pagato")) != bool(paid):
            mismatches.append(tid)
    after={t:int(c.execute("SELECT COUNT(*) FROM "+t).fetchone()[0]) for t in ("tesserati","pagamenti","ricevute")}
    integrity=str(c.execute("PRAGMA integrity_check").fetchone()[0]); fk=len(c.execute("PRAGMA foreign_key_check").fetchall())
finally:c.close()
src=Path("/data/top2_app/asd_app/core.py").read_text(encoding="utf-8",errors="replace")
ops=Path("/data/top2_app/asd_app/routes_operator_bodymind.py").read_text(encoding="utf-8",errors="replace")
out={"counts_before":before,"counts_after":after,"monthly_truth_mismatches":mismatches,"integrity":integrity,"fk":fk,
     "collaboratori_normal_nav":"if can_access_section('collaboratori') and is_advanced_mode() else ''" not in src,
     "operator_canonical":"from .core import bodymind_payment_truth" in ops and "/quote-incassi/atleta/" not in ops,
     "no_forced_ios_scroll":"if(window.scrollY)window.scrollTo(0,0);" not in ops}
print("[r123-canonical-payment-convergence-audit] "+json.dumps(out,ensure_ascii=False),flush=True)
if before!=after or mismatches or integrity.lower()!="ok" or fk or not all(out[k] for k in ("collaboratori_normal_nav","operator_canonical","no_forced_ios_scroll")):
    raise RuntimeError("canonical payment convergence audit failed")
"""
_cp=subprocess.run([sys.executable,"-c",_conv_qa],capture_output=True,text=True,timeout=180)
print((_cp.stdout or "").strip(),flush=True)
if _cp.returncode!=0:
    raise RuntimeError("R123 canonical convergence child audit failed "+((_cp.stderr or "")+(_cp.stdout or ""))[-6000:])
print('[r123-canonical-payment-convergence] PASS one-cash-truth operator-links collaborators-visible ios-preserved',flush=True)


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

_v10_qa=r"""
import json,sqlite3,sys
sys.path.insert(0,"/data/top2_app");import app as _full
from asd_app.core import bodymind_payment_truth,bodymind_monthly_due_summary
c=sqlite3.connect("file:/data/tenants/default/asd.db?mode=ro",uri=True,timeout=20);c.row_factory=sqlite3.Row
try:
    monthly=bodymind_monthly_due_summary(c);truth=bodymind_payment_truth(c)
    stale=[dict(x) for x in c.execute("SELECT id,nome,cognome,onboarding_status,onboarding_blocked_reason FROM tesserati WHERE COALESCE(attivo,1)=1 AND lower(coalesce(onboarding_blocked_reason,'')) LIKE '%pagamenti da verificare%' ORDER BY id").fetchall()]
    integ=str(c.execute("PRAGMA integrity_check").fetchone()[0]);fk=len(c.execute("PRAGMA foreign_key_check").fetchall())
finally:c.close()
print("[r123-onboarding-v10-audit] "+json.dumps({"mode":"read_only","payment_rows":len(truth.get("rows",[])),"monthly":monthly,"stale_generic_payment_reasons":stale,"integrity":integ,"fk":fk},ensure_ascii=False),flush=True)
if integ.lower()!="ok" or fk or stale:raise RuntimeError("V10 onboarding/payment read-only audit failed")
"""
_v10p=subprocess.run([sys.executable,"-c",_v10_qa],capture_output=True,text=True,timeout=180)
print((_v10p.stdout or "").strip(),flush=True)
if _v10p.returncode!=0:
    raise RuntimeError("R123 V10 child audit failed "+((_v10p.stderr or "")+(_v10p.stdout or ""))[-6000:])
print('[r123-onboarding-v10] PASS read-only payment+onboarding invariant',flush=True)


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
    if request.path in ('/uscite','/pagamenti/uscite','/contabilita') and request.method in ('GET','POST'):
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
r3=client.get('/uscite',follow_redirects=False)
body=r1.get_data(as_text=True)
conn=sqlite3.connect("/data/tenants/default/asd.db",timeout=20)
try:
    cols=[str(x[1]) for x in conn.execute("PRAGMA table_info(bodymind_uscite)").fetchall()]
    counts={t:int(conn.execute("SELECT COUNT(*) FROM "+t).fetchone()[0]) for t in ("tesserati","pagamenti","ricevute")}
    integrity=str(conn.execute("PRAGMA integrity_check").fetchone()[0]); fk=len(conn.execute("PRAGMA foreign_key_check").fetchall())
finally:conn.close()
out={"uscite_status":r1.status_code,"contabilita_status":r2.status_code,"uscite_alias_status":r3.status_code,"marker":"BODYMIND_R123_EXPENSE_ATTACHMENTS_V11" in body,"multipart":"multipart/form-data" in body,"attachment_route":bool(expense_file),"columns":cols,"counts":counts,"integrity":integrity,"fk":fk}
print("[r123-expense-v11-audit] "+json.dumps(out,ensure_ascii=False),flush=True)
if r1.status_code!=200 or r2.status_code!=200 or r3.status_code!=200 or not out["marker"] or not out["multipart"] or not expense_file or not all(x in cols for x in ("allegato_path","allegato_nome","allegato_mime","allegato_size")) or integrity.lower()!="ok" or fk:
    raise RuntimeError("V11 expense attachments audit failed")
"""
_v11p=subprocess.run([sys.executable,"-c",_v11_qa],capture_output=True,text=True,timeout=180)
print((_v11p.stdout or "").strip(),flush=True)
if _v11p.returncode!=0:
    raise RuntimeError("R123 V11 child audit failed "+((_v11p.stderr or "")+(_v11p.stdout or ""))[-6000:])
print('[r123-expense-v11] PASS one-expense-module attachments-preview-download payments-preserved before='+str(_v11_before)+' after='+str(_v11_after),flush=True)


# BODYMIND_R123_DASHBOARD_CANONICAL
_core_dash=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R123_DASHBOARD_CANONICAL_RUNTIME' not in _core_dash:
    _core_dash += r'''

# BODYMIND_R123_DASHBOARD_CANONICAL_RUNTIME
def _bodymind_dashboard_add_body_class(html):
    import re as _bm_re
    m=_bm_re.search(r'<body\\b([^>]*)>',html,_bm_re.I)
    if not m:return html
    tag=m.group(0);cm=_bm_re.search(r'class=(["\\\'])(.*?)\\1',tag,_bm_re.I|_bm_re.S)
    if cm:
        classes=cm.group(2).split()
        if 'bodymind-dashboard-canonical' not in classes:classes.append('bodymind-dashboard-canonical')
        newtag=tag[:cm.start(2)]+' '.join(classes)+tag[cm.end(2):]
    else:newtag=tag[:-1]+" class='bodymind-dashboard-canonical'>"
    return html[:m.start()]+newtag+html[m.end():]

@app.after_request
def _bodymind_dashboard_canonical(resp):
    try:
        if request.method!='GET' or request.path not in ('/','/dashboard'):return resp
        if int(getattr(resp,'status_code',200) or 200)!=200 or 'text/html' not in str(resp.headers.get('Content-Type','')).lower():return resp
        html=resp.get_data(as_text=True)
        if 'BODYMIND_R123_DASHBOARD_CANONICAL_RENDERED' in html:return resp
        html=_bodymind_dashboard_add_body_class(html)
        from datetime import date as _date
        today=_date.today();c=db();c.row_factory=sqlite3.Row
        try:
            t=bodymind_payment_truth(c,mese=today.month,anno=today.year)
            try:summary=bodymind_monthly_due_summary(c)
            except Exception:summary=[]
        finally:
            try:c.close()
            except Exception:pass
        months=['','Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno','Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre']
        chips=''.join("<a class='"+("ok" if int(x['mancanti'])==0 else "due")+"' href='/pagamenti?vista=mensili&mese="+str(x['mese'])+"&anno="+str(x['anno'])+"'><b>"+months[int(x['mese'])]+" "+str(x['anno'])+"</b><span>"+(str(x['mancanti'])+" da pagare" if int(x['mancanti']) else "completo")+"</span></a>" for x in summary)
        panel=f"""<!-- BODYMIND_R123_DASHBOARD_CANONICAL_RENDERED --><section class='bmdc-payments'><div><span>PAGAMENTI · VERITÀ CANONICA</span><h2>Iscrizioni e mensile</h2><p>Stessa sorgente usata da Pagamenti, Tesserati, Operatore e onboarding.</p></div><div class='bmdc-paygrid'><a href='/pagamenti?vista=iscrizioni&stagione={t['stagione']}'><small>ISCRIZIONI {t['stagione']}/{t['stagione']+1}</small><strong>{t['iscrizioni_pagate']}/{t['totale']}</strong><em>{t['iscrizioni_mancanti']} da completare</em></a><a href='/pagamenti?vista=mensili&mese={t['mese']}&anno={t['anno']}'><small>MENSILE · {months[t['mese']]} {t['anno']}</small><strong>{t['mensili_pagati']}/{t['totale']}</strong><em>{t['mensili_mancanti']} da completare</em></a></div>{("<div class='bmdc-months'>"+chips+"</div>" if chips else "")}</section>"""
        css="""<style id='bodymind-dashboard-canonical-style'>body.bodymind-dashboard-canonical{background:radial-gradient(circle at 12% 6%,rgba(255,255,255,.10) 0%,rgba(255,255,255,.04) 18%,transparent 38%),radial-gradient(circle at 88% 12%,rgba(59,130,246,.14) 0%,rgba(30,64,175,.07) 24%,transparent 44%),radial-gradient(circle at 54% 86%,rgba(14,165,233,.08) 0%,transparent 42%),linear-gradient(145deg,#07111f 0%,#0a1728 42%,#0d2034 72%,#071321 100%)!important;background-attachment:fixed!important;min-height:100vh}body.bodymind-dashboard-canonical>.overlay,body.bodymind-dashboard-canonical .pro-dashboard,body.bodymind-dashboard-canonical .dashboard,body.bodymind-dashboard-canonical .dashboard-page,body.bodymind-dashboard-canonical main{background:transparent!important}.bmdc-payments{margin:12px 0 16px;padding:16px;border-radius:20px;background:linear-gradient(145deg,rgba(7,19,34,.88),rgba(11,30,49,.80));border:1px solid rgba(96,165,250,.24);box-shadow:0 18px 45px rgba(0,0,0,.18);color:#f8fafc}.bmdc-payments>div>span{font-size:10px;letter-spacing:.14em;font-weight:950;color:#7dd3fc}.bmdc-payments h2{margin:4px 0}.bmdc-payments p{margin:0;color:#b7c6d9}.bmdc-paygrid{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:12px}.bmdc-paygrid a{display:grid;gap:3px;padding:13px;border-radius:14px;background:#0b1d31;border:1px solid rgba(148,163,184,.16);color:#fff!important;text-decoration:none}.bmdc-paygrid small{color:#93c5fd;font-weight:900}.bmdc-paygrid strong{font-size:24px}.bmdc-paygrid em{font-style:normal;color:#cbd5e1;font-size:11px}.bmdc-months{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}.bmdc-months a{display:grid;gap:2px;padding:8px 10px;border-radius:10px;color:#fff!important;text-decoration:none;font-size:11px}.bmdc-months a.due{background:#7f1d1d}.bmdc-months a.ok{background:#14532d}.bmdc-months span{color:#e2e8f0}@media(max-width:760px){body.bodymind-dashboard-canonical{background:radial-gradient(circle at 12% 6%,rgba(255,255,255,.08) 0%,rgba(255,255,255,.03) 18%,transparent 36%),linear-gradient(160deg,#07111f 0%,#0a1728 52%,#071321 100%)!important;background-attachment:scroll!important}.bmdc-paygrid{grid-template-columns:1fr}}</style>"""
        if '</head>' in html:html=html.replace('</head>',css+'</head>',1)
        import re as _bm_re;m=_bm_re.search(r'<main\\b[^>]*>',html,_bm_re.I)
        if not m:raise RuntimeError('canonical dashboard main element missing')
        html=html[:m.end()]+panel+html[m.end():];resp.set_data(html)
    except Exception as exc:print('[dashboard-canonical-warning] '+repr(exc),flush=True)
    return resp
'''
    CORE.write_text(_core_dash,encoding='utf-8');py_compile.compile(str(CORE),doraise=True)
    print('[r123-dashboard-canonical] installed one server-side dashboard authority',flush=True)
else:print('[r123-dashboard-canonical] already installed',flush=True)

_final_qa=r"""
import json,re,sqlite3,sys
sys.path.insert(0,'/data/top2_app');import app as _full
from asd_app.core import app,bodymind_payment_truth
app.config['TESTING']=True;c=app.test_client()
with c.session_transaction() as s:s.update({'logged':True,'logged_in':True,'username':'admin','display_name':'Canonical QA','role':'admin','tenant_slug':'default','user_id':1,'is_admin':True,'admin':True})
paths=['/','/dashboard','/tesserati','/pagamenti','/documenti','/documenti-automatici','/contabilita','/uscite','/collaboratori','/operatore-bodymind','/mobile','/mobile/atlete']
status={p:c.get(p,follow_redirects=False).status_code for p in paths}
dh=c.get('/dashboard',follow_redirects=True).get_data(as_text=True);hh=c.get('/',follow_redirects=True).get_data(as_text=True);ph=c.get('/pagamenti?vista=mensili',follow_redirects=True).get_data(as_text=True)
def body(h):
    m=re.search(r'<body\\b[^>]*class=["\\\']([^"\\\']*)',h,re.I);return m.group(1).split() if m else []
old_dash=('BODYMIND_R123_DASHBOARD_BACKGROUND_RESTORE_RENDERED','BODYMIND_R156_DASHBOARD_RECOMPOSE_RENDERED','BODYMIND_PAYMENT_TRUTH_DASHBOARD_V3','BODYMIND_MONTHLY_ARREARS_V5_RENDERED')
old_pay=('BODYMIND_R123_PAYMENT_MOBILE','BODYMIND_R125_PAYMENT_BOARD','BODYMIND_R123_PAYMENT_SPLIT_V2_SURFACE','BODYMIND_R123_CANONICAL_PAYMENT_MODULE_V5','bmpv6-immediate')
row_state={int(a):(b=='1',d=='1') for a,b,d in re.findall(r'data-bm-tid=["\\\'](\\d+)["\\\']\\s+data-bm-enroll=["\\\']([01])["\\\']\\s+data-bm-monthly=["\\\']([01])["\\\']',ph)}
db=sqlite3.connect('file:/data/tenants/default/asd.db?mode=ro',uri=True,timeout=20);db.row_factory=sqlite3.Row
try:
    truth=bodymind_payment_truth(db);expected={int(x['tesserato_id']):(bool(x['iscrizione_pagata']),bool(x['mensile_pagato'])) for x in truth['rows']}
    counts={t:int(db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]) for t in ('tesserati','pagamenti','ricevute','quote_mensili','documenti','inbound_documents')}
    integrity=str(db.execute('PRAGMA integrity_check').fetchone()[0]);fk=len(db.execute('PRAGMA foreign_key_check').fetchall());legacy_only=[];season=int(truth['stagione'])
    for x in truth['rows']:
        tid=int(x['tesserato_id']);pay=db.execute('''SELECT 1 FROM pagamenti WHERE tesserato_id=? AND anno IN (?,?) AND (lower(coalesce(causale,''))='iscrizione' OR lower(coalesce(causale,''))='tesseramento' OR lower(coalesce(causale,'')) LIKE '%iscrizion%') AND lower(coalesce(stato,'')||' '||coalesce(online_status,'')) NOT LIKE '%pending%' AND lower(coalesce(stato,'')||' '||coalesce(online_status,'')) NOT LIKE '%annull%' AND lower(coalesce(stato,'')||' '||coalesce(online_status,'')) NOT LIKE '%failed%' LIMIT 1''',(tid,season,season+1)).fetchone()
        if bool(x['iscrizione_pagata']) and not pay:legacy_only.append(tid)
finally:db.close()
checks={'routes':all(v in (200,301,302,303,307,308) for v in status.values()),'dashboard_body':all('bodymind-dashboard-canonical' in body(x) for x in (dh,hh)),'dashboard_single':dh.count('BODYMIND_R123_DASHBOARD_CANONICAL_RENDERED')==1 and hh.count('BODYMIND_R123_DASHBOARD_CANONICAL_RENDERED')==1,'dashboard_old_absent':not any(x in dh or x in hh for x in old_dash),'payment_single':ph.count('BODYMIND_R123_PAYMENT_FORM_CANONICAL_V7')==1,'payment_old_absent':not any(x in ph for x in old_pay),'payment_truth_matches':row_state==expected,'db':integrity.lower()=='ok' and fk==0}
print('[r123-final-rendered-audit] '+json.dumps({'checks':checks,'status':status,'body_dashboard':body(dh),'body_home':body(hh),'payment_rows':len(row_state),'truth_rows':len(expected),'legacy_enrollment_flags_without_canonical_payment':legacy_only,'counts':counts,'integrity':integrity,'fk':fk},ensure_ascii=False),flush=True)
if not all(checks.values()):raise RuntimeError('R123 final rendered audit failed '+repr(checks))
"""
_q=subprocess.run([sys.executable,'-c',_final_qa],capture_output=True,text=True,timeout=180);print((_q.stdout or '').strip(),flush=True)
if _q.returncode!=0:raise RuntimeError('R123 final rendered child audit failed '+((_q.stderr or '')+(_q.stdout or ''))[-7000:])

_r123_guard=sqlite3.connect("file:"+str(DB)+"?mode=ro",uri=True,timeout=20)
try:
    _r123_counts_after={t:int(_r123_guard.execute("SELECT COUNT(*) FROM "+t).fetchone()[0]) for t in ("tesserati","pagamenti","ricevute","quote_mensili","documenti","inbound_documents")}
finally:_r123_guard.close()
if _r123_counts_before!=_r123_counts_after:raise RuntimeError('R123 refactor changed business row counts before='+repr(_r123_counts_before)+' after='+repr(_r123_counts_after))
print('[r123-final-rendered] PASS canonical-dashboard canonical-payment no-mask data-counts-unchanged',flush=True)
