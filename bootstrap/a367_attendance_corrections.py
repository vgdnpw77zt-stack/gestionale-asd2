"""A367: attendance correction console for administrators only.

Adds per-record status correction or audited deletion, never bulk month deletion.
Maintains canonical presenze table and reconciles package_usages on each change.
A364 monthly view and A365 family graph read those same rows; no double ledgers.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
import sqlite3
from urllib.parse import urlencode

from flask import abort, make_response, redirect, request
from a364_monthly_attendance import esc, month_name, next_month, parse_month

STATES = {'presente': 'Presente', 'assente': 'Assente', 'giustificato': 'Giustificata'}
AUDIT_DDL = """CREATE TABLE IF NOT EXISTS bodymind_a367_attendance_corrections (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  presenza_id INTEGER NOT NULL,
  tesserato_id INTEGER NOT NULL,
  corso_id INTEGER NOT NULL,
  data TEXT NOT NULL,
  operazione TEXT NOT NULL CHECK (operazione IN ('modifica','elimina')),
  precedente_json TEXT NOT NULL,
  nuovo_stato TEXT,
  motivo TEXT NOT NULL,
  operatore TEXT NOT NULL,
  creato_il TEXT NOT NULL
)"""


def month_rows(conn, month):
    """Unaltered rows including historical statuses and original course assignment."""
    return conn.execute("""
      SELECT p.id,p.tesserato_id,p.corso_id,p.data,p.stato,p.note,
             p.updated_at,p.chiusa,
             t.nome,t.cognome,c.nome AS corso,COALESCE(c.orario,'') AS orario
      FROM presenze p
      LEFT JOIN tesserati t ON t.id=p.tesserato_id
      LEFT JOIN corsi c ON c.id=p.corso_id
      WHERE p.data>=? AND p.data<?
      ORDER BY p.data DESC,c.orario,c.nome,t.cognome,t.nome,p.id
    """,(month.isoformat(),next_month(month).isoformat())).fetchall()


def apply_change(conn, *, presenza_id, expected_updated_at, operation, new_status,
                 month, reason, actor, reconciler):
    """One strictly scoped change and its audit committed atomically."""
    if operation not in ('modifica','elimina'):
        raise ValueError('Operazione non riconosciuta')
    if operation=='modifica' and new_status not in STATES:
        raise ValueError('Stato non riconosciuto')
    if not isinstance(presenza_id,int) or presenza_id < 1:
        raise ValueError('Registrazione non valida')
    reason=(reason or '').strip()
    if len(reason)<6 or len(reason)>300:
        raise ValueError('Inserisci una motivazione da 6 a 300 caratteri')
    actor=(actor or '').strip()[:100] or 'Amministratore'
    now=datetime.now(timezone.utc).isoformat(timespec='seconds')
    try:
        conn.execute('BEGIN IMMEDIATE')
        row=conn.execute('SELECT * FROM presenze WHERE id=?',(presenza_id,)).fetchone()
        if row is None:
            raise ValueError('Presenza già cancellata o inesistente')
        previous=dict(row)
        if str(previous['data'])[:7]!=month.strftime('%Y-%m'):
            raise ValueError('Mese diverso da quello della presenza')
        if int(previous.get('chiusa') or 0):
            raise ValueError('Registrazione chiusa: chiedere la riapertura amministrativa')
        if str(previous.get('updated_at') or '') != str(expected_updated_at or ''):
            raise ValueError('Registrazione cambiata da un altro operatore: aggiorna la pagina')
        if operation=='modifica' and previous['stato']==new_status:
            raise ValueError('Lo stato è già impostato così')
        conn.execute(AUDIT_DDL)
        if operation=='elimina':
            result=conn.execute('DELETE FROM presenze WHERE id=?',(presenza_id,))
            if result.rowcount!=1:
                raise RuntimeError('Cancellazione non confermata')
        else:
            result=conn.execute('UPDATE presenze SET stato=?,updated_at=? WHERE id=?',
                                (new_status,now,presenza_id))
            if result.rowcount!=1:
                raise RuntimeError('Modifica non confermata')
        conn.execute("""INSERT INTO bodymind_a367_attendance_corrections
              (presenza_id,tesserato_id,corso_id,data,operazione,
               precedente_json,nuovo_stato,motivo,operatore,creato_il)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
              (presenza_id,int(previous['tesserato_id']),int(previous['corso_id']),previous['data'],
               operation,json.dumps(previous,ensure_ascii=False,sort_keys=True),
               new_status if operation=='modifica' else None,reason,actor,now))
        # Reconcile pack usages by the *remaining* real presences for this course/date.
        active={int(r[0]) for r in conn.execute(
            "SELECT tesserato_id FROM presenze WHERE corso_id=? AND data=? AND stato='presente'",
            (int(previous['corso_id']),previous['data'])).fetchall()}
        reconciler(conn.cursor(),int(previous['corso_id']),previous['data'],active)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


