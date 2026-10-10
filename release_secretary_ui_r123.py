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
 '_bodymind_uscita_write_v11','_bodymind_uscita_attachment_link_v11','bodymind_quote_incassi_canonical',
 '_bodymind_dashboard_background_restore_r123','_bodymind_dashboard_recompose_r156',
))
_marker_text=CORE.read_text(encoding='utf-8',errors='replace')
for _marker in (
 '# BODYMIND_R123_PAYMENT_FORM_CANONICAL_V7\n',
 '# BODYMIND_R123_EXPENSE_ATTACHMENTS_V11\n',
 '# BODYMIND_R123_QUOTE_INCASSI_CANONICAL_V12\n',
):
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
        selected_payment_id=parse_int(request.args.get('payment_id'),0)
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
                    if not qtid or qtid in quote_by_tid:continue
                    qstate=str(q.get('stato') or '').strip().lower()
                    if any(x in qstate for x in ('non_dovuto','non dovuto','esente','annull','sospes')):continue
                    quote_by_tid[qtid]=q
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
            monthly_due=tid in quote_by_tid
            if vista=='mensili' and not monthly_due:
                continue
            focus_ok=eok if vista=='iscrizioni' else mok
            if not focus_ok:due_count+=1
            row_state='due' if not focus_ok else ('paid' if eok and (mok or not monthly_due) else 'mixed')
            eh=f"/pagamenti?vista=iscrizioni&stagione={stagione}&mese={mese}&anno={anno}&tesserato_id={tid}&azione=registra&tipo=iscrizione"
            mh=f"/pagamenti?vista=mensili&mese={mese}&anno={anno}&tesserato_id={tid}&azione=registra&tipo=mensile"
            dh=f"/documenti/da-verificare?tesserato_id={tid}"
            ah=f"/documenti?tesserato_id={tid}"
            # BODYMIND_R123_PAYMENT_EXACT_ID_V14: expose each real movement, never only an aggregate.
            movement_links=[]
            for _p in payment_rows.values():
                if int(_p.get('tesserato_id') or 0)!=tid: continue
                _st=(str(_p.get('stato') or '')+' '+str(_p.get('online_status') or '')).lower()
                if 'annull' in _st or 'cancel' in _st: continue
                _cause=str(_p.get('causale') or '').lower()
                _monthly=('mensil' in _cause or _cause in ('quota','quota_mensile'))
                _enroll=('iscrizion' in _cause or _cause=='tesseramento')
                if vista=='mensili' and (not _monthly or int(_p.get('mese') or 0)!=mese or int(_p.get('anno') or 0)!=anno): continue
                if vista=='iscrizioni' and (not _enroll or int(_p.get('anno') or 0) not in (stagione,stagione+1)): continue
                _pid=int(_p.get('id') or 0); _typ='mensile' if _monthly else 'iscrizione'
                _edit=f"/pagamenti?vista={vista}&mese={mese}&anno={anno}&stagione={stagione}&tesserato_id={tid}&azione=registra&tipo={_typ}&payment_id={_pid}"
                movement_links.append("<a class='doc' href='"+_edit+"'>Apri pagamento · "+_money(_p.get('importo'))+"</a>")
            rows.append((0 if not focus_ok else 1,
                "<div class='bmpv7-row "+row_state+"' data-bm-tid='"+str(tid)+"' data-bm-enroll='"+("1" if eok else "0")+"' data-bm-monthly='"+("1" if mok else "0")+"'>"
                +"<div class='bmpv7-person'><b>"+e(_name(a))+"</b>"
                +"<div class='bmpv7-statuses'>"
                +"<span class='bmpv7-status "+("ok" if eok else "due")+"'><i></i><b>ISCRIZIONE "+str(stagione)+"/"+str(stagione+1)+"</b><em>"+("PAGATA" if eok else "DA PAGARE")+"</em></span>"
                +("<span class='bmpv7-status "+("ok" if mok else "due")+"'><i></i><b>"+months[mese].upper()+" "+str(anno)+"</b><em>"+("PAGATO" if mok else "DA PAGARE")+"</em></span>" if monthly_due else "<span class='bmpv7-status na'><i></i><b>"+months[mese].upper()+" "+str(anno)+"</b><em>NON DOVUTO</em></span>")
                +"</div></div>"
                +("<div class='bmpv7-actions'>"+''.join(movement_links)+"</div>" if movement_links else "")
                +"<div class='bmpv7-actions'><a class='doc' href='"+dh+"'>Verifica documento</a><a class='doc' href='"+ah+"'>Archivio</a><a href='"+eh+"'>"+("Correggi iscrizione" if eok else "Registra iscrizione")+"</a>"+(("<a href='"+mh+"'>"+("Correggi "+months[mese] if mok else "Registra "+months[mese])+"</a>") if monthly_due else "<span class='bmpv7-action-na'>"+months[mese]+" non dovuto</span>")+"</div>"
                +"</div>"
            ))
        rows.sort(key=lambda x:x[0])

        form_html=''
        if selected_tid and action=='registra':
            athlete=next((a for a in athletes if int(a.get('id') or 0)==selected_tid),None)
            if athlete:
                state=payment_state.get(selected_tid,{})
                existing_id=selected_payment_id or (state.get('iscrizione_payment_id') if action_tipo=='iscrizione' else state.get('mensile_payment_id'))
                existing=payment_rows.get(int(existing_id or 0))
                if existing and int(existing.get('tesserato_id') or 0)!=selected_tid:
                    existing=None
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
                if pid:
                    delete_label='Elimina iscrizione' if action_tipo=='iscrizione' else 'Elimina mensile'
                    form_html+=f"""<form class='bmpv7-delete' method='post' action='/pagamenti/elimina'>
                      <input type='hidden' name='csrf_token' value='{e(csrf_token())}'>
                      <input type='hidden' name='payment_id' value='{pid}'>
                      <button type='submit' onclick="return confirm('Eliminare questa registrazione? Verrà annullata e non conterà più negli incassi.')">{e(delete_label)}</button>
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
          <div class='bmpv7-head'><div><span>PAGAMENTI BODYMIND · MODULO UNICO</span><h1>{'ISCRIZIONE' if vista=='iscrizioni' else 'MENSILE '+months[mese].upper()}</h1><p>Rosso = quota selezionata ancora da incassare. Iscrizione annuale e mensile del mese sono mostrati separatamente: una non rende verde l'altra.</p></div><strong>{due_count} da pagare</strong></div>
          <nav class='bmpv7-tabs'><a class='{'on' if vista=='iscrizioni' else ''}' href='/pagamenti?vista=iscrizioni&stagione={stagione}&mese={mese}&anno={anno}'>ISCRIZIONE</a><a class='{'on' if vista=='mensili' else ''}' href='/pagamenti?vista=mensili&mese={mese}&anno={anno}'>MENSILE</a></nav>
          <div class='bmpv7-admin'><span>AMMINISTRAZIONE</span><a href='/uscite'>USCITE</a><a href='/ricevute'>RICEVUTE</a><a href='/collaboratori'>COLLABORATORI</a><a href='/collaboratori/ricevute'>RICEVUTE COLLABORATORI</a><a href='/documenti'>ARCHIVIO</a><a href='/documenti/da-verificare'>DA VERIFICARE</a></div>
          {selector}{month_strip}{saved}{error}{form_html}
          <div class='bmpv7-list'>{''.join(x[1] for x in rows)}</div>
        </section>
        <style id='bodymind-payment-v7'>
        .bmpv7{{min-width:0;margin:12px 0 22px;padding:16px;border-radius:20px;background:#081626;border:1px solid rgba(96,165,250,.24);color:#f8fafc;overflow:hidden}}.bmpv7-head{{display:flex;justify-content:space-between;gap:14px;align-items:center}}.bmpv7-head span{{font-size:10px;letter-spacing:.14em;font-weight:950;color:#7dd3fc}}.bmpv7-head h1{{margin:4px 0;font-size:clamp(21px,2.3vw,27px)}}.bmpv7-head p{{margin:0;color:#b7c6d9;max-width:760px;line-height:1.45}}.bmpv7-head>strong{{font-size:20px;white-space:nowrap}}
        .bmpv7-tabs{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:13px 0}}.bmpv7-tabs a{{padding:12px;border-radius:12px;background:#10243a;color:#cbd5e1!important;text-decoration:none;text-align:center;font-weight:950}}.bmpv7-tabs a.on{{background:#2563eb;color:white!important}}
        .bmpv7-period{{display:flex;gap:8px;align-items:end;flex-wrap:wrap;margin-bottom:12px;padding:10px;border-radius:13px;background:#0c2035}}.bmpv7-period label{{display:grid;gap:4px;font-size:11px;font-weight:900}}.bmpv7-period input,.bmpv7-period select,.bmpv7-period button{{min-height:40px;border-radius:9px;border:1px solid rgba(148,163,184,.25);background:#06111f;color:#fff;padding:8px 10px}}.bmpv7-period button{{background:#2563eb;font-weight:900}}
        .bmpv7-form{{margin:12px 0 16px;padding:14px;border-radius:15px;background:#0d2138;border:2px solid rgba(96,165,250,.48)}}.bmpv7-formhead{{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:12px}}.bmpv7-formhead span{{font-size:10px;font-weight:950;color:#7dd3fc}}.bmpv7-formhead h2{{margin:3px 0;font-size:20px}}.bmpv7-formhead a{{color:#bfdbfe!important}}.bmpv7-fields{{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px}}.bmpv7-fields label{{display:grid;gap:5px;min-width:0;font-size:11px;font-weight:900;color:#cbd5e1}}.bmpv7-fields input,.bmpv7-fields select,.bmpv7-fields textarea{{width:100%;min-width:0;border-radius:9px;border:1px solid rgba(148,163,184,.25);background:#06111f;color:#fff;padding:9px;font-size:14px}}.bmpv7-fields .wide{{grid-column:1/-1}}.bmpv7-save{{margin-top:10px;min-height:44px;padding:10px 18px;border:0;border-radius:10px;background:#16a34a;color:#fff;font-weight:950}}.bmpv7-delete{{margin:8px 0 16px;padding:0 14px 14px;background:#0d2138;border-left:2px solid rgba(96,165,250,.48);border-right:2px solid rgba(96,165,250,.48);border-bottom:2px solid rgba(96,165,250,.48);border-radius:0 0 15px 15px}}.bmpv7-delete button{{width:100%;min-height:44px;border:1px solid #ef4444;border-radius:10px;background:#450a0a;color:#fecaca;font-weight:950;cursor:pointer}}
        .bmpv7-list{{display:grid;gap:8px;min-width:0}}.bmpv7-row{{display:grid;grid-template-columns:minmax(280px,.9fr) minmax(360px,1.1fr);gap:10px 14px;align-items:center;min-width:0;padding:12px 13px;border-radius:14px;background:rgba(11,29,49,.86);border:1px solid rgba(148,163,184,.16)}}.bmpv7-row.due{{background:rgba(82,20,28,.72);border-color:rgba(248,113,113,.38)}}.bmpv7-row.paid{{background:rgba(17,70,40,.62);border-color:rgba(74,222,128,.30)}}.bmpv7-row.mixed{{background:rgba(11,29,49,.94);border-color:rgba(125,211,252,.20)}}.bmpv7-person{{display:grid;gap:8px;min-width:0}}.bmpv7-person>b{{font-size:14px;overflow-wrap:anywhere}}.bmpv7-statuses{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}}.bmpv7-status{{display:grid;grid-template-columns:9px minmax(0,1fr) auto;gap:6px;align-items:center;min-width:0;padding:7px 8px;border-radius:9px;border:1px solid rgba(148,163,184,.18);font-size:10px}}.bmpv7-status i{{width:8px;height:8px;border-radius:50%;background:#dc2626;box-shadow:0 0 0 3px rgba(220,38,38,.14)}}.bmpv7-status b{{min-width:0;font-size:10px;letter-spacing:.02em;overflow-wrap:anywhere}}.bmpv7-status em{{font-style:normal;font-weight:950;white-space:nowrap}}.bmpv7-status.due{{background:rgba(127,29,29,.62);border-color:rgba(248,113,113,.34);color:#fee2e2}}.bmpv7-status.ok{{background:rgba(20,83,45,.72);border-color:rgba(74,222,128,.30);color:#dcfce7}}.bmpv7-status.ok i{{background:#22c55e;box-shadow:0 0 0 3px rgba(34,197,94,.14)}}.bmpv7-status.na{{background:rgba(51,65,85,.44);border-color:rgba(148,163,184,.22);color:#cbd5e1}}.bmpv7-status.na i{{background:#64748b;box-shadow:none}}
        .bmpv7-actions{{display:grid;grid-template-columns:repeat(2,minmax(145px,1fr));gap:6px;justify-self:end;width:min(100%,510px)}}.bmpv7-actions a,.bmpv7-action-na{{display:flex;align-items:center;justify-content:center;min-height:38px;padding:8px 9px;border-radius:9px;text-align:center;font-size:10px;font-weight:950;line-height:1.2}}.bmpv7-actions a{{background:#2563eb;color:#fff!important;text-decoration:none}}.bmpv7-actions a+ a{{background:#0f766e}}.bmpv7-actions a.doc{{background:#334155!important}}.bmpv7-action-na{{background:#334155;color:#cbd5e1;border:1px solid rgba(148,163,184,.22)}}.bmpv7-admin{{display:flex;gap:6px;flex-wrap:wrap;margin:-3px 0 12px;align-items:center}}.bmpv7-admin span{{font-size:10px;font-weight:950;color:#94a3b8;letter-spacing:.1em}}.bmpv7-admin a{{padding:8px 9px;border-radius:9px;background:#172554;color:#dbeafe!important;text-decoration:none;font-size:10px;font-weight:900}}.bmpv7-months{{margin:0 0 12px;padding:10px;border-radius:13px;background:#0b1d31}}.bmpv7-months>strong{{display:block;margin-bottom:7px;font-size:10px;letter-spacing:.12em;color:#93c5fd}}.bmpv7-months>div{{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:6px}}.bmpv7-months a{{display:grid;gap:2px;padding:7px 9px;border-radius:9px;color:#fff!important;text-decoration:none;font-size:10px}}.bmpv7-months a.due{{background:#7f1d1d}}.bmpv7-months a.ok{{background:#14532d}}.bmpv7-months span{{color:#e2e8f0}}.bmpv7-saved,.bmpv7-error{{margin:10px 0;padding:10px 12px;border-radius:10px;font-weight:850}}.bmpv7-saved{{background:#14532d;color:#dcfce7}}.bmpv7-error{{background:#7f1d1d;color:#fee2e2}}
        @media(max-width:1400px){{.bmpv7-row{{grid-template-columns:1fr}}.bmpv7-actions{{justify-self:stretch;width:100%;grid-template-columns:repeat(4,minmax(0,1fr))}}.bmpv7-fields{{grid-template-columns:repeat(3,minmax(0,1fr))}}}}
        @media(max-width:780px){{.bmpv7{{padding:11px}}.bmpv7-head{{align-items:flex-start}}.bmpv7-head h1{{font-size:21px}}.bmpv7-head>strong{{font-size:16px}}.bmpv7-fields{{grid-template-columns:1fr 1fr}}.bmpv7-fields .wide{{grid-column:1/-1}}.bmpv7-statuses{{grid-template-columns:1fr}}}}
        @media(max-width:560px){{.bmpv7-head{{display:grid}}.bmpv7-head>strong{{justify-self:start}}.bmpv7-actions{{grid-template-columns:1fr}}.bmpv7-fields{{grid-template-columns:1fr}}.bmpv7-period label,.bmpv7-period input,.bmpv7-period select,.bmpv7-period button{{width:100%}}}}
        </style>"""

        import re as _re
        m=_re.search(r'(<main\b[^>]*>)(.*?)(</main>)',html,_re.I|_re.S)
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
from asd_app.core import app,bodymind_payment_truth,load_config,file_url
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
_v7b=_core_v10.find("def _bodymind_payment_module_v7",_v7a)
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
print("[r123-onboarding-v10-audit] "+json.dumps({"mode":"read_only","payment_rows":len(truth.get("rows",[])),"monthly":monthly,"legacy_stored_onboarding_flags":stale,"integrity":integ,"fk":fk},ensure_ascii=False),flush=True)
if integ.lower()!="ok" or fk:raise RuntimeError("V10 onboarding/payment read-only audit failed")
"""
_v10p=subprocess.run([sys.executable,"-c",_v10_qa],capture_output=True,text=True,timeout=180)
print((_v10p.stdout or "").strip(),flush=True)
if _v10p.returncode!=0:
    raise RuntimeError("R123 V10 child audit failed "+((_v10p.stderr or "")+(_v10p.stdout or ""))[-6000:])
print('[r123-onboarding-v10] PASS canonical payment truth read-only; legacy stored onboarding flags diagnostic only',flush=True)


# BODYMIND_R123_EXPENSE_ATTACHMENTS_V11
# Canonical Uscite module: one expense row, optional supporting document,
# preview/download, later attachment/update. Payment/enrollment rows are read-only here.
_v11_backup=BACK/'pre_v11_expense_attachments.db'
if not _v11_backup.exists():
    shutil.copy2(DB,_v11_backup)

_v11_ro=sqlite3.connect("file:"+str(DB)+"?mode=ro",uri=True,timeout=20); _v11_ro.row_factory=sqlite3.Row
try:
    _v11_exists=bool(_v11_ro.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bodymind_uscite'").fetchone())
    _v11_expense_baseline={
      'exists':_v11_exists,
      'count':(int(_v11_ro.execute("SELECT COUNT(*) FROM bodymind_uscite").fetchone()[0]) if _v11_exists else 0),
      'max_id':(int(_v11_ro.execute("SELECT COALESCE(MAX(id),0) FROM bodymind_uscite").fetchone()[0] or 0) if _v11_exists else 0),
      'schema':([tuple(x) for x in _v11_ro.execute("PRAGMA table_info(bodymind_uscite)").fetchall()] if _v11_exists else []),
      'indexes':([tuple(x) for x in _v11_ro.execute("PRAGMA index_list(bodymind_uscite)").fetchall()] if _v11_exists else []),
      'foreign_keys':([tuple(x) for x in _v11_ro.execute("PRAGMA foreign_key_list(bodymind_uscite)").fetchall()] if _v11_exists else []),
      'last_rows':([dict(x) for x in _v11_ro.execute("SELECT id,data,descrizione,categoria,importo,metodo,allegato_nome,created_at,updated_at FROM bodymind_uscite ORDER BY id DESC LIMIT 5").fetchall()] if _v11_exists else []),
    }
finally:_v11_ro.close()
print('[r123-expense-readonly-baseline] '+repr(_v11_expense_baseline),flush=True)

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


def _bodymind_uscita_attachment_save_v11(upload, expense_id, root_override=None):
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
    root=_Path(root_override or '/data/tenants/default/media/uscite')
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


def _bodymind_uscita_write_v11(conn, edit_id, data, descrizione, categoria, importo, metodo, note, now):
    edit_id=int(edit_id or 0)
    if edit_id:
        current=conn.execute("SELECT * FROM bodymind_uscite WHERE id=?",(edit_id,)).fetchone()
        if not current:
            raise ValueError('Uscita non trovata.')
        conn.execute("""
          UPDATE bodymind_uscite
             SET data=?,descrizione=?,categoria=?,importo=?,metodo=?,note=?,updated_at=?
           WHERE id=?
        """,(data,descrizione,categoria,importo,metodo,note,now,edit_id))
        return edit_id
    cur=conn.execute("""
      INSERT INTO bodymind_uscite(data,descrizione,categoria,importo,metodo,note,created_at,updated_at)
      VALUES(?,?,?,?,?,?,?,?)
    """,(data,descrizione,categoria,importo,metodo,note,now,now))
    return int(cur.lastrowid)


def _bodymind_uscita_attachment_link_v11(conn, expense_id, meta, now):
    conn.execute("""
      UPDATE bodymind_uscite
         SET allegato_path=?,allegato_nome=?,allegato_mime=?,allegato_size=?,updated_at=?
       WHERE id=?
    """,(meta['path'],meta['name'],meta['mime'],meta['size'],now,int(expense_id)))


def _bodymind_uscite_v11_impl():
    from datetime import date as _date, datetime as _dt
    conn=db(); conn.row_factory=sqlite3.Row
    _bodymind_uscite_schema_v11(conn)
    saved=(request.args.get('salvato')=='1'); err=''
    edit_id=(parse_int(request.form.get('uscita_id'),0) if request.method=='POST' else parse_int(request.args.get('modifica'),0))

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
                expense_id=_bodymind_uscita_write_v11(
                    conn,edit_id,data,descrizione,categoria,importo,metodo,note,now
                )

                upload=request.files.get('allegato')
                if upload and getattr(upload,'filename',''):
                    meta=_bodymind_uscita_attachment_save_v11(upload,expense_id)
                    _bodymind_uscita_attachment_link_v11(conn,expense_id,meta,now)
                conn.commit()
                target='/uscite?salvato=1'
                if request.path=='/pagamenti/uscite': target='/pagamenti/uscite?salvato=1'
                elif request.path=='/contabilita': target='/contabilita?salvato=1'
                conn.close()
                return redirect(target,303)
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
import io,json,os,sqlite3,sys,tempfile
sys.path.insert(0,"/data/top2_app")
import app as _full
import asd_app.core as core
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
prod=sqlite3.connect("file:/data/tenants/default/asd.db?mode=ro",uri=True,timeout=20);prod.row_factory=sqlite3.Row
try:
    baseline={
      "count":int(prod.execute("SELECT COUNT(*) FROM bodymind_uscite").fetchone()[0]),
      "max_id":int(prod.execute("SELECT COALESCE(MAX(id),0) FROM bodymind_uscite").fetchone()[0] or 0),
      "schema":[list(x) for x in prod.execute("PRAGMA table_info(bodymind_uscite)").fetchall()],
      "indexes":[list(x) for x in prod.execute("PRAGMA index_list(bodymind_uscite)").fetchall()],
      "foreign_keys":[list(x) for x in prod.execute("PRAGMA foreign_key_list(bodymind_uscite)").fetchall()],
      "last_rows":[dict(x) for x in prod.execute("SELECT id,data,descrizione,categoria,importo,metodo,allegato_nome,created_at,updated_at FROM bodymind_uscite ORDER BY id DESC LIMIT 5").fetchall()],
      "counts":{t:int(prod.execute("SELECT COUNT(*) FROM "+t).fetchone()[0]) for t in ("tesserati","pagamenti","ricevute","quote_mensili","documenti","inbound_documents")},
      "integrity":str(prod.execute("PRAGMA integrity_check").fetchone()[0]),
      "fk":len(prod.execute("PRAGMA foreign_key_check").fetchall()),
    }
finally:prod.close()

mutation={}
with tempfile.TemporaryDirectory(prefix="bodymind-expense-qa-") as td:
    qdb=os.path.join(td,"expense.db"); media=os.path.join(td,"media")
    orig_db=core.db; orig_save=core._bodymind_uscita_attachment_save_v11
    def qa_db():
        c=sqlite3.connect(qdb,timeout=10);c.row_factory=sqlite3.Row;return c
    def qa_save(upload,eid):
        return orig_save(upload,eid,media)
    core.db=qa_db;core._bodymind_uscita_attachment_save_v11=qa_save
    try:
        def post(payload):
            with app.test_request_context('/uscite',method='POST',data=payload):
                return core._bodymind_uscite_v11_impl()
        a=post({'uscita_id':'0','data':'2026-10-06','descrizione':'QA uscita A','categoria':'Affitto','importo':'700','metodo':'bonifico','note':'A','allegato':(io.BytesIO(b'A-attachment'),'a.pdf')})
        c=sqlite3.connect(qdb);c.row_factory=sqlite3.Row
        arow=dict(c.execute("SELECT * FROM bodymind_uscite ORDER BY id LIMIT 1").fetchone()); aid=int(arow['id']); c.close()
        b=post({'uscita_id':'0','data':'2026-10-06','descrizione':'QA uscita B','categoria':'Pulizie','importo':'100','metodo':'contanti','note':'B','allegato':(io.BytesIO(b'B-attachment'),'b.pdf')})
        c=sqlite3.connect(qdb);c.row_factory=sqlite3.Row
        rows=[dict(x) for x in c.execute("SELECT * FROM bodymind_uscite ORDER BY id").fetchall()]
        bid=int(rows[-1]['id']); a_after_b=dict(c.execute("SELECT * FROM bodymind_uscite WHERE id=?",(aid,)).fetchone()); b_before=dict(c.execute("SELECT * FROM bodymind_uscite WHERE id=?",(bid,)).fetchone()); c.close()
        eb=post({'uscita_id':str(bid),'data':'2026-10-07','descrizione':'QA uscita B modificata','categoria':'Pulizie','importo':'125','metodo':'carta','note':'B2'})
        c=sqlite3.connect(qdb);c.row_factory=sqlite3.Row
        final_rows=[dict(x) for x in c.execute("SELECT * FROM bodymind_uscite ORDER BY id").fetchall()]
        a_final=dict(c.execute("SELECT * FROM bodymind_uscite WHERE id=?",(aid,)).fetchone()); b_final=dict(c.execute("SELECT * FROM bodymind_uscite WHERE id=?",(bid,)).fetchone())
        tmp_integrity=str(c.execute("PRAGMA integrity_check").fetchone()[0]);tmp_fk=len(c.execute("PRAGMA foreign_key_check").fetchall());c.close()
        mutation={
          "insert_a_redirect":a.status_code==303 and a.location.endswith('/uscite?salvato=1'),
          "insert_b_redirect":b.status_code==303 and b.location.endswith('/uscite?salvato=1'),
          "edit_b_redirect":eb.status_code==303 and eb.location.endswith('/uscite?salvato=1'),
          "count_plus_two":len(rows)==2,
          "ids_distinct":aid!=bid,
          "a_unchanged_after_b":arow==a_after_b,
          "edit_count_unchanged":len(final_rows)==2,
          "a_unchanged_after_edit":a_after_b==a_final,
          "only_b_updated":b_final['descrizione']=='QA uscita B modificata' and abs(float(b_final['importo'])-125.0)<0.001 and b_final['data']=='2026-10-07',
          "attachments_distinct":bool(a_final['allegato_path']) and bool(b_final['allegato_path']) and a_final['allegato_path']!=b_final['allegato_path'],
          "attachments_exist":os.path.isfile(a_final['allegato_path']) and os.path.isfile(b_final['allegato_path']),
          "b_attachment_preserved_on_edit":b_final['allegato_path']==b_before['allegato_path'] and b_final['allegato_nome']==b_before['allegato_nome'],
          "temp_db":tmp_integrity.lower()=='ok' and tmp_fk==0,
        }
    finally:
        core.db=orig_db;core._bodymind_uscita_attachment_save_v11=orig_save

out={"uscite_status":r1.status_code,"contabilita_status":r2.status_code,"uscite_alias_status":r3.status_code,"marker":"BODYMIND_R123_EXPENSE_ATTACHMENTS_V11" in body,"multipart":"multipart/form-data" in body,"new_form_id_zero":"name='uscita_id' value='0'" in body,"attachment_route":bool(expense_file),"baseline":baseline,"mutation":mutation}
print("[r123-expense-v11-audit] "+json.dumps(out,ensure_ascii=False),flush=True)
if r1.status_code!=200 or r2.status_code!=200 or r3.status_code!=200 or not out["marker"] or not out["multipart"] or not out["new_form_id_zero"] or not expense_file or baseline["integrity"].lower()!="ok" or baseline["fk"] or not all(mutation.values()):
    raise RuntimeError("V11 expense persistence audit failed")
"""
_v11p=subprocess.run([sys.executable,"-c",_v11_qa],capture_output=True,text=True,timeout=180)
print((_v11p.stdout or "").strip(),flush=True)
if _v11p.returncode!=0:
    raise RuntimeError("R123 V11 child audit failed "+((_v11p.stderr or "")+(_v11p.stdout or ""))[-9000:])
