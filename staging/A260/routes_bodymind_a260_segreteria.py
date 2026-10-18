# -*- coding: utf-8 -*-
"""A260 staging: dashboard di segreteria con 3 stati e azioni reali.

GET di sola presentazione: nessuna mutazione di stato, nessun reminder inviato.
Non sostituisce la dashboard fino a collaudo privato end-to-end.
"""
from __future__ import annotations

from .core import app, admin_required, db, e, layout, get_dashboard_metrics, current_month_year, request, _active_tesserati_rows


def _safe_local_url(raw, fallback='/tesserati'):
    text=str(raw or '').strip()
    return text if text.startswith('/') and not text.startswith('//') and not any(x in text for x in ('\r','\n','\\')) else fallback


def _group(alert):
    severity=str(alert.get('severity') or '').strip().lower()
    meta=alert.get('meta') or {}
    if severity=='critical' or (isinstance(meta,dict) and bool(meta.get('blocker'))):
        return 'urgent'
    return 'upcoming'


def summarize(metrics, members):
    alerts=[a for a in (metrics.get('alerts') or []) if isinstance(a,dict) and str(a.get('status') or 'open') not in ('archiviato','resolved','closed')]
    urgent=[a for a in alerts if _group(a)=='urgent']
    upcoming=[a for a in alerts if _group(a)=='upcoming']
    alerted=set()
    for a in alerts:
        meta=a.get('meta') or {}
        raw=(meta.get('tesserato_id') if isinstance(meta,dict) else None) or a.get('tesserato_id')
        try: alerted.add(int(raw))
        except (ValueError,TypeError): pass
    # La categoria OK si riferisce SOLO ai tesserati attivi senza avvisi nel modello attuale.
    clean=[r for r in members if int(r['id']) not in alerted]
    return urgent, upcoming, clean


def _row(alert):
    title=e(str(alert.get('title') or 'Azione da completare'))
    person=e(str(alert.get('person_name') or 'Segreteria'))
    detail=e(str(alert.get('description') or '')[:230])
    url=e(_safe_local_url(alert.get('primary_action_url')))
    action=e(str(alert.get('primary_action_label') or 'Apri scheda'))
    return f"<article class='a260-line'><div><strong>{title}</strong><span>{person}</span><p>{detail}</p></div><a href='{url}'>{action} →</a></article>"


def _safe_period(value,default,low,high):
    try: value=int(value)
    except (ValueError,TypeError):return default
    return value if low<=value<=high else default


