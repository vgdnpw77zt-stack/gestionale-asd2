# -*- coding: utf-8 -*-
from __future__ import annotations
import py_compile, re, shutil, sqlite3
from datetime import datetime
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
BACK=Path('/data/release_backups/20261002_r110_simple_athlete_truth')
BACK.mkdir(parents=True,exist_ok=True)

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

def backup_file(p):
    dst=BACK/p.name
    if p.exists() and not dst.exists(): shutil.copy2(p,dst)

def backup_db():
    dst=BACK/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_pre_r110.db')
    src=sqlite3.connect(str(DB),timeout=30); out=sqlite3.connect(str(dst))
    try: src.backup(out)
    finally: out.close(); src.close()
    return str(dst)

def compile_file(p):
    py_compile.compile(str(p),doraise=True)

# ------------------------------------------------------------------
# Shared operational task filter: hide aggregate "tesseramento bloccato"
# when the specific missing items are already the actionable truth.
# ------------------------------------------------------------------
CORE=APP/'asd_app/core.py'
cs=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R110_TASK_DEDUP' not in cs and 'def get_operational_tasks' in cs:
    backup_file(CORE)
    cs += r'''

# BODYMIND_R110_TASK_DEDUP
_bodymind_r110_get_operational_tasks_base = get_operational_tasks
def get_operational_tasks(*args, **kwargs):
    items = _bodymind_r110_get_operational_tasks_base(*args, **kwargs)
    out=[]; seen=set()
    for item in (items or []):
        try:
            getter=item.get
        except Exception:
            getter=lambda k,d=None: item[k] if k in item.keys() else d
        typ=str(getter('tipo','') or getter('type','') or getter('category','') or getter('categoria','')).strip().lower()
        title=str(getter('title','') or getter('titolo','')).strip().lower()
        if typ=='tesseramento_bloccato' or 'tesseramento bloccato' in title:
            continue
        tid=int(getter('tesserato_id',0) or 0)
        if typ in ('pagamento_mancante','quota_mese_mancante','certificato_mancante','mu_mancante','modulo_unico_mancante','tutela_minore'):
            key=(tid,typ)
            if key in seen:
                continue
            seen.add(key)
        out.append(item)
    return out
'''
    CORE.write_text(cs,encoding='utf-8'); compile_file(CORE)
    print('[r110-core] PASS operational-task aggregate-filter specific-dedupe',flush=True)
elif 'BODYMIND_R110_TASK_DEDUP' in cs:
    print('[r110-core] already applied',flush=True)
else:
    print('[r110-core] get_operational_tasks not found; DB/UI simplification remains active',flush=True)

