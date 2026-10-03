# -*- coding: utf-8 -*-
from __future__ import annotations
import py_compile, shutil
from pathlib import Path

APP=Path('/data/top2_app')
BACK=Path('/data/release_backups/20261002_r87_mobile_athlete_delete')
BACK.mkdir(parents=True,exist_ok=True)

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

matches=[]
for p in (APP/'asd_app').rglob('*.py'):
    try:
        s=p.read_text(encoding='utf-8',errors='replace')
    except Exception:
        continue
    if 'def fix24_mobile_atlete' in s and 'Schede e controlli essenziali.' in s:
        matches.append((p,s))

if len(matches)!=1:
    raise RuntimeError('R87 expected exactly one mobile athlete source, found '+str([str(x[0]) for x in matches]))

p,s=matches[0]
if 'BODYMIND_R87_MOBILE_ATHLETE_DELETE' not in s:
    try: rel=p.relative_to(APP)
    except Exception: rel=Path(p.name)
    dst=BACK/rel
    dst.parent.mkdir(parents=True,exist_ok=True)
    if not dst.exists():
        shutil.copy2(p,dst)

    css_old="<style>.certline{margin-top:8px;padding:8px 10px;border-radius:11px;font-size:12px;font-weight:800}.certline.missing,.certline.expired{background:#fee2e2;color:#991b1b}.certline.soon{background:#fef3c7;color:#854d0e}.certline.ok{background:#dcfce7;color:#166534}.filter-title{display:flex;align-items:center;min-height:48px;background:#fff7ed;color:#9a3412;border:1px solid #fed7aa;border-radius:14px;padding:11px 13px;margin-bottom:10px;font-size:13px;line-height:1.3;font-weight:800}</style>"
    css_new="<style>/* BODYMIND_R87_MOBILE_ATHLETE_DELETE */.certline{margin-top:8px;padding:8px 10px;border-radius:11px;font-size:12px;font-weight:800}.certline.missing,.certline.expired{background:#fee2e2;color:#991b1b}.certline.soon{background:#fef3c7;color:#854d0e}.certline.ok{background:#dcfce7;color:#166534}.filter-title{display:flex;align-items:center;min-height:48px;background:#fff7ed;color:#9a3412;border:1px solid #fed7aa;border-radius:14px;padding:11px 13px;margin-bottom:10px;font-size:13px;line-height:1.3;font-weight:800}.athlete-card{padding:0!important;overflow:hidden}.athlete-open{display:block;padding:16px;color:inherit;text-decoration:none}.athlete-delete-form{display:flex;margin:0;padding:0 16px 14px}.athlete-delete{width:100%;min-height:42px;border:1px solid #fecaca;border-radius:12px;background:#7f1d1d;color:#fff;font-weight:900;font-size:13px}</style>"
    if css_old not in s:
        raise RuntimeError('R87 mobile CSS anchor missing')
    s=s.replace(css_old,css_new,1)

    old="""{% for item in items %}{% set r=item.row %}<a class='card' href='/mobile/atleta/{{r["id"]}}'><div class='name'>{{r['nome']}} {{r['cognome']}}</div><div class='muted'>{{r['corso'] or 'Corso non indicato'}}</div><div class='certline {{item.cert_state}}'>{{item.cert_label}} · {{item.cert_detail}}</div><div class='chips'><span class='chip'>Apri scheda</span>{% if r['email'] %}<span class='chip ok'>Email presente</span>{% endif %}</div></a>{% else %}<div class='card empty'>{{'Nessun certificato richiede controllo.' if cert_filter else 'Nessuna atleta trovata.'}}</div>{% endfor %}"""
    new="""{% for item in items %}{% set r=item.row %}<div class='card athlete-card'><a class='athlete-open' href='/mobile/atleta/{{r["id"]}}'><div class='name'>{{r['nome']}} {{r['cognome']}}</div><div class='muted'>{{r['corso'] or 'Corso non indicato'}}</div><div class='certline {{item.cert_state}}'>{{item.cert_label}} · {{item.cert_detail}}</div><div class='chips'><span class='chip'>Apri scheda</span>{% if r['email'] %}<span class='chip ok'>Email presente</span>{% endif %}</div></a>{% if not cert_filter %}<form method='POST' action='/tesserati/delete' class='athlete-delete-form' onsubmit="return confirm('Eliminare definitivamente {{r['nome']}} {{r['cognome']}}? Questa operazione richiede conferma.');"><input type='hidden' name='id' value='{{r["id"]}}'><button type='submit' class='athlete-delete'>Elimina atleta</button></form>{% endif %}</div>{% else %}<div class='card empty'>{{'Nessun certificato richiede controllo.' if cert_filter else 'Nessuna atleta trovata.'}}</div>{% endfor %}"""
    if old not in s:
        raise RuntimeError('R87 athlete card anchor missing')
    s=s.replace(old,new,1)

    p.write_text(s,encoding='utf-8')
    py_compile.compile(str(p),doraise=True)
    print('[r87-mobile-athlete-delete] PASS source='+str(rel)+' backend=/tesserati/delete explicit-confirm route-audit',flush=True)
else:
    # Self-heal a partial/older R87 write that used a template helper unavailable on this mobile page.
    changed=False
    if '{{csrf_input()|safe}}' in s:
        s=s.replace('{{csrf_input()|safe}}','')
        changed=True
    # BODYMIND_R87_SURNAME_FIRST_LABEL
    # Keep the already surname-sorted list visually consistent: show COGNOME NOME.
    old_name="<div class='name'>{{r['nome']}} {{r['cognome']}}</div>"
    new_name="<div class='name'>{{r['cognome']}} {{r['nome']}}</div>"
    if old_name in s:
        s=s.replace(old_name,new_name)
        changed=True
    if changed:
        p.write_text(s,encoding='utf-8')
        py_compile.compile(str(p),doraise=True)
        print('[r87-mobile-athlete-delete] repaired mobile template / surname-first label',flush=True)
    print('[r87-mobile-athlete-delete] already applied source='+str(p),flush=True)