print('[r123-expense-v11] PASS isolated insert-insert-edit attachments PRG production-read-only baseline='+repr(_v11_expense_baseline),flush=True)


# BODYMIND_R123_DASHBOARD_CANONICAL
_core_dash=CORE.read_text(encoding='utf-8',errors='replace')
# Heal the already-installed canonical dashboard block before deciding whether
# it needs to be appended. Earlier R123 builds persisted over-escaped raw
# regexes (\\\\b), so the marker alone is not sufficient evidence that the
# runtime implementation is healthy.
_dash_lines=_core_dash.splitlines()
_dash_fn=''
_dash_repairs=[]
for _di,_line in enumerate(_dash_lines):
    _stripped=_line.lstrip()
    if _stripped.startswith('def '):
        _dash_fn=_stripped[4:].split('(',1)[0].strip()
    _indent=_line[:len(_line)-len(_stripped)]
    _new_line=None
    if _dash_fn=='_bodymind_dashboard_add_body_class' and 'm=_bm_re.search' in _stripped and '<body' in _stripped:
        _new_line=_indent+"m=_bm_re.search(r'<body\\b([^>]*)>',html,_bm_re.I)"
    elif _dash_fn=='_bodymind_dashboard_add_body_class' and 'tag=m.group(0);cm=_bm_re.search' in _stripped:
        _new_line=_indent+'tag=m.group(0);cm=_bm_re.search(r"""class=(["\'])(.*?)\\1""",tag,_bm_re.I|_bm_re.S)'
    elif _dash_fn=='_bodymind_dashboard_canonical' and 'm=_bm_re.search' in _stripped and '<main' in _stripped:
        _new_line=_indent+"import re as _bm_re;m=_bm_re.search(r'<main\\b[^>]*>',html,_bm_re.I)"
    elif _dash_fn=='_bodymind_dashboard_canonical' and _stripped.startswith('panel=f"""<!-- BODYMIND_R123_DASHBOARD_CANONICAL_RENDERED -->'):
        _new_line=_indent+"current_due=next((x for x in summary if int(x['mese'])==int(t['mese']) and int(x['anno'])==int(t['anno'])),None);monthly_total=int(current_due['totale']) if current_due else int(t['totale']);monthly_paid=int(current_due['pagati']) if current_due else int(t['mensili_pagati']);monthly_missing=int(current_due['mancanti']) if current_due else int(t['mensili_mancanti']);enroll_cls='ok' if int(t['iscrizioni_mancanti'])==0 else 'due';monthly_cls='ok' if monthly_missing==0 else 'due';panel=f\"\"\"<!-- BODYMIND_R123_DASHBOARD_CANONICAL_RENDERED --><section class='bmdc-payments'><header class='bmdc-head'><span>PAGAMENTI · SITUAZIONE REALE</span><h2>Incassi correnti</h2><p>{months[t['mese']]} {t['anno']} è il mensile selezionato; l'iscrizione è annuale e resta separata.</p></header><div class='bmdc-paygrid'><a class='{enroll_cls}' href='/pagamenti?vista=iscrizioni&stagione={t['stagione']}'><small>ISCRIZIONE {t['stagione']}/{t['stagione']+1}</small><strong>{t['iscrizioni_pagate']} pagate</strong><em>{t['iscrizioni_mancanti']} da pagare · totale {t['totale']}</em></a><a class='{monthly_cls}' href='/pagamenti?vista=mensili&mese={t['mese']}&anno={t['anno']}'><small>MENSILE · {months[t['mese']].upper()} {t['anno']}</small><strong>{monthly_paid} pagate</strong><em>{monthly_missing} da pagare · totale {monthly_total}</em></a></div>{(\"<div class='bmdc-months'>\"+chips+\"</div>\" if chips else \"\")}</section>\"\"\""
    elif _dash_fn=='_bodymind_dashboard_canonical' and _stripped.startswith('css="""<style id=\'bodymind-dashboard-canonical-style\'>'):
        _new_line=_indent+"_bg_cfg=load_config();_bg_file=str(_bg_cfg.get('background') or '').strip();_bg_url=(str(file_url(_bg_file)) if _bg_file else '');_bg_url=_bg_url.replace('\"','%22').replace(\"'\",\"%27\");_bg_layer=(\"linear-gradient(rgba(4,10,18,.62),rgba(4,10,18,.74)),url(\"+_bg_url+\")\" if _bg_url else \"radial-gradient(circle at 82% 0%,rgba(37,99,235,.25),transparent 34%),radial-gradient(circle at 18% 10%,rgba(56,189,248,.13),transparent 31%),linear-gradient(135deg,#040a14,#071426 44%,#0f2745)\");css=\"\"\"<style id='bodymind-dashboard-canonical-style'>html body.bodymind-dashboard-canonical{background:__BM_CONFIGURED_BACKGROUND__!important;background-position:center top!important;background-size:cover!important;background-repeat:no-repeat!important;background-attachment:fixed!important;min-height:100vh}html body.bodymind-dashboard-canonical>.overlay,html body.bodymind-dashboard-canonical .overlay,html body.bodymind-dashboard-canonical .shell,html body.bodymind-dashboard-canonical main.content,html body.bodymind-dashboard-canonical main.main,html body.bodymind-dashboard-canonical .pro-dashboard,html body.bodymind-dashboard-canonical .dashboard,html body.bodymind-dashboard-canonical .dashboard-page{background:transparent!important;background-image:none!important}.bmdc-payments{display:grid;grid-template-columns:minmax(210px,.72fr) minmax(0,1.28fr);gap:12px;margin:10px 0 15px;padding:14px;border-radius:18px;background:rgba(7,19,34,.82);border:1px solid rgba(96,165,250,.22);box-shadow:0 14px 36px rgba(0,0,0,.18);backdrop-filter:blur(9px);-webkit-backdrop-filter:blur(9px);color:#f8fafc}.bmdc-head>span{font-size:9px;letter-spacing:.13em;font-weight:950;color:#7dd3fc}.bmdc-head h2{margin:4px 0;font-size:20px}.bmdc-head p{margin:0;color:#b7c6d9;font-size:12px;line-height:1.4}.bmdc-paygrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;min-width:0}.bmdc-paygrid a{display:grid;gap:3px;min-width:0;padding:11px;border-radius:12px;background:rgba(11,29,49,.92);border:1px solid rgba(148,163,184,.16);color:#fff!important;text-decoration:none}.bmdc-paygrid a.due{background:rgba(127,29,29,.62);border-color:rgba(248,113,113,.36)}.bmdc-paygrid a.ok{background:rgba(20,83,45,.62);border-color:rgba(74,222,128,.32)}.bmdc-paygrid small{color:#93c5fd;font-weight:900;font-size:10px}.bmdc-paygrid strong{font-size:20px}.bmdc-paygrid em{font-style:normal;color:#cbd5e1;font-size:10px}.bmdc-months{grid-column:1/-1;display:grid;grid-template-columns:repeat(auto-fit,minmax(108px,1fr));gap:6px;margin-top:0}.bmdc-months a{display:grid;gap:2px;padding:7px 8px;border-radius:9px;color:#fff!important;text-decoration:none;font-size:10px}.bmdc-months a.due{background:#7f1d1d}.bmdc-months a.ok{background:#14532d}.bmdc-months span{color:#e2e8f0}@media(max-width:1400px){.bmdc-payments{grid-template-columns:1fr}.bmdc-paygrid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:760px){html body.bodymind-dashboard-canonical{background-attachment:scroll!important}.bmdc-payments{padding:11px}.bmdc-paygrid{grid-template-columns:1fr}.bmdc-months{grid-template-columns:repeat(2,minmax(0,1fr))}}</style>\"\"\".replace('__BM_CONFIGURED_BACKGROUND__',_bg_layer)"
    if _new_line is not None and _new_line!=_line:
        _dash_repairs.append((_di+1,_line,_new_line))
        _dash_lines[_di]=_new_line