# ------------------------------------------------------------------
# Desktop sheet: keep advanced legacy view at ?advanced=1, but normal sheet
# is a small truth panel derived from canonical payments/documents.
# ------------------------------------------------------------------
DESK=APP/'asd_app/routes_tesserati.py'
ds=DESK.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R110_SIMPLE_DESKTOP' not in ds:
    backup_file(DESK)
    start=ds.find('def tesserato_scheda')
    if start<0: raise RuntimeError('R110 desktop tesserato_scheda not found')
    end=ds.find('\n@app.route',start)
    if end<0: end=len(ds)
    block=ds[start:end]
    m=re.search(r'^(\s*)r = dict\(row\)\s*$',block,re.M)
    if not m: raise RuntimeError('R110 desktop row anchor missing')
    indent=m.group(1)
    insert=r'''
__IND__# BODYMIND_R110_SIMPLE_DESKTOP
__IND__if request.args.get('advanced') != '1':
__IND__   from datetime import date as _r110_date
__IND__   _today=_r110_date.today(); _month=_today.month; _year=_today.year
__IND__   _season_start=_year if _month>=7 else _year-1
__IND__   def _paid_row(p):
__IND__       st=(str(p['stato'] or '')+' '+str(p['online_status'] or '')).lower()
__IND__       bad=any(x in st for x in ('pending','attesa','cancel','annull','failed','fallit','refunded','rimbors'))
__IND__       good=any(x in st for x in ('paid','pagat','saldat','complet','incassat'))
__IND__       return (not bad) and (good or (bool(p['data']) and float(p['importo'] or 0)>0))
__IND__   _payments=c.execute("SELECT * FROM pagamenti WHERE tesserato_id=? ORDER BY id DESC",(tesserato_id,)).fetchall()
__IND__   _month_paid=any(_paid_row(p) and str(p['causale'] or '').lower()=='mensile' and int(p['mese'] or 0)==_month and int(p['anno'] or 0)==_year for p in _payments)
__IND__   _enroll_paid=any(_paid_row(p) and str(p['causale'] or '').lower() in ('iscrizione','tesseramento') and int(p['anno'] or 0)==_season_start for p in _payments)
__IND__   _mu=bool(c.execute("""SELECT 1 FROM documenti WHERE tesserato_id=? AND COALESCE(visibile,1)=1 AND (
__IND__       LOWER(COALESCE(doc_type,''))='modulo_unico_tesseramento' OR
__IND__       LOWER(COALESCE(categoria,'')) LIKE '%modulo iscrizione%' OR
__IND__       LOWER(COALESCE(titolo,'')) LIKE '%modulo unico%' OR LOWER(COALESCE(titolo,'')) LIKE '%domanda iscrizione%'
__IND__   ) LIMIT 1""",(tesserato_id,)).fetchone())
__IND__   _med=bool(c.execute("""SELECT 1 FROM documenti WHERE tesserato_id=? AND COALESCE(visibile,1)=1
__IND__       AND LOWER(COALESCE(doc_type,''))='certificato_medico'
__IND__       AND LOWER(COALESCE(titolo,'')) NOT LIKE '%richiesta%' LIMIT 1""",(tesserato_id,)).fetchone())
__IND__   _cert_raw=str(r.get('certificato_scadenza') or '')
__IND__   _cert_ok=False; _cert_warn=False
__IND__   if _med:
__IND__       try:
__IND__           _exp=datetime.strptime(_cert_raw[:10],'%Y-%m-%d').date() if _cert_raw else None
__IND__           _cert_ok=bool(_exp and _exp>=_today)
__IND__           _cert_warn=not bool(_exp)
__IND__       except Exception:
__IND__           _cert_warn=True
__IND__   _minor=bool(int(r.get('minorenne') or 0))
__IND__   _guardian=str(r.get('genitore') or '').strip()
__IND__   _guardian_contact=str(r.get('telefono_genitore') or r.get('email_genitore') or '').strip()
__IND__   _consent=0
__IND__   try:
__IND__       _mr=c.execute("SELECT * FROM minori WHERE tesserato_id=? ORDER BY id DESC LIMIT 1",(tesserato_id,)).fetchone()
__IND__       _consent=int(_mr['consenso_firmato'] or 0) if _mr and 'consenso_firmato' in _mr.keys() else 0
__IND__       if _mr:
__IND__           _guardian=_guardian or str(_mr['genitore'] or '').strip()
__IND__           _guardian_contact=_guardian_contact or str(_mr['telefono_genitore'] or _mr['email_genitore'] or '').strip()
__IND__   except Exception: pass
__IND__   _tutela_ok=(not _minor) or bool(_guardian and _guardian_contact and _consent)
__IND__   def _dot(ok,warn=False):
__IND__       return ('#f59e0b','Da verificare') if warn else (('#16a34a','OK') if ok else ('#dc2626','Manca'))
__IND__   _states=[
__IND__     ('Iscrizione',*_dot(_enroll_paid), 'Quota iscrizione stagione '+str(_season_start)+'/'+str(_season_start+1)),
__IND__     ('Mese',*_dot(_month_paid), 'Mensile '+str(_month).zfill(2)+'/'+str(_year)),
__IND__     ('Modulo Unico',*_dot(_mu), 'Modulo Unico / modulo iscrizione'),
__IND__     ('Certificato',*_dot(_cert_ok,_cert_warn), ('Scadenza '+_cert_raw if _cert_raw else 'Certificato medico')),
__IND__     ('Tutela',*_dot(_tutela_ok), 'Genitore e consenso' if _minor else 'Maggiorenne'),
__IND__   ]
__IND__   _cards=''.join("<div class='r110-state'><span class='r110-dot' style='background:"+color+"'></span><div><b>"+e(label)+"</b><small>"+e(detail)+"</small></div><strong>"+e(state)+"</strong></div>" for label,color,state,detail in _states)
__IND__   _overall=all(x in (True,) for x in (_enroll_paid,_month_paid,_mu,_cert_ok,_tutela_ok))
__IND__   _name=(str(r.get('nome') or '')+' '+str(r.get('cognome') or '')).strip()
__IND__   simple=f"""<main class='r110-page'>
__IND__     <section class='r110-head'><div><span>Atleta</span><h1>{e(_name)}</h1><p>{e(str(r.get('corso') or 'Corso non indicato'))}</p></div><div class='r110-over {'ok' if _overall else 'bad'}'>{'REGOLARE' if _overall else 'DA COMPLETARE'}</div></section>
__IND__     <section class='r110-grid'>{_cards}</section>
__IND__     <section class='r110-actions'>
__IND__       <a href='/tesserati/{int(tesserato_id)}/scheda?advanced=1'>Modifica dati</a>
__IND__       <a href='/documenti?tesserato_id={int(tesserato_id)}'>Documenti</a>
__IND__       <a href='/pagamenti'>Pagamenti</a>
__IND__       <a href='/tesserati'>Torna alle atlete</a>
__IND__     </section>
__IND__   </main>
__IND__   <style id='bodymind-r110-simple-desktop'>
__IND__   .r110-page{{max-width:1000px;margin:18px auto 50px}}.r110-head{{display:flex;justify-content:space-between;gap:16px;align-items:center;padding:22px;border-radius:22px;background:rgba(12,25,43,.92);border:1px solid rgba(148,163,184,.16)}}.r110-head span{{font-size:11px;text-transform:uppercase;color:#93c5fd;font-weight:900;letter-spacing:.12em}}.r110-head h1{{margin:4px 0;font-size:34px}}.r110-head p{{margin:0;color:#9fb0c8}}.r110-over{{padding:12px 16px;border-radius:999px;font-weight:950}}.r110-over.ok{{background:#14532d;color:#dcfce7}}.r110-over.bad{{background:#7f1d1d;color:#fee2e2}}.r110-grid{{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:9px;margin-top:12px}}.r110-state{{display:grid;grid-template-columns:14px 1fr;gap:9px;align-items:start;padding:14px;border-radius:16px;background:rgba(15,23,42,.75);border:1px solid rgba(148,163,184,.13)}}.r110-dot{{width:12px;height:12px;border-radius:50%;margin-top:4px;box-shadow:0 0 0 4px rgba(255,255,255,.04)}}.r110-state b,.r110-state small,.r110-state strong{{display:block}}.r110-state small{{color:#94a3b8;margin-top:3px;font-size:11px}}.r110-state strong{{grid-column:2;font-size:11px}}.r110-actions{{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}}.r110-actions a{{padding:11px 14px;border-radius:13px;background:#17324d;color:#fff!important;text-decoration:none;font-weight:900}}@media(max-width:820px){{.r110-grid{{grid-template-columns:1fr 1fr}}.r110-head{{align-items:flex-start;flex-direction:column}}}}@media(max-width:520px){{.r110-grid{{grid-template-columns:1fr}}}}
__IND__   </style>"""
__IND__   return layout(simple)
'''
    insert=insert.replace('__IND__',indent)
    pos=m.end()
    block=block[:pos]+insert+block[pos:]
    ds=ds[:start]+block+ds[end:]
    DESK.write_text(ds,encoding='utf-8'); compile_file(DESK)
    print('[r110-desktop] PASS simple-truth-sheet advanced-preserved',flush=True)
else:
    print('[r110-desktop] already applied',flush=True)

# ------------------------------------------------------------------
# Mobile sheet: preserve the existing POST and advanced form. Normal GET
# becomes the same five-state truth panel. ?advanced=1 opens the old editor.
# ------------------------------------------------------------------
matches=[]
for p in (APP/'asd_app').rglob('*.py'):
    try: s=p.read_text(encoding='utf-8',errors='replace')
    except Exception: continue
    if 'BODYMIND_R100_PROFILE_SAVE_VERIFY' in s and 'def fix12_mobile_atleta' in s:
        matches.append((p,s))
if len(matches)!=1:
    raise RuntimeError('R110 expected one canonical mobile profile source, got '+repr([str(x[0]) for x in matches]))
