"""A364 — read-only monthly attendance, built on the canonical A309 records.

No migrations, writes, changes to existing POSTs, source-on-volume or site service.
Never trust an athlete ID from a family request: resolve the opaque family token
against that tenant's own tesserati row for every request.
"""
from __future__ import annotations

import calendar
import hashlib
import html
import re
import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote, urlencode

from flask import abort, make_response, redirect, request

RELEASE = "A364"
EXPECTED_ATTENDANCE_SHA = "fc8a956bf054ee4ff907095dfbf29e0f753543a02fbf593e0698e017e48e99d6"
EXPECTED_PORTAL_SHA = "35afdadb806a9ad1f22188e7f20439356f7282dad3adb4fc867554485ee4f686"
MONTHS = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre")
WEEKDAYS = ("lun", "mar", "mer", "gio", "ven", "sab", "dom")
CATEGORIES = {"kids": "Kids", "adult": "Adult", "pro": "Pro"}


def esc(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def parse_month(raw, today=None):
    raw = str(raw or (today or date.today()).strftime("%Y-%m")).strip()
    if not re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])", raw):
        raise ValueError("Mese non valido")
    return date(int(raw[:4]), int(raw[5:]), 1)


def next_month(d):
    return date(d.year + (d.month == 12), (d.month % 12) + 1, 1)


def previous_month(d):
    return date(d.year - (d.month == 1), (d.month - 2) % 12 + 1, 1)


def lesson_days(month):
    return [date(month.year, month.month, i) for i in range(1, calendar.monthrange(month.year, month.month)[1] + 1)
            if date(month.year, month.month, i).weekday() in (0, 2)]


def month_name(d):
    return f"{MONTHS[d.month - 1].capitalize()} {d.year}"


def day_name(d):
    return f"{WEEKDAYS[d.weekday()].capitalize()} {d.day} {MONTHS[d.month - 1][:3]}"


def month_selector(month, action, extra=None):
    today = date.today()
    years = range(min(2025, today.year - 1, month.year), max(today.year + 2, month.year + 1))
    values = [date(y, m, 1) for y in years for m in range(1, 13)]
    choices = "".join(f'<option value="{d:%Y-%m}" {"selected" if d==month else ""}>{esc(month_name(d))}</option>' for d in reversed(values))
    fields = "".join(f'<input type="hidden" name="{esc(k)}" value="{esc(v)}">' for k, v in (extra or {}).items())
    return (f'<form method="get" action="{esc(action)}" class="bm364-month-form" aria-label="Scegli il mese">'
            f'{fields}<label for="bm364-month-select">Mese</label><select id="bm364-month-select" name="mese">{choices}</select>'
            '<button type="submit">Visualizza</button></form>')


def read_connection():
    # The application's existing db() helper may perform schema/bootstrap work.
    # This feature opens an independent, strictly read-only SQLite connection.
    from asd_app.core import get_workspace_db_path
    path = Path(get_workspace_db_path()).resolve(strict=True)
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=8)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def course_category(name, cid, explicit):
    if cid in explicit:
        return explicit[cid]
    s = str(name or "").casefold().replace("_", " ")
    if any(term in s for term in ("pro", "agon", "élite", "elite", "advanced")):
        return "pro"
    if any(term in s for term in ("kids", "kid", "bambin", "junior", "baby", "piccol")):
        return "kids"
    if any(term in s for term in ("adult", "adulti")):
        return "adult"
    return "other"


def course_categories(conn):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bodymind_rapid_course_categories'").fetchone() is None:
        return {}
    return {int(r['corso_id']): str(r['categoria']) for r in conn.execute(
        "SELECT corso_id,categoria FROM bodymind_rapid_course_categories")}