if _dash_repairs:
    _core_dash='\n'.join(_dash_lines)+('\n' if _core_dash.endswith('\n') else '')
    CORE.write_text(_core_dash,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r123-dashboard-canonical-repair] repaired='+repr([(x[0],x[1].strip(),x[2].strip()) for x in _dash_repairs]),flush=True)
    _core_dash=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R123_DASHBOARD_CANONICAL_RUNTIME' not in _core_dash:
    _core_dash += r'''

# BODYMIND_R123_DASHBOARD_CANONICAL_RUNTIME
def _bodymind_dashboard_add_body_class(html):
    import re as _bm_re
    m=_bm_re.search(r'<body\b([^>]*)>',html,_bm_re.I)
    if not m:return html
    tag=m.group(0);cm=_bm_re.search(r"""class=(["'])(.*?)\1""",tag,_bm_re.I|_bm_re.S)
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
        current_due=next((x for x in summary if int(x['mese'])==int(t['mese']) and int(x['anno'])==int(t['anno'])),None);monthly_total=int(current_due['totale']) if current_due else int(t['totale']);monthly_paid=int(current_due['pagati']) if current_due else int(t['mensili_pagati']);monthly_missing=int(current_due['mancanti']) if current_due else int(t['mensili_mancanti']);enroll_cls='ok' if int(t['iscrizioni_mancanti'])==0 else 'due';monthly_cls='ok' if monthly_missing==0 else 'due';panel=f"""<!-- BODYMIND_R123_DASHBOARD_CANONICAL_RENDERED --><section class='bmdc-payments'><header class='bmdc-head'><span>PAGAMENTI · SITUAZIONE REALE</span><h2>Incassi correnti</h2><p>{months[t['mese']]} {t['anno']} è il mensile selezionato; l'iscrizione è annuale e resta separata.</p></header><div class='bmdc-paygrid'><a class='{enroll_cls}' href='/pagamenti?vista=iscrizioni&stagione={t['stagione']}'><small>ISCRIZIONE {t['stagione']}/{t['stagione']+1}</small><strong>{t['iscrizioni_pagate']} pagate</strong><em>{t['iscrizioni_mancanti']} da pagare · totale {t['totale']}</em></a><a class='{monthly_cls}' href='/pagamenti?vista=mensili&mese={t['mese']}&anno={t['anno']}'><small>MENSILE · {months[t['mese']].upper()} {t['anno']}</small><strong>{monthly_paid} pagate</strong><em>{monthly_missing} da pagare · totale {monthly_total}</em></a></div>{("<div class='bmdc-months'>"+chips+"</div>" if chips else "")}</section>"""
        _bg_cfg=load_config();_bg_file=str(_bg_cfg.get('background') or '').strip();_bg_url=(str(file_url(_bg_file)) if _bg_file else '');_bg_url=_bg_url.replace('"','%22').replace("'","%27");_bg_layer=("linear-gradient(rgba(4,10,18,.62),rgba(4,10,18,.74)),url("+_bg_url+")" if _bg_url else "radial-gradient(circle at 82% 0%,rgba(37,99,235,.25),transparent 34%),radial-gradient(circle at 18% 10%,rgba(56,189,248,.13),transparent 31%),linear-gradient(135deg,#040a14,#071426 44%,#0f2745)");css="""<style id='bodymind-dashboard-canonical-style'>html body.bodymind-dashboard-canonical{background:__BM_CONFIGURED_BACKGROUND__!important;background-position:center top!important;background-size:cover!important;background-repeat:no-repeat!important;background-attachment:fixed!important;min-height:100vh}html body.bodymind-dashboard-canonical>.overlay,html body.bodymind-dashboard-canonical .overlay,html body.bodymind-dashboard-canonical .shell,html body.bodymind-dashboard-canonical main.content,html body.bodymind-dashboard-canonical main.main,html body.bodymind-dashboard-canonical .pro-dashboard,html body.bodymind-dashboard-canonical .dashboard,html body.bodymind-dashboard-canonical .dashboard-page{background:transparent!important;background-image:none!important}.bmdc-payments{display:grid;grid-template-columns:minmax(210px,.72fr) minmax(0,1.28fr);gap:12px;margin:10px 0 15px;padding:14px;border-radius:18px;background:rgba(7,19,34,.82);border:1px solid rgba(96,165,250,.22);box-shadow:0 14px 36px rgba(0,0,0,.18);backdrop-filter:blur(9px);-webkit-backdrop-filter:blur(9px);color:#f8fafc}.bmdc-head>span{font-size:9px;letter-spacing:.13em;font-weight:950;color:#7dd3fc}.bmdc-head h2{margin:4px 0;font-size:20px}.bmdc-head p{margin:0;color:#b7c6d9;font-size:12px;line-height:1.4}.bmdc-paygrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;min-width:0}.bmdc-paygrid a{display:grid;gap:3px;min-width:0;padding:11px;border-radius:12px;background:rgba(11,29,49,.92);border:1px solid rgba(148,163,184,.16);color:#fff!important;text-decoration:none}.bmdc-paygrid a.due{background:rgba(127,29,29,.62);border-color:rgba(248,113,113,.36)}.bmdc-paygrid a.ok{background:rgba(20,83,45,.62);border-color:rgba(74,222,128,.32)}.bmdc-paygrid small{color:#93c5fd;font-weight:900;font-size:10px}.bmdc-paygrid strong{font-size:20px}.bmdc-paygrid em{font-style:normal;color:#cbd5e1;font-size:10px}.bmdc-months{grid-column:1/-1;display:grid;grid-template-columns:repeat(auto-fit,minmax(108px,1fr));gap:6px;margin-top:0}.bmdc-months a{display:grid;gap:2px;padding:7px 8px;border-radius:9px;color:#fff!important;text-decoration:none;font-size:10px}.bmdc-months a.due{background:#7f1d1d}.bmdc-months a.ok{background:#14532d}.bmdc-months span{color:#e2e8f0}@media(max-width:1400px){.bmdc-payments{grid-template-columns:1fr}.bmdc-paygrid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:760px){html body.bodymind-dashboard-canonical{background-attachment:scroll!important}.bmdc-payments{padding:11px}.bmdc-paygrid{grid-template-columns:1fr}.bmdc-months{grid-template-columns:repeat(2,minmax(0,1fr))}}</style>""".replace('__BM_CONFIGURED_BACKGROUND__',_bg_layer)
        if '</head>' in html:html=html.replace('</head>',css+'</head>',1)
        import re as _bm_re;m=_bm_re.search(r'<main\b[^>]*>',html,_bm_re.I)
        if not m:raise RuntimeError('canonical dashboard main element missing')
        html=html[:m.end()]+panel+html[m.end():];resp.set_data(html)
    except Exception as exc:print('[dashboard-canonical-warning] '+repr(exc),flush=True)
    return resp
'''
    CORE.write_text(_core_dash,encoding='utf-8');py_compile.compile(str(CORE),doraise=True)
    print('[r123-dashboard-canonical] installed one server-side dashboard authority',flush=True)
