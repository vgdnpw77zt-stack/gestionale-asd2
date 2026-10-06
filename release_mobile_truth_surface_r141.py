from __future__ import annotations
import py_compile, shutil, sqlite3
from pathlib import Path

APP=Path('/data/top2_app')
CORE=APP/'asd_app/core.py'
DB=Path('/data/tenants/default/asd.db')
BACK=Path('/data/release_backups/20261004_r141_mobile_truth_surface')
BACK.mkdir(parents=True,exist_ok=True)

s=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R141_MOBILE_TRUTH_SURFACE' not in s:
    shutil.copy2(CORE,BACK/'core.py')
    s += r'''

# BODYMIND_R141_MOBILE_TRUTH_SURFACE
def _r141_file_exists(filename):
    from pathlib import Path as _P
    raw=_P(str(filename or '').strip())
    roots=[_P('/data/tenants/default/media'),_P('/data/top2_app/user_static'),_P('/data/top2_app/static'),_P('/data/top2_app'),_P('/data/tenants/default')]
    candidates=[raw] if raw.is_absolute() else [root/raw for root in roots]
    for fp in candidates:
        try:
            if fp.is_file():
                return True
        except Exception:
            pass
    return False

def _r141_doc_family(row):
    def _v(k):
        try:return str(row[k] or '').lower()
        except Exception:return ''
    hay=' '.join(_v(k) for k in ('doc_type','categoria','titolo','original_filename','filename'))
    if any(x in hay for x in ('modulo_unico_tesseramento','modulo unico','modulo iscrizione',"modulo d'iscrizione",'domanda iscrizione','domanda di iscrizione')):
        return 'mu'
    if 'richiesta certificato' in hay or 'richiesta_certificato' in hay or 'ecg' in hay or 'elettrocard' in hay or 'referto' in hay:
        return 'other'
    if 'certificato_medico' in hay or ('certificat' in hay and 'medic' in hay):
        return 'medical'
    return 'other'

def _r141_truth(conn,row):
    from datetime import date as _D, datetime as _DT
    tid=int(row['id'])
    docs=conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND COALESCE(visibile,1)=1 ORDER BY id",(tid,)).fetchall()
    mu_ok=any(_r141_doc_family(d)=='mu' and _r141_file_exists(d['filename']) for d in docs)
    med_file=any(_r141_doc_family(d)=='medical' and _r141_file_exists(d['filename']) for d in docs)

    today=_D.today()
    expiry=str(row['certificato_scadenza'] or '').strip() if 'certificato_scadenza' in row.keys() else ''
    cert_ok=False
    if med_file and expiry:
        try:
            exp=_DT.strptime(expiry[:10],'%Y-%m-%d').date()
            cert_ok=exp>=today
            cert_detail=('Valido fino al '+exp.strftime('%d/%m/%Y')) if cert_ok else ('Scaduto il '+exp.strftime('%d/%m/%Y'))
        except Exception:
            cert_detail='Scadenza da verificare'
    elif med_file:
        cert_detail='File presente, scadenza da verificare'
    elif expiry:
        cert_detail='Data presente ma file certificato assente'
    else:
        cert_detail='Certificato medico mancante'

    month=today.month; year=today.year
    season=year if month>=7 else year-1
    # Payment state must be identical to /pagamenti, Dashboard, Centro operativo,
    # Task, Tesserati and Operatore. Do not parse payment rows again here.
    pay_truth=bodymind_payment_truth(conn,tesserato_id=tid,mese=month,anno=year,stagione=season)
    pay_row=(pay_truth.get('rows') or [{}])[0] if (pay_truth.get('rows') or []) else {}
    mensile=bool(pay_row.get('mensile_pagato'))
    tesseramento=bool(pay_row.get('iscrizione_pagata'))

    minor=False
    try: minor=bool(int(row['minorenne'] or 0))
    except Exception: minor=False
    if not minor and 'data_nascita' in row.keys():
        raw_birth=str(row['data_nascita'] or '').strip()
        for fmt in ('%Y-%m-%d','%d/%m/%Y'):
            try:
                b=_DT.strptime(raw_birth[:10],fmt).date()
                minor=(today.year-b.year-((today.month,today.day)<(b.month,b.day)))<18
                break
            except Exception:
                pass

    guardian=str(row['genitore'] or '').strip() if 'genitore' in row.keys() else ''
    contact=((str(row['telefono_genitore'] or '').strip() if 'telefono_genitore' in row.keys() else '') or
             (str(row['email_genitore'] or '').strip() if 'email_genitore' in row.keys() else ''))
    consent=False
    for k in ('consenso_informato','privacy_ok','liberatoria_ok'):
        if k in row.keys():
            try:
                if int(row[k] or 0): consent=True
            except Exception:
                if str(row[k] or '').strip().lower() in ('1','si','sì','true','ok'):
                    consent=True
    tutela_ok=(not minor) or bool(mu_ok and guardian and contact and consent)

    checks=[
      ('Modulo Unico',mu_ok,'Presente e apribile' if mu_ok else 'MANCANTE'),
      ('Certificato',cert_ok,cert_detail),
      ('Mensile',mensile,('Pagamento '+str(month).zfill(2)+'/'+str(year)+' registrato') if mensile else ('Pagamento '+str(month).zfill(2)+'/'+str(year)+' mancante/incongruente')),
      ('Tesseramento',tesseramento,('Quota '+str(season)+'/'+str(season+1)+' registrata') if tesseramento else ('Quota '+str(season)+'/'+str(season+1)+' mancante/incongruente')),
    ]
    if minor:
        checks.append(('Tutela',tutela_ok,'Completa' if tutela_ok else ('Non valida senza MU' if not mu_ok else 'Genitore/contatto/consenso incompleto')))
    return {
      'mu_ok':mu_ok,'cert_ok':cert_ok,'mensile_ok':mensile,'tesseramento_ok':tesseramento,
      'minor':minor,'tutela_ok':tutela_ok,'checks':checks,'overall':all(x[1] for x in checks),
      'cert_detail':cert_detail
    }

def _r141_nav(active):
    items=[
      ('Home','⌂','/mobile','home'),
      ('Atlete','♙','/mobile/atlete','atlete'),
      ('Presenze','✓','/presenze-semplici','presenze'),
      ('Pagamenti','€','/pagamenti','pagamenti'),
      ('Documenti','▤','/documenti-automatici','documenti')
    ]
    out=["<nav class='r141-nav'>"]
    for label,icon,href,key in items:
        cls=' active' if key==active else ''
        out.append("<a class='r141-nav-item"+cls+"' href='"+href+"'><span>"+icon+"</span><b>"+label+"</b></a>")
    out.append("</nav>")
    return ''.join(out)

def _r141_style():
    return """<style id='bodymind-r141-style'>
    :root{color-scheme:dark}*{box-sizing:border-box}
    body.r141-standalone{margin:0;background:#071529;color:#eef6ff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
    .r141-page{max-width:760px;margin:auto;padding:18px 18px 118px}
    .r141-top{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:18px}
    .r141-top h1{font-size:34px;margin:0 0 5px}.r141-top p{margin:0;color:#aabbd0}
    .r141-home{background:#102944;border:1px solid #234665;color:#fff;text-decoration:none;padding:11px 16px;border-radius:999px;font-weight:900}
    .r141-search{display:grid;grid-template-columns:1fr auto;gap:8px;margin-bottom:12px}
    .r141-search input{min-height:52px;border-radius:15px;border:1px solid #2b4e70;background:#0a1c31;color:#fff;padding:0 15px;font-size:16px}
    .r141-search button{border:1px solid #3b668c;border-radius:15px;background:#123354;color:#fff;padding:0 18px;font-weight:900}
    .r141-new{display:block;background:#fff;color:#081428;text-decoration:none;border-radius:18px;padding:16px 18px;font-size:20px;font-weight:950;margin-bottom:12px}
    .r141-athlete{background:#0b1d33;border:1px solid #27445f;border-radius:20px;margin:10px 0;overflow:hidden}
    .r141-athlete.bad{border-color:#71303a}.r141-athlete.ok{border-color:#246343}
    .r141-athlete>a{display:block;color:inherit;text-decoration:none;padding:16px}
    .r141-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}
    .r141-head h2{margin:0;font-size:21px}.r141-head p{margin:4px 0 0;color:#a9b9cb}
    .r141-head>strong{font-size:10px;white-space:nowrap;padding:7px 9px;border-radius:999px;background:#7f1d1d;color:#fee2e2}
    .r141-athlete.ok .r141-head>strong{background:#14532d;color:#dcfce7}
    .r141-checks{display:grid;gap:6px;margin-top:12px}
    .r141-check{display:grid;grid-template-columns:10px 96px 1fr;gap:8px;align-items:start;background:#081727;padding:8px 9px;border-radius:11px}
    .r141-check i{width:9px;height:9px;border-radius:50%;margin-top:4px;background:#dc2626}
    .r141-check.ok i{background:#16a34a}.r141-check b{font-size:12px}.r141-check span{font-size:12px;color:#aebfd1;line-height:1.35}
    .r141-reasons{margin-top:9px;padding:10px 11px;border-radius:12px;background:#3d1118;color:#fecaca;font-size:12px;line-height:1.45}
    .r141-nav{position:fixed;z-index:1000;left:12px;right:12px;bottom:max(10px,env(safe-area-inset-bottom));height:72px;display:grid;grid-template-columns:repeat(5,1fr);background:#061321;border:1px solid #1d3b57;border-radius:22px;overflow:hidden;box-shadow:0 15px 40px rgba(0,0,0,.42)}
    .r141-nav-item{color:#d8e5f3;text-decoration:none;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:5px;font-size:11px;border-right:1px solid rgba(71,111,145,.32)}
    .r141-nav-item:last-child{border-right:0}.r141-nav-item span{font-size:22px;line-height:1}.r141-nav-item.active{background:#0c4566;color:#fff;box-shadow:inset 0 0 0 1px #38bdf8}
    .r141-dash-panel{margin:12px 0;padding:15px;border-radius:18px;background:#0b1d33;border:1px solid #27445f}
    .r141-dash-panel h3{margin:0 0 7px;font-size:18px}.r141-dash-panel p{margin:0 0 9px;color:#aebfd1;font-size:13px}
    .r141-dash-list{display:grid;gap:6px}.r141-dash-name{display:flex;justify-content:space-between;gap:10px;padding:9px 10px;border-radius:11px;background:#081727;color:#fff;text-decoration:none;font-weight:800}
    .r141-dash-name.bad span{color:#fca5a5}.r141-count{display:inline-flex;min-width:30px;height:30px;align-items:center;justify-content:center;border-radius:999px;background:#7f1d1d;color:#fff;font-weight:950}
    </style>"""

@app.after_request
def _bodymind_r141_mobile_truth_surface(resp):
    try:
        from html import escape as _e
        path=request.path or ''
        _status=int(getattr(resp,'status_code',200) or 200)
        if request.method!='GET':
            return resp
        _mobile_athlete_redirect=(
            path=='/mobile/atlete'
            and _status in (301,302,303,307,308)
            and str(resp.headers.get('Location','')).startswith('/tesserati')
            and bool(session.get('logged'))
            and str(session.get('role') or '').lower()=='admin'
        )
        if _status!=200 and not _mobile_athlete_redirect:
            return resp
        if _status==200 and 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp

        if path=='/mobile/atlete':
            conn=db(); conn.row_factory=sqlite3.Row
            try:
                rows=conn.execute("SELECT * FROM tesserati ORDER BY TRIM(cognome) COLLATE NOCASE,TRIM(nome) COLLATE NOCASE").fetchall()
                q=(request.args.get('q') or '').strip().lower()
                items=[]
                for row in rows:
                    hay=(' '.join(str(row[k] or '') for k in ('nome','cognome','corso','email') if k in row.keys())).lower()
                    if q and q not in hay:
                        continue
                    items.append((row,_r141_truth(conn,row)))
            finally:
                conn.close()

            cards=[]
            for row,tr in items:
                reasons=[lab+': '+det for lab,ok,det in tr['checks'] if not ok]
                lines=[]
                for lab,ok,det in tr['checks']:
                    tone='ok' if ok else 'bad'
                    lines.append("<div class='r141-check "+tone+"'><i></i><b>"+_e(lab)+"</b><span>"+_e(det)+"</span></div>")
                state='REGOLARE' if tr['overall'] else 'DA COMPLETARE'
                statecls='ok' if tr['overall'] else 'bad'
                reasonhtml=("<div class='r141-reasons'><b>Da sistemare</b><br>"+"<br>".join(_e(x) for x in reasons)+"</div>") if reasons else ""
                name=(str(row['cognome'] or '')+' '+str(row['nome'] or '')).strip()
                cards.append("<article class='r141-athlete "+statecls+"'><a href='/mobile/atleta/"+str(int(row['id']))+"'><div class='r141-head'><div><h2>"+_e(name)+"</h2><p>"+_e(str(row['corso'] or 'Corso non indicato'))+"</p></div><strong>"+state+"</strong></div><div class='r141-checks'>"+''.join(lines)+"</div>"+reasonhtml+"</a></article>")

            qv=_e(request.args.get('q') or '')
            html="<!doctype html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'><title>Atlete</title>"+_r141_style()+"</head><body class='r141-standalone'><main class='r141-page'><div class='r141-top'><div><h1>Atlete</h1><p>Stato reale di documenti e pagamenti.</p></div><a class='r141-home' href='/mobile'>⌂ Home</a></div><form class='r141-search' method='get'><input name='q' value='"+qv+"' placeholder='Cerca nome, corso o email'><button>Cerca</button></form><a class='r141-new' href='/mobile/atleta/nuova'>＋ Nuova atleta</a>"+''.join(cards)+"</main>"+_r141_nav('atlete')+"</body></html>"
            resp.set_data(html)
            resp.status_code=200
            resp.headers.pop('Location',None)
            resp.headers['Content-Type']='text/html; charset=utf-8'
            return resp

        if path=='/mobile':
            html=resp.get_data(as_text=True)
            if 'BODYMIND_R141_DASHBOARD_TRUTH' in html:
                return resp
            conn=db(); conn.row_factory=sqlite3.Row
            try:
                rows=conn.execute("SELECT * FROM tesserati ORDER BY TRIM(cognome) COLLATE NOCASE,TRIM(nome) COLLATE NOCASE").fetchall()
                missing_mu=[]; bad_cert=[]; bad_pay=[]
                for row in rows:
                    tr=_r141_truth(conn,row)
                    name=(str(row['cognome'] or '')+' '+str(row['nome'] or '')).strip()
                    item=(int(row['id']),name)
                    if not tr['mu_ok']: missing_mu.append(item)
                    if not tr['cert_ok']: bad_cert.append((int(row['id']),name,tr['cert_detail']))
                    if not tr['mensile_ok']: bad_pay.append(item)
            finally:
                conn.close()

            def names(items,detail=False):
                out=[]
                for x in items:
                    tid=x[0]; nm=x[1]
                    suffix=(" <span>"+_e(str(x[2]))+"</span>") if detail and len(x)>2 else ""
                    out.append("<a class='r141-dash-name bad' href='/mobile/atleta/"+str(tid)+"'><b>"+_e(nm)+"</b>"+suffix+"</a>")
                return ''.join(out) if out else "<div class='r141-dash-name'><b>Nessuna</b><span>✓</span></div>"

            panel="<!-- BODYMIND_R141_DASHBOARD_TRUTH -->"+_r141_style()+"<section class='r141-dash-panel'><h3>Modulo Unico mancante <span class='r141-count'>"+str(len(missing_mu))+"</span></h3><p>Atlete senza un MU visibile e realmente presente sul disco.</p><div class='r141-dash-list'>"+names(missing_mu)+"</div></section><section class='r141-dash-panel'><h3>Certificato medico mancante/non valido <span class='r141-count'>"+str(len(bad_cert))+"</span></h3><p>File assente, scadenza assente/non valida oppure certificato non riconosciuto.</p><div class='r141-dash-list'>"+names(bad_cert,True)+"</div></section><section class='r141-dash-panel'><h3>Mensile da verificare <span class='r141-count'>"+str(len(bad_pay))+"</span></h3><p>Pagamento del mese corrente non presente nella verità canonica dei pagamenti.</p><div class='r141-dash-list'>"+names(bad_pay)+"</div></section>"
            if '</main>' in html:
                html=html.replace('</main>',panel+'</main>',1)
            elif '</body>' in html:
                html=html.replace('</body>',panel+'</body>',1)
            else:
                html+=panel
            resp.set_data(html)
            return resp
    except Exception as exc:
        print('[r141-warning] '+repr(exc),flush=True)
    return resp
'''
    CORE.write_text(s,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r141-install] PASS mobile athlete truth + dashboard truth panels installed',flush=True)
