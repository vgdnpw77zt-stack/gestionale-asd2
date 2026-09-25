# -*- coding: utf-8 -*-
"""BodyMind: accessi famiglia amministrabili + home mobile essenziale."""
import secrets
from flask import request, redirect, render_template_string, url_for
from .core import app, db, admin_required, csrf_input


def _is_mobile():
    ua=(request.headers.get('User-Agent') or '').lower()
    return any(x in ua for x in ('iphone','ipad','android','mobile'))

@app.before_request
def bodymind_mobile_home_redirect():
    if request.path == '/' and _is_mobile():
        return redirect('/mobile')

MOBILE = r'''<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#071426"><title>BodyMind · Home</title><style>
*{box-sizing:border-box}html,body{margin:0;background:#f5f7fb;color:#111827;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}body{padding:0 0 calc(82px + env(safe-area-inset-bottom))}.top{background:#071426;color:#fff;padding:calc(18px + env(safe-area-inset-top)) 18px 22px}.top b{font-size:13px;letter-spacing:.14em;text-transform:uppercase;color:#b9c7d8}.top h1{font-size:30px;letter-spacing:-.035em;margin:7px 0 4px}.top p{margin:0;color:#c9d4e2}.wrap{padding:14px}.alerts{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-bottom:12px}.alert{background:#fff!important;color:#0f172a!important;border:1px solid #d8e2ee;border-radius:18px;padding:14px;min-height:96px;text-decoration:none;display:block;box-shadow:0 5px 16px rgba(15,23,42,.05)}.alert strong{display:block;font-size:27px;margin:6px 0;color:#071426!important}.alert small{color:#52647a!important;font-weight:650;line-height:1.25}.alert .sym{font-size:22px;display:block;min-height:28px}.actions{display:grid;grid-template-columns:1fr 1fr;gap:10px}.action{background:#fff;color:#111827;text-decoration:none;border:1px solid #e0e7ef;border-radius:20px;padding:16px;min-height:112px;display:flex;flex-direction:column;justify-content:space-between;box-shadow:0 7px 20px rgba(15,23,42,.04)}.action i{font-style:normal;font-size:25px}.action b{font-size:17px}.action small{color:#64748b;line-height:1.25}.section{font-size:13px;color:#64748b;text-transform:uppercase;letter-spacing:.12em;font-weight:800;margin:20px 2px 10px}.nav{position:fixed;z-index:30;left:8px;right:8px;bottom:max(8px,env(safe-area-inset-bottom));height:64px;background:rgba(7,20,38,.96);border-radius:20px;display:grid;grid-template-columns:repeat(5,1fr);box-shadow:0 15px 40px rgba(0,0,0,.24);overflow:hidden}.nav a{color:#dbe7f5;text-decoration:none;display:flex;align-items:center;justify-content:center;flex-direction:column;font-size:10px;gap:3px}.nav span{font-size:20px}@media(max-width:370px){.actions{grid-template-columns:1fr}.alerts{grid-template-columns:1fr 1fr}}
</style></head><body><header class="top"><b>BodyMind Aerial Studio</b><h1>Dashboard</h1><p>Quello che serve oggi, senza rumore.</p></header><main class="wrap"><div class="alerts"><a class="alert" href="/tesserati"><span class="sym">⚠️</span><strong>{{cert}}</strong><small>Certificati da verificare/scaduti</small></a><a class="alert" href="/pagamenti"><span class="sym">€</span><strong>{{quote}}</strong><small>Quote da controllare</small></a><a class="alert" href="/documenti"><span class="sym">▤</span><strong>{{docs}}</strong><small>Documenti da verificare</small></a><a class="alert" href="/tesserati"><span class="sym">👤</span><strong>{{athletes}}</strong><small>Atlete/tesserati</small></a></div><div class="section">Azioni principali</div><div class="actions"><a class="action" href="/tesserati"><i>👤</i><b>Atlete</b><small>Schede, certificati e fascicoli</small></a><a class="action" href="/presenze"><i>✓</i><b>Presenze</b><small>Segna e controlla le lezioni</small></a><a class="action" href="/pagamenti"><i>€</i><b>Pagamenti</b><small>Quote, incassi e ricevute</small></a><a class="action" href="/documenti"><i>▤</i><b>Documenti</b><small>Modelli e archivio</small></a><a class="action" href="/mobile/autopilot"><i>⚙</i><b>Autopilot</b><small>Importa file o scatta una foto</small></a><a class="action" href="/corsi"><i>◯</i><b>Corsi</b><small>Orari e attività</small></a><a class="action" href="/famiglie/accessi"><i>♡</i><b>Famiglie</b><small>Accessi e link personali</small></a></div></main><nav class="nav"><a href="/mobile"><span>⌂</span>Home</a><a href="/tesserati"><span>♙</span>Atlete</a><a href="/presenze"><span>✓</span>Presenze</a><a href="/pagamenti"><span>€</span>Pagamenti</a><a href="/documenti"><span>▤</span>Documenti</a></nav></body></html>'''