MOB,ms=matches[0]
if 'BODYMIND_R110_SIMPLE_MOBILE' not in ms:
    backup_file(MOB)
    start=ms.find('def fix12_mobile_atleta')
    end=ms.find('\n@app.',start)
    if end<0: end=len(ms)
    block=ms[start:end]
    anchor="        if request.method=='POST':\n"
    if anchor not in block:
        raise RuntimeError('R110 mobile POST anchor missing')
    mobile=r'''        # BODYMIND_R110_SIMPLE_MOBILE
        if request.method=='GET' and request.args.get('advanced')!='1':
            from datetime import date as _r110_date
            _today=_r110_date.today(); _month=_today.month; _year=_today.year; _season=_year if _month>=7 else _year-1
            def _paid(p):
                st=(str(p['stato'] or '')+' '+str(p['online_status'] or '')).lower()
                return not any(x in st for x in ('pending','attesa','cancel','annull','failed','rimbors')) and (any(x in st for x in ('paid','pagat','saldat','complet','incassat')) or (bool(p['data']) and float(p['importo'] or 0)>0))
            _ps=conn.execute('SELECT * FROM pagamenti WHERE tesserato_id=? ORDER BY id DESC',(tid,)).fetchall()
            _mp=any(_paid(p) and str(p['causale'] or '').lower()=='mensile' and int(p['mese'] or 0)==_month and int(p['anno'] or 0)==_year for p in _ps)
            _ip=any(_paid(p) and str(p['causale'] or '').lower() in ('iscrizione','tesseramento') and int(p['anno'] or 0)==_season for p in _ps)
            _mu=bool(conn.execute("""SELECT 1 FROM documenti WHERE tesserato_id=? AND COALESCE(visibile,1)=1 AND (LOWER(COALESCE(doc_type,''))='modulo_unico_tesseramento' OR LOWER(COALESCE(categoria,'')) LIKE '%modulo iscrizione%' OR LOWER(COALESCE(titolo,'')) LIKE '%modulo unico%' OR LOWER(COALESCE(titolo,'')) LIKE '%domanda iscrizione%') LIMIT 1""",(tid,)).fetchone())
            _med=bool(conn.execute("""SELECT 1 FROM documenti WHERE tesserato_id=? AND COALESCE(visibile,1)=1 AND LOWER(COALESCE(doc_type,''))='certificato_medico' AND LOWER(COALESCE(titolo,'')) NOT LIKE '%richiesta%' LIMIT 1""",(tid,)).fetchone())
            _cert=str(row['certificato_scadenza'] or '') if 'certificato_scadenza' in row.keys() else ''
            _certok=False
            if _med and _cert:
                try:_certok=datetime.strptime(_cert[:10],'%Y-%m-%d').date()>=_today
                except Exception:pass
            _minor=bool(int(row['minorenne'] or 0)) if 'minorenne' in row.keys() else False
            def _rv(k):
                try:
                    if k in row.keys() and row[k] not in (None,''): return row[k]
                except Exception:pass
                try:
                    if mrow and k in mrow.keys() and mrow[k] not in (None,''): return mrow[k]
                except Exception:pass
                return ''
            _guard=bool(str(_rv('genitore')).strip() and str(_rv('telefono_genitore') or _rv('email_genitore')).strip() and int(_rv('consenso_firmato') or 0))
            _tut=(not _minor) or _guard
            items=[('Iscrizione',_ip,'Stagione '+str(_season)+'/'+str(_season+1)),('Mese',_mp,str(_month).zfill(2)+'/'+str(_year)),('Modulo Unico',_mu,'Modulo iscrizione'),('Certificato',_certok,_cert or 'mancante'),('Tutela',_tut,'genitore/consenso' if _minor else 'maggiorenne')]
            name=(str(row['nome'] or '')+' '+str(row['cognome'] or '')).strip()
            tpl="""<!doctype html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'><title>BodyMind · {{name}}</title>
            <style>body{margin:0;background:#071426;color:#eaf2ff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}.r110m{max-width:700px;margin:auto;padding:16px 14px 36px}.head{padding:18px;border-radius:20px;background:#0d2036;border:1px solid #203b57}.head h1{margin:4px 0}.head p{margin:0;color:#9fb3ca}.state{display:grid;grid-template-columns:16px 1fr auto;gap:9px;align-items:center;padding:14px;margin-top:9px;border-radius:15px;background:#0b1b2e;border:1px solid #1d3651}.dot{width:12px;height:12px;border-radius:50%}.state small{display:block;color:#91a6bd;margin-top:3px}.actions{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}.actions a{padding:12px;border-radius:13px;background:#163b5f;color:white;text-decoration:none;text-align:center;font-weight:900}.ok{color:#86efac}.bad{color:#fca5a5}</style></head><body><main class='r110m'><section class='head'><small>ATLETA</small><h1>{{name}}</h1><p>{{course or 'Corso non indicato'}}</p></section>{% for label,ok,detail in items %}<div class='state'><span class='dot' style='background:{{"#16a34a" if ok else "#dc2626"}}'></span><div><b>{{label}}</b><small>{{detail}}</small></div><strong class='{{"ok" if ok else "bad"}}'>{{"OK" if ok else "Manca"}}</strong></div>{% endfor %}<div class='actions'><a href='/mobile/atleta/{{tid}}?advanced=1'>Modifica dati</a><a href='/mobile/atleta/{{tid}}/documenti'>Documenti</a><a href='/pagamenti'>Pagamenti</a><a href='/mobile/atlete'>Atlete</a></div></main></body></html>"""
            return render_template_string(tpl,name=name,course=(row['corso'] or ''),items=items,tid=tid)

'''
    block=block.replace(anchor,mobile+anchor,1)
    ms=ms[:start]+block+ms[end:]
    MOB.write_text(ms,encoding='utf-8'); compile_file(MOB)
    print('[r110-mobile] PASS simple-truth-sheet advanced-preserved POST-preserved',flush=True)
else:
    print('[r110-mobile] already applied',flush=True)

# ------------------------------------------------------------------
# Close only redundant aggregate alerts. Preserve all history and specific
# alerts. This is not a deletion and can be rolled back from the DB backup.
# ------------------------------------------------------------------
backup=''
conn=sqlite3.connect(str(DB),timeout=30); conn.row_factory=sqlite3.Row
try:
    open_agg=int(conn.execute("SELECT COUNT(*) FROM smart_alerts WHERE status='open' AND tipo='tesseramento_bloccato'").fetchone()[0]) if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='smart_alerts'").fetchone() else 0
    if open_agg:
        backup=backup_db()
        conn.execute("UPDATE smart_alerts SET status='closed',closed_at=COALESCE(closed_at,datetime('now')),updated_at=datetime('now') WHERE status='open' AND tipo='tesseramento_bloccato'")
        conn.commit()
    remaining_agg=int(conn.execute("SELECT COUNT(*) FROM smart_alerts WHERE status='open' AND tipo='tesseramento_bloccato'").fetchone()[0]) if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='smart_alerts'").fetchone() else 0
    counts={t:int(conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]) for t in ('tesserati','pagamenti','quote_mensili','documenti','inbound_documents') if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone()}
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0]); fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally: conn.close()