else:
    # Upgrade an already-installed R141 block on the persistent runtime. Failed
    # deploys can leave generated source on /data, so the release must converge
    # existing code instead of treating the marker as sufficient.
    _orig=s

    # R141 originally leaked a flat body background into /mobile when injecting
    # truth panels. Keep that background only for the standalone athlete page so
    # the dashboard's underlying theme/background can render again.
    s=s.replace(
        "body{margin:0;background:#071529;color:#eef6ff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}",
        "body.r141-standalone{margin:0;background:#071529;color:#eef6ff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}"
    )
    s=s.replace(
        "</head><body><main class='r141-page'>",
        "</head><body class='r141-standalone'><main class='r141-page'>",
        1
    )
    # Older persistent R141 variants can contain additional head markup before
    # the body. Match the stable page wrapper as a second, idempotent fallback.
    s=s.replace(
        "<body><main class='r141-page'>",
        "<body class='r141-standalone'><main class='r141-page'>",
        1
    )

    # Converge the persistent R141 payment fragment to the single canonical
    # payment service. Document truth remains untouched.
    _old_r141_pay="""    pays=conn.execute("SELECT * FROM pagamenti WHERE tesserato_id=? ORDER BY id DESC",(tid,)).fetchall()
    month=today.month; year=today.year
    season=year if month>=7 else year-1
    mensile=False; tesseramento=False
    for p in pays:
        if not _r141_paid(p):
            continue
        try: causale=str(p['causale'] or '').strip().lower()
        except Exception: causale=''
        try: pm=int(p['mese'] or 0)
        except Exception: pm=0
        try: py=int(p['anno'] or 0)
        except Exception: py=0
        if (('mensil' in causale) or causale in ('quota','quota_mensile','mensile')) and pm==month and py==year:
            mensile=True
        if any(x in causale for x in ('iscrizione','tesseramento')) and py in (season,season+1):
            tesseramento=True

"""
    _new_r141_pay="""    month=today.month; year=today.year
    season=year if month>=7 else year-1
    # Payment state must be identical to /pagamenti, Dashboard, Centro operativo,
    # Task, Tesserati and Operatore. Do not parse payment rows again here.
    pay_truth=bodymind_payment_truth(conn,tesserato_id=tid,mese=month,anno=year,stagione=season)
    pay_row=(pay_truth.get('rows') or [{}])[0] if (pay_truth.get('rows') or []) else {}
    mensile=bool(pay_row.get('mensile_pagato'))
    tesseramento=bool(pay_row.get('iscrizione_pagata'))

"""
    if _old_r141_pay in s:
        s=s.replace(_old_r141_pay,_new_r141_pay,1)

    _old_r141_helper="""def _r141_paid(row):
    def _v(k):
        try:return row[k]
        except Exception:return None
    st=(str(_v('stato') or '')+' '+str(_v('online_status') or '')).lower()
    if any(x in st for x in ('pending','attesa','cancel','annull','failed','fallit','refund','rimbors')):
        return False
    try: amount=float(_v('importo') or 0)
    except Exception: amount=0
    dt=bool(str(_v('data') or '').strip())
    return any(x in st for x in ('paid','pagat','saldat','complet','incassat')) or (dt and amount>0)

"""
    if _old_r141_helper in s:
        s=s.replace(_old_r141_helper,'',1)
    _old_head="""        path=request.path or ''
        if request.method!='GET' or int(getattr(resp,'status_code',200) or 200)!=200:
            return resp
        if 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp

        if path=='/mobile/atlete':"""
    _new_head="""        path=request.path or ''
        _status=int(getattr(resp,'status_code',200) or 200)
        if request.method!='GET':
            return resp
        _mobile_athlete_redirect=(
            path=='/mobile/atlete'
            and _status in (301,302,303,307,308)
            and str(resp.headers.get('Location','')).startswith('/tesserati')
            and bool(session.get('logged'))
            and str(session.get('role') or '').lower()=='admin'
        )
        if _status!=200 and not _mobile_athlete_redirect:
            return resp
        if _status==200 and 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp

        if path=='/mobile/atlete':"""
    if '_mobile_athlete_redirect' not in s:
        if _old_head not in s:
            raise RuntimeError('R141 persistent runtime header anchor missing')
        s=s.replace(_old_head,_new_head,1)
    _old_resp="""            resp.set_data(html)
            resp.headers['Content-Type']='text/html; charset=utf-8'
            return resp"""
    _new_resp="""            resp.set_data(html)
            resp.status_code=200
            resp.headers.pop('Location',None)
            resp.headers['Content-Type']='text/html; charset=utf-8'
            return resp"""
    # Only the athlete-list branch needs to convert the canonical redirect.
    if 'resp.status_code=200' not in s[s.find('BODYMIND_R141_MOBILE_TRUTH_SURFACE'):]:
        if _old_resp not in s:
            raise RuntimeError('R141 persistent runtime athlete response anchor missing')
        s=s.replace(_old_resp,_new_resp,1)

    # BODYMIND_R141_STANDALONE_BODY_GUARD
    # Some persistent variants build the R141 athlete HTML from a legacy route
    # whose source body is simply <body> (often followed by <header>, not <main>).
    # Scope the flat R141 background at the final rendered response instead of
    # guessing which historical template wrapper produced the page.
    _r141_block=s.find('BODYMIND_R141_MOBILE_TRUTH_SURFACE')
    _r141_ath=s.find("        if path=='/mobile/atlete':",_r141_block)
    _r141_resp=s.find("            resp.set_data(html)",_r141_ath)
    _r141_guard="            # BODYMIND_R141_STANDALONE_BODY_GUARD_RUNTIME\n            if \"class='r141-standalone'\" not in html:\n                html=html.replace('<body>',\"<body class='r141-standalone'>\",1)\n"
    if _r141_ath<0 or _r141_resp<0:
        raise RuntimeError('R141 persistent athlete response guard anchor missing')
    if 'BODYMIND_R141_STANDALONE_BODY_GUARD_RUNTIME' not in s[_r141_ath:_r141_resp+500]:
        s=s[:_r141_resp]+_r141_guard+s[_r141_resp:]

    if s!=_orig:
        shutil.copy2(CORE,BACK/'core_pre_upgrade.py')
        CORE.write_text(s,encoding='utf-8')
        py_compile.compile(str(CORE),doraise=True)
        print('[r141-install] upgraded persistent R141 runtime',flush=True)
    else:
        print('[r141-install] already current',flush=True)