@app.route('/mobile')
@admin_required
def bodymind_mobile_dashboard():
    conn=db()
    try:
        athletes=conn.execute('SELECT COUNT(*) FROM tesserati').fetchone()[0]
        try: cert=conn.execute("SELECT COUNT(*) FROM tesserati WHERE COALESCE(certificato_scadenza,'')='' OR certificato_scadenza < date('now','+30 day')").fetchone()[0]
        except Exception: cert=0
        try: quote=conn.execute("SELECT COUNT(*) FROM pagamenti WHERE lower(COALESCE(online_status,stato,'')) NOT IN ('pagato','paid','pagato_online_verificato')").fetchone()[0]
        except Exception: quote=0
        try: docs=conn.execute("SELECT COUNT(*) FROM inbound_documents WHERE lower(COALESCE(status,'')) NOT IN ('archived_to_tesserato','accepted','resolved')").fetchone()[0]
        except Exception: docs=0
    finally: conn.close()
    return render_template_string(MOBILE,athletes=athletes,cert=cert,quote=quote,docs=docs)

ACCESSI = r'''<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Accessi Famiglie</title><style>*{box-sizing:border-box}body{margin:0;background:#f5f7fb;color:#111827;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.top{background:#071426;color:#fff;padding:22px}.top a{color:#fff}.wrap{max-width:1000px;margin:auto;padding:18px}.card{background:#fff;border:1px solid #dfe7f0;border-radius:18px;padding:15px;margin:10px 0;display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center}.name{font-size:18px;font-weight:800}.muted{color:#64748b;font-size:13px}.buttons{display:flex;gap:7px;flex-wrap:wrap;justify-content:flex-end}.btn,button{border:0;border-radius:11px;padding:10px 12px;background:#071426;color:#fff;font-weight:750;text-decoration:none;cursor:pointer}.light{background:#e8eef5;color:#111827}.danger{background:#991b1b}.token{font-family:ui-monospace,monospace;font-size:11px;word-break:break-all;color:#64748b;margin-top:5px}@media(max-width:650px){.card{grid-template-columns:1fr}.buttons{justify-content:flex-start}.top{padding-top:calc(18px + env(safe-area-inset-top))}.wrap{padding:12px}.btn,button{flex:1;text-align:center}}</style></head><body><header class="top"><a href="{{'/mobile' if mobile else '/famiglie'}}">← Famiglie</a><h1>Accessi Famiglie</h1><p>Genera, copia o revoca il link personale di ogni allieva.</p></header><main class="wrap">{% for t in rows %}<div class="card"><div><div class="name">{{t['nome']}} {{t['cognome']}}</div><div class="muted">{{t['corso'] or 'Nessun corso'}} · {{t['email_genitore'] or t['email'] or 'email non presente'}}</div>{% if t['online_token'] %}<div class="token">Codice personale: <b style="font-size:22px;color:#071426;letter-spacing:.15em">{{t['family_pin'] if t['family_pin'] and t['family_pin']|string|length == 4 else '----'}}</b></div>{% else %}<div class="token">Accesso non ancora generato</div>{% endif %}</div><div class="buttons">{% if t['online_token'] %}<button class="light" type="button" data-copy="{{t['family_pin']}}">Copia codice</button><button class="light" type="button" data-copy="{{base}}/famiglia/{{t['family_pin']}}">Copia link atleta</button><a class="btn light" target="_blank" href="/famiglia/{{t['family_pin']}}">Apri area atleta</a><form method="post" action="/famiglie/accessi/{{t['id']}}/rigenera">{{csrf|safe}}<button>Rigenera</button></form><form method="post" action="/famiglie/accessi/{{t['id']}}/revoca">{{csrf|safe}}<button class="danger">Revoca</button></form>{% else %}<form method="post" action="/famiglie/accessi/{{t['id']}}/genera">{{csrf|safe}}<button>Genera accesso</button></form>{% endif %}</div></div>{% endfor %}</main><script>document.addEventListener('click',async e=>{let b=e.target.closest('[data-copy]');if(!b)return;try{await navigator.clipboard.writeText(b.dataset.copy);let x=b.textContent;b.textContent='Copiato ✓';setTimeout(()=>b.textContent=x,1400)}catch(_){prompt('Copia questo link',b.dataset.copy)}})</script></body></html>'''