@app.get('/segreteria/oggi')
@admin_required
def a260_segreteria_oggi():
    mm,yy=current_month_year()
    mm=_safe_period(request.args.get('mese'),mm,1,12)
    yy=_safe_period(request.args.get('anno'),yy,2020,2100)
    metrics=get_dashboard_metrics(mm,yy)
    conn=db()
    try:
        members=_active_tesserati_rows(conn)
    finally:
        conn.close()
    urgent, upcoming, clean=summarize(metrics,members)
    urgent_markup=''.join(_row(a) for a in urgent[:12]) or "<p class='a260-empty'>Nessuna criticità urgente in questo periodo.</p>"
    upcoming_markup=''.join(_row(a) for a in upcoming[:12]) or "<p class='a260-empty'>Nessuna altra scadenza segnalata.</p>"
    clean_names=''.join(f"<span>{e(str(p['cognome'] or '')+' '+str(p['nome'] or ''))}</span>" for p in clean[:15])
    more=('<span>e altre '+str(len(clean)-15)+' schede</span>' if len(clean)>15 else '')
    # Indicatore onesto: il controllo non sostituisce le verifiche del dossier individuale.
    return layout(f"""
<style id='a260-secretariat'>
.a260-page {{max-width:1100px;margin:22px auto 90px;padding:0 12px;color:#eff3fa;font:15px/1.5 system-ui,-apple-system,sans-serif}}
.a260-page * {{box-sizing:border-box}}
.a260-intro {{display:flex;justify-content:space-between;align-items:end;gap:16px;flex-wrap:wrap;padding:22px 24px;background:#172338;border:1px solid #334763;border-radius:20px}}
.a260-eyebrow {{text-transform:uppercase;letter-spacing:.13em;color:#b9cfed;font-size:11px;font-weight:800}}
.a260-intro h1 {{font-size:clamp(25px,3vw,34px);line-height:1.15;letter-spacing:-.025em;margin:7px 0}}
.a260-intro p {{margin:0;color:#c5d0df;max-width:560px}}
.a260-links {{display:flex;gap:8px;flex-wrap:wrap}}
.a260-links a {{text-decoration:none;color:#eaf2fc!important;background:#253c59;border:1px solid #4a6484;border-radius:11px;padding:10px 13px;min-height:42px;font-weight:750;font-size:13px}}
.a260-links a:first-child {{background:#26608c}}
.a260-grid {{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:13px;margin-top:16px}}
.a260-card {{min-width:0;background:#1a2431;border:1px solid #3a4a5d;border-radius:18px;padding:20px;box-shadow:none}}
.a260-title {{display:flex;align-items:center;gap:9px;font-size:15px;font-weight:800;margin:0}}
.a260-dot {{width:9px;height:9px;flex:0 0 9px;border-radius:50%;background:#b5c0d3}}
.a260-card.urgent .a260-dot {{background:#f1787c}}.a260-card.upcoming .a260-dot {{background:#eabf75}}.a260-card.ok .a260-dot {{background:#81c6a6}}
.a260-count {{font-size:36px;font-weight:780;letter-spacing:-.04em;line-height:1.2;margin:9px 0 4px}}
.a260-hint {{font-size:12px;color:#bdc8d7;margin:0}}
.a260-body {{display:grid;grid-template-columns:1fr 1fr;gap:13px;margin-top:13px}}
.a260-panel {{min-width:0;background:#1a2431;border:1px solid #3a4a5d;border-radius:18px;padding:17px}}
.a260-panel h2 {{font-size:17px;margin:0 0 10px}}
.a260-line {{display:flex;gap:12px;justify-content:space-between;align-items:center;padding:13px 0;border-bottom:1px solid #364459}}
.a260-line:last-child {{border:0}}
.a260-line strong {{display:block;font-size:13px;color:#f6f7fa}}
.a260-line span {{display:block;font-size:12px;color:#b8cbe4;margin-top:2px}}
.a260-line p {{font-size:12px;line-height:1.4;color:#bec7d5;margin:4px 0 0}}
.a260-line a {{text-decoration:none;color:#d6edff!important;white-space:nowrap;background:#273e56;border:1px solid #466683;padding:9px 10px;border-radius:10px;font-size:12px;font-weight:750}}
.a260-empty {{font-size:13px;color:#b7c6d6;margin:9px 0}}
.a260-clear {{margin-top:13px;background:#192533;border:1px solid #35495d;border-radius:17px;padding:15px 18px}}
.a260-clear h2 {{font-size:16px;margin:0 0 8px}}
.a260-tags {{display:flex;flex-wrap:wrap;gap:6px}}
.a260-tags span {{font-size:12px;border:1px solid #4b615d;background:#223b36;padding:5px 9px;border-radius:99px}}
.a260-note {{font-size:12px;color:#aabbd0;margin-top:10px}}
@media(max-width:850px){{.a260-grid{{grid-template-columns:1fr 1fr 1fr}}.a260-body{{grid-template-columns:1fr}}}}
@media(max-width:620px){{.a260-page{{padding:0 9px;margin:7px auto 65px}}.a260-intro{{padding:15px}}.a260-intro h1{{font-size:26px}}.a260-grid{{gap:7px}}.a260-card{{padding:11px;border-radius:13px}}.a260-title{{font-size:12px;gap:5px}}.a260-count{{font-size:27px}}.a260-hint{{font-size:11px;line-height:1.25}}.a260-body{{gap:9px}}.a260-panel{{padding:13px}}.a260-line{{align-items:start;flex-direction:column;gap:7px}}.a260-line a{{width:100%;text-align:center}}}}
</style>
<main class='a260-page'>
<header class='a260-intro'><div><div class='a260-eyebrow'>BodyMind · Segreteria</div><h1>La giornata, senza complicazioni.</h1>
<p>Apri una scheda, risolvi un problema o registra una quota. Il resto rimane nel sistema.</p></div>
<nav class='a260-links'><a href='/quote-incassi/incasso-rapido'>+ Registra contanti</a><a href='/documenti/da-verificare'>Documenti</a><a href='/motore-automazioni'>Automazioni</a></nav></header>
<section class='a260-grid' aria-label='Stato attività'>
<div class='a260-card urgent'><p class='a260-title'><i class='a260-dot' aria-hidden='true'></i>Da fare</p><div class='a260-count'>{len(urgent)}</div><p class='a260-hint'>Criticità che richiedono attenzione</p></div>
<div class='a260-card upcoming'><p class='a260-title'><i class='a260-dot' aria-hidden='true'></i>In scadenza</p><div class='a260-count'>{len(upcoming)}</div><p class='a260-hint'>Avvisi da gestire per tempo</p></div>
<div class='a260-card ok'><p class='a260-title'><i class='a260-dot' aria-hidden='true'></i>Tutto in regola</p><div class='a260-count'>{len(clean)}</div><p class='a260-hint'>Tesserati attivi senza avvisi</p></div></section>
<section class='a260-body'><div class='a260-panel'><h2>Da fare adesso</h2>{urgent_markup}</div>
<div class='a260-panel'><h2>Prossime scadenze</h2>{upcoming_markup}</div></section>
<section class='a260-clear'><h2>Tutto in regola · {len(clean)} {'tesserato' if len(clean)==1 else 'tesserati'}</h2><div class='a260-tags'>{clean_names}{more}</div>
<p class='a260-note'>Stato basato sugli avvisi registrati nel gestionale per {mm:02d}/{yy}; non sostituisce il controllo individuale dei documenti.</p></section>
</main>
""")