# Static gates + source guarantees.
desk=DESK.read_text(encoding='utf-8',errors='replace'); mob=MOB.read_text(encoding='utf-8',errors='replace'); core=CORE.read_text(encoding='utf-8',errors='replace')
checks={
 'desktop_simple':'BODYMIND_R110_SIMPLE_DESKTOP' in desk and '?advanced=1' in desk,
 'mobile_simple':'BODYMIND_R110_SIMPLE_MOBILE' in mob and "request.method=='POST'" in mob,
 'payments_canonical':"SELECT * FROM pagamenti WHERE tesserato_id=?" in desk and ("SELECT * FROM pagamenti WHERE tesserato_id=?" in mob or "BODYMIND_R144_CANONICAL_PROFILE_TRUTH" in mob),
 'quote_not_payment_truth':'quote_mensili' not in desk[desk.find('BODYMIND_R110_SIMPLE_DESKTOP'):desk.find('BODYMIND_R110_SIMPLE_DESKTOP')+12000],
 'aggregate_alerts_closed':remaining_agg==0,
 'db_ok':integrity.lower()=='ok' and fk==0,
}
print('[r110-summary] counts='+repr(counts)+' open_aggregate_before='+str(open_agg)+' remaining='+str(remaining_agg)+' backup='+backup,flush=True)
print('[r110-checks] '+repr(checks)+' integrity='+integrity+' fk='+str(fk),flush=True)
failed=[k for k,v in checks.items() if not v]
if failed: raise RuntimeError('R110 QA failed '+repr(failed))
print('[r110-selftest] PASS simple-athlete payment-truth no-dossier-default specific-task-only db-ok',flush=True)

# BODYMIND_R110_PAYMENT_LINK_FOCUS
# Keep the default athlete sheet contextual: opening Pagamenti from an athlete
# must retain that athlete as the selected filter.
for _p in (DESK, MOB):
    _src=_p.read_text(encoding='utf-8',errors='replace')
    _before=_src
    _src=_src.replace("<a href='/pagamenti'>Pagamenti</a>", "<a href='/pagamenti?tesserato_id={int(tesserato_id)}'>Pagamenti</a>" if _p==DESK else "<a href='/pagamenti?tesserato_id={{tid}}'>Pagamenti</a>")
    if _src!=_before:
        backup_file(_p)
        _p.write_text(_src,encoding='utf-8')
        compile_file(_p)
        print('[r110-payment-focus] patched '+str(_p),flush=True)

_desk_now=DESK.read_text(encoding='utf-8',errors='replace')
_mob_now=MOB.read_text(encoding='utf-8',errors='replace')
if "/pagamenti?tesserato_id={int(tesserato_id)}" not in _desk_now:
    raise RuntimeError('R110 contextual desktop payment link missing')
if "/pagamenti?tesserato_id={{tid}}" not in _mob_now:
    raise RuntimeError('R110 contextual mobile payment link missing')
print('[r110-payment-focus] PASS athlete-scoped payment navigation',flush=True)


# BODYMIND_R110_PAYMENT_TASK_TRUTH_V2
# One payment truth for operational tasks. Canonical paid records win, but
# already-registered legacy enrollment flags and paid quote_mensili states
# remain valid so existing secretary work is never lost.
_core_v2=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R110_PAYMENT_TASK_TRUTH_V2' not in _core_v2:
    _core_v2 += r'''

# BODYMIND_R110_PAYMENT_TASK_TRUTH_V2
def _bodymind_payment_paid_row_v2(p):
    try:
        get=p.get
    except Exception:
        get=lambda k,d=None: p[k] if k in p.keys() else d
    st=(str(get('stato','') or '')+' '+str(get('online_status','') or '')).lower()
    if any(x in st for x in ('pending','attesa','cancel','annull','failed','fallit','refunded','rimbors')):
        return False
    if any(x in st for x in ('paid','pagat','saldat','complet','incassat')):
        return True
    try: amount=float(get('importo',0) or 0)
    except Exception: amount=0
    return bool(get('data','') or get('paid_at','')) and amount>0

def _bodymind_enrollment_paid_v2(conn, tid, season_start):
    row=conn.execute("SELECT * FROM tesserati WHERE id=?",(int(tid),)).fetchone()
    if row:
        keys=set(row.keys())
        if ('iscrizione_pagata' in keys and int(row['iscrizione_pagata'] or 0)==1) or ('tesseramento_pagato' in keys and int(row['tesseramento_pagato'] or 0)==1):
            return True
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pagamenti'").fetchone():
        return False
    for p in conn.execute("SELECT * FROM pagamenti WHERE tesserato_id=? ORDER BY id DESC",(int(tid),)).fetchall():
        cause=str(p['causale'] or '').strip().lower() if 'causale' in p.keys() else ''
        yr=int(p['anno'] or 0) if 'anno' in p.keys() else 0
        if cause in ('iscrizione','tesseramento') and yr in (int(season_start),int(season_start)+1) and _bodymind_payment_paid_row_v2(p):
            return True
    return False

def _bodymind_month_paid_v2(conn, tid, mese, anno):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pagamenti'").fetchone():
        for p in conn.execute("SELECT * FROM pagamenti WHERE tesserato_id=? AND mese=? AND anno=? ORDER BY id DESC",(int(tid),int(mese),int(anno))).fetchall():
            cause=str(p['causale'] or '').strip().lower() if 'causale' in p.keys() else ''
            if (cause=='mensile' or 'mensil' in cause or cause in ('quota','quota_mensile')) and _bodymind_payment_paid_row_v2(p):
                return True
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='quote_mensili'").fetchone():
        q=conn.execute("SELECT * FROM quote_mensili WHERE tesserato_id=? AND mese=? AND anno=? ORDER BY id DESC LIMIT 1",(int(tid),int(mese),int(anno))).fetchone()
        if q:
            st=str(q['stato'] or '').strip().lower() if 'stato' in q.keys() else ''
            if any(x in st for x in ('pagat','saldat','paid','incassat','complet')):
                return True
    return False

_bodymind_r110_tasks_v1=get_operational_tasks
def get_operational_tasks(*args, **kwargs):
    items=_bodymind_r110_tasks_v1(*args, **kwargs) or []
    try:
        from datetime import date as _bm_date
        import re as _bm_re
        today=_bm_date.today(); season=today.year if today.month>=7 else today.year-1
        conn=db(); conn.row_factory=sqlite3.Row
        out=[]
        for item in items:
            try: get=item.get
            except Exception: get=lambda k,d=None: item[k] if k in item.keys() else d
            typ=str(get('tipo','') or get('type','') or get('category','') or get('categoria','')).strip().lower()
            tid=int(get('tesserato_id',0) or 0)
            if tid>0 and typ=='pagamento_mancante' and _bodymind_enrollment_paid_v2(conn,tid,season):
                continue
            if tid>0 and typ=='quota_mese_mancante':
                hay=' '.join(str(get(k,'') or '') for k in ('title','titolo','message','messaggio','note'))
                m=_bm_re.search(r'(?<!\d)(0?[1-9]|1[0-2])\s*[/\-]\s*(20\d{2})(?!\d)',hay)
                mm=int(m.group(1)) if m else today.month
                yy=int(m.group(2)) if m else today.year
                if _bodymind_month_paid_v2(conn,tid,mm,yy):
                    continue
            out.append(item)
        return out
    except Exception:
        return items
'''
    CORE.write_text(_core_v2,encoding='utf-8')
    compile_file(CORE)
    print('[r110-payment-task-truth-v2] PASS runtime task truth installed',flush=True)