# Fresh-process QA: verify the final rendered mobile surfaces, not only source text.
import subprocess, sys
qa=r'''
import re,sqlite3,sys
from pathlib import Path
sys.path.insert(0,"/data/top2_app")
import app as _full
from asd_app.core import app
app.config["TESTING"]=True
c=app.test_client()
with c.session_transaction() as sess:
    sess.update({"logged":True,"logged_in":True,"username":"admin","display_name":"R141 QA","role":"admin","tenant_slug":"default","user_id":1,"is_admin":True,"admin":True,"_csrf_token":"r141"})
alist=c.get("/mobile/atlete",follow_redirects=False)
ah=alist.get_data(as_text=True)
dash=c.get("/mobile",follow_redirects=False)
dh=dash.get_data(as_text=True)
try:
    rule_info=[(str(r.rule),r.endpoint,sorted(r.methods or [])) for r in app.url_map.iter_rules() if str(r.rule)=="/mobile/atlete"]
    src_info=[]
    import inspect
    for _,ep,_ in rule_info:
        try: src_info.append((ep,inspect.getsource(app.view_functions[ep])[:5000]))
        except Exception as exc: src_info.append((ep,"ERR:"+repr(exc)))
except Exception as exc:
    rule_info=[]; src_info=[("ERR",repr(exc))]
print("[r141-diag] athletes_status="+str(alist.status_code)+" location="+str(alist.headers.get("Location",""))+" body="+repr(ah[:1200])+" rules="+repr(rule_info)+" src="+repr(src_info),flush=True)
checks={
 "athletes_200":alist.status_code==200,
 "truth_surface":"Stato reale di documenti e pagamenti." in ah and "Modulo Unico" in ah and "Mensile" in ah and "Tesseramento" in ah,
 "dashboard_200":dash.status_code==200,
 "dashboard_mu":"BODYMIND_R141_DASHBOARD_TRUTH" in dh and "Modulo Unico mancante" in dh,
 "dashboard_cert":"Certificato medico mancante/non valido" in dh,
 "dashboard_names":"r141-dash-name" in dh,
 "dashboard_background_not_overridden":"body{margin:0;background:#071529" not in dh and "body.r141-standalone{margin:0;background:#071529" in dh,
 "standalone_background_scoped":"body.r141-standalone{margin:0;background:#071529" in ah and "body{margin:0;background:#071529" not in ah,
 "canonical_payment_helper":"pay_truth=bodymind_payment_truth" in Path("/data/top2_app/asd_app/core.py").read_text(encoding="utf-8",errors="replace"),
}
# Specific regression: if Balbinetti has no visible physical medical file,
# the rendered athlete card must not be globally green because of expiry alone.
conn=sqlite3.connect("/data/tenants/default/asd.db",timeout=20);conn.row_factory=sqlite3.Row
try:
    b=conn.execute("SELECT * FROM tesserati WHERE lower(cognome) LIKE 'balbinetti%' LIMIT 1").fetchone()
    if b:
        docs=conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1",(int(b["id"]),)).fetchall()
        roots=[Path("/data/tenants/default/media"),Path("/data/top2_app/user_static"),Path("/data/top2_app/static"),Path("/data/top2_app"),Path("/data/tenants/default")]
        def exists(fn):
            raw=Path(str(fn or "").strip()); cs=[raw] if raw.is_absolute() else [r/raw for r in roots]
            return any(x.is_file() for x in cs)
        def med(d):
            hay=" ".join(str(d[k] or "").lower() for k in ("doc_type","categoria","titolo","original_filename","filename") if k in d.keys())
            return ("richiesta certificato" not in hay and "richiesta_certificato" not in hay and ("certificato_medico" in hay or ("certificat" in hay and "medic" in hay)))
        has_med=any(med(d) and exists(d["filename"]) for d in docs)
        if not has_med:
            name=(str(b["cognome"] or "")+" "+str(b["nome"] or "")).strip()
            pos=ah.find(name)
            frag=ah[pos:pos+5000] if pos>=0 else ""
            checks["balbinetti_missing_cert_red"]=("Certificato medico mancante" in frag or "file certificato assente" in frag.lower()) and "DA COMPLETARE" in frag
    integ=str(conn.execute("PRAGMA integrity_check").fetchone()[0]); fk=len(conn.execute("PRAGMA foreign_key_check").fetchall())
finally:conn.close()
checks["db_ok"]=(integ.lower()=="ok" and fk==0)
print("[r141-selftest] "+repr(checks)+" integrity="+integ+" fk="+str(fk),flush=True)
if not all(checks.values()):
    raise RuntimeError("R141 QA failed "+repr(checks))
'''
proc=subprocess.run([sys.executable,'-c',qa],capture_output=True,text=True,timeout=120)
print((proc.stdout or '').strip(),flush=True)
if proc.returncode!=0:
    raise RuntimeError('R141 child QA failed '+((proc.stderr or '')+(proc.stdout or ''))[-5000:])