CSS = """<style id="bm367-style">
.bm367{max-width:1050px;margin:20px auto 80px;padding:14px;color:#e7efff}
.bm367 *{box-sizing:border-box}.bm367 h1{color:#fff;font-size:clamp(26px,5vw,38px)}
.bm367 p{color:#bdd2e8;line-height:1.55}.bm367 a{color:#a9dcff!important}
.bm367-head{display:flex;gap:12px;flex-wrap:wrap;align-items:center;justify-content:space-between}
.bm367-period{display:flex;flex-wrap:wrap;gap:8px;align-items:center;background:#10263e;border:1px solid #395a7c;border-radius:16px;padding:14px;margin:18px 0}
.bm367 :is(input,select,textarea,button){font-size:16px;min-height:42px;border-radius:9px;padding:9px;color:#fff;background:#112f4a;border:1px solid #56799f}
.bm367 button{cursor:pointer;background:#1e6190;font-weight:750}.bm367 .danger{background:#762b39;border-color:#e1a0a0}
.bm367 .danger:disabled{opacity:.5}.bm367 details{background:#122940;border:1px solid #385877;border-radius:16px;margin:11px 0;padding:12px}
.bm367 summary{cursor:pointer;font-size:18px;font-weight:800;padding:9px;list-style-position:inside}
.bm367-record{padding:15px 12px;border-top:1px solid #31516e}
.bm367-record strong{display:block;color:#fff;margin-bottom:4px}.bm367-record small{display:block;color:#b5cbe3}
.bm367-record form{margin:12px 0 0;display:flex;flex-wrap:wrap;gap:9px;align-items:end}
.bm367-record form label{display:flex;flex-direction:column;gap:5px;min-width:130px;flex:1}
.bm367-record form textarea{min-height:42px;resize:vertical;flex:2}.bm367-record form button{white-space:nowrap}
.bm367-info{border:1px solid #567ca3;background:#10293f;border-radius:14px;padding:15px}
.bm367-locked{color:#ffd8a8!important}
@media(max-width:620px){.bm367{padding:8px}.bm367-record form label{min-width:100%}.bm367-record form button{width:100%}}
</style>"""


def render_console(rows, month, csrf, saved):
    grouped=defaultdict(list)
    for r in rows:
        grouped[str(r['data'])].append(r)
    chunks=[]
    for day, daily in grouped.items():
        persons=[]
        for r in daily:
            who=f"{r['cognome'] or ''} {r['nome'] or ''}".strip()
            course=f"{r['corso'] or 'Corso non disponibile'} · {r['orario'] or 'orario non indicato'}"
            rid=int(r['id'])
            etag=esc(r['updated_at'] or '')
            locked=bool(r['chiusa'])
            choices=''.join(f'<option value="{k}" {"selected" if r["stato"]==k else ""}>{v}</option>'
                            for k,v in STATES.items())
            common=f'<input type="hidden" name="record_id" value="{rid}"><input type="hidden" name="mese" value="{month:%Y-%m}"><input type="hidden" name="updated_at" value="{etag}">{csrf}'
            forms=('<p class="bm367-locked">Giornata chiusa: modifiche disabilitate</p>' if locked else
                   f'<form method="post" action="/presenze/storico/azione">{common}<input type="hidden" name="operazione" value="modifica">'
                   f'<label>Stato<select name="nuovo_stato">{choices}</select></label>'
                   f'<label>Motivazione<input type="text" name="motivo" required minlength="6" maxlength="300" placeholder="Correzione presenza"></label>'
                   f'<button type="submit">Salva correzione</button></form>'
                   f'<form method="post" action="/presenze/storico/azione" onsubmit="return confirm(\'Eliminare SOLO questa registrazione di presenza? L’operazione sarà tracciata. Confermi?\')">{common}'
                   f'<input type="hidden" name="operazione" value="elimina">'
                   f'<label>Motivo eliminazione<input type="text" name="motivo" required minlength="6" maxlength="300" placeholder="Registrata per errore"></label>'
                   f'<button type="submit" class="danger">Elimina questa registrazione</button></form>')
            persons.append(f'<article class="bm367-record"><strong>{esc(who)}</strong><small>{esc(course)}</small>'
                           f'<small>Stato: {esc(STATES.get(r["stato"],str(r["stato"])))}</small>{forms}</article>')
        chunks.append(f'<details><summary>{esc(day)} · {len(daily)} registrazioni</summary>{"".join(persons)}</details>')
    banner='<p class="bm367-info" role="status">Correzione salvata. Il registro mensile e la famiglia leggeranno i nuovi dati.</p>' if saved else ''
    return CSS + f'''<main class="bm367"><div class="bm367-head"><div><small>BODYMIND · SEGRETERIA</small><h1>Correzioni presenze</h1></div>
      <a href="/presenze/mensile?mese={month:%Y-%m}">← Torna al registro mensile</a></div>
      <p class="bm367-info">Puoi correggere o eliminare una singola registrazione, anche di ottobre. Non vengono cancellati mesi interi. Ogni intervento richiede una motivazione, resta archiviato e aggiorna gli eventuali ingressi del pacchetto.</p>
      <form method="get" action="/presenze/storico" class="bm367-period">
      <label>Mese <input type="month" name="mese" value="{month:%Y-%m}" required></label>
      <button type="submit">Apri mese</button></form>
      {banner}<h2>{esc(month_name(month))} · {len(rows)} registrazioni</h2>
      {''.join(chunks) if chunks else '<p>Nessuna registrazione per il mese scelto.</p>'}</main>'''