else:
    print('[r110-payment-task-truth-v2] already installed',flush=True)

# Close only stale payment alerts that are contradicted by the same truth.
# Never delete history; take a DB backup before changing alert status.
_conn=sqlite3.connect(str(DB),timeout=30); _conn.row_factory=sqlite3.Row
try:
    from datetime import date as _bm_date
    import re as _bm_re
    _today=_bm_date.today(); _season=_today.year if _today.month>=7 else _today.year-1
    _alerts=[]
    if _conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='smart_alerts'").fetchone():
        _alerts=_conn.execute("SELECT * FROM smart_alerts WHERE status='open' AND tipo IN ('pagamento_mancante','quota_mese_mancante') ORDER BY id").fetchall()
    _close=[]
    def _paidrow(p):
        st=(str(p['stato'] or '') if 'stato' in p.keys() else '')+' '+(str(p['online_status'] or '') if 'online_status' in p.keys() else '')
        st=st.lower()
        if any(x in st for x in ('pending','attesa','cancel','annull','failed','fallit','refunded','rimbors')): return False
        if any(x in st for x in ('paid','pagat','saldat','complet','incassat')): return True
        try: amount=float(p['importo'] or 0)
        except Exception: amount=0
        return bool((p['data'] if 'data' in p.keys() else '') or (p['paid_at'] if 'paid_at' in p.keys() else '')) and amount>0
    def _enroll(tid):
        a=_conn.execute("SELECT * FROM tesserati WHERE id=?",(tid,)).fetchone()
        if a:
            ks=set(a.keys())
            if ('iscrizione_pagata' in ks and int(a['iscrizione_pagata'] or 0)==1) or ('tesseramento_pagato' in ks and int(a['tesseramento_pagato'] or 0)==1): return True
        for p in _conn.execute("SELECT * FROM pagamenti WHERE tesserato_id=?",(tid,)).fetchall():
            cause=str(p['causale'] or '').lower()
            yr=int(p['anno'] or 0)
            if cause in ('iscrizione','tesseramento') and yr in (_season,_season+1) and _paidrow(p): return True
        return False
    def _month(tid,mm,yy):
        for p in _conn.execute("SELECT * FROM pagamenti WHERE tesserato_id=? AND mese=? AND anno=?",(tid,mm,yy)).fetchall():
            cause=str(p['causale'] or '').lower()
            if (cause=='mensile' or 'mensil' in cause or cause in ('quota','quota_mensile')) and _paidrow(p): return True
        if _conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='quote_mensili'").fetchone():
            q=_conn.execute("SELECT * FROM quote_mensili WHERE tesserato_id=? AND mese=? AND anno=? ORDER BY id DESC LIMIT 1",(tid,mm,yy)).fetchone()
            if q and any(x in str(q['stato'] or '').lower() for x in ('pagat','saldat','paid','incassat','complet')): return True
        return False
    for a in _alerts:
        tid=int(a['tesserato_id'] or 0)
        if not tid: continue
        if str(a['tipo'])=='pagamento_mancante' and _enroll(tid):
            _close.append(int(a['id'])); continue
        if str(a['tipo'])=='quota_mese_mancante':
            hay=' '.join(str(a[k] or '') for k in ('title','message') if k in a.keys())
            m=_bm_re.search(r'(?<!\d)(0?[1-9]|1[0-2])\s*[/\-]\s*(20\d{2})(?!\d)',hay)
            mm=int(m.group(1)) if m else _today.month; yy=int(m.group(2)) if m else _today.year
            if _month(tid,mm,yy): _close.append(int(a['id']))
    if _close:
        backup_db()
        marks=','.join('?' for _ in _close)
        _conn.execute("UPDATE smart_alerts SET status='closed',closed_at=COALESCE(closed_at,datetime('now')),updated_at=datetime('now') WHERE id IN ("+marks+")",_close)
        _conn.commit()
    _pc=int(_conn.execute("SELECT COUNT(*) FROM pagamenti").fetchone()[0]) if _conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pagamenti'").fetchone() else 0
    _flags=int(_conn.execute("SELECT COUNT(*) FROM tesserati WHERE COALESCE(iscrizione_pagata,0)=1 OR COALESCE(tesseramento_pagato,0)=1").fetchone()[0])
    _qpaid=0
    if _conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='quote_mensili'").fetchone():
        _qpaid=int(_conn.execute("SELECT COUNT(*) FROM quote_mensili WHERE lower(coalesce(stato,'')) LIKE '%pagat%' OR lower(coalesce(stato,'')) LIKE '%saldat%' OR lower(coalesce(stato,'')) LIKE '%paid%' OR lower(coalesce(stato,'')) LIKE '%incassat%'").fetchone()[0])
    print('[r110-payment-task-truth-v2] canonical_payments='+str(_pc)+' enrollment_flags='+str(_flags)+' paid_monthly_quotes='+str(_qpaid)+' stale_alerts_closed='+str(len(_close)),flush=True)
finally:
    _conn.close()