def admin_month_rows(conn, month):
    end = next_month(month)
    rows = conn.execute('''
        SELECT p.data,p.stato,p.corso_id,p.tesserato_id,
               c.nome AS corso,COALESCE(c.orario,'') AS orario,
               t.nome AS nome,t.cognome AS cognome
        FROM presenze p
        LEFT JOIN corsi c ON c.id=p.corso_id
        LEFT JOIN tesserati t ON t.id=p.tesserato_id
        WHERE p.data>=? AND p.data<?
        ORDER BY p.data,c.nome,t.cognome,t.nome,p.id
    ''', (month.isoformat(), end.isoformat())).fetchall()
    allowed = {d.isoformat() for d in lesson_days(month)}
    parsed = [dict(r) for r in rows if r['data'] in allowed]
    others = len(rows) - len(parsed)
    return parsed, others


def render_admin(month, day, entries, skipped, explicit):
    all_days = lesson_days(month)
    if day not in all_days:
        raise ValueError("Giorno non valido per il mese scelto")
    day_values = {d.isoformat() for d in all_days}
    days = defaultdict(list)
    for r in entries:
        if r['data'] in day_values:
            days[r['data']].append(r)
    month_present = sum(r['stato'] == 'presente' for r in entries)
    month_absent = sum(r['stato'] in ('assente','giustificato') for r in entries)
    unique_present = len({r['tesserato_id'] for r in entries if r['stato']=='presente'})
    form = month_selector(month, "/presenze/mensile")
    tabs = []
    for d in all_days:
        rows = days[d.isoformat()]
        n = sum(r['stato']=='presente' for r in rows)
        selected = ' aria-current="date" class="bm364-day selected"' if day==d else ' class="bm364-day"'
        href = "/presenze/mensile?" + urlencode({"mese":month.strftime("%Y-%m"),"giorno":d.isoformat()})
        tabs.append(f'<a href="{esc(href)}"{selected}><strong>{esc(day_name(d))}</strong><small>{n} presenti</small></a>')
    selected_rows = days[day.isoformat()]
    grouped = defaultdict(list)
    for row in selected_rows:
        cid=int(row['corso_id']); label=str(row['corso'] or f"Corso #{cid}")
        key = (course_category(label,cid,explicit), cid, label, str(row['orario'] or ''))
        grouped[key].append(row)
    sections=[]
    for (category,cid,name,orario), persons in sorted(grouped.items(),key=lambda item:(list(CATEGORIES).index(item[0][0]) if item[0][0] in CATEGORIES else 3,item[0][3].casefold(),item[0][2].casefold())):
        chips=[]
        for r in sorted(persons,key=lambda rr:(str(rr['cognome'] or '').casefold(),str(rr['nome'] or '').casefold())):
            state=str(r['stato'] or '').strip().lower()
            label='Presente' if state=='presente' else ('Giustificata' if state=='giustificato' else ('Assente' if state=='assente' else 'Da verificare'))
            fullname=f"{r['cognome'] or ''} {r['nome'] or ''}".strip() or "Atleta non disponibile"
            css='yes' if state=='presente' else ('no' if state in ('assente','giustificato') else 'maybe')
            chips.append(f'<li class="bm364-athlete {css}"><span>{esc(fullname)}</span><em>{label}</em></li>')
        edit = "/presenze-semplici?" + urlencode({"corso_id":cid, "gruppo":category if category in CATEGORIES else "kids", "data":day.isoformat(),"mese":month.strftime('%Y-%m')})
        sections.append(f'<section class="bm364-course"><header><div><small>{esc(CATEGORIES.get(category,"Altri corsi"))} · {esc(orario or "Orario non indicato")}</small><h3>{esc(name)}</h3></div>'
                        + (f'<a href="{esc(edit)}">Apri registro</a>' if category in CATEGORIES else '') + '</header><ul>'+''.join(chips)+'</ul></section>')
    empty = '<p class="bm364-empty">Nessuna presenza salvata per questa data. Non significa che le atlete siano assenti.</p>'
    stats = (f'<div class="bm364-metrics"><div><strong>{month_present}</strong><small>Presenze registrate</small></div>'
             f'<div><strong>{month_absent}</strong><small>Assenze registrate</small></div>'
             f'<div><strong>{unique_present}</strong><small>Atlete presenti nel mese</small></div></div>')
    info=f'<p class="bm364-note">{skipped} registrazioni effettuate fuori dai lunedì e mercoledì non sono incluse in questa vista. Restano conservate nel registro originale.</p>' if skipped else ''
    body = (f'<main class="bm364-wrap bm364-admin"><div class="bm364-top"><div><span class="bm364-eyebrow">BODYMIND · PRESENZE</span>'
            f'<h1>Registro mensile</h1><p>Tutte le giornate di {esc(month_name(month))}, organizzate per gruppo, orario e corso.</p></div>'
            '<a class="bm364-back" href="/presenze-semplici">← Segna le presenze</a></div>' +form+stats+
            '<nav class="bm364-days" aria-label="Giornate di lezione">'+''.join(tabs)+'</nav>'+
            f'<h2>{esc(day_name(day))} · Elenco delle atlete</h2>'+(''.join(sections) if sections else empty)+info+'</main>')
    return CSS + body