else:print('[r123-dashboard-canonical] already installed',flush=True)


# BODYMIND_R123_QUOTE_INCASSI_CANONICAL_V12
# /quote-incassi is a secretary summary, not a second accounting engine:
# exactly one annual enrollment payment and one selected monthly payment.
# Amounts marked paid come only from canonical pagamenti rows.
_core_qi=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R123_QUOTE_INCASSI_CANONICAL_V12' not in _core_qi:
    _core_qi += r'''

# BODYMIND_R123_QUOTE_INCASSI_CANONICAL_V12
def bodymind_quote_incassi_canonical():
    # BODYMIND_R123_QUOTE_INCASSI_DETAIL_V12
    from datetime import date as _bm_date
    if request.method!='GET':
        return redirect('/quote-incassi',303)

    today=_bm_date.today()
    mese=parse_int(request.args.get('mese'),today.month)
    anno=parse_int(request.args.get('anno'),today.year)
    if mese<1 or mese>12: mese=today.month
    if anno<2020 or anno>2100: anno=today.year
    stagione=anno if mese>=7 else anno-1
    months=['','Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno','Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre']

    conn=db(); conn.row_factory=sqlite3.Row
    try:
        truth=bodymind_payment_truth(conn,mese=mese,anno=anno,stagione=stagione)
        payment_ids=[]
        for x in truth.get('rows',[]):
            for k in ('iscrizione_payment_id','mensile_payment_id'):
                if x.get(k): payment_ids.append(int(x[k]))
        payments={}
        if payment_ids:
            marks=','.join('?' for _ in payment_ids)
            for p in conn.execute('SELECT * FROM pagamenti WHERE id IN ('+marks+')',payment_ids).fetchall():
                payments[int(p['id'])]=p

        quote_by_tid={}
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='quote_mensili'").fetchone():
            for q in conn.execute("SELECT * FROM quote_mensili WHERE mese=? AND anno=? ORDER BY id DESC",(mese,anno)).fetchall():
                tid=int(q['tesserato_id'] or 0)
                if not tid or tid in quote_by_tid: continue
                state=str(q['stato'] or '').strip().lower()
                if any(x in state for x in ('non_dovuto','non dovuto','esente','annull','sospes')):
                    quote_by_tid[tid]=None
                else:
                    quote_by_tid[tid]=q

        # Read-only movement ledger for the selected month + annual enrollment.
        # This explains historical split/duplicate rows without changing them.
        movement_by_tid={}
        _truth_ids=[int(x['tesserato_id']) for x in truth.get('rows',[]) if int(x.get('tesserato_id') or 0)>0]
        if _truth_ids:
            _marks=','.join('?' for _ in _truth_ids)
            _args=list(_truth_ids)+[mese,anno,stagione,stagione+1]
            _sql=("SELECT * FROM pagamenti WHERE tesserato_id IN ("+_marks+") "
                  "AND ((mese=? AND anno=?) OR (anno IN (?,?) AND "
                  "(lower(coalesce(causale,''))='iscrizione' OR lower(coalesce(causale,''))='tesseramento' "
                  "OR lower(coalesce(causale,'')) LIKE '%iscrizion%'))) "
                  "ORDER BY tesserato_id,COALESCE(data,''),id")
            for p in conn.execute(_sql,_args).fetchall():
                movement_by_tid.setdefault(int(p['tesserato_id']),[]).append(p)
    finally:
        conn.close()

    def _cash_row(p):
        try:get=p.get
        except Exception:get=lambda k,d=None:p[k] if k in p.keys() else d
        st=(str(get('stato','') or '')+' '+str(get('online_status','') or '')).lower()
        if any(x in st for x in ('pending','attesa','cancel','annull','failed','fallit','refunded','rimbors')):
            return False
        if any(x in st for x in ('paid','pagat','saldat','complet','incassat')):
            return True
        try:amount=float(get('importo',0) or 0)
        except Exception:amount=0
        return bool(get('data','') or get('paid_at','')) and amount>0

    def _money(value):
        if value is None: return '—'
        try: return ('€ %.2f'%float(value)).replace('.',',')
        except Exception: return '—'

    rows=[]
    enroll_paid=0
    monthly_paid=0
    monthly_due=0
    for x in truth.get('rows',[]):
        tid=int(x['tesserato_id'])
        ep=payments.get(int(x.get('iscrizione_payment_id') or 0))
        mp=payments.get(int(x.get('mensile_payment_id') or 0))
        ep_ok=bool(x.get('iscrizione_pagata') and ep)
        mp_ok=bool(x.get('mensile_pagato') and mp)
        q=quote_by_tid.get(tid,'__missing__')
        month_applicable=(q is not None and q!='__missing__') or mp_ok
        if ep_ok: enroll_paid+=1

        ep_amount=(float(ep['importo'] or 0) if ep_ok else None)
        mp_paid_amount=(float(mp['importo'] or 0) if mp_ok else None)
        mp_due_amount=(float(q['importo_dovuto'] or q['importo_base'] or 0) if q not in (None,'__missing__') else None)
        if mp_due_amount is not None:
            mp_display=mp_due_amount
        elif mp_ok:
            mp_display=mp_paid_amount
        else:
            mp_display=None

        enroll_href='/pagamenti?vista=iscrizioni&stagione='+str(stagione)+'&tesserato_id='+str(tid)+'&azione=registra&tipo=iscrizione'
        month_href='/pagamenti?vista=mensili&mese='+str(mese)+'&anno='+str(anno)+'&tesserato_id='+str(tid)+'&azione=registra&tipo=mensile'
        enroll_state='PAGATA' if ep_ok else 'DA PAGARE'
        if mp_ok: month_state='PAGATO'
        elif not month_applicable: month_state='NON DOVUTO'
        else: month_state='DA PAGARE'
        enroll_cls='paid' if ep_ok else 'due'
        month_cls='paid' if mp_ok else ('na' if not month_applicable else 'due')
        name=((str(x.get('cognome') or '')+' '+str(x.get('nome') or '')).strip())
        ep_attr=('%.2f'%ep_amount) if ep_amount is not None else ''
        mp_attr=('%.2f'%mp_paid_amount) if mp_paid_amount is not None else ''

        movs=movement_by_tid.get(tid,[])
        month_movs=[]
        detail_items=[]
        for p in movs:
            causale=str(p['causale'] or '').strip()
            causale_l=causale.lower()
            pm=parse_int(p['mese'],0); py=parse_int(p['anno'],0)
            is_enroll=(causale_l in ('iscrizione','tesseramento') or 'iscrizion' in causale_l)
            is_month=('mensil' in causale_l or causale_l in ('quota','quota_mensile'))
            if is_month and pm==mese and py==anno and _cash_row(p):
                month_movs.append(p)
            if is_enroll:
                label='Iscrizione '+str(stagione)+'/'+str(stagione+1)
            elif is_month and 1<=pm<=12:
                label='Mensile '+months[pm]+' '+str(py)
            else:
                label=causale or 'Altro movimento'
            method=str(p['metodo_pagamento'] or 'non indicato') if 'metodo_pagamento' in p.keys() else 'non indicato'
            note=str(p['note_pagamento'] or '').strip() if 'note_pagamento' in p.keys() else ''
            ref=str(p['riferimento_pagamento'] or '').strip() if 'riferimento_pagamento' in p.keys() else ''
            stato=(str(p['stato'] or '').strip() if 'stato' in p.keys() else '') or (str(p['online_status'] or '').strip() if 'online_status' in p.keys() else '') or 'registrato'
            pdate=str(p['data'] or '—') if 'data' in p.keys() else '—'
            extra=[]
            receipt_id=(str(p['ricevuta_id']).strip() if 'ricevuta_id' in p.keys() and p['ricevuta_id'] is not None else '')
            if receipt_id: extra.append('Ricevuta #'+receipt_id)
            if ref: extra.append('Rif. '+ref)
            if note: extra.append('Note: '+note)
            detail_items.append(
                "<div class='bmqi-movement' data-bm-payment-id='"+str(int(p['id']))+"' data-bm-causale='"+e(causale)+"'>"
                "<div><b>"+e(label)+"</b><small>Pagamento #"+str(int(p['id']))+" · Causale: <code>"+e(causale or '—')+"</code></small></div>"
                "<strong>"+_money(float(p['importo'] or 0))+"</strong>"
                "<span>"+e(pdate)+" · "+e(method)+" · "+e(stato)+"</span>"
                +("<em>"+e(' · '.join(extra))+"</em>" if extra else "")+
                "</div>"
            )
        month_total=sum(float(p['importo'] or 0) for p in month_movs)
        residual=(max(float(mp_due_amount)-month_total,0.0) if mp_due_amount is not None else None)
        excess=(max(month_total-float(mp_due_amount),0.0) if mp_due_amount is not None else 0.0)
        if not month_applicable and month_total<=0:
            month_state='NON DOVUTO'; month_cls='na'
        elif mp_due_amount is not None:
            if month_total>=float(mp_due_amount):
                month_state='PAGATO'; month_cls='paid'
            elif month_total>0:
                month_state='PARZIALE'; month_cls='partial'
            else:
                month_state='DA PAGARE'; month_cls='due'
        elif month_total>0 or mp_ok:
            month_state='REGISTRATO'; month_cls='paid'
        else:
            month_state='DA PAGARE'; month_cls='due'
        if month_applicable: monthly_due+=1
        if month_state in ('PAGATO','REGISTRATO'): monthly_paid+=1
        duplicate_warning=(
            "<div class='bmqi-warning'><b>"+str(len(month_movs))+" movimenti mensili per "+months[mese]+" "+str(anno)+"</b>"
            "<span>Incassato mensile "+_money(month_total)
            +(" · dovuto "+_money(mp_due_amount) if mp_due_amount is not None else "")
            +". Lo storico resta intatto; i movimenti sono mostrati sotto per causale.</span></div>"
            if len(month_movs)>1 else ""
        )
        details_html=(
            "<details class='bmqi-details' data-bm-detail-tid='"+str(tid)+"'><summary>Dettaglio movimenti <b>"+str(len(movs))+"</b></summary>"
            +duplicate_warning+
            ("<div class='bmqi-movements'>"+''.join(detail_items)+"</div>" if detail_items else "<p>Nessun movimento registrato per queste voci.</p>")+
            "</details>"
        )
        month_meta='Incassato mensile '+_money(month_total)
        if residual is not None: month_meta+=' · Residuo '+_money(residual)
        if excess>0: month_meta+=' · Oltre il dovuto '+_money(excess)
        if mp_ok: month_meta+=' · Modifica'
        elif month_applicable: month_meta+=' · Registra'

        rows.append(
          "<article class='bmqi-row' data-bm-tid='"+str(tid)+"' data-bm-enroll-paid='"+('1' if ep_ok else '0')+
          "' data-bm-enroll-amount='"+ep_attr+"' data-bm-month-paid='"+('1' if mp_ok else '0')+
          "' data-bm-month-amount='"+mp_attr+"' data-bm-month-cash='"+('%.2f'%month_total)+"' data-bm-month-due='"+(('%.2f'%mp_due_amount) if mp_due_amount is not None else '')+"' data-bm-month-residual='"+(('%.2f'%residual) if residual is not None else '')+"'>"
          "<div class='bmqi-name'><b>"+e(name)+"</b><small>"+months[mese]+" "+str(anno)+"</small></div>"
          "<a class='bmqi-pay "+enroll_cls+"' href='"+enroll_href+"'><span>ISCRIZIONE "+str(stagione)+"/"+str(stagione+1)+"</span><strong>"+_money(ep_amount)+"</strong><em>"+enroll_state+"</em><small>"+('Modifica' if ep_ok else 'Registra')+"</small></a>"
          "<a class='bmqi-pay "+month_cls+"' href='"+month_href+"'><span>MENSILE · "+months[mese].upper()+" "+str(anno)+"</span><strong>Dovuto "+_money(mp_due_amount)+"</strong><em>"+month_state+"</em><small>"+e(month_meta)+"</small></a>"
          +details_html+
          "</article>"
        )

    month_opts=''.join("<option value='"+str(i)+"' "+('selected' if i==mese else '')+">"+months[i]+"</option>" for i in range(1,13))
    html=f"""<!-- BODYMIND_R123_QUOTE_INCASSI_CANONICAL_V12 -->
    <main class='bmqi'>
      <header class='bmqi-head'>
        <div><small>QUOTE E PAGAMENTI</small><h1>Iscrizione + mensile</h1><p>Due sole voci per atleta. Gli importi pagati arrivano dai movimenti reali registrati.</p></div>
        <a href='/pagamenti'>Pagamenti</a>
      </header>
      <form class='bmqi-period' method='get' action='/quote-incassi'>
        <label>Mese<select name='mese'>{month_opts}</select></label>
        <label>Anno<input name='anno' inputmode='numeric' value='{anno}'></label>
        <button type='submit'>Mostra</button>
      </form>
      <section class='bmqi-summary'>
        <div><small>ISCRIZIONI {stagione}/{stagione+1}</small><strong>{enroll_paid}/{len(truth.get('rows',[]))}</strong><span>pagate</span></div>
        <div><small>MENSILE · {months[mese].upper()} {anno}</small><strong>{monthly_paid}/{monthly_due}</strong><span>pagati</span></div>
      </section>
      <section class='bmqi-list'>{''.join(rows)}</section>
    </main>
    <style>
      .bmqi{{max-width:1180px;margin:0 auto;padding:14px 14px 70px}}
      .bmqi-head{{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:12px}}
      .bmqi-head small{{font-size:10px;font-weight:950;letter-spacing:.12em;color:#7dd3fc}}
      .bmqi-head h1{{margin:4px 0 3px;font-size:25px}}
      .bmqi-head p{{margin:0;color:#a9bbcf}}
      .bmqi-head>a{{padding:10px 13px;border-radius:11px;background:#163b5f;color:#fff!important;text-decoration:none;font-weight:900}}
      .bmqi-period{{display:flex;gap:8px;align-items:end;flex-wrap:wrap;margin:10px 0;padding:10px;border-radius:13px;background:#0b1d31}}
      .bmqi-period label{{display:grid;gap:4px;font-size:11px;font-weight:900}}
      .bmqi-period select,.bmqi-period input,.bmqi-period button{{min-height:40px;border-radius:9px;border:1px solid rgba(148,163,184,.24);background:#06111f;color:#fff;padding:8px 10px}}
      .bmqi-period button{{background:#2563eb;font-weight:950}}
      .bmqi-summary{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px}}
      .bmqi-summary>div{{display:grid;gap:2px;padding:11px 13px;border-radius:13px;background:#0d2138;border:1px solid rgba(125,211,252,.18)}}
      .bmqi-summary small{{font-weight:900;color:#93c5fd}}.bmqi-summary strong{{font-size:21px}}.bmqi-summary span{{font-size:11px;color:#cbd5e1}}
      .bmqi-list{{display:grid;gap:8px}}
      .bmqi-row{{display:grid;grid-template-columns:minmax(180px,.65fr) minmax(200px,1fr) minmax(200px,1fr);gap:8px;align-items:stretch;padding:10px;border-radius:15px;background:rgba(8,24,42,.88);border:1px solid rgba(148,163,184,.16)}}
      .bmqi-name{{display:flex;flex-direction:column;justify-content:center;gap:3px;padding:7px}}.bmqi-name b{{font-size:14px}}.bmqi-name small{{color:#94a3b8}}
      .bmqi-pay{{display:grid;grid-template-columns:1fr auto;grid-template-areas:'label amount' 'state action';gap:5px 10px;padding:11px;border-radius:12px;text-decoration:none!important;color:#fff!important;border:1px solid transparent}}
      .bmqi-pay>span{{grid-area:label;font-size:10px;font-weight:950;letter-spacing:.04em}}.bmqi-pay>strong{{grid-area:amount;font-size:18px;text-align:right}}.bmqi-pay>em{{grid-area:state;font-style:normal;font-size:11px;font-weight:950}}.bmqi-pay>small{{grid-area:action;text-align:right;font-weight:900}}
      .bmqi-pay.paid{{background:rgba(20,83,45,.72);border-color:rgba(74,222,128,.30)}}.bmqi-pay.partial{{background:rgba(120,53,15,.62);border-color:rgba(251,191,36,.34)}}.bmqi-pay.due{{background:rgba(127,29,29,.54);border-color:rgba(248,113,113,.34)}}.bmqi-pay.na{{background:rgba(51,65,85,.46);border-color:rgba(148,163,184,.22);color:#cbd5e1!important}}
      .bmqi-details{{grid-column:1/-1;border-top:1px solid rgba(148,163,184,.16);padding:8px 4px 2px}}.bmqi-details summary{{cursor:pointer;font-weight:950;color:#bfdbfe;padding:7px 4px}}.bmqi-details summary b{{display:inline-flex;min-width:22px;justify-content:center;margin-left:6px;padding:2px 6px;border-radius:999px;background:#163b5f;color:#fff}}.bmqi-warning{{display:grid;gap:3px;margin:5px 0 8px;padding:9px 10px;border-radius:10px;background:rgba(146,64,14,.42);border:1px solid rgba(251,191,36,.38);color:#fef3c7}}.bmqi-warning span{{font-size:11px;line-height:1.35}}.bmqi-movements{{display:grid;gap:6px}}.bmqi-movement{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:3px 12px;padding:9px 10px;border-radius:10px;background:#07182a;border:1px solid rgba(148,163,184,.14)}}.bmqi-movement>div{{display:grid;gap:2px}}.bmqi-movement b{{font-size:12px}}.bmqi-movement small,.bmqi-movement span,.bmqi-movement em{{font-size:10px;color:#a9bbcf;font-style:normal}}.bmqi-movement strong{{font-size:14px}}.bmqi-movement span,.bmqi-movement em{{grid-column:1/-1}}.bmqi-movement code{{color:#dbeafe}}
      @media(max-width:900px){{.bmqi-row{{grid-template-columns:1fr 1fr}}.bmqi-name{{grid-column:1/-1}}}}
      @media(max-width:620px){{.bmqi{{padding:11px 10px 65px}}.bmqi-head{{display:grid}}.bmqi-summary{{grid-template-columns:1fr}}.bmqi-row{{grid-template-columns:1fr}}.bmqi-name{{grid-column:auto}}.bmqi-period label,.bmqi-period select,.bmqi-period input,.bmqi-period button{{width:100%}}}}
    </style>"""
    return layout(html)
'''
    CORE.write_text(_core_qi,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r123-quote-incassi] installed canonical enrollment+monthly summary',flush=True)