# BODYMIND_R110_CANONICAL_PAYMENT_FLOW_V3
# One payment truth for Dashboard / Centro operativo / Tasks / Tesserati / Pagamenti.
# This appends one canonical helper to core.py and makes old GET entry points converge
# on /pagamenti without altering historical payment rows.
_core_v3=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R110_CANONICAL_PAYMENT_FLOW_V3' not in _core_v3:
    _core_v3 += r'''

# BODYMIND_R110_CANONICAL_PAYMENT_FLOW_V3
def bodymind_payment_truth(conn, tesserato_id=None, mese=None, anno=None, stagione=None):
    from datetime import date as _bm_date
    today=_bm_date.today()
    mese=int(mese or today.month)
    anno=int(anno or today.year)
    stagione=int(stagione if stagione is not None else (anno if mese>=7 else anno-1))

    def _table_local(name):
        return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())

    def _paid_row(p):
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

    active=[]
    if _table_local('tesserati'):
        sql="SELECT * FROM tesserati WHERE COALESCE(attivo,1)=1"
        args=()
        if tesserato_id:
            sql+=" AND id=?"; args=(int(tesserato_id),)
        sql+=" ORDER BY cognome,nome"
        active=conn.execute(sql,args).fetchall()

    payments=[]
    if _table_local('pagamenti'):
        sql="SELECT * FROM pagamenti"
        args=()
        if tesserato_id:
            sql+=" WHERE tesserato_id=?"; args=(int(tesserato_id),)
        sql+=" ORDER BY id DESC"
        payments=conn.execute(sql,args).fetchall()

    by_tid={}
    for a in active:
        tid=int(a['id'])
        by_tid[tid]={
            'tesserato_id':tid,
            'nome':str(a['nome'] or '') if 'nome' in a.keys() else '',
            'cognome':str(a['cognome'] or '') if 'cognome' in a.keys() else '',
            'iscrizione_pagata':False,
            'mensile_pagato':False,
            'iscrizione_payment_id':None,
            'mensile_payment_id':None,
        }
        # Preserve historical explicit enrollment flags as valid truth.
        if 'iscrizione_pagata' in a.keys() and int(a['iscrizione_pagata'] or 0)==1:
            by_tid[tid]['iscrizione_pagata']=True
        if 'tesseramento_pagato' in a.keys() and int(a['tesseramento_pagato'] or 0)==1:
            by_tid[tid]['iscrizione_pagata']=True

    for p in payments:
        if not _paid_row(p):
            continue
        tid=int(p['tesserato_id'] or 0) if 'tesserato_id' in p.keys() else 0
        if tid not in by_tid:
            continue
        cause=str(p['causale'] or '').strip().lower() if 'causale' in p.keys() else ''
        pm=int(p['mese'] or 0) if 'mese' in p.keys() else 0
        py=int(p['anno'] or 0) if 'anno' in p.keys() else 0
        if (cause in ('iscrizione','tesseramento') or 'iscrizion' in cause) and py in (stagione,stagione+1):
            if not by_tid[tid]['iscrizione_pagata']:
                by_tid[tid]['iscrizione_pagata']=True
                by_tid[tid]['iscrizione_payment_id']=int(p['id']) if 'id' in p.keys() else None
        if (cause=='mensile' or 'mensil' in cause or cause in ('quota','quota_mensile')) and pm==mese and py==anno:
            if not by_tid[tid]['mensile_pagato']:
                by_tid[tid]['mensile_pagato']=True
                by_tid[tid]['mensile_payment_id']=int(p['id']) if 'id' in p.keys() else None

    # Legacy quote_mensili can prove that a monthly was already marked paid,
    # but never creates a second cash receipt.
    if _table_local('quote_mensili'):
        qrows=conn.execute("SELECT * FROM quote_mensili WHERE mese=? AND anno=?",(mese,anno)).fetchall()
        for q in qrows:
            tid=int(q['tesserato_id'] or 0) if 'tesserato_id' in q.keys() else 0
            if tid not in by_tid: continue
            st=str(q['stato'] or '').strip().lower() if 'stato' in q.keys() else ''
            if any(x in st for x in ('pagat','saldat','paid','incassat','complet')):
                by_tid[tid]['mensile_pagato']=True

    rows=list(by_tid.values())
    return {
        'mese':mese,'anno':anno,'stagione':stagione,
        'totale':len(rows),
        'iscrizioni_pagate':sum(1 for x in rows if x['iscrizione_pagata']),
        'iscrizioni_mancanti':sum(1 for x in rows if not x['iscrizione_pagata']),
        'mensili_pagati':sum(1 for x in rows if x['mensile_pagato']),
        'mensili_mancanti':sum(1 for x in rows if not x['mensile_pagato']),
        'rows':rows,
    }

# Last task wrapper: all payment task decisions use bodymind_payment_truth().
_bodymind_payment_flow_v3_tasks=get_operational_tasks
def get_operational_tasks(*args, **kwargs):
    items=_bodymind_payment_flow_v3_tasks(*args, **kwargs) or []
    try:
        from datetime import date as _bm_date
        today=_bm_date.today()
        conn=db(); conn.row_factory=sqlite3.Row
        truth=bodymind_payment_truth(conn,mese=today.month,anno=today.year)
        state={int(x['tesserato_id']):x for x in truth['rows']}
        out=[]; seen=set()
        for item in items:
            try:get=item.get
            except Exception:get=lambda k,d=None:item[k] if k in item.keys() else d
            typ=str(get('tipo','') or get('type','') or get('category','') or get('categoria','')).strip().lower()
            tid=int(get('tesserato_id',0) or 0)
            st=state.get(tid,{})
            semantic=None
            if typ=='pagamento_mancante':
                semantic='iscrizione'
                if st.get('iscrizione_pagata'): continue
            elif typ=='quota_mese_mancante':
                semantic='mensile'
                if st.get('mensile_pagato'): continue
            if semantic:
                key=(tid,semantic)
                if key in seen: continue
                seen.add(key)
                # Normalize action to the one canonical module.
                try:
                    item=dict(item)
                    item['href']=('/pagamenti?vista=iscrizioni&tesserato_id='+str(tid)) if semantic=='iscrizione' else ('/pagamenti?vista=mensili&mese='+str(today.month)+'&anno='+str(today.year)+'&tesserato_id='+str(tid))
                    item['url']=item['href']
                    item['action_url']=item['href']
                except Exception:
                    pass
            out.append(item)
        return out
    except Exception:
        return items

@app.before_request
def _bodymind_payment_entry_convergence_v3():
    try:
        # Old secretary entry points become aliases of the canonical payment module.
        if request.method=='GET' and request.path in ('/quote-incassi','/quote-incassi/','/pagamenti-pro','/pagamenti-automatici'):
            from flask import redirect
            qs=request.query_string.decode('utf-8','ignore')
            target='/pagamenti'+(('?'+qs) if qs else '')
            return redirect(target,302)
    except Exception:
        return None

@app.after_request
def _bodymind_dashboard_payment_truth_v3(resp):
    try:
        if request.method!='GET' or request.path!='/dashboard' or int(getattr(resp,'status_code',200) or 200)!=200:
            return resp
        if 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp
        html=resp.get_data(as_text=True)
        if 'BODYMIND_PAYMENT_TRUTH_DASHBOARD_V3' in html:
            return resp
        from datetime import date as _bm_date
        today=_bm_date.today()
        c=db(); c.row_factory=sqlite3.Row
        try:
            t=bodymind_payment_truth(c,mese=today.month,anno=today.year)
        finally:
            try:c.close()
            except Exception:pass
        months=['','Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno','Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre']
        panel=f"""<!-- BODYMIND_PAYMENT_TRUTH_DASHBOARD_V3 -->
        <section class='bmpay-unified'>
          <div class='bmpay-title'><div><span>PAGAMENTI · UNICA VERITÀ</span><h2>Iscrizioni e mensile</h2><p>Gli stessi stati valgono in Dashboard, Centro operativo, Task, Tesserati e Pagamenti.</p></div></div>
          <div class='bmpay-grid'>
            <a href='/pagamenti?vista=iscrizioni&stagione={t["stagione"]}'><small>ISCRIZIONI {t["stagione"]}/{t["stagione"]+1}</small><strong>{t["iscrizioni_pagate"]}/{t["totale"]}</strong><span>{t["iscrizioni_mancanti"]} da completare</span></a>
            <a href='/pagamenti?vista=mensili&mese={t["mese"]}&anno={t["anno"]}'><small>MENSILE · {months[t["mese"]]} {t["anno"]}</small><strong>{t["mensili_pagati"]}/{t["totale"]}</strong><span>{t["mensili_mancanti"]} da completare</span></a>
            <a href='/tesserati'><small>TESSERATI</small><strong>{t["totale"]}</strong><span>Apri le schede individuali</span></a>
          </div>
        </section>
        <style id='bodymind-payment-truth-dashboard-v3'>
        .bmpay-unified{{margin:14px 0 18px;padding:18px;border-radius:20px;background:linear-gradient(135deg,#0a1728,#102c46);border:1px solid rgba(96,165,250,.24);color:#f8fafc}}
        .bmpay-title span{{font-size:10px;font-weight:950;letter-spacing:.14em;color:#7dd3fc}}.bmpay-title h2{{margin:4px 0;font-size:25px}}.bmpay-title p{{margin:0;color:#b7c6d9}}
        .bmpay-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;margin-top:13px}}.bmpay-grid a{{display:grid;gap:4px;padding:14px;border-radius:15px;background:#0b1d31;border:1px solid rgba(148,163,184,.16);color:white!important;text-decoration:none}}.bmpay-grid small{{font-size:10px;font-weight:900;color:#93c5fd}}.bmpay-grid strong{{font-size:24px}}.bmpay-grid span{{font-size:11px;color:#cbd5e1}}
        @media(max-width:760px){{.bmpay-grid{{grid-template-columns:1fr}}}}
        </style>
        <script id='bodymind-payment-entry-links-v3'>(function(){{
          document.querySelectorAll('a[href]').forEach(function(a){{
            var h=a.getAttribute('href')||'';
            if(h.indexOf('/quote-incassi')===0 || h.indexOf('/pagamenti-pro')===0 || h.indexOf('/pagamenti-automatici')===0){{
              a.setAttribute('href','/pagamenti');
            }}
          }});
        }})();</script>"""
        # Put the one payment module near the top of the dashboard, after <main> if possible.
        m=re.search(r'<main\b[^>]*>',html,re.I)
        if m:
            html=html[:m.end()]+panel+html[m.end():]
        else:
            html=html.replace('<body>','<body>'+panel,1) if '<body>' in html else panel+html
        resp.set_data(html)
    except Exception as exc:
        print('[payment-dashboard-v3-warning] '+repr(exc),flush=True)
    return resp
'''
    CORE.write_text(_core_v3,encoding='utf-8')
    compile_file(CORE)
    print('[r110-payment-flow-v3] PASS one-truth helper task-normalization dashboard-module entry-convergence',flush=True)