def install(app):
    from asd_app.core import (admin_required, auth, can_access_section,
                              csrf_input, current_username, db, layout,
                              reconcile_package_usages)
    route_set={r.rule for r in app.url_map.iter_rules()}
    if '/presenze/storico' in route_set or '/presenze/storico/azione' in route_set:
        raise RuntimeError('A367 route collision: refusing installation')

    @app.get('/presenze/storico', endpoint='bm367_attendance_console')
    @admin_required
    def attendance_console():
        try:
            month=parse_month(request.args.get('mese'))
        except ValueError:
            abort(400)
        conn=db()
        try:
            rows=month_rows(conn,month)
        finally:
            conn.close()
        response=make_response(layout(render_console(rows,month,csrf_input(),request.args.get('salvato')=='1')))
        response.headers['Cache-Control']='private, no-store'
        response.headers['X-BodyMind-Attendance-Corrections']='A367'
        return response

    @app.post('/presenze/storico/azione', endpoint='bm367_attendance_action')
    @admin_required
    def attendance_action():
        try:
            month=parse_month(request.form.get('mese'))
            rid=int(request.form.get('record_id') or 0)
            conn=db()
            try:
                apply_change(conn,presenza_id=rid,
                            expected_updated_at=request.form.get('updated_at'),
                            operation=request.form.get('operazione'),
                            new_status=request.form.get('nuovo_stato'),
                            month=month,reason=request.form.get('motivo'),
                            actor=current_username(),
                            reconciler=reconcile_package_usages)
            finally:
                conn.close()
        except (ValueError,sqlite3.DatabaseError,RuntimeError) as exc:
            message=esc(str(exc))
            return layout(f'<main class="bm367">{CSS}<h1>Modifica non eseguita</h1><p>{message}</p><a href="/presenze/storico">Torna allo storico</a></main>'),400
        return redirect('/presenze/storico?'+urlencode({'mese':month.strftime('%Y-%m'),'salvato':'1'}),303)

    def add_admin_link(response):
        if request.endpoint!='bm364_admin_monthly' or request.method!='GET' or response.status_code!=200:
            return response
        page=response.get_data(as_text=True)
        anchor='<main class="bm364-wrap bm364-admin">'
        if page.count(anchor)!=1 or 'bm367-correct-link' in page:
            return response
        try:month=parse_month(request.args.get('mese'))
        except ValueError:return response
        link=f'<div id="bm367-correct-link" style="padding:9px 10px 16px"><a href="/presenze/storico?mese={month:%Y-%m}" style="display:inline-block;padding:12px 17px;border:1px solid #92c4ec;border-radius:12px;color:#e3f5ff;text-decoration:none;background:#174666">✎ Modifica o elimina presenze del mese</a></div>'
        response.set_data(page.replace(anchor,anchor+link,1))
        response.headers['Cache-Control']='private, no-store'
        return response

    # Executes after core's normal render: only the admin monthly page is touched.
    app.after_request_funcs.setdefault(None,[]).insert(0,add_admin_link)
    print('BODYMIND A367 ATTENDANCE CORRECTIONS READY — admin only, per-record audited writes',flush=True)