def family_rows(conn, tid, month):
    return [dict(r) for r in conn.execute('''
       SELECT p.data,p.stato,c.nome AS corso,COALESCE(c.orario,'') AS orario
       FROM presenze p LEFT JOIN corsi c ON c.id=p.corso_id
       WHERE p.tesserato_id=? AND p.data>=? AND p.data<?
       ORDER BY p.data DESC,c.nome COLLATE NOCASE,p.id
    ''', (tid,month.isoformat(),next_month(month).isoformat())).fetchall()]


def render_family(month, athlete, entries, token):
    present=sum(r['stato']=='presente' for r in entries)
    absent=sum(r['stato'] in ('assente','giustificato') for r in entries)
    recorded=present+absent
    rate=round(present*100/recorded) if recorded else 0
    days=defaultdict(list)
    for r in entries:
        try:d=date.fromisoformat(str(r['data'])[:10])
        except ValueError:continue
        days[d].append(r)
    tiles=[]
    for d, rows in sorted(days.items(),reverse=True):
        status=[]
        for r in rows:
            state=str(r['stato'] or '').lower()
            label='Presente' if state=='presente' else ('Giustificata' if state=='giustificato' else ('Assente' if state=='assente' else 'Da verificare'))
            cls='yes' if state=='presente' else ('no' if state in ('assente','giustificato') else 'maybe')
            subtitle=' · '.join(x for x in (str(r['corso'] or 'Corso'),str(r['orario'] or '')) if x)
            status.append(f'<div class="bm364-line"><div><strong>{esc(subtitle)}</strong></div><span class="bm364-pill {cls}">{label}</span></div>')
        tiles.append(f'<article class="bm364-family-day"><div class="bm364-family-date"><span>{esc(WEEKDAYS[d.weekday()].upper())}</span><strong>{d.day}</strong></div><div class="bm364-family-day-body">'+''.join(status)+'</div></article>')
    safe_token=quote(str(token),safe='')
    route=f'/app-tesserato/{safe_token}/presenze'
    month_form=month_selector(month,route)
    empty='<div class="bm364-family-empty">Nessuna presenza ancora registrata per questo mese. Le giornate non registrate non vengono considerate assenze.</div>'
    chart = (f'<div class="bm364-donut" style="--pct:{rate}%" role="img" aria-label="{rate} per cento di presenze registrate"><span><b>{rate}%</b><small>frequenza</small></span></div>')
    content = (f'<div class="bm364-family-shell"><main class="bm364-family-main"><a class="bm364-family-back" href="/app-tesserato/{safe_token}">← Torna alla mia area</a>'
       f'<div class="bm364-family-intro"><small>BODYMIND · IL MIO PERCORSO</small><h1>Le mie presenze</h1><p>{esc(athlete)} · {esc(month_name(month))}</p></div>'+
       month_form+f'<section class="bm364-family-summary">{chart}<div><h2>Il tuo mese in volo</h2><p><strong>{present}</strong> presenze registrate</p><p><strong>{absent}</strong> assenze o giustificazioni registrate</p><small>La percentuale considera soltanto le lezioni effettivamente registrate. Non indica la frequenza alle lezioni ancora da segnare.</small></div></section>'+
       '<h2 class="bm364-family-days-title">Le mie giornate</h2>'+(''.join(tiles) if tiles else empty)+
       '</main></div>')
    return '<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"><title>Presenze · BodyMind</title>'+CSS+'</head><body class="bm364-family-body">'+content+'</body></html>'