else:
    print('[r110-payment-flow-v3] already installed',flush=True)

# Read-only integrity gate for the unified payment flow.
_c=sqlite3.connect(str(DB),timeout=20); _c.row_factory=sqlite3.Row
try:
    _integrity=str(_c.execute('PRAGMA integrity_check').fetchone()[0])
    _fk=len(_c.execute('PRAGMA foreign_key_check').fetchall())
    _pay_count=int(_c.execute('SELECT COUNT(*) FROM pagamenti').fetchone()[0]) if _c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pagamenti'").fetchone() else 0
finally:_c.close()
if _integrity.lower()!='ok' or _fk:
    raise RuntimeError('R110 payment-flow-v3 DB guard failed')
print('[r110-payment-flow-v3-selftest] PASS pagamenti='+str(_pay_count)+' integrity='+_integrity+' fk='+str(_fk),flush=True)


# BODYMIND_R110_CANONICAL_ENTRYPOINTS_V4
# Tesserati, Dashboard, Centro operativo and all payment shortcuts open the
# exact same /pagamenti module, with semantic view + athlete/period context.
for _profile_src in (DESK, MOB):
    _txt=_profile_src.read_text(encoding='utf-8',errors='replace')
    if 'BODYMIND_R110_CANONICAL_PROFILE_PAYMENT_LINKS_V4' not in _txt:
        if _profile_src==DESK:
            old="<a href='/pagamenti?tesserato_id={int(tesserato_id)}'>Pagamenti</a>"
            new="<a href='/pagamenti?vista=iscrizioni&tesserato_id={int(tesserato_id)}'>Iscrizione</a><a href='/pagamenti?vista=mensili&tesserato_id={int(tesserato_id)}'>Mensile</a><!-- BODYMIND_R110_CANONICAL_PROFILE_PAYMENT_LINKS_V4 -->"
        else:
            old="<a href='/pagamenti?tesserato_id={{tid}}'>Pagamenti</a>"
            new="<a href='/pagamenti?vista=iscrizioni&tesserato_id={{tid}}'>Iscrizione</a><a href='/pagamenti?vista=mensili&tesserato_id={{tid}}'>Mensile</a><!-- BODYMIND_R110_CANONICAL_PROFILE_PAYMENT_LINKS_V4 -->"
        if old in _txt:
            backup_file(_profile_src)
            _txt=_txt.replace(old,new,1)
            _profile_src.write_text(_txt,encoding='utf-8')
            compile_file(_profile_src)
            print('[r110-profile-payment-links-v4] PASS '+str(_profile_src),flush=True)
        elif 'BODYMIND_R110_CANONICAL_PROFILE_PAYMENT_LINKS_V4' in _txt:
            print('[r110-profile-payment-links-v4] already '+str(_profile_src),flush=True)
        else:
            print('[r110-profile-payment-links-v4] anchor not found '+str(_profile_src),flush=True)