# BODYMIND_R157_MOBILE_HOME_BACKGROUND
# Mobile-home-only visual convergence. /mobile is the real iPhone dashboard;
# previous desktop-only background restores did not affect this route.
_core_r157=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R157_MOBILE_HOME_BACKGROUND_RUNTIME' not in _core_r157:
    _core_r157 += r'''

# BODYMIND_R157_MOBILE_HOME_BACKGROUND_RUNTIME
@app.after_request
def _bodymind_mobile_home_background_r157(resp):
    try:
        if request.method!='GET' or request.path!='/mobile':
            return resp
        if int(getattr(resp,'status_code',200) or 200)!=200:
            return resp
        if 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp
        html=resp.get_data(as_text=True)
        if 'BODYMIND_R157_MOBILE_HOME_BACKGROUND_RENDERED' in html:
            return resp
        addon=r"""<!-- BODYMIND_R157_MOBILE_HOME_BACKGROUND_RENDERED -->
<style id="bodymind-r157-mobile-home-background">
html,html body{
  min-height:100%!important;
  background-color:#050d18!important;
  background-position:center top!important;
  background-size:cover!important;
  background-repeat:no-repeat!important;
  background-attachment:fixed!important;
}
html body:before{
  content:"";position:fixed;inset:0;pointer-events:none;z-index:-1;
  background:none!important;
}
html body>.overlay,html body .overlay{background:transparent!important}
html body main,html body .wrap,html body .mobile-home,html body .dashboard,html body .dashboard-page{
  background:transparent!important;
}
.r141-dash-panel{
  background:linear-gradient(145deg,rgba(8,25,43,.86),rgba(13,38,62,.80))!important;
  border-color:rgba(125,211,252,.20)!important;
  box-shadow:0 18px 42px rgba(0,0,0,.20)!important;
  backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);
}
@supports(-webkit-touch-callout:none){
  html,html body{background-attachment:scroll!important}
}
</style>
<script id="bodymind-r157-mobile-home-js">
(function(){
  try{
    document.documentElement.style.setProperty('background-color','#050d18','important');
    document.body.style.setProperty('background-color','transparent','important');
  }catch(_){}
})();
</script>"""
        if '</body>' in html:
            html=html.replace('</body>',addon+'</body>',1)
        else:
            html+=addon
        resp.set_data(html)
    except Exception as exc:
        print('[r157-mobile-home-background-warning] '+repr(exc),flush=True)
    return resp
'''
    CORE.write_text(_core_r157,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r157-mobile-home-background] installed /mobile premium background override',flush=True)