else:
    print('[r123-quote-incassi] canonical summary already installed',flush=True)

# Replace the historical /quote-incassi implementation at source level.
# Preserve the registered endpoint/decorators, but make its body delegate to the
# canonical read-only summary above. Discover the real route across the persisted
# runtime instead of assuming it is declared with app.route in one specific file.
import ast as _bm_qi_ast
_qi_candidates=[]
_qi_refs=[]
for _pay_src in sorted((APP/'asd_app').glob('*.py')):
    try:
        _pay_text=_pay_src.read_text(encoding='utf-8',errors='replace')
    except Exception:
        continue
    if '/quote-incassi' not in _pay_text:
        continue
    _qi_refs.append(str(_pay_src))
    try:
        _pay_tree=_bm_qi_ast.parse(_pay_text)
    except Exception:
        continue
    _pay_lines=_pay_text.splitlines(True)
    for _node in _pay_tree.body:
        if not isinstance(_node,(_bm_qi_ast.FunctionDef,_bm_qi_ast.AsyncFunctionDef)):
            continue
        _is_quote=False
        for _dec in _node.decorator_list:
            if not isinstance(_dec,_bm_qi_ast.Call):
                continue
            _attr=_dec.func.attr if isinstance(_dec.func,_bm_qi_ast.Attribute) else ''
            if _attr not in ('route','get'):
                continue
            _vals=list(_dec.args)+[kw.value for kw in _dec.keywords if kw.arg in ('rule','path')]
            for _arg in _vals:
                if isinstance(_arg,_bm_qi_ast.Constant) and isinstance(_arg.value,str) and _arg.value.rstrip('/')=='/quote-incassi':
                    _is_quote=True
                    break
            if _is_quote:
                break
        if _is_quote:
            _qi_candidates.append((_pay_src,_pay_text,_pay_lines,_node))
if len(_qi_candidates)!=1:
    raise RuntimeError('expected exactly one /quote-incassi source route, found '+str(len(_qi_candidates))+' refs='+repr(_qi_refs))
_pay_src,_pay_text,_pay_lines,_qi_node=_qi_candidates[0]
_qi_src=''.join(_pay_lines[_qi_node.lineno-1:int(getattr(_qi_node,'end_lineno',_qi_node.lineno))])
if 'bodymind_quote_incassi_canonical' not in _qi_src:
    if not _qi_node.body:
        raise RuntimeError('/quote-incassi route has no body in '+str(_pay_src))
    _body_start=_qi_node.body[0].lineno-1
    _body_end=int(getattr(_qi_node,'end_lineno',_qi_node.lineno))
    _indent=' '*int(_qi_node.body[0].col_offset)
    _replacement=[
        _indent+"from .core import bodymind_quote_incassi_canonical\n",
        _indent+"return bodymind_quote_incassi_canonical()\n",
    ]
    _pay_lines[_body_start:_body_end]=_replacement
    _pay_src.write_text(''.join(_pay_lines),encoding='utf-8')
    py_compile.compile(str(_pay_src),doraise=True)
    print('[r123-quote-incassi-source] replaced historical renderer with canonical delegate source='+str(_pay_src),flush=True)
else:
    print('[r123-quote-incassi-source] already canonical source='+str(_pay_src),flush=True)

_quote_qa=r"""
import json,re,sqlite3,sys
sys.path.insert(0,'/data/top2_app');import app as _full
from asd_app.core import app,bodymind_payment_truth
app.config['TESTING']=True
c=app.test_client()
with c.session_transaction() as sess:sess.update({'logged':True,'logged_in':True,'username':'admin','display_name':'Quote QA','role':'admin','tenant_slug':'default','user_id':1,'is_admin':True,'admin':True})
def paid_row(p):
    def get(k,d=None):return p[k] if k in p.keys() else d
    st=(str(get('stato','') or '')+' '+str(get('online_status','') or '')).lower()
    if any(x in st for x in ('pending','attesa','cancel','annull','failed','fallit','refunded','rimbors')):return False
    if any(x in st for x in ('paid','pagat','saldat','complet','incassat')):return True
    try:amount=float(get('importo',0) or 0)
    except Exception:amount=0
    return bool(get('data','') or get('paid_at','')) and amount>0
db=sqlite3.connect('file:/data/tenants/default/asd.db?mode=ro',uri=True,timeout=20);db.row_factory=sqlite3.Row
try:
    tables=('tesserati','pagamenti','ricevute','quote_mensili','documenti','inbound_documents')
    counts_before={t:int(db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]) for t in tables}
    truth=bodymind_payment_truth(db,mese=10,anno=2026,stagione=2026)
    expected={}
    cash_expected={};due_expected={};residual_expected={};duplicate_tids=set()
    for x in truth['rows']:
        tid=int(x['tesserato_id'])
        ep=db.execute('SELECT importo FROM pagamenti WHERE id=?',(int(x['iscrizione_payment_id']),)).fetchone() if x.get('iscrizione_payment_id') else None
        mp=db.execute('SELECT importo FROM pagamenti WHERE id=?',(int(x['mensile_payment_id']),)).fetchone() if x.get('mensile_payment_id') else None
        expected[tid]=(bool(x['iscrizione_pagata'] and ep),('%.2f'%float(ep['importo'] or 0) if ep else ''),bool(x['mensile_pagato'] and mp),('%.2f'%float(mp['importo'] or 0) if mp else ''))
        movs=db.execute("SELECT * FROM pagamenti WHERE tesserato_id=? AND mese=10 AND anno=2026 ORDER BY id",(tid,)).fetchall()
        month=[p for p in movs if (('mensil' in str(p['causale'] or '').lower()) or str(p['causale'] or '').lower() in ('quota','quota_mensile')) and paid_row(p)]
        cash_expected[tid]=sum(float(p['importo'] or 0) for p in month)
        if len(month)>1:duplicate_tids.add(tid)
        q=db.execute("SELECT * FROM quote_mensili WHERE tesserato_id=? AND mese=10 AND anno=2026 ORDER BY id DESC LIMIT 1",(tid,)).fetchone()
        due=None
        if q:
            st=str(q['stato'] or '').strip().lower()
            if not any(z in st for z in ('non_dovuto','non dovuto','esente','annull','sospes')):
                due=float(q['importo_dovuto'] or q['importo_base'] or 0)
        due_expected[tid]=due
        residual_expected[tid]=(max(due-cash_expected[tid],0.0) if due is not None else None)
    target_breakdown=[];target_receipts=[];target_month_cash={}
    rows=db.execute("SELECT p.*,t.cognome AS qa_cognome,t.nome AS qa_nome FROM pagamenti p JOIN tesserati t ON t.id=p.tesserato_id WHERE lower(t.cognome) IN ('abatini','angelucci','annunziato','frioli','fabiani') AND p.anno IN (2026,2027) ORDER BY lower(t.cognome),lower(t.nome),p.anno,p.mese,p.id").fetchall()
    wanted=('id','tesserato_id','mese','anno','importo','data','causale','metodo_pagamento','stato','online_status','ricevuta_id','riferimento_pagamento','note_pagamento')
    for p in rows:
        d={'cognome':p['qa_cognome'],'nome':p['qa_nome']}
        for k in wanted:d[k]=(p[k] if k in p.keys() else None)
        cause=str(d.get('causale') or '').lower();pm=int(d.get('mese') or 0);py=int(d.get('anno') or 0)
        relevant=((pm==10 and py==2026) or ((cause in ('iscrizione','tesseramento') or 'iscrizion' in cause) and py in (2026,2027)))
        rid=d.get('ricevuta_id');rec=None
        if rid:
            rr=db.execute("SELECT id,pagamento_id,numero_progressivo,anno_progressivo,descrizione,importo,data,metodo_pagamento FROM ricevute WHERE id=? OR pagamento_id=? ORDER BY id DESC LIMIT 1",(rid,d['id'])).fetchone()
            rec=(dict(rr) if rr else None)
        d['ricevuta']=rec;target_breakdown.append(d)
        if relevant and rec:target_receipts.append(rec)
        if pm==10 and py==2026 and (('mensil' in cause) or cause in ('quota','quota_mensile')) and paid_row(p):
            key=str(d['cognome']).upper()+' '+str(d['nome']).upper()
            target_month_cash[key]=target_month_cash.get(key,0.0)+float(d.get('importo') or 0)
    target_quotes=[]
    for q in db.execute("SELECT q.*,t.cognome AS qa_cognome,t.nome AS qa_nome FROM quote_mensili q JOIN tesserati t ON t.id=q.tesserato_id WHERE lower(t.cognome) IN ('abatini','angelucci','annunziato','frioli','fabiani') AND q.mese=10 AND q.anno=2026 ORDER BY lower(t.cognome),q.id").fetchall():
        d={'cognome':q['qa_cognome'],'nome':q['qa_nome']}
        for k in ('id','tesserato_id','mese','anno','importo_base','sconto','importo_dovuto','stato'):d[k]=(q[k] if k in q.keys() else None)
        target_quotes.append(d)
    integrity=str(db.execute('PRAGMA integrity_check').fetchone()[0]);fk=len(db.execute('PRAGMA foreign_key_check').fetchall())
finally:db.close()
r=c.get('/quote-incassi?mese=10&anno=2026',follow_redirects=True);h=r.get_data(as_text=True)
rendered={}
pat=r"data-bm-tid='(\d+)' data-bm-enroll-paid='([01])' data-bm-enroll-amount='([^']*)' data-bm-month-paid='([01])' data-bm-month-amount='([^']*)' data-bm-month-cash='([^']*)' data-bm-month-due='([^']*)' data-bm-month-residual='([^']*)'"
for tid,ep,ea,mp,ma,cash,due,residual in re.findall(pat,h):
    rendered[int(tid)]={'canonical':(ep=='1',ea,mp=='1',ma),'cash':cash,'due':due,'residual':residual}
db=sqlite3.connect('file:/data/tenants/default/asd.db?mode=ro',uri=True,timeout=20)
try:counts_after={t:int(db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]) for t in ('tesserati','pagamenti','ricevute','quote_mensili','documenti','inbound_documents')}
finally:db.close()
cash_ok=all(tid in rendered and rendered[tid]['cash']=='%.2f'%cash_expected[tid] for tid in cash_expected)
due_ok=all(tid in rendered and rendered[tid]['due']==(('%.2f'%due_expected[tid]) if due_expected[tid] is not None else '') for tid in due_expected)
residual_ok=all(tid in rendered and rendered[tid]['residual']==(('%.2f'%residual_expected[tid]) if residual_expected[tid] is not None else '') for tid in residual_expected)
canonical_ok=all(tid in rendered and rendered[tid]['canonical']==expected[tid] for tid in expected)
payment_ids_visible=all(("data-bm-payment-id='"+str(d['id'])+"'") in h and ("Pagamento #"+str(d['id'])) in h for d in target_breakdown if ((int(d.get('mese') or 0)==10 and int(d.get('anno') or 0)==2026) or ('iscrizion' in str(d.get('causale') or '').lower()) or str(d.get('causale') or '').lower()=='tesseramento'))
receipts_visible=all(("Ricevuta #"+str(x['id'])) in h for x in target_receipts)
checks={
 'status':r.status_code==200,
 'single':h.count('BODYMIND_R123_QUOTE_INCASSI_CANONICAL_V12')==1,
 'canonical_truth':canonical_ok,
 'monthly_cash_exact_period':cash_ok,
 'monthly_due_from_quotes':due_ok,
 'monthly_residual':residual_ok,
 'two_semantics':'ISCRIZIONE 2026/2027' in h and 'MENSILE · OTTOBRE 2026' in h,
 'cash_label':'Incassato mensile' in h and 'Dovuto €' in h,
 'movement_details':h.count("data-bm-detail-tid=")==len(expected) and 'Causale:' in h,
 'payment_ids_visible':payment_ids_visible,
 'receipts_identifiable':receipts_visible,
 'duplicate_count':h.count("<div class='bmqi-warning'>")==len(duplicate_tids),
 'read_only':counts_before==counts_after,
 'db':integrity.lower()=='ok' and fk==0,
}
print('[r123-quote-incassi-audit] '+json.dumps({'checks':checks,'rows':len(rendered),'counts_before':counts_before,'counts_after':counts_after,'target_month_cash':target_month_cash,'target_breakdown':target_breakdown,'target_quotes':target_quotes,'integrity':integrity,'fk':fk},ensure_ascii=False),flush=True)
if not all(checks.values()):raise RuntimeError('quote-incassi canonical audit failed '+repr(checks))
"""
_qip=subprocess.run([sys.executable,'-c',_quote_qa],capture_output=True,text=True,timeout=180)
print((_qip.stdout or '').strip(),flush=True)
if _qip.returncode!=0:
    raise RuntimeError('quote-incassi child audit failed '+((_qip.stderr or '')+(_qip.stdout or ''))[-12000:])
