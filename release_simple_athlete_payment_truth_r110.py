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
 'payments_canonical':"SELECT * FROM pagamenti WHERE tesserato_id=?" in desk and "SELECT * FROM pagamenti WHERE tesserato_id=?" in mob,
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