CSS = '''<style id="bm364-styles">
.bm364-wrap,.bm364-wrap *, .bm364-family-shell,.bm364-family-shell *{box-sizing:border-box}
.bm364-wrap{max-width:1180px;margin:20px auto 80px;padding:22px;color:#f0f4ff;font:inherit}
.bm364-wrap h1,.bm364-wrap h2,.bm364-wrap h3{color:#fff}
.bm364-top{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}
.bm364-top h1{font-size:clamp(27px,4vw,40px);margin:8px 0}.bm364-top p{color:#a9bdcd;margin:0 0 24px}
.bm364-eyebrow{letter-spacing:.17em;font-weight:750;font-size:12px;color:#9cc8fd}
.bm364-back,.bm364-family-back{color:#ddeaff!important;text-decoration:none;border:1px solid #6382a9;border-radius:99px;padding:11px 18px;display:inline-flex;width:max-content}
.bm364-month-form{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:18px;border-radius:18px;background:#13283e;border:1px solid #36536f;margin:16px 0}
.bm364-month-form label{font-weight:750}.bm364-month-form select{min-height:44px;background:#f9fbff!important;color:#19283c!important;border-radius:10px;border:1px solid #96aec6;padding:8px 12px;min-width:180px;max-width:100%;font-size:16px}
.bm364-month-form button{min-height:44px;background:#4d88d5;color:#fff;border:none;padding:10px 18px;border-radius:11px;font-weight:750;cursor:pointer}
.bm364-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:18px 0 20px}
.bm364-metrics>div{background:linear-gradient(135deg,#142943,#213952);border:1px solid #36526d;border-radius:15px;padding:17px}.bm364-metrics strong{display:block;color:#fff;font-size:29px}.bm364-metrics small{color:#c4d5e8}
.bm364-days{display:grid;grid-template-columns:repeat(auto-fit,minmax(128px,1fr));gap:9px;margin:22px 0}.bm364-day{color:#d4e3f8!important;background:#13263e;border:1px solid #39506b;border-radius:13px;padding:13px 11px;text-decoration:none;display:flex;flex-direction:column;gap:5px}.bm364-day strong{font-size:15px}.bm364-day small{color:#a9c5de}.bm364-day.selected{border-color:#78bcf7;background:#255085;box-shadow:inset 0 0 0 1px #78bcf7}
.bm364-admin>h2{font-size:22px;margin:26px 0 14px}.bm364-course{border:1px solid #37536c;background:#11263c;border-radius:16px;padding:18px;margin-bottom:12px}.bm364-course header{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center}.bm364-course header small{color:#a4c6e6}.bm364-course h3{margin:3px 0 10px;font-size:20px}.bm364-course header a{color:#def4ff!important;background:#1e5173;padding:10px 14px;text-decoration:none;border-radius:10px}
.bm364-course ul{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));list-style:none;margin:10px 0 0;padding:0;gap:7px}.bm364-athlete{display:flex;align-items:center;justify-content:space-between;gap:7px;padding:11px 12px;border-radius:11px;border:1px solid #36516a;background:#172f49;font-size:14px}.bm364-athlete span{overflow-wrap:anywhere}.bm364-athlete em{font-style:normal;font-size:11px;white-space:nowrap}.bm364-athlete.yes em{color:#a3f6c5}.bm364-athlete.no em{color:#ffd2b1}.bm364-athlete.maybe em{color:#fcd875}.bm364-empty,.bm364-note{padding:20px;border:1px solid #425a71;border-radius:16px;background:#11253b;color:#c8d7e8}
.bm364-family-body{margin:0;background:#071526;color:#e9f1ff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}.bm364-family-shell{min-height:100dvh;background:radial-gradient(ellipse at 80% 0,#334c83aa,transparent 48%),radial-gradient(ellipse at 10% 40%,#114b5f6b,transparent 47%),#071526}.bm364-family-main{max-width:840px;padding:28px clamp(14px,4vw,32px) 100px;margin:auto}.bm364-family-back{margin:10px 0 30px}.bm364-family-intro small{color:#b7d8fd;font-weight:700;letter-spacing:.14em;font-size:11px}.bm364-family-intro h1{font-size:clamp(34px,5vw,52px);margin:12px 0;color:#fff}.bm364-family-intro p{color:#c9def7;font-size:17px}
.bm364-family-summary{display:flex;align-items:center;gap:27px;padding:24px;border:1px solid #587193;border-radius:23px;background:linear-gradient(120deg,#1f314bb8,#15263e);margin:24px 0}.bm364-family-summary h2{margin:4px 0 12px;font-size:22px}.bm364-family-summary p{margin:8px 0;color:#d5e5f6}.bm364-family-summary p strong{color:#fff;font-size:21px}.bm364-family-summary small{color:#9fbad7;font-size:12px;line-height:1.5;display:block;margin-top:8px}
.bm364-donut{--pct:0%;border-radius:50%;flex:none;width:150px;aspect-ratio:1;display:grid;place-items:center;background:conic-gradient(#92f6ca var(--pct),#314966 0);box-shadow:0 0 25px #55adcb20}.bm364-donut span{width:118px;aspect-ratio:1;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-direction:column;background:#12253c}.bm364-donut b{font-size:28px}.bm364-donut small{color:#adc6dd;margin:0}
.bm364-family-days-title{font-size:22px;margin-top:28px;color:#fff}.bm364-family-day{display:flex;gap:15px;border:1px solid #2c5270;border-radius:18px;padding:14px;margin-bottom:12px;background:#10253c}.bm364-family-date{min-width:66px;border-radius:12px;background:#234667;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:10px}.bm364-family-date span{font-size:12px;letter-spacing:.12em;color:#bcd7f5}.bm364-family-date strong{font-size:27px;color:#fff}.bm364-family-day-body{min-width:0;width:100%}.bm364-line{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:10px 2px;border-bottom:1px solid #25435e}.bm364-line:last-child{border-bottom:0}.bm364-line strong{font-size:14px;line-height:1.4;overflow-wrap:anywhere}.bm364-pill{padding:6px 11px;border-radius:30px;font-size:12px;font-weight:750;flex:none}.bm364-pill.yes{color:#b4fbd1;background:#164c3a}.bm364-pill.no{color:#ffe4d1;background:#6b3829}.bm364-pill.maybe{color:#fff1a9;background:#614a20}.bm364-family-empty{padding:30px;border:1px dashed #53718a;border-radius:18px;color:#c5d8ef;line-height:1.6}
@media(max-width:640px){.bm364-wrap{padding:10px 8px 80px}.bm364-metrics{grid-template-columns:1fr 1fr}.bm364-metrics>div:last-child{grid-column:1/-1}.bm364-days{grid-template-columns:repeat(3,minmax(0,1fr))}.bm364-day{padding:10px 7px}.bm364-day strong{font-size:13px}.bm364-family-summary{padding:17px;gap:15px}.bm364-donut{width:108px}.bm364-donut span{width:82px}.bm364-donut b{font-size:22px}.bm364-family-summary h2{font-size:18px}.bm364-line{align-items:flex-start;flex-direction:column;gap:5px}}
@media print{.bm364-back,.bm364-days,.bm364-month-form,.bm364-course header a{display:none!important}.bm364-wrap,.bm364-course{color:#000!important;background:#fff!important}.bm364-course h3,.bm364-wrap h1,.bm364-wrap h2{color:#000!important}}
</style>'''


