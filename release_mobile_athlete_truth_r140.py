from __future__ import annotations
import py_compile, shutil
from pathlib import Path

APP=Path('/data/top2_app')
BACK=Path('/data/release_backups/20261004_r140_mobile_athlete_truth')
BACK.mkdir(parents=True,exist_ok=True)

matches=[]
for p in (APP/'asd_app').rglob('*.py'):
    try:s=p.read_text(encoding='utf-8',errors='replace')
    except Exception:continue
    if 'def fix24_mobile_atlete' in s and 'Schede e controlli essenziali.' in s:
        matches.append((p,s))
if len(matches)!=1:
    raise RuntimeError('R140 expected one mobile athlete list source, found '+repr([str(x[0]) for x in matches]))

p,s=matches[0]
if 'BODYMIND_R140_MOBILE_ATHLETE_TRUTH' not in s:
    start=s.find('def fix24_mobile_atlete():')
    end=s.find('\n@app.',start)
    if start<0: raise RuntimeError('R140 function start missing')
    if end<0: end=len(s)
    old=s[start:end]
    new=r'''def fix24_mobile_atlete():
    # BODYMIND_R140_MOBILE_ATHLETE_TRUTH
    from datetime import date as _date, datetime as _datetime
    from pathlib import Path as _Path
    q=(request.args.get('q') or '').strip()
    cert_filter=(request.args.get('cert') or '').strip().lower()=='alert'
    today=_date.today(); month=today.month; year=today.year; season=year if month>=7 else year-1

    def _file_exists(filename):
        raw=_Path(str(filename or '').strip())
        roots=[_Path('/data/tenants/default/media'),_Path('/data/top2_app/user_static'),_Path('/data/top2_app/static'),_Path('/data/top2_app'),_Path('/data/tenants/default')]
        candidates=[raw] if raw.is_absolute() else [root/raw for root in roots]
        for fp in candidates:
            try:
                if fp.is_file(): return True
            except Exception: pass
        return False

    def _paid(row):
        try: st=(str(row['stato'] or '')+' '+str(row['online_status'] or '')).lower()
        except Exception: st=''
        if any(x in st for x in ('pending','attesa','cancel','annull','failed','fallit','rimbors')):
            return False
        try: amount=float(row['importo'] or 0)
        except Exception: amount=0
        try: dt=bool(row['data'])
        except Exception: dt=False
        return any(x in st for x in ('paid','pagat','saldat','complet','incassat')) or (dt and amount>0)

    conn=db()
    try:
        rows=conn.execute('SELECT * FROM tesserati ORDER BY TRIM(cognome) COLLATE NOCASE, TRIM(nome) COLLATE NOCASE').fetchall()
        items=[]
        for row in rows:
            hay=('%s %s %s %s'%(row['nome'] or '',row['cognome'] or '',row['corso'] or '',row['email'] or '')).lower()
            if q and q.lower() not in hay: continue
            tid=int(row['id'])

            mu_rows=conn.execute("""SELECT filename FROM documenti WHERE tesserato_id=? AND COALESCE(visibile,1)=1 AND (
                LOWER(COALESCE(doc_type,''))='modulo_unico_tesseramento' OR
                LOWER(COALESCE(categoria,'')) LIKE '%modulo iscrizione%' OR
                LOWER(COALESCE(titolo,'')) LIKE '%modulo unico%' OR
                LOWER(COALESCE(titolo,'')) LIKE '%domanda iscrizione%')""",(tid,)).fetchall()
            mu_ok=any(_file_exists(r['filename']) for r in mu_rows)

            med_rows=conn.execute("""SELECT filename FROM documenti WHERE tesserato_id=? AND COALESCE(visibile,1)=1
                AND LOWER(COALESCE(doc_type,''))='certificato_medico'
                AND LOWER(COALESCE(titolo,'')) NOT LIKE '%richiesta%'""",(tid,)).fetchall()
            med_file=any(_file_exists(r['filename']) for r in med_rows)
            expiry=str(row['certificato_scadenza'] or '').strip() if 'certificato_scadenza' in row.keys() else ''
            cert_ok=False; cert_reason='Certificato medico non caricato'
            if med_file and expiry:
                try:
                    exp=_datetime.strptime(expiry[:10],'%Y-%m-%d').date()
                    cert_ok=exp>=today
                    cert_reason=('Certificato valido fino al '+expiry[:10]) if cert_ok else ('Certificato scaduto il '+expiry[:10])
                except Exception:
                    cert_reason='Scadenza certificato da verificare'
            elif med_file:
                cert_reason='Certificato presente, scadenza da verificare'
            elif expiry:
                cert_reason='Scadenza presente ma file certificato assente'

            pays=conn.execute('SELECT * FROM pagamenti WHERE tesserato_id=? ORDER BY id DESC',(tid,)).fetchall()
            month_paid=any(_paid(x) and str(x['causale'] or '').lower()=='mensile' and int(x['mese'] or 0)==month and int(x['anno'] or 0)==year for x in pays)
            enroll_paid=any(_paid(x) and str(x['causale'] or '').lower() in ('iscrizione','tesseramento') and int(x['anno'] or 0)==season for x in pays)

            minor=bool(int(row['minorenne'] or 0)) if 'minorenne' in row.keys() else False
            guardian=str(row['genitore'] or '').strip() if 'genitore' in row.keys() else ''
            contact=(str(row['telefono_genitore'] or '').strip() if 'telefono_genitore' in row.keys() else '') or (str(row['email_genitore'] or '').strip() if 'email_genitore' in row.keys() else '')
            consent=0
            try:
                mr=conn.execute('SELECT * FROM minori WHERE tesserato_id=? ORDER BY id DESC LIMIT 1',(tid,)).fetchone()
                if mr:
                    if not guardian and 'genitore' in mr.keys(): guardian=str(mr['genitore'] or '').strip()
                    if not contact:
                        if 'telefono_genitore' in mr.keys(): contact=str(mr['telefono_genitore'] or '').strip()
                        if not contact and 'email_genitore' in mr.keys(): contact=str(mr['email_genitore'] or '').strip()
                    if 'consenso_firmato' in mr.keys(): consent=int(mr['consenso_firmato'] or 0)
            except Exception: pass
            tutela_ok=(not minor) or bool(mu_ok and guardian and contact and consent)

            checks=[
                ('Modulo Unico',mu_ok,'Presente e apribile' if mu_ok else 'Modulo Unico mancante'),
                ('Certificato',cert_ok,cert_reason),
                ('Mensile',month_paid,('Pagamento '+str(month).zfill(2)+'/'+str(year)+' registrato') if month_paid else ('Pagamento '+str(month).zfill(2)+'/'+str(year)+' mancante/incongruente')),
                ('Iscrizione',enroll_paid,('Quota '+str(season)+'/'+str(season+1)+' registrata') if enroll_paid else ('Quota '+str(season)+'/'+str(season+1)+' mancante/incongruente')),
            ]
            if minor:
                checks.append(('Tutela',tutela_ok,'Tutela completa' if tutela_ok else ('Tutela non valida senza MU' if not mu_ok else 'Genitore/contatto/consenso incompleto')))

            overall=all(x[1] for x in checks)
            reasons=[label+': '+detail for label,ok,detail in checks if not ok]
            if cert_filter and cert_ok: continue
            items.append({'row':row,'checks':checks,'overall':overall,'reasons':reasons})
    finally:
        conn.close()

    tpl="""<!doctype html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'><title>BodyMind · Atlete</title>""" + r22.ATHLETE_CSS + """
<style>/* BODYMIND_R140_MOBILE_ATHLETE_TRUTH */
.truth-card{padding:0!important;overflow:hidden;border:1px solid #334155!important}.truth-card.good{border-color:#166534!important}.truth-card.bad{border-color:#7f1d1d!important}.truth-open{display:block;padding:16px;color:inherit;text-decoration:none}.truth-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.truth-overall{font-size:11px;font-weight:950;padding:6px 9px;border-radius:999px}.truth-overall.good{background:#14532d;color:#dcfce7}.truth-overall.bad{background:#7f1d1d;color:#fee2e2}.truth-grid{display:grid;gap:6px;margin-top:10px}.truth-line{display:grid;grid-template-columns:10px 92px 1fr;gap:7px;align-items:start;padding:7px 8px;border-radius:10px;background:#0b1b2e}.truth-dot{width:9px;height:9px;border-radius:50%;margin-top:4px}.truth-line b{font-size:11px;color:#e2e8f0}.truth-line small{font-size:11px;color:#94a3b8;line-height:1.3}.truth-reasons{margin-top:9px;padding:9px 10px;border-radius:11px;background:#3f1117;color:#fecaca;font-size:11px;line-height:1.45}.athlete-delete-form{display:flex;margin:0;padding:0 16px 14px}.athlete-delete{width:100%;min-height:42px;border:1px solid #fecaca;border-radius:12px;background:#7f1d1d;color:#fff;font-weight:900;font-size:13px}</style></head><body>
<header class='top'><a class='homepill' href='/mobile'>⌂ Home</a><div class='topline'><a class='back' href='/mobile'>‹</a><div><h1>{{'Certificati' if cert_filter else 'Atlete'}}</h1><p>{{'Chi richiede controllo adesso.' if cert_filter else 'Stato reale: MU, certificato, pagamenti e tutela.'}}</p></div></div></header>
<main class='wrap'><form class='search'><input type='hidden' name='cert' value='{{"alert" if cert_filter else ""}}'><input name='q' value='{{q}}' placeholder='Cerca nome, corso o email'><button>Cerca</button></form>
{% if not cert_filter %}<a class='card' href='/mobile/atleta/nuova'><div class='name'>＋ Nuova atleta</div><div class='muted'>Inserimento anagrafica completa</div></a>{% endif %}
{% for item in items %}{% set r=item.row %}<div class='card truth-card {{"good" if item.overall else "bad"}}'><a class='truth-open' href='/mobile/atleta/{{r["id"]}}'><div class='truth-head'><div><div class='name'>{{r['cognome']}} {{r['nome']}}</div><div class='muted'>{{r['corso'] or 'Corso non indicato'}}</div></div><span class='truth-overall {{"good" if item.overall else "bad"}}'>{{"REGOLARE" if item.overall else "DA COMPLETARE"}}</span></div><div class='truth-grid'>{% for label,ok,detail in item.checks %}<div class='truth-line'><span class='truth-dot' style='background:{{"#16a34a" if ok else "#dc2626"}}'></span><b>{{label}}</b><small>{{detail}}</small></div>{% endfor %}</div>{% if item.reasons %}<div class='truth-reasons'><b>Da sistemare:</b><br>{{item.reasons|join('<br>')|safe}}</div>{% endif %}</a>{% if not cert_filter %}<form method='POST' action='/tesserati/delete' class='athlete-delete-form' onsubmit="return confirm('Eliminare definitivamente {{r['nome']}} {{r['cognome']}}?');"><input type='hidden' name='id' value='{{r["id"]}}'><button type='submit' class='athlete-delete'>Elimina atleta</button></form>{% endif %}</div>{% else %}<div class='card empty'>Nessuna atleta trovata.</div>{% endfor %}</main>""" + r22.ATHLETE_NAV + """</body></html>"""
    return render_template_string(tpl,items=items,q=q,cert_filter=cert_filter)
'''
    shutil.copy2(p,BACK/p.name)
    s=s[:start]+new+s[end:]
    p.write_text(s,encoding='utf-8')
    py_compile.compile(str(p),doraise=True)
    print('[r140-mobile-list] PASS source='+str(p),flush=True)
else:
    print('[r140-mobile-list] already applied',flush=True)