else:
    print('[r157-mobile-home-background] already installed',flush=True)

# Converge an already-persisted R157 function without adding another hook.
_r157_live=CORE.read_text(encoding='utf-8',errors='replace')
_r157_old="html,html body{\n  min-height:100%!important;\n  background:\n    radial-gradient(circle at 8% 2%,rgba(255,255,255,.13) 0%,rgba(255,255,255,.045) 18%,transparent 36%),\n    radial-gradient(circle at 92% 10%,rgba(56,189,248,.24) 0%,rgba(37,99,235,.11) 27%,transparent 48%),\n    radial-gradient(circle at 48% 92%,rgba(16,185,129,.10) 0%,transparent 40%),\n    linear-gradient(155deg,#050d18 0%,#08182a 43%,#102a43 72%,#06111e 100%)!important;\n  background-attachment:fixed!important;\n}\nhtml body:before{\n  content:\"\";position:fixed;inset:0;pointer-events:none;z-index:-1;\n  background:\n    radial-gradient(ellipse at 50% -8%,rgba(255,255,255,.09),transparent 44%),\n    linear-gradient(118deg,transparent 0 47%,rgba(255,255,255,.025) 47.2% 47.8%,transparent 48%);\n}"
_r157_new="html,html body{\n  min-height:100%!important;\n  background-color:#050d18!important;\n  background-position:center top!important;\n  background-size:cover!important;\n  background-repeat:no-repeat!important;\n  background-attachment:fixed!important;\n}\nhtml body:before{\n  content:\"\";position:fixed;inset:0;pointer-events:none;z-index:-1;\n  background:none!important;\n}"
if _r157_old in _r157_live:
    _r157_live=_r157_live.replace(_r157_old,_r157_new,1)
    CORE.write_text(_r157_live,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r157-mobile-home-background-convergence] removed gradient image override',flush=True)
elif _r157_new in _r157_live:
    print('[r157-mobile-home-background-convergence] already converged',flush=True)
else:
    raise RuntimeError('R157 persisted background convergence anchor missing')

# Read-only invariant gate.
_r157_conn=sqlite3.connect(str(DB),timeout=20)
try:
    _r157_counts={t:int(_r157_conn.execute("SELECT COUNT(*) FROM "+t).fetchone()[0]) for t in ("tesserati","pagamenti","ricevute","documenti")}
    _r157_integrity=str(_r157_conn.execute("PRAGMA integrity_check").fetchone()[0])
    _r157_fk=len(_r157_conn.execute("PRAGMA foreign_key_check").fetchall())
finally:
    _r157_conn.close()
if _r157_integrity.lower()!='ok' or _r157_fk:
    raise RuntimeError('R157 mobile-home background DB guard failed')
print('[r157-mobile-home-background-selftest] PASS route=/mobile ui-only counts='+str(_r157_counts)+' integrity='+_r157_integrity+' fk='+str(_r157_fk),flush=True)