_core_v4=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R110_CANONICAL_ENTRYPOINTS_V4' not in _core_v4:
    _core_v4 += r'''

# BODYMIND_R110_CANONICAL_ENTRYPOINTS_V4
@app.after_request
def _bodymind_payment_entrypoints_v4(resp):
    try:
        if request.method!='GET' or int(getattr(resp,'status_code',200) or 200)!=200:
            return resp
        if 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp
        html=resp.get_data(as_text=True)
        if not html:
            return resp

        # Every visible legacy entry becomes an alias of the canonical module.
        import re as _bm_re
        html=_bm_re.sub(r"href=([\"'])(/quote-incassi/?|/pagamenti-pro/?|/pagamenti-automatici/?)([^\"']*)\\1",
                        lambda m:'href='+m.group(1)+'/pagamenti'+(m.group(3) or '')+m.group(1),html,flags=_bm_re.I)

        # Dashboard and Centro operativo display the same truth component.
        if request.path in ('/dashboard','/cuore-operativo','/centro-operativo'):
            if 'BODYMIND_PAYMENT_TRUTH_DASHBOARD_V3' not in html:
                from datetime import date as _bm_date
                today=_bm_date.today()
                c=db(); c.row_factory=sqlite3.Row
                try:
                    t=bodymind_payment_truth(c,mese=today.month,anno=today.year)
                finally:
                    try:c.close()
                    except Exception:pass
                months=['','Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno','Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre']
                panel=f"""<!-- BODYMIND_PAYMENT_TRUTH_DASHBOARD_V3 -->
                <section class='bmpay-unified'>
                  <div class='bmpay-title'><div><span>PAGAMENTI · MODULO UNICO</span><h2>Iscrizioni e mensile</h2><p>Questa è la stessa situazione usata da Tesserati, Task e Pagamenti.</p></div></div>
                  <div class='bmpay-grid'>
                    <a href='/pagamenti?vista=iscrizioni&stagione={t["stagione"]}'><small>ISCRIZIONI {t["stagione"]}/{t["stagione"]+1}</small><strong>{t["iscrizioni_pagate"]}/{t["totale"]}</strong><span>{t["iscrizioni_mancanti"]} da completare</span></a>
                    <a href='/pagamenti?vista=mensili&mese={t["mese"]}&anno={t["anno"]}'><small>MENSILE · {months[t["mese"]]} {t["anno"]}</small><strong>{t["mensili_pagati"]}/{t["totale"]}</strong><span>{t["mensili_mancanti"]} da completare</span></a>
                    <a href='/tesserati'><small>TESSERATI</small><strong>{t["totale"]}</strong><span>Apri una persona e gestisci gli stessi due stati</span></a>
                  </div>
                </section>
                <style id='bodymind-payment-entrypoints-v4'>
                .bmpay-unified{{margin:14px 0 18px;padding:18px;border-radius:20px;background:linear-gradient(135deg,#0a1728,#102c46);border:1px solid rgba(96,165,250,.24);color:#f8fafc}}
                .bmpay-title span{{font-size:10px;font-weight:950;letter-spacing:.14em;color:#7dd3fc}}.bmpay-title h2{{margin:4px 0;font-size:25px}}.bmpay-title p{{margin:0;color:#b7c6d9}}
                .bmpay-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;margin-top:13px}}.bmpay-grid a{{display:grid;gap:4px;padding:14px;border-radius:15px;background:#0b1d31;border:1px solid rgba(148,163,184,.16);color:white!important;text-decoration:none}}.bmpay-grid small{{font-size:10px;font-weight:900;color:#93c5fd}}.bmpay-grid strong{{font-size:24px}}.bmpay-grid span{{font-size:11px;color:#cbd5e1}}
                @media(max-width:760px){{.bmpay-grid{{grid-template-columns:1fr}}}}
                </style>"""
                m=_bm_re.search(r'<main\b[^>]*>',html,_bm_re.I)
                if m: html=html[:m.end()]+panel+html[m.end():]
                elif '<body' in html:
                    bm=_bm_re.search(r'<body\b[^>]*>',html,_bm_re.I)
                    if bm: html=html[:bm.end()]+panel+html[bm.end():]
                else: html=panel+html

        if 'BODYMIND_PAYMENT_ENTRYPOINTS_V4_RENDERED' not in html:
            html=html.replace('</body>','<!-- BODYMIND_PAYMENT_ENTRYPOINTS_V4_RENDERED --></body>',1) if '</body>' in html else html+'<!-- BODYMIND_PAYMENT_ENTRYPOINTS_V4_RENDERED -->'
        resp.set_data(html)
    except Exception as exc:
        print('[payment-entrypoints-v4-warning] '+repr(exc),flush=True)
    return resp
'''
    CORE.write_text(_core_v4,encoding='utf-8')
    compile_file(CORE)
    print('[r110-entrypoints-v4] PASS dashboard-center-tesserati legacy-links converge to /pagamenti',flush=True)
else:
    print('[r110-entrypoints-v4] already installed',flush=True)

_c=sqlite3.connect(str(DB),timeout=20)
try:
    _ok=str(_c.execute('PRAGMA integrity_check').fetchone()[0])
    _fk=len(_c.execute('PRAGMA foreign_key_check').fetchall())
finally:_c.close()
if _ok.lower()!='ok' or _fk:
    raise RuntimeError('R110 entrypoints-v4 DB guard failed')
print('[r110-entrypoints-v4-selftest] PASS integrity='+_ok+' fk='+str(_fk),flush=True)