@app.route('/famiglie/accessi')
@admin_required
def bodymind_family_accesses():
    conn=db()
    try:
        cols={r['name'] for r in conn.execute('PRAGMA table_info(tesserati)').fetchall()}
        required = {'email':'TEXT','email_genitore':'TEXT','online_token':'TEXT','family_pin':'TEXT'}
        changed_schema=False
        for col, decl in required.items():
            if col not in cols:
                conn.execute(f'ALTER TABLE tesserati ADD COLUMN {col} {decl}')
                cols.add(col); changed_schema=True
        conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_tesserati_family_pin ON tesserati(family_pin) WHERE family_pin IS NOT NULL')
        if changed_schema: conn.commit()

        active=conn.execute("SELECT id,family_pin FROM tesserati WHERE online_token IS NOT NULL AND trim(COALESCE(online_token,''))<>''").fetchall()
        used={str(r['family_pin']).strip() for r in active if str(r['family_pin'] or '').strip().isdigit() and len(str(r['family_pin'] or '').strip())==4}
        changed=False
        for r in active:
            old=str(r['family_pin'] or '').strip()
            if not (old.isdigit() and len(old)==4):
                for _ in range(20000):
                    candidate=f'{secrets.randbelow(10000):04d}'
                    if candidate not in used:
                        used.add(candidate); conn.execute('UPDATE tesserati SET family_pin=? WHERE id=?',(candidate,int(r['id']))); changed=True; break
        if changed: conn.commit()
        tid=(request.args.get('tid') or '').strip()
        if tid.isdigit(): rows=conn.execute('SELECT id,nome,cognome,corso,email,email_genitore,online_token,family_pin FROM tesserati WHERE id=?',(int(tid),)).fetchall()
        else: rows=conn.execute('SELECT id,nome,cognome,corso,email,email_genitore,online_token,family_pin FROM tesserati ORDER BY cognome,nome').fetchall()
    finally: conn.close()
    base=request.url_root.rstrip('/')
    return render_template_string(ACCESSI,rows=rows,csrf=csrf_input(),base=base,mobile=_is_mobile())

def _set_token(tid, mode):
    conn=db()
    try:
        row=conn.execute('SELECT id FROM tesserati WHERE id=?',(tid,)).fetchone()
        if not row: return redirect('/famiglie/accessi')
        cols={r['name'] for r in conn.execute('PRAGMA table_info(tesserati)').fetchall()}
        for col, decl in {'online_token':'TEXT','family_pin':'TEXT'}.items():
            if col not in cols:
                conn.execute(f'ALTER TABLE tesserati ADD COLUMN {col} {decl}')
                cols.add(col)
        conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_tesserati_family_pin ON tesserati(family_pin) WHERE family_pin IS NOT NULL')
        if mode in ('genera','rigenera'):
            token = secrets.token_urlsafe(32)
            for _ in range(100):
                pin = f'{secrets.randbelow(10000):04d}'
                if not conn.execute('SELECT 1 FROM tesserati WHERE family_pin=? AND id<>?',(pin,tid)).fetchone(): break
            else: raise RuntimeError('Impossibile generare un codice famiglia univoco')
        else:
            token = None; pin = None
        conn.execute('UPDATE tesserati SET online_token=?, family_pin=? WHERE id=?',(token,pin,tid)); conn.commit()
    finally: conn.close()
    return redirect('/famiglie/accessi?tid=%d'%tid)

@app.post('/famiglie/accessi/<int:tid>/genera')
@admin_required
def bodymind_family_generate(tid): return _set_token(tid,'genera')
@app.post('/famiglie/accessi/<int:tid>/rigenera')
@admin_required
def bodymind_family_regenerate(tid): return _set_token(tid,'rigenera')
@app.post('/famiglie/accessi/<int:tid>/revoca')
@admin_required
def bodymind_family_revoke(tid): return _set_token(tid,'revoca')