def install(app):
    from asd_app.core import auth, can_access_section, layout
    import asd_app.a309_presence_rapid as rapid
    import asd_app.routes_bodymind_final as portal
    if hashlib.sha256(Path(rapid.__file__).read_bytes()).hexdigest()!=EXPECTED_ATTENDANCE_SHA:
        raise RuntimeError("A364 attendance source drift: refusing feature install")
    if hashlib.sha256(Path(portal.__file__).read_bytes()).hexdigest()!=EXPECTED_PORTAL_SHA:
        raise RuntimeError("A364 family source drift: refusing feature install")

    @app.get('/presenze/mensile', endpoint='bm364_admin_monthly')
    def admin_monthly():
        if not auth(): return redirect('/login')
        if not can_access_section('presenze'): abort(403)
        try:
            month=parse_month(request.args.get('mese'))
            days=lesson_days(month)
            selected=request.args.get('giorno')
            if selected:
                d=date.fromisoformat(selected)
                if d not in days: abort(400)
            else:
                past=[d for d in days if d<=date.today()]
                d=past[-1] if past else days[0]
        except ValueError:
            abort(400)
        conn=read_connection()
        try:
            rows,skipped=admin_month_rows(conn,month)
            explicit=course_categories(conn)
        finally:
            conn.close()
        response=make_response(layout(render_admin(month,d,rows,skipped,explicit)))
        response.headers['Cache-Control']='private, no-store'
        response.headers['X-BodyMind-Attendance-Release']=RELEASE
        return response

    @app.get('/app-tesserato/<token>/presenze', endpoint='bm364_family_monthly')
    def family_monthly(token):
        try:month=parse_month(request.args.get('mese'))
        except ValueError:abort(400)
        conn=read_connection()
        try:
            athlete=conn.execute('SELECT id,nome,cognome FROM tesserati WHERE online_token=?',(token,)).fetchone()
            if athlete is None: abort(404)
            tid=int(athlete['id'])
            rows=family_rows(conn,tid,month)
            name=' '.join((str(athlete['nome'] or ''),str(athlete['cognome'] or ''))).strip()
        finally:
            conn.close()
        response=make_response(render_family(month,name,rows,token))
        response.headers['Cache-Control']='private, no-store'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-BodyMind-Attendance-Release']=RELEASE
        return response

    def add_links(response):
        if request.method!='GET' or response.status_code!=200 or response.mimetype!='text/html' or response.direct_passthrough:
            return response
        if request.endpoint not in ('bodymind_r123_presenze_semplici','app_tesserato') and request.path!='/presenze-semplici':
            return response
        page=response.get_data(as_text=True)
        if 'bm364-entry-link' in page:return response
        if request.path=='/presenze-semplici':
            old='<main class="a309-page">'
            if page.count(old)==1:
                add='<div id="bm364-entry-link" style="margin:12px 0 18px;padding:14px;border-radius:14px;border:1px solid #78baf9;background:#173956;color:#fff"><a href="/presenze/mensile" style="color:#fff;text-decoration:none;font-weight:750">📅 Apri registro mensile · Lunedì e mercoledì →</a></div>'
                page=page.replace(old,old+add,1)
        elif request.endpoint=='app_tesserato':
            token=(request.view_args or {}).get('token')
            old='<section class="section" id="corsi">'
            if token and page.count(old)==1:
                link='/app-tesserato/'+quote(str(token),safe='')+'/presenze'
                add=(f'<section id="bm364-entry-link" aria-label="Storico presenze" style="margin:24px 0;padding:23px;border:1px solid #4b7192;background:linear-gradient(115deg,#19344b,#153354);border-radius:22px;color:#eaf3ff">'
                     f'<small style="letter-spacing:.12em;color:#acd6ff">IL MIO PERCORSO</small><h2 style="margin:9px 0;color:#fff;font-size:22px">Le mie presenze, mese per mese</h2>'
                     f'<p style="color:#c2daed">Scopri le giornate frequentate e il grafico del tuo mese.</p><a href="{esc(link)}" style="color:#071a2b;background:#b9f4df;font-weight:800;padding:12px 16px;border-radius:12px;text-decoration:none;display:inline-block">Apri le mie presenze →</a></section>')
                page=page.replace(old,add+old,1)
        else:return response
        response.set_data(page)
        response.headers['Cache-Control']='private, no-store'
        return response

    # Flask runs after_request callbacks in reverse registration order. Placing this
    # first means it runs *after* the A362 family clean-up and any old injectors.
    app.after_request_funcs.setdefault(None,[]).insert(0,add_links)
    print('BODYMIND A364 MONTHLY ATTENDANCE READY — readonly database, existing A309 POST untouched',flush=True)