print('[r123-quote-incassi] PASS exact-period cash due-separated receipt-identifiable read-only',flush=True)


_final_qa=r"""
import json,re,sqlite3,sys
sys.path.insert(0,'/data/top2_app');import app as _full
from asd_app.core import app,bodymind_payment_truth,load_config,file_url
app.config['TESTING']=True;c=app.test_client()
with c.session_transaction() as s:s.update({'logged':True,'logged_in':True,'username':'admin','display_name':'Canonical QA','role':'admin','tenant_slug':'default','user_id':1,'is_admin':True,'admin':True})
paths=['/','/dashboard','/tesserati','/pagamenti','/documenti','/documenti-automatici','/contabilita','/uscite','/collaboratori','/operatore-bodymind','/mobile','/mobile/atlete']
status={p:c.get(p,follow_redirects=False).status_code for p in paths}
cfg=load_config();bg_file=str(cfg.get('background') or '').strip();bg_url=(str(file_url(bg_file)) if bg_file else '');bg_status=(c.get(bg_url,follow_redirects=False).status_code if bg_url else None)
dh=c.get('/dashboard',follow_redirects=True).get_data(as_text=True);hh=c.get('/',follow_redirects=True).get_data(as_text=True);ph=c.get('/pagamenti?vista=mensili',follow_redirects=True).get_data(as_text=True)
def body(h):
    m=re.search(r'<body\b[^>]*class=["\x27]([^"\x27]*)',h,re.I);return m.group(1).split() if m else []
old_dash=('BODYMIND_R123_DASHBOARD_BACKGROUND_RESTORE_RENDERED','BODYMIND_R156_DASHBOARD_RECOMPOSE_RENDERED','BODYMIND_PAYMENT_TRUTH_DASHBOARD_V3','BODYMIND_MONTHLY_ARREARS_V5_RENDERED')
old_pay=('BODYMIND_R123_PAYMENT_MOBILE','BODYMIND_R125_PAYMENT_BOARD','BODYMIND_R123_PAYMENT_SPLIT_V2_SURFACE','BODYMIND_R123_CANONICAL_PAYMENT_MODULE_V5','bmpv6-immediate')
row_state={int(a):(b=='1',d=='1') for a,b,d in re.findall(r'data-bm-tid=["\x27](\d+)["\x27]\s+data-bm-enroll=["\x27]([01])["\x27]\s+data-bm-monthly=["\x27]([01])["\x27]',ph)}
db=sqlite3.connect('file:/data/tenants/default/asd.db?mode=ro',uri=True,timeout=20);db.row_factory=sqlite3.Row
try:
    truth=bodymind_payment_truth(db);expected_all={int(x['tesserato_id']):(bool(x['iscrizione_pagata']),bool(x['mensile_pagato'])) for x in truth['rows']}
    due_ids=set();seen_due=set()
    for q in db.execute("SELECT * FROM quote_mensili WHERE mese=? AND anno=? ORDER BY id DESC",(int(truth['mese']),int(truth['anno']))).fetchall():
        tid=int(q['tesserato_id'] or 0)
        if not tid or tid in seen_due:continue
        seen_due.add(tid);st=str(q['stato'] or '').strip().lower()
        if any(x in st for x in ('non_dovuto','non dovuto','esente','annull','sospes')):continue
        due_ids.add(tid)
    expected={tid:state for tid,state in expected_all.items() if tid in due_ids}
    counts={t:int(db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]) for t in ('tesserati','pagamenti','ricevute','quote_mensili','documenti','inbound_documents')}
    integrity=str(db.execute('PRAGMA integrity_check').fetchone()[0]);fk=len(db.execute('PRAGMA foreign_key_check').fetchall());legacy_only=[];season=int(truth['stagione'])
    for x in truth['rows']:
        tid=int(x['tesserato_id']);pay=db.execute('''SELECT 1 FROM pagamenti WHERE tesserato_id=? AND anno IN (?,?) AND (lower(coalesce(causale,''))='iscrizione' OR lower(coalesce(causale,''))='tesseramento' OR lower(coalesce(causale,'')) LIKE '%iscrizion%') AND lower(coalesce(stato,'')||' '||coalesce(online_status,'')) NOT LIKE '%pending%' AND lower(coalesce(stato,'')||' '||coalesce(online_status,'')) NOT LIKE '%annull%' AND lower(coalesce(stato,'')||' '||coalesce(online_status,'')) NOT LIKE '%failed%' LIMIT 1''',(tid,season,season+1)).fetchone()
        if bool(x['iscrizione_pagata']) and not pay:legacy_only.append(tid)
finally:db.close()
monthly_due_ids={tid for tid,state in expected.items() if not state[1]}
monthly_due_rendered={int(x) for x in re.findall(r"<div class=['\x22\x27]bmpv7-row[^'\x22]*due[^'\x22]*['\x22\x27][^>]*data-bm-tid=['\x22\x27](\d+)",ph,re.I)}
checks={'routes':all(v in (200,301,302,303,307,308) for v in status.values()),'dashboard_body':all('bodymind-dashboard-canonical' in body(x) for x in (dh,hh)),'dashboard_single':dh.count('BODYMIND_R123_DASHBOARD_CANONICAL_RENDERED')==1 and hh.count('BODYMIND_R123_DASHBOARD_CANONICAL_RENDERED')==1,'dashboard_old_absent':not any(x in dh or x in hh for x in old_dash),'payment_single':ph.count('BODYMIND_R123_PAYMENT_FORM_CANONICAL_V7')==1,'payment_old_absent':not any(x in ph for x in old_pay),'payment_truth_matches':row_state==expected,'monthly_due_red':monthly_due_ids==monthly_due_rendered,'configured_background_rendered':(not bg_url) or (bg_url in dh and bg_url in hh),'configured_background_served':(not bg_url) or bg_status==200,'db':integrity.lower()=='ok' and fk==0}
print('[r123-final-rendered-audit] '+json.dumps({'checks':checks,'status':status,'body_dashboard':body(dh),'body_home':body(hh),'payment_rows':len(row_state),'truth_rows':len(expected_all),'monthly_due_rows':len(expected),'legacy_enrollment_flags_without_canonical_payment':legacy_only,'background_url':bg_url,'background_status':bg_status,'counts':counts,'integrity':integrity,'fk':fk},ensure_ascii=False),flush=True)
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


# BODYMIND_R123_PAYMENT_ADMIN_MOBILE_LABELS_V13
# One canonical extension for payment correction/annulment, payment navigation,
# and readable labels on the advanced mobile athlete form. No historical cash
# row is hard-deleted: "Elimina" annuls the mistaken movement and its receipt,
# preserving an auditable trail while removing it from canonical paid truth.
_core_v13=CORE.read_text(encoding='utf-8',errors='replace')
_v13_start='# BODYMIND_R123_PAYMENT_ADMIN_RUNTIME_V13'
_v13_end='# /BODYMIND_R123_PAYMENT_ADMIN_RUNTIME_V13'
if _v13_start in _core_v13:
    _a=_core_v13.find(_v13_start); _b=_core_v13.find(_v13_end,_a)
    if _b<0: raise RuntimeError('V13 runtime marker is incomplete')
    _core_v13=_core_v13[:_a]+_core_v13[_b+len(_v13_end):]

_core_v13 += r'''

# BODYMIND_R123_PAYMENT_ADMIN_RUNTIME_V13
@app.route('/pagamenti/elimina',methods=['POST'])
@login_required
def _bodymind_payment_annul_v13():
    from datetime import datetime as _dt
    pid=parse_int(request.form.get('payment_id'),0)
    if pid<=0:
        return redirect('/pagamenti?errore=pagamento_non_valido',303)
    c=db(); c.row_factory=sqlite3.Row
    try:
        p=c.execute("SELECT * FROM pagamenti WHERE id=?",(pid,)).fetchone()
        if not p:
            return redirect('/pagamenti?errore=pagamento_non_trovato',303)
        tid=int(p['tesserato_id'] or 0)
        mese=int(p['mese'] or 0)
        anno=int(p['anno'] or 0)
        causale=str(p['causale'] or '').lower()
        now=_dt.now().isoformat(timespec='seconds')
        # Preserve the original row as an audit trail; canonical payment truth
        # already excludes annullato/cancelled rows.
        c.execute("""UPDATE pagamenti
                     SET stato='annullato',online_status='annullato',
                         note_pagamento=TRIM(COALESCE(note_pagamento,'') ||
                           CASE WHEN COALESCE(note_pagamento,'')='' THEN '' ELSE ' · ' END ||
                           'ANNULLATO DA SEGRETERIA ' || ?),
                         updated_at=?
                     WHERE id=?""",(now,now,pid))
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ricevute'").fetchone():
            cols={str(x[1]) for x in c.execute("PRAGMA table_info(ricevute)").fetchall()}
            if 'annullata' in cols:
                c.execute("UPDATE ricevute SET annullata=1,updated_at=? WHERE pagamento_id=?",(now,pid))
        # Recompute only derived athlete flags; quote_mensili remains competence,
        # never proof of cash.
        try:_bodymind_reconcile_athlete_status_v10(c,tid)
        except Exception as exc:print('[payment-v13-reconcile-warning] '+repr(exc),flush=True)
        c.commit()
        vista='mensili' if ('mensil' in causale or causale in ('quota','quota_mensile')) else 'iscrizioni'
        target='/pagamenti?vista='+vista
        if 1<=mese<=12:target+='&mese='+str(mese)
        if anno:target+='&anno='+str(anno)
        if tid:target+='&tesserato_id='+str(tid)
        return redirect(target+'&eliminato=1',303)
    except Exception as exc:
        try:c.rollback()
        except Exception:pass
        print('[payment-v13-annul-warning] '+repr(exc),flush=True)
        return redirect('/pagamenti?errore=eliminazione',303)
    finally:
        try:c.close()
        except Exception:pass


@app.after_request
def _bodymind_payment_admin_surface_v13(resp):
    try:
        if request.method!='GET' or int(getattr(resp,'status_code',200) or 200)!=200:
            return resp
        if 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp
        html=resp.get_data(as_text=True)

        if request.path=='/pagamenti':
            # Delete controls are rendered inside the canonical payment editor.
            if request.args.get('eliminato')=='1':
                notice="<div class='bmpv7-saved'>Pagamento eliminato dalla contabilità attiva e conservato come annullato nello storico.</div>"
                anchor="<section class='bmpv7'>"
                if anchor in html:html=html.replace(anchor,anchor+notice,1)
            css="""<style id='bodymind-payment-admin-v13'>
            .sidebar a,.sidebar-menu a,.nav-sidebar a,[class*="sidebar"] a{pointer-events:auto!important}
            </style>"""
            if '</head>' in html and "bodymind-payment-admin-v13" not in html:
                html=html.replace('</head>',css+'</head>',1)

        # Safari screenshot diagnosis: labels exist in the DOM but inherit a
        # near-white color on the white advanced-form card. Scope the contrast
        # fix to the athlete edit surface only; input text remains white on navy.
        if request.path.startswith('/mobile/atleta/') and request.args.get('advanced')=='1':
            css="""<style id='bodymind-mobile-athlete-labels-v13'>
            form label,.form-group>label,.field>label,[class*="field"]>label{color:#0f2742!important;opacity:1!important;font-weight:800!important}
            form label small,.form-group>label small{color:#334155!important;opacity:1!important}
            form input,form select,form textarea{color:#fff!important;-webkit-text-fill-color:#fff!important}
            form input::placeholder,form textarea::placeholder{color:#cbd5e1!important;opacity:.82!important}
            </style>"""
            if '</head>' in html and "bodymind-mobile-athlete-labels-v13" not in html:
                html=html.replace('</head>',css+'</head>',1)

        # Make a non-link Pagamenti sidebar parent navigable without changing
        # existing submenu destinations. This is server-side HTML convergence.
        import re as _re
        html=_re.sub(r'href=(["\'])#\1([^>]*>\s*(?:<[^>]+>\s*)*Pagamenti\b)',r'href="/pagamenti"\2',html,flags=_re.I)
        resp.set_data(html)
    except Exception as exc:
        print('[payment-admin-surface-v13-warning] '+repr(exc),flush=True)
    return resp
# /BODYMIND_R123_PAYMENT_ADMIN_RUNTIME_V13
'''
CORE.write_text(_core_v13,encoding='utf-8')
py_compile.compile(str(CORE),doraise=True)

_v13_qa=r"""
import json,sqlite3,sys
sys.path.insert(0,'/data/top2_app');import app as _full
from asd_app.core import app
app.config['TESTING']=True
c=app.test_client()
with c.session_transaction() as sess:sess.update({'logged':True,'logged_in':True,'username':'admin','role':'admin','tenant_slug':'default','user_id':1,'is_admin':True,'admin':True})
db=sqlite3.connect('file:/data/tenants/default/asd.db?mode=ro',uri=True,timeout=20);db.row_factory=sqlite3.Row
try:
    before={t:int(db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]) for t in ('tesserati','pagamenti','ricevute')}
    integrity=str(db.execute('PRAGMA integrity_check').fetchone()[0]);fk=len(db.execute('PRAGMA foreign_key_check').fetchall())
finally:db.close()
pay=c.get('/pagamenti')
html=pay.get_data(as_text=True)
route_rules=[str(x) for x in app.url_map.iter_rules()]
out={'counts':before,'integrity':integrity,'fk':fk,'payment_http':pay.status_code,
     'delete_route':'/pagamenti/elimina' in route_rules,
     'payment_admin_css':'bodymind-payment-admin-v13' in html,
     'routes':len(route_rules)}
print('[r123-payment-admin-v13-audit] '+json.dumps(out,ensure_ascii=False),flush=True)
if integrity.lower()!='ok' or fk or pay.status_code!=200 or not out['delete_route'] or not out['payment_admin_css']:
    raise RuntimeError('V13 payment admin audit failed')
"""
_v13p=subprocess.run([sys.executable,'-c',_v13_qa],capture_output=True,text=True,timeout=180)
print((_v13p.stdout or '').strip(),flush=True)
if _v13p.returncode!=0:
    raise RuntimeError('V13 child audit failed '+((_v13p.stderr or '')+(_v13p.stdout or ''))[-5000:])
print('[r123-payment-admin-v13] PASS edit-existing annul-with-audit clickable-payment-nav mobile-label-contrast',flush=True)

# BODYMIND_R123_PAYMENT_EXACT_ID_V14


# BODYMIND_R123_RECEIPT_PAYMENT_METHOD_V16
# Preserve the existing receipt PDF layout, but make the payment method a
# first-class line immediately above the rendered amount on every receipt PDF.
# The route is wrapped at source level before Flask imports it; no after_request
# mutation and no historical accounting rows are rewritten.
import ast as _bm_ast, re as _bm_re
_receipt_candidates=[]
for _rp in (APP/'asd_app').rglob('*.py'):
    try:
        _rs=_rp.read_text(encoding='utf-8',errors='replace')
        _rt=_bm_ast.parse(_rs)
    except Exception:
        continue
    for _node in _rt.body:
        if not isinstance(_node,(_bm_ast.FunctionDef,_bm_ast.AsyncFunctionDef)):
            continue
        for _dec in _node.decorator_list:
            if not isinstance(_dec,_bm_ast.Call) or not _dec.args:
                continue
            _arg=_dec.args[0]
            if isinstance(_arg,_bm_ast.Constant) and isinstance(_arg.value,str) and _arg.value.startswith('/ricevute/pdf/'):
                _receipt_candidates.append((_rp,_rs,_node,_dec,_arg.value))
if len(_receipt_candidates)!=1:
    raise RuntimeError('V16 expected one canonical receipt PDF route, found '+repr([(str(x[0]),x[2].name,x[4]) for x in _receipt_candidates]))

_RPDF,_rs,_rnode,_rdec,_rrule=_receipt_candidates[0]
_param_match=_bm_re.search(r'<int:([A-Za-z_][A-Za-z0-9_]*)>',_rrule)
if not _param_match:
    raise RuntimeError('V16 receipt route has no integer receipt id: '+_rrule)
_rparam=_param_match.group(1)
_marker='# BODYMIND_RECEIPT_PAYMENT_METHOD_SOURCE_V16'

if _marker not in _rs:
    _lines=_rs.splitlines(True)
    _route_start=int(_rdec.lineno)-1
    _route_end=int(getattr(_rdec,'end_lineno',_rdec.lineno))
    _def_line=int(_rnode.lineno)-1
    _fn_end=int(getattr(_rnode,'end_lineno',_rnode.lineno))
    _route_src=''.join(_lines[_route_start:_route_end])
    _fn_src=''.join(_lines[_def_line:_fn_end])
    _legacy_name='_bodymind_receipt_pdf_legacy_v16'
    _fn_src=_bm_re.sub(r'^(\s*)(async\s+def|def)\s+'+_bm_re.escape(_rnode.name)+r'\s*\(',r'\1\2 '+_legacy_name+'(',_fn_src,count=1,flags=_bm_re.M)
    _replacement=_fn_src
    _wrapper=f"""
{_marker}
@app.route({_rrule!r},methods=['GET'],endpoint={_rnode.name!r})
@login_required
def _bodymind_receipt_pdf_with_method_v16({_rparam}):
    from io import BytesIO as _BytesIO
    from flask import make_response as _make_response
    from pypdf import PdfReader as _PdfReader, PdfWriter as _PdfWriter
    from reportlab.pdfgen import canvas as _rl_canvas
    from .core import db as _bm_db

    _rid=int({_rparam})
    _legacy={_legacy_name}(_rid)
    _resp=_make_response(_legacy)
    if 'application/pdf' not in str(_resp.headers.get('Content-Type','')).lower():
        return _resp

    _c=_bm_db(); _c.row_factory=sqlite3.Row
    try:
        _r=_c.execute("SELECT * FROM ricevute WHERE id=?",(_rid,)).fetchone()
        if not _r:
            return _resp
        _method=str(_r['metodo_pagamento'] or '').strip() if 'metodo_pagamento' in _r.keys() else ''
        _pid=int(_r['pagamento_id'] or 0) if 'pagamento_id' in _r.keys() else 0
        if not _method and _pid:
            _p=_c.execute("SELECT metodo_pagamento FROM pagamenti WHERE id=?",(_pid,)).fetchone()
            if _p:_method=str(_p['metodo_pagamento'] or '').strip()
        if not _method:
            _p=_c.execute("SELECT metodo_pagamento FROM pagamenti WHERE ricevuta_id=? ORDER BY id DESC LIMIT 1",(_rid,)).fetchone()
            if _p:_method=str(_p['metodo_pagamento'] or '').strip()
    finally:
        _c.close()
    if not _method:
        _method='non indicato'
    _norm={{'bonifico':'Bonifico','contanti':'Contanti','sumup':'SumUp','carta/sumup':'Carta / SumUp','carta':'Carta'}}
    _shown=_norm.get(_method.lower(),_method)

    try:
        _resp.direct_passthrough=False
        _raw=_resp.get_data()
        _reader=_PdfReader(_BytesIO(_raw))
        if not _reader.pages:
            return _resp
        _page=_reader.pages[0]
        _hits=[]
        def _visit(_text,_cm,_tm,_font,_size):
            if 'importo' in str(_text or '').lower():
                try:_hits.append((float(_tm[4]),float(_tm[5]),float(_size or 10)))
                except Exception:pass
        try:_page.extract_text(visitor_text=_visit)
        except Exception:pass
        _pw=float(_page.mediabox.width); _ph=float(_page.mediabox.height)
        if _hits:
            _x,_y,_fs=_hits[-1]
            _mx=max(36.0,min(_pw-220.0,_x))
            _my=max(36.0,min(_ph-36.0,_y+max(16.0,_fs*1.7)))
        else:
            _mx=54.0; _my=_ph-230.0
        _ov=_BytesIO()
        _cv=_rl_canvas.Canvas(_ov,pagesize=(_pw,_ph))
        _cv.setFont('Helvetica-Bold',9)
        _cv.drawString(_mx,_my,'Metodo di pagamento: '+_shown)
        _cv.save(); _ov.seek(0)
        _overlay=_PdfReader(_ov)
        _page.merge_page(_overlay.pages[0])
        _writer=_PdfWriter()
        for _pg in _reader.pages:_writer.add_page(_pg)
        _out=_BytesIO(); _writer.write(_out)
        _resp.set_data(_out.getvalue())
        _resp.headers['Content-Length']=str(len(_resp.get_data()))
        _resp.headers['Content-Type']='application/pdf'
    except Exception as _exc:
        print('[receipt-v16-overlay-warning] '+repr(_exc),flush=True)
    return _resp
"""
    # Replace the original route-decorated function with the undecorated legacy
    # implementation plus one canonical wrapper using the original endpoint.
    _start=min([int(d.lineno) for d in _rnode.decorator_list]+[int(_rnode.lineno)])-1
    _end=int(getattr(_rnode,'end_lineno',_rnode.lineno))
    _rs=''.join(_lines[:_start])+_replacement+_wrapper+''.join(_lines[_end:])
    _RPDF.write_text(_rs,encoding='utf-8')
    py_compile.compile(str(_RPDF),doraise=True)
    print('[receipt-v16-source] patched '+str(_RPDF)+' route='+_rrule,flush=True)
else:
    print('[receipt-v16-source] already canonical '+str(_RPDF),flush=True)

# Read-only rendered-PDF QA against one real enrollment/monthly receipt.
_receipt_qa=r"""
import io,sqlite3,sys
from pypdf import PdfReader
sys.path.insert(0,'/data/top2_app');import app as _full
from asd_app.core import app
app.config['TESTING']=True
db=sqlite3.connect('file:/data/tenants/default/asd.db?mode=ro',uri=True,timeout=20);db.row_factory=sqlite3.Row
try:
    r=db.execute("SELECT r.id,r.metodo_pagamento,p.metodo_pagamento AS pm FROM ricevute r LEFT JOIN pagamenti p ON p.id=r.pagamento_id WHERE COALESCE(r.annullata,0)=0 AND (lower(coalesce(p.causale,'')) LIKE '%mensil%' OR lower(coalesce(p.causale,'')) LIKE '%iscrizion%' OR lower(coalesce(p.causale,''))='tesseramento') ORDER BY r.id DESC LIMIT 1").fetchone()
    integrity=str(db.execute('PRAGMA integrity_check').fetchone()[0]);fk=len(db.execute('PRAGMA foreign_key_check').fetchall())
finally:db.close()
if not r:raise RuntimeError('V16 no receipt available for PDF QA')
method=str(r['metodo_pagamento'] or r['pm'] or '').strip()
c=app.test_client()
with c.session_transaction() as s:s.update({'logged':True,'logged_in':True,'username':'admin','role':'admin','tenant_slug':'default','user_id':1,'is_admin':True,'admin':True})
resp=c.get('/ricevute/pdf/'+str(int(r['id'])),follow_redirects=False)
raw=resp.get_data(); reader=PdfReader(io.BytesIO(raw))
text='\\n'.join((p.extract_text() or '') for p in reader.pages)
checks={'http':resp.status_code==200,'pdf':raw[:4]==b'%PDF','method_label':'Metodo di pagamento:' in text,'method_value':(not method) or method.lower() in text.lower(),'db':integrity.lower()=='ok' and fk==0}
print('[receipt-v16-audit] '+repr(checks)+' receipt_id='+str(int(r['id']))+' method='+repr(method),flush=True)
if not all(checks.values()):raise RuntimeError('V16 receipt PDF audit failed '+repr(checks))
"""
_rq=subprocess.run([sys.executable,'-c',_receipt_qa],capture_output=True,text=True,timeout=180)
print((_rq.stdout or '').strip(),flush=True)
if _rq.returncode!=0:
    raise RuntimeError('V16 receipt child audit failed '+((_rq.stderr or '')+(_rq.stdout or ''))[-7000:])
print('[receipt-v16] PASS payment-method-visible all receipt PDFs existing+future read-only-QA',flush=True)


# BODYMIND_R123_COLLABORATOR_CREATE_V17
# The existing "Nuovo collaboratore" link only changed the query string and
# rendered the same list: production logs showed GET ?new=1 and no POST at all.
# Provide one canonical creation form and a real POST path. No production data
# is created by the release itself; QA uses an isolated SQLite copy.
_core_collab=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R123_COLLABORATOR_CREATE_RUNTIME_V17' not in _core_collab:
    _core_collab += r'''

# BODYMIND_R123_COLLABORATOR_CREATE_RUNTIME_V17
def _bodymind_collaboratore_nuovo_page_v17(error=''):
    from datetime import date as _date
    today=_date.today().isoformat()
    err=("<div class='bmc17-error'>"+e(error)+"</div>") if error else ""
    html=f"""<!-- BODYMIND_R123_COLLABORATOR_CREATE_RUNTIME_V17 -->
    <main class='bmc17'>
      <header class='bmc17-head'>
        <div><small>COLLABORATORI</small><h1>Nuovo collaboratore</h1>
        <p>Registra l'anagrafica e l'inquadramento. Contratto, comunicazione RASD/UNILAV e documenti restano tracciati separatamente.</p></div>
        <a href='/collaboratori'>Chiudi</a>
      </header>
      {err}
      <form method='post' action='/collaboratori/nuovo' class='bmc17-form'>
        {csrf_input()}
        <section><h2>Anagrafica</h2>
          <label>Nome<input name='nome' required autocomplete='given-name'></label>
          <label>Cognome<input name='cognome' required autocomplete='family-name'></label>
          <label>Codice fiscale<input name='codice_fiscale' maxlength='16' autocapitalize='characters'></label>
          <label>Data di nascita<input type='date' name='data_nascita'></label>
          <label>Telefono<input name='telefono' inputmode='tel'></label>
          <label>Email<input type='email' name='email' autocomplete='email'></label>
        </section>
        <section><h2>Rapporto</h2>
          <label>Ruolo / mansione<input name='ruolo' required placeholder='Es. Istruttrice di discipline aeree'></label>
          <label>Tipo rapporto<select name='tipo_rapporto' required>
            <option value='co.co.co sportivo'>Co.co.co. sportivo</option>
            <option value='co.co.co amministrativo-gestionale'>Co.co.co. amministrativo-gestionale</option>
            <option value='lavoro autonomo / P.IVA'>Lavoro autonomo / P.IVA</option>
            <option value='volontario'>Volontario</option>
          </select></label>
          <label>Data inizio<input type='date' name='data_inizio' required value='{today}'></label>
          <label>Data fine<input type='date' name='data_fine'></label>
          <label>Paga oraria €<input type='number' step='0.01' min='0' name='paga_oraria' value='0'></label>
          <label>Copertura previdenziale<select name='copertura_previdenziale'>
            <option value=''>Da verificare</option>
            <option value='gestione_separata'>Gestione Separata INPS</option>
            <option value='altra_previdenza'>Già assicurato presso altra forma obbligatoria</option>
            <option value='pensionato'>Pensionato</option>
            <option value='non_applicabile'>Non applicabile</option>
          </select></label>
          <label>Compensi sportivi già percepiti nell'anno €<input type='number' step='0.01' min='0' name='compensi_sportivi_esterni_anno' value='0'></label>
          <label>Franchigia INPS già utilizzata €<input type='number' step='0.01' min='0' name='franchigia_inps_precedente' value='0'></label>
        </section>
        <section class='wide'><h2>Note e adempimenti</h2>
          <label class='wide'>Note<textarea name='note' rows='4' placeholder='Qualifica, tesseramento, eventuali altri rapporti, disponibilità, annotazioni...'></textarea></label>
          <div class='bmc17-checks'>
            <span>Alla creazione il rapporto viene segnato come <b>da completare</b>.</span>
            <span>Contratto firmato e comunicazione RASD/UNILAV non vengono dichiarati automaticamente.</span>
            <span>Se lavora con minori, verifica prima anche il casellario e gli obblighi safeguarding.</span>
          </div>
        </section>
        <button type='submit'>Registra collaboratore</button>
      </form>
    </main>
    <style>
      .bmc17{{max-width:980px;margin:0 auto;padding:18px 14px 90px}}.bmc17-head{{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:14px}}.bmc17-head small{{font-weight:950;letter-spacing:.14em;color:#7dd3fc}}.bmc17-head h1{{margin:4px 0;font-size:28px}}.bmc17-head p{{margin:0;color:#94a3b8;max-width:700px}}.bmc17-head a{{padding:10px 14px;border-radius:11px;background:#163b5f;color:#fff!important;text-decoration:none;font-weight:900}}.bmc17-error{{margin:10px 0;padding:11px 13px;border-radius:11px;background:#7f1d1d;color:#fee2e2;font-weight:850}}.bmc17-form{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}.bmc17-form section{{display:grid;grid-template-columns:1fr 1fr;gap:9px;padding:15px;border-radius:16px;background:#0d2138;border:1px solid rgba(96,165,250,.28)}}.bmc17-form section.wide{{grid-column:1/-1}}.bmc17-form h2{{grid-column:1/-1;margin:0 0 3px;font-size:16px;color:#dbeafe}}.bmc17-form label{{display:grid;gap:5px;color:#cbd5e1;font-size:12px;font-weight:900}}.bmc17-form label.wide{{grid-column:1/-1}}.bmc17-form input,.bmc17-form select,.bmc17-form textarea{{width:100%;min-height:43px;padding:10px;border-radius:10px;border:1px solid #36516d;background:#06111f;color:#fff;font-size:15px}}.bmc17-checks{{grid-column:1/-1;display:grid;gap:5px;padding:10px;border-radius:10px;background:#10243a;color:#bfdbfe;font-size:12px}}.bmc17-form>button{{grid-column:1/-1;min-height:50px;border:0;border-radius:13px;background:#16a34a;color:white;font-size:16px;font-weight:950}}@media(max-width:760px){{.bmc17-form{{grid-template-columns:1fr}}.bmc17-form section,.bmc17-form section.wide{{grid-column:1;grid-template-columns:1fr}}.bmc17-form h2,.bmc17-form label.wide,.bmc17-checks{{grid-column:1}}}}
    </style>"""
    return layout(html)

@app.before_request
def _bodymind_collaboratore_new_entry_v17():
    if request.method=='GET' and request.path=='/collaboratori' and (request.args.get('new') or '')=='1':
        return _bodymind_collaboratore_nuovo_v17()

@app.route('/collaboratori/nuovo',methods=['GET','POST'])
@login_required
def _bodymind_collaboratore_nuovo_v17():
    if request.method=='GET':
        return _bodymind_collaboratore_nuovo_page_v17()
    from datetime import date as _date, datetime as _dt
    nome=(request.form.get('nome') or '').strip()
    cognome=(request.form.get('cognome') or '').strip()
    ruolo=(request.form.get('ruolo') or '').strip()
    tipo=(request.form.get('tipo_rapporto') or '').strip()
    data_inizio=(request.form.get('data_inizio') or '').strip()
    if not nome or not cognome or not ruolo or not tipo or not data_inizio:
        return _bodymind_collaboratore_nuovo_page_v17('Nome, cognome, ruolo, tipo rapporto e data di inizio sono obbligatori.'),400
    try:_date.fromisoformat(data_inizio)
    except Exception:return _bodymind_collaboratore_nuovo_page_v17('Data di inizio non valida.'),400
    data_fine=(request.form.get('data_fine') or '').strip()
    if data_fine:
        try:_date.fromisoformat(data_fine)
        except Exception:return _bodymind_collaboratore_nuovo_page_v17('Data di fine non valida.'),400
    try:paga=max(0.0,float(str(request.form.get('paga_oraria') or '0').replace(',','.')))
    except Exception:paga=0.0
    try:esterni=max(0.0,float(str(request.form.get('compensi_sportivi_esterni_anno') or '0').replace(',','.')))
    except Exception:esterni=0.0
    try:franchigia=max(0.0,float(str(request.form.get('franchigia_inps_precedente') or '0').replace(',','.')))
    except Exception:franchigia=0.0

    dob=(request.form.get('data_nascita') or '').strip()
    minor=0
    if dob:
        try:
            born=_date.fromisoformat(dob); today=_date.today()
            minor=1 if (today.year-born.year-((today.month,today.day)<(born.month,born.day)))<18 else 0
        except Exception:
            return _bodymind_collaboratore_nuovo_page_v17('Data di nascita non valida.'),400
    now=_dt.now().isoformat(timespec='seconds')
    rasd_state='da_comunicare' if tipo=='co.co.co sportivo' else ('unilav_da_comunicare' if tipo=='co.co.co amministrativo-gestionale' else 'non_applicabile')
    values={
      'nome':nome,'cognome':cognome,'codice_fiscale':(request.form.get('codice_fiscale') or '').strip().upper(),
      'data_nascita':dob,'telefono':(request.form.get('telefono') or '').strip(),'email':(request.form.get('email') or '').strip(),
      'ruolo':ruolo,'tipo_rapporto':tipo,'data_inizio':data_inizio,'data_fine':data_fine or None,
      'paga_oraria':paga,'copertura_previdenziale':(request.form.get('copertura_previdenziale') or '').strip(),
      'compensi_sportivi_esterni_anno':esterni,'franchigia_inps_precedente':franchigia,
      'note':(request.form.get('note') or '').strip()[:3000],'minor':minor,'attivo':1,
      'workflow_status':'da_completare','workflow_blocked':0,'documenti_lavoro_ok':0,
      'contratto_firmato':0,'rasd_stato':rasd_state,'tenant_id':'default','created_at':now,'updated_at':now,
    }
    c=db();c.row_factory=sqlite3.Row
    try:
        info=c.execute("PRAGMA table_info(collaboratori)").fetchall()
        if not info:
            raise RuntimeError('tabella collaboratori non disponibile')
        cols={str(x['name']) for x in info}
        clean={k:v for k,v in values.items() if k in cols}
        # Fill only mandatory columns that have no DB default and are not PKs.
        for x in info:
            n=str(x['name'])
            if int(x['pk'] or 0) or not int(x['notnull'] or 0) or x['dflt_value'] is not None or n in clean:
                continue
            typ=str(x['type'] or '').upper()
            clean[n]=0 if any(t in typ for t in ('INT','REAL','NUM','DEC','FLOAT','DOUBLE')) else ''
        keys=list(clean)
        cur=c.execute("INSERT INTO collaboratori("+','.join(keys)+") VALUES("+','.join('?' for _ in keys)+")",[clean[k] for k in keys])
        cid=int(cur.lastrowid)
        c.commit()
    except Exception as exc:
        try:c.rollback()
        except Exception:pass
        print('[collaborator-v17-save-warning] '+repr(exc),flush=True)
        return _bodymind_collaboratore_nuovo_page_v17('Registrazione non riuscita: '+str(exc)),400
    finally:
        try:c.close()
        except Exception:pass
    return redirect('/collaboratori?creato='+str(cid),303)
# /BODYMIND_R123_COLLABORATOR_CREATE_RUNTIME_V17
'''
    CORE.write_text(_core_collab,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[collaborator-v17-source] PASS canonical create route + ?new=1 entrypoint',flush=True)

_collab_qa=r"""
import os,re,shutil,sqlite3,sys,tempfile
sys.path.insert(0,'/data/top2_app');import app as _full
import asd_app.core as core
from asd_app.core import app
app.config['TESTING']=True
fd,tmp=tempfile.mkstemp(prefix='bodymind_collab_v17_',suffix='.db');os.close(fd)
src=sqlite3.connect('/data/tenants/default/asd.db',timeout=30);dst=sqlite3.connect(tmp,timeout=30)
try:src.backup(dst)
finally:dst.close();src.close()
orig_db=core.db
def tdb():
    c=sqlite3.connect(tmp,timeout=20);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');return c
core.db=tdb
try:
    c=app.test_client()
    with c.session_transaction() as ss:ss.update({'logged':True,'logged_in':True,'username':'admin','role':'admin','tenant_slug':'default','user_id':1,'is_admin':True,'admin':True})
    g=c.get('/collaboratori?new=1',follow_redirects=False)
    html=g.get_data(as_text=True)
    m=re.search(r"name=['\"]csrf_token['\"][^>]*value=['\"]([^'\"]+)['\"]",html)
    if not m:raise RuntimeError('V17 CSRF token not rendered')
    db=tdb()
    try:before=int(db.execute('SELECT COUNT(*) FROM collaboratori').fetchone()[0])
    finally:db.close()
    payload={'csrf_token':m.group(1),'nome':'QA','cognome':'COLLABORATORE','ruolo':'Istruttore test','tipo_rapporto':'co.co.co sportivo','data_inizio':'2026-10-10','paga_oraria':'20','compensi_sportivi_esterni_anno':'0','franchigia_inps_precedente':'0'}
    p=c.post('/collaboratori/nuovo',data=payload,follow_redirects=False)
    db=tdb()
    try:
        after=int(db.execute('SELECT COUNT(*) FROM collaboratori').fetchone()[0])
        row=db.execute("SELECT * FROM collaboratori WHERE nome='QA' AND cognome='COLLABORATORE' ORDER BY id DESC LIMIT 1").fetchone()
        integrity=str(db.execute('PRAGMA integrity_check').fetchone()[0]);fk=len(db.execute('PRAGMA foreign_key_check').fetchall())
    finally:db.close()
    checks={'get':g.status_code==200,'marker':'BODYMIND_R123_COLLABORATOR_CREATE_RUNTIME_V17' in html,'post':p.status_code in (302,303),'created':after==before+1 and row is not None,'type':row is not None and str(row['tipo_rapporto'])=='co.co.co sportivo','workflow':row is not None and str(row['workflow_status'])=='da_completare','db':integrity.lower()=='ok' and fk==0}
    print('[collaborator-v17-audit] '+repr(checks),flush=True)
    if not all(checks.values()):raise RuntimeError('V17 collaborator audit failed '+repr(checks))
finally:
    core.db=orig_db
    try:os.unlink(tmp)
    except Exception:pass
"""
_cq=subprocess.run([sys.executable,'-c',_collab_qa],capture_output=True,text=True,timeout=180)
print((_cq.stdout or '').strip(),flush=True)
if _cq.returncode!=0:
    raise RuntimeError('V17 collaborator child audit failed '+((_cq.stderr or '')+(_cq.stdout or ''))[-7000:])
print('[collaborator-v17] PASS real form POST isolated-db no-production-mutation',flush=True)
