"""A293 payment settings and surgical UNPAID monthly-fee editing.

Explicit integration: register(app, db, admin_required, csrf_input, current_username).
No automatic settlements, receipts, notifications, or external HTTP calls.
Core's global CSRF guard MUST be verified before enabling the POST endpoints.
"""
from datetime import datetime, timezone, date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from urllib.parse import urlsplit
from html import escape
import re
from flask import request, abort, redirect, render_template_string
import hmac, json, sqlite3

_PROVIDERS = {
    "sumup": ("sumup.com",),
    "stripe": ("stripe.com",),
    "paypal": ("paypal.com", "paypal.me"),
}

def _eur(v):
    try:
        d = Decimal(str(v))
        if not d.is_finite() or d < 0 or d != d.quantize(Decimal(".01")): raise ValueError
        return d
    except (ValueError, InvalidOperation, TypeError):
        raise ValueError("Importo non valido, usare due decimali")

def _link(v, provider):
    if provider not in _PROVIDERS or not isinstance(v, str) or len(v)>2000:
        raise ValueError("Provider o URL non valido")
    try:
        u=urlsplit(v)
        h=(u.hostname or "").lower().rstrip(".")
        valid=(u.scheme=="https" and bool(h) and not u.username and not u.password
               and u.port in (None,443) and not any(c in v for c in "\r\n\t\\")
               and any(h==d or h.endswith("."+d) for d in _PROVIDERS[provider]))
    except ValueError:
        valid=False
    if not valid: raise ValueError("Il link deve essere HTTPS sul dominio ufficiale del provider")
    return v

def _table(con,name):
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())

def _cols(con,name):
    return {r[1] for r in con.execute('PRAGMA table_info("'+name+'")')}

def _schema(con):
    con.execute("""CREATE TABLE IF NOT EXISTS bodymind_a293_providers(
        provider TEXT PRIMARY KEY, enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
        updated_by TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    con.execute("""CREATE TABLE IF NOT EXISTS bodymind_a293_offer_links(
        id INTEGER PRIMARY KEY AUTOINCREMENT, provider TEXT NOT NULL,
        tesserato_id INTEGER NOT NULL, anno INTEGER NOT NULL, mese INTEGER NOT NULL,
        importo TEXT NOT NULL, url TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1
        CHECK(active IN (0,1)), updated_by TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(provider,tesserato_id,anno,mese))""")
    con.execute("""CREATE TABLE IF NOT EXISTS bodymind_a293_admin_audit(
        id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL,
        target_type TEXT NOT NULL, target_id TEXT NOT NULL,
        old_value TEXT NOT NULL, new_value TEXT NOT NULL,
        reason TEXT NOT NULL, actor TEXT NOT NULL,
        occurred_at TEXT NOT NULL DEFAULT (datetime('now')))""")

def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def _audit(con,action,kind,ident,old,new,reason,actor):
    con.execute("""INSERT INTO bodymind_a293_admin_audit
        (action,target_type,target_id,old_value,new_value,reason,actor)
        VALUES(?,?,?,?,?,?,?)""",
        (action,kind,str(ident),json.dumps(old,sort_keys=True),json.dumps(new,sort_keys=True),reason,actor))

def _row_state(row):
    return sha256(('|'.join(str(row[k]) for k in ("id","tesserato_id","anno","mese","importo_dovuto","stato"))).encode()).hexdigest()

def _monthly_row(con,quota_id):
    if not _table(con,"quote_mensili") or not {
        "id","tesserato_id","anno","mese","importo_dovuto","stato"
    }.issubset(_cols(con,"quote_mensili")):
        raise RuntimeError("Schema quote_mensili non compatibile")
    con.row_factory=sqlite3.Row
    row=con.execute("SELECT * FROM quote_mensili WHERE id=?",(int(quota_id),)).fetchone()
    if row is None: raise ValueError("Quota inesistente")
    if int(row["mese"] or 0) not in range(1,13) or int(row["anno"] or 0)<2020:
        raise ValueError("Periodo quota non valido")
    if any(x in str(row["stato"] or "").lower() for x in
           ("esente","non_dovut","non dovut","annull","sospes","rimbors")):
        raise ValueError("Esenzione/annullamento richiede procedura distinta")
    if not con.execute("SELECT 1 FROM tesserati WHERE id=?",
                       (int(row["tesserato_id"]),)).fetchone():
        raise ValueError("Atleta inesistente")
    return row

def _has_payment(con, athlete_id, year, month):
    if not _table(con,"pagamenti"): raise RuntimeError("Tabella pagamenti mancante")
    c=_cols(con,"pagamenti")
    if not {"tesserato_id","anno","mese","causale"}.issubset(c):
        raise RuntimeError("Schema pagamenti non compatibile")
    # Conservative: any payment in the selected period blocks edits, not
    # merely 'mensile'. Older imports used multiple descriptions for dues.
    # Unknown dates on a monthly-looking row also block editing.
    return bool(con.execute("""SELECT 1 FROM pagamenti
         WHERE tesserato_id=? AND (
             (anno=? AND mese=?)
             OR ((anno IS NULL OR anno=0 OR mese IS NULL OR mese=0)
                 AND (lower(coalesce(causale,'')) LIKE '%mensil%'
                      OR lower(coalesce(causale,'')) LIKE '%quota%'))
         ) LIMIT 1""",(athlete_id,year,month)).fetchone())

def _has_open_request(con, athlete_id, year, month):
    # Old provider checkout requests can remain payable even without a
    # canonical payment entry. Fail closed before offering or editing.
    if not _table(con,"payment_requests"):return False
    required={"tesserato_id","anno","mese","status"}
    if not required.issubset(_cols(con,"payment_requests")):return True
    return bool(con.execute("""SELECT 1 FROM payment_requests
      WHERE tesserato_id=? AND anno=? AND mese=?
      AND lower(coalesce(status,'')) NOT IN
         ('paid','pagato','completed','canceled','cancelled','annullato','expired','refunded')
      AND (deleted_at IS NULL OR trim(deleted_at)='') LIMIT 1""",
      (athlete_id,year,month)).fetchone())

def _latest_monthly(con, tid, year, month):
    if not _table(con,"quote_mensili") or not {
        "id","tesserato_id","anno","mese","importo_dovuto","stato"
    }.issubset(_cols(con,"quote_mensili")):
        return None
    con.row_factory=sqlite3.Row
    return con.execute("""SELECT * FROM quote_mensili
        WHERE tesserato_id=? AND anno=? AND mese=? ORDER BY id DESC LIMIT 1""",
        (tid,year,month)).fetchone()

def _check_unpaid(con,q):
    tid,year,month=(int(q["tesserato_id"]),int(q["anno"]),int(q["mese"]))
    if _has_payment(con,tid,year,month):
        raise ValueError("Esiste una registrazione di pagamento: necessaria rettifica contabile separata")
    if _has_open_request(con,tid,year,month):
        raise ValueError("Richiesta di pagamento ancora aperta: riconciliare prima di modificare")
    if _table(con,"bodymind_a293_offer_links"):
        exists=con.execute("""SELECT 1 FROM bodymind_a293_offer_links
           WHERE tesserato_id=? AND anno=? AND mese=? LIMIT 1""",(tid,year,month)).fetchone()
        if exists: raise ValueError("Esiste un link di pagamento, anche se disattivato nel portale: verificare la revoca presso il provider e usare una procedura separata")
    return True

def safe_monthly_correction(con, *, quota_id, expected_state, new_amount, reason, actor):
    """EXPLICIT single transaction; no write to pagamenti or ricevute."""
    if not actor or not isinstance(reason,str) or not 12<=len(reason.strip())<=600:
        raise ValueError("Motivazione e operatore obbligatori")
    value=_eur(new_amount)
    con.execute("BEGIN IMMEDIATE")
    try:
        _schema(con)
        q=_monthly_row(con,quota_id)
        if not isinstance(expected_state,str) or not hmac.compare_digest(_row_state(q),expected_state):
            raise ValueError("Quota aggiornata nel frattempo: ricaricare")
        _check_unpaid(con,q)
        old=_eur(q["importo_dovuto"])
        if value==old: raise ValueError("Importo invariato")
        con.execute("UPDATE quote_mensili SET importo_dovuto=? WHERE id=?",
                    (float(value),int(q["id"])))
        _audit(con,"monthly_due_update","quota_mensile",q["id"],
               {"amount":format(old,".2f"),"period":[q["anno"],q["mese"]]},
               {"amount":format(value,".2f"),"period":[q["anno"],q["mese"]]},
               reason.strip(),actor)
        con.commit()
        return {"id":int(q["id"]),"before":format(old,".2f"),"after":format(value,".2f")}
    except BaseException:
        con.rollback()
        raise

def _reconciled_outstanding(con, tid, year, month):
    # Live adapter; fails closed when read-model does not confirm a clean debt.
    from .bodymind_a269_read_model import collect as _collect
    audited=next((r for r in _collect(con,year=int(year),month=int(month))
                 if int(r.athlete_id)==int(tid)),None)
    if (not audited or audited.state!="da_pagare" or not all((
        audited.reconciled,audited.credits_verified,audited.waivers_verified))):
        return None
    return _eur(audited.outstanding)

def eligible_offer(con, *, token_verified_tesserato_id, provider, year, month):
    """For use ONLY after established family-token authorization checks.

    Returns URL and amount, not a paid status. Re-checks canonical monthly due.
    """
    tid=int(token_verified_tesserato_id)
    if tid<=0 or provider not in _PROVIDERS or not _table(con,"bodymind_a293_offer_links"):
        return None
    flag=con.execute("SELECT enabled FROM bodymind_a293_providers WHERE provider=?",(provider,)).fetchone()
    if not flag or not bool(flag[0]): return None
    q=_latest_monthly(con,tid,int(year),int(month))
    if q is None:return None
    if any(x in str(q["stato"] or "").lower()
           for x in ("non_dovut","non dovut","esente","annull","sospes","rimbors")):return None
    try:
        if (_eur(q["importo_dovuto"])<=0 or _has_payment(con,tid,int(year),int(month))
                or _has_open_request(con,tid,int(year),int(month))):
            return None
        # A269 is the reconciled read model used by the existing A291 portal.
        outstanding=_reconciled_outstanding(con,tid,int(year),int(month))
        if outstanding is None or outstanding<=0 or outstanding!=_eur(q["importo_dovuto"]):
            return None
        link=con.execute("""SELECT url,importo FROM bodymind_a293_offer_links
          WHERE provider=? AND tesserato_id=? AND anno=? AND mese=? AND active=1""",
          (provider,tid,int(year),int(month))).fetchone()
        if not link or _eur(link["importo"])!=outstanding:return None
        return {"provider":provider,"url":_link(link["url"],provider),
                "amount":format(_eur(link["importo"]),".2f"),
                "year":int(year),"month":int(month)}
    except (ValueError,RuntimeError,sqlite3.Error,ImportError):
        return None

_STYLE="""<style>
*{box-sizing:border-box}body{font:15px system-ui;background:#09182a;color:#f1f5f9;margin:0}
main{max-width:1030px;margin:0 auto;padding:24px 14px 50px}
h1{font-size:clamp(24px,4vw,35px)}h2{font-size:21px}a{color:#a5d9ff}
section{border:1px solid #31506b;background:#12283f;border-radius:17px;padding:19px;margin:15px 0}
form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
label{display:flex;flex-direction:column;gap:5px}input,select,textarea,button{
font:inherit;color:#f8fafc;padding:12px;border-radius:9px;border:1px solid #53708c;
background:#09182a;min-width:0}button{background:#a4d9ed;color:#09243a;font-weight:800;
border:0;cursor:pointer}small{color:#bfccdc}.full{grid-column:1/-1}
.notice{color:#ffe2a1}@media(max-width:680px){form{grid-template-columns:1fr}}
</style>"""

def register(app, db, admin_required, csrf_input, current_username):
    # BODYMIND_A293_FAMILY_PAYMENT_CTA: only an already validated family
    # page, a matching pwa_token and a configured EXACT monthly SumUp link.
    # Never touch payments or receipts here. No generic provider redirects.
    @app.after_request
    def bodymind_a293_family_sumup_offer(resp):
        try:
            if request.method!="GET" or resp.status_code!=200 or resp.mimetype!="text/html":
                return resp
            m=re.fullmatch(r"/app-tesserato/([A-Za-z0-9_-]{16,256})/?",request.path)
            if not m or resp.direct_passthrough or resp.is_streamed:
                return resp
            con=db()
            try:
                if not _table(con,"tesserati") or "online_token" not in _cols(con,"tesserati"):
                    return resp
                rows=con.execute("""SELECT id FROM tesserati
                   WHERE online_token=? AND COALESCE(attivo,1)=1 LIMIT 2""",(m.group(1),)).fetchall()
                if len(rows)!=1:return resp
                tid=int(rows[0][0])
                con.execute("PRAGMA query_only=ON")
                now=date.today()
                periods=[]
                for n in range(0,4):
                    year=now.year
                    month=now.month-n
                    while month<1:
                        month+=12;year-=1
                    offer=eligible_offer(con,token_verified_tesserato_id=tid,
                                         provider="sumup",year=year,month=month)
                    if offer:periods.append(offer)
            finally:con.close()
            if not periods:return resp
            html=resp.get_data(as_text=True)
            close_tag="</main>" if "</main>" in html else "</body>" if "</body>" in html else ""
            if not close_tag:return resp
            cards=[]
            for offer in periods:
                cards.append('<div style="display:flex;align-items:center;justify-content:space-between;'
                  'flex-wrap:wrap;gap:12px;border:1px solid #536b80;background:#10283f;'
                  'border-radius:14px;padding:15px;margin:12px 0;color:white">'
                  '<span>Quota '+str(offer["month"])+'/'+str(offer["year"])+' · <b>€ '+
                  escape(offer["amount"])+'</b></span><a rel="noopener noreferrer" target="_blank" '
                  'style="display:inline-flex;align-items:center;justify-content:center;'
                  'border-radius:10px;padding:12px 18px;background:#c4eafa;color:#092035;'
                  'font-weight:800;text-decoration:none;min-height:44px" href="'+
                  escape(offer["url"],quote=True)+'">Paga con SumUp ↗</a></div>')
            snippet='<section aria-label="Pagamenti online" style="max-width:900px;margin:20px auto;'
            snippet+='padding:14px"><h2>Pagamenti online</h2>'
            snippet+=''.join(cards)
            snippet+='<small>Il pagamento viene verificato dalla segreteria; '
            snippet+='non viene registrato automaticamente aprendo il link.</small></section>'
            resp.set_data(html.replace(close_tag,snippet+close_tag,1))
            resp.headers["Cache-Control"]="private, no-store"
            resp.headers.pop("ETag",None)
            return resp
        except Exception:
            # Never disclose token, athlete, payment URL or exception in logs.
            return resp

    @app.after_request
    def bodymind_a293_settings_navigation(resp):
        # Add a visible link inside the existing settings/payment provider
        # screens. No global CSS or changes to legacy provider configuration.
        try:
            if (request.method!="GET" or resp.status_code!=200 or
                    resp.mimetype!="text/html" or request.path not in
                    ("/impostazioni","/pagamenti/provider-links","/pagamenti")):
                return resp
            html=resp.get_data(as_text=True)
            if "/impostazioni/pagamenti-online" in html:return resp
            marker="</main>" if "</main>" in html else "</body>" if "</body>" in html else ""
            if not marker:return resp
            html=html.replace(marker,
              '<div style="margin:16px auto;max-width:1080px;padding:16px;border-radius:14px;'
              'border:1px solid #54718a;background:#112a40;color:#fff">'
              '<strong>Pagamenti online e rettifiche quote</strong><p>'
              'Configura i link SumUp individuali e gestisci le quote aperte.</p>'
              '<a href="/impostazioni/pagamenti-online" style="color:#9bdcff;'
              'font-weight:800">Apri impostazioni SumUp →</a></div>'+marker,1)
            resp.set_data(html)
            resp.headers.pop("ETag",None)
            return resp
        except Exception:
            return resp

    @app.route("/impostazioni/pagamenti-online",methods=["GET"])
    @admin_required
    def bodymind_a293_settings_page():
        con=db()
        try:
            exists=_table(con,"bodymind_a293_providers")
            methods=[dict(r) for r in con.execute(
                "SELECT * FROM bodymind_a293_providers ORDER BY provider")] if exists else []
            links=[dict(r) for r in con.execute(
                "SELECT * FROM bodymind_a293_offer_links ORDER BY id DESC LIMIT 40")
            ] if _table(con,"bodymind_a293_offer_links") else []
            quotas=[dict(r) for r in con.execute(
                "SELECT q.id,q.tesserato_id,q.anno,q.mese,q.importo_dovuto,q.stato,t.nome,t.cognome "
                "FROM quote_mensili q JOIN tesserati t ON t.id=q.tesserato_id "
                "ORDER BY q.anno DESC,q.mese DESC,q.id DESC LIMIT 80")
            ] if _table(con,"quote_mensili") else []
        finally:
            con.close()
        return render_template_string("""<!doctype html><html lang="it"><head>
        <meta name="viewport" content="width=device-width,initial-scale=1"><meta charset="utf-8">
        <title>Pagamenti online · BodyMind</title>"""+_STYLE+"""</head><body><main>
        <a href="/impostazioni">← Impostazioni</a><h1>Pagamenti online</h1>
        <p>Inserisci qui i link SumUp. I link sono specifici per atleta, mese e importo.
        Non vengono registrati incassi automaticamente.</p>
        <section><h2>Attiva provider</h2>
        {% for provider in ["sumup","stripe","paypal"] %}
        <form method="post" action="/impostazioni/pagamenti-online/provider">
        {{csrf|safe}}<input type="hidden" name="provider" value="{{provider}}">
        <label>{{provider|upper}}<select name="enabled"><option value="0">Disattivato</option>
        <option value="1">Attivo (link verificati)</option></select></label>
        <button type="submit">Salva {{provider|upper}}</button></form>
        {% endfor %}
        <p><small>Attuali: {% for p in methods %}{{p.provider}} {{'ATTIVO' if p.enabled else 'disattivato'}} · {% endfor %}</small></p>
        </section>
        <section><h2>Link individuale SumUp / Stripe / PayPal</h2>
        <form method="post" action="/impostazioni/pagamenti-online/link">
        {{csrf|safe}}
        <label>Provider<select name="provider">{% for p in ['sumup','stripe','paypal'] %}
        <option value="{{p}}">{{p|upper}}</option>{% endfor %}</select></label>
        <label>Atleta (ID)<input type="number" name="tesserato_id" min="1" required></label>
        <label>Anno<input type="number" name="anno" min="2020" max="2100" required></label>
        <label>Mese<input type="number" name="mese" min="1" max="12" required></label>
        <label>Importo €<input name="importo" inputmode="decimal" placeholder="45.00" required></label>
        <label>Link HTTPS ufficiale<input name="url" type="url" maxlength="2000" required></label>
        <label>Stato<select name="active"><option value="1">Attivo</option>
        <option value="0">Disattivato</option></select></label>
        <label class="full">Motivo configurazione<input name="reason" minlength="12" required></label>
        <button class="full">Salva link verificato</button>
        </form><p class="notice">Il link non basta per registrare un pagamento.
        L'importo deve corrispondere alla quota realmente dovuta.</p></section>
        <section><h2>Ultimi link configurati</h2>
        {% for l in links %}<p>#{{l.id}} · {{l.provider}} · atleta #{{l.tesserato_id}}
        · {{l.mese}}/{{l.anno}} · € {{l.importo}} · {{'Attivo' if l.active else 'Disattivo'}}</p>
        {% else %}<p>Nessun link configurato.</p>{% endfor %}</section>
        <section><h2>Rettifica chirurgica delle quote non ancora pagate</h2>
        <p>Per pagamenti già presenti o ricevute emesse serve la procedura di rettifica contabile:
        gli originali non vengono alterati.</p>
        <p><a href="/amministrazione/rettifiche-quote">Apri rettifiche quote →</a></p>
        {% for q in quotas[:12] %}<p>#{{q.id}} · {{q.nome}} {{q.cognome}} · {{q.mese}}/{{q.anno}}
         · € {{q.importo_dovuto}}</p>{% endfor %}</section>
        </main></body></html>""",csrf=csrf_input(),methods=methods,links=links,quotas=quotas)

    @app.route("/impostazioni/pagamenti-online/provider",methods=["POST"])
    @admin_required
    def bodymind_a293_provider_save():
        p=request.form.get("provider","").lower()
        enabled=request.form.get("enabled")
        if p not in _PROVIDERS or enabled not in ("0","1"):abort(400)
        con=db()
        try:
            con.execute("BEGIN IMMEDIATE")
            _schema(con)
            con.execute("""INSERT INTO bodymind_a293_providers(provider,enabled,updated_by,updated_at)
                VALUES(?,?,?,?) ON CONFLICT(provider) DO UPDATE SET
                enabled=excluded.enabled,updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
                (p,int(enabled),current_username(),_now()))
            _audit(con,"provider_toggle","provider",p,{},{"enabled":enabled},
                   "Modifica impostazione pagamento",current_username())
            con.commit()
        except BaseException:con.rollback();raise
        finally:con.close()
        return redirect("/impostazioni/pagamenti-online")

    @app.route("/impostazioni/pagamenti-online/link",methods=["POST"])
    @admin_required
    def bodymind_a293_link_save():
        con=db()
        try:
            p=str(request.form.get("provider") or "").lower()
            tid=int(request.form.get("tesserato_id") or 0)
            year=int(request.form.get("anno") or 0)
            month=int(request.form.get("mese") or 0)
            amt=_eur(request.form.get("importo"))
            url=_link(request.form.get("url"),p)
            active=request.form.get("active")
            reason=str(request.form.get("reason") or "").strip()
            if tid<=0 or year<2020 or year>2100 or month not in range(1,13) or active not in ("0","1") or len(reason)<12:
                abort(400)
            con.execute("BEGIN IMMEDIATE")
            _schema(con)
            q=_latest_monthly(con,tid,year,month)
            if q is None or _eur(q["importo_dovuto"])!=amt or amt<=0:
                raise ValueError("Quota positiva con importo corrispondente non trovata")
            if not con.execute("SELECT 1 FROM tesserati WHERE id=?",(tid,)).fetchone():
                raise ValueError("Atleta inesistente")
            # Even when saving disabled links, avoid stale unverified amounts.
            if active=="1":_check_unpaid(con,q)
            # A shared/reusable link cannot be safely matched back to one
            # athlete and due period. Reject duplicates across obligations.
            shared=con.execute("""SELECT 1 FROM bodymind_a293_offer_links
              WHERE url=? AND NOT (provider=? AND tesserato_id=? AND anno=? AND mese=?)
              LIMIT 1""",(url,p,tid,year,month)).fetchone()
            if shared: raise ValueError("Link già associato a un'altra atleta/periodo: usare un link individuale")
            old=con.execute("""SELECT url,importo,active FROM bodymind_a293_offer_links
              WHERE provider=? AND tesserato_id=? AND anno=? AND mese=?""",(p,tid,year,month)).fetchone()
            con.execute("""INSERT INTO bodymind_a293_offer_links
              (provider,tesserato_id,anno,mese,importo,url,active,updated_by,updated_at)
              VALUES(?,?,?,?,?,?,?,?,?)
              ON CONFLICT(provider,tesserato_id,anno,mese) DO UPDATE SET
              importo=excluded.importo,url=excluded.url,active=excluded.active,
              updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
              (p,tid,year,month,format(amt,".2f"),url,int(active),current_username(),_now()))
            _audit(con,"payment_link_set","athlete_period",f"{tid}:{year}:{month}:{p}",
                   dict(old) if old else {},{"amount":format(amt,".2f"),"active":active,"provider":p},
                   reason,current_username())
            con.commit()
        except (ValueError,sqlite3.Error) as exc:
            con.rollback();abort(400,description=str(exc))
        finally:con.close()
        return redirect("/impostazioni/pagamenti-online")

    @app.route("/amministrazione/rettifiche-quote",methods=["GET"])
    @admin_required
    def bodymind_a293_quota_list():
        con=db()
        try:
            if not _table(con,"quote_mensili"):rows=[]
            else:
                rows=[dict(r) for r in con.execute("""SELECT q.id,q.tesserato_id,q.anno,q.mese,
                    q.importo_dovuto,q.stato,t.nome,t.cognome FROM quote_mensili q
                    JOIN tesserati t ON t.id=q.tesserato_id
                    ORDER BY q.anno DESC,q.mese DESC,q.id DESC LIMIT 100""")]
            for row in rows:
                row["etag"]=_row_state(row)
        finally:con.close()
        return render_template_string("""<!doctype html><html lang="it"><head>
        <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
        <title>Rettifiche quote · BodyMind</title>"""+_STYLE+"""</head><body><main>
        <a href="/impostazioni/pagamenti-online">← Pagamenti online</a><h1>Rettifiche quote</h1>
        <p>Modifiche soltanto su quote mensili senza pagamenti e senza precedenti link di pagamento.
        Ogni variazione è tracciata. Le ricevute emesse restano intatte.</p>
        {% for q in rows %}
        <section><b>{{q.nome}} {{q.cognome}} · quota #{{q.id}} · {{q.mese}}/{{q.anno}}</b>
        <p>Importo attuale: € {{q.importo_dovuto}} · Stato: {{q.stato}}</p>
        <form method="post" action="/amministrazione/rettifiche-quote/{{q.id}}/anteprima">
        {{csrf|safe}}<input type="hidden" name="expected_state" value="{{q.etag}}">
        <label>Nuovo importo<input name="importo" inputmode="decimal" required></label>
        <label>Motivazione<input name="reason" minlength="12" maxlength="600" required></label>
        <button class="full">Mostra anteprima e verifica</button></form></section>
        {% else %}<p>Nessuna quota mensile disponibile.</p>{% endfor %}
        </main></body></html>""",csrf=csrf_input(),rows=rows)

    @app.route("/amministrazione/rettifiche-quote/<int:quota_id>/anteprima",methods=["POST"])
    @admin_required
    def bodymind_a293_quota_preview(quota_id):
        con=db()
        try:
            q=_monthly_row(con,quota_id)
            etag=request.form.get("expected_state","")
            if not hmac.compare_digest(etag,_row_state(q)):
                abort(409,description="Quota aggiornata nel frattempo")
            _check_unpaid(con,q)
            old=_eur(q["importo_dovuto"])
            new=_eur(request.form.get("importo"))
            if new==old:abort(400,description="Importo invariato")
            reason=str(request.form.get("reason") or "").strip()
            if not 12<=len(reason)<=600:abort(400)
            delta=new-old
        except (ValueError,RuntimeError) as exc:
            abort(409,description=str(exc))
        finally:con.close()
        return render_template_string("""<!doctype html><html lang="it"><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <title>Conferma rettifica · BodyMind</title>"""+_STYLE+"""</head><body><main>
        <a href="/amministrazione/rettifiche-quote">← Annulla senza modifiche</a>
        <h1>Anteprima rettifica mensile</h1><section>
        <p>Atleta #{{tid}} · periodo {{month}}/{{year}} · quota #{{quota_id}}</p>
        <p>Importo precedente: <strong>€ {{old}}</strong></p>
        <p>Nuovo importo: <strong>€ {{new}}</strong></p>
        <p>Differenza: <strong>€ {{delta}}</strong></p>
        <p>Motivazione: {{reason}}</p>
        <p class="notice">Verificato: nessun pagamento e nessun link associato.
        Questa operazione NON modifica ricevute, pagamenti o documenti.</p>
        <form method="post" action="/amministrazione/rettifiche-quote/{{quota_id}}">
        {{csrf|safe}}
        <input type="hidden" name="expected_state" value="{{etag}}">
        <input type="hidden" name="importo" value="{{new}}">
        <input type="hidden" name="reason" value="{{reason}}">
        <button class="full">Conferma e registra rettifica</button></form>
        </section></main></body></html>""",quota_id=int(q["id"]),
        tid=int(q["tesserato_id"]),year=int(q["anno"]),month=int(q["mese"]),
        old=format(old,".2f"),new=format(new,".2f"),
        delta=format(delta,"+.2f"),reason=reason,etag=etag,csrf=csrf_input())

    @app.route("/amministrazione/rettifiche-quote/<int:quota_id>",methods=["POST"])
    @admin_required
    def bodymind_a293_quota_update(quota_id):
        con=db()
        try:
            safe_monthly_correction(con,quota_id=quota_id,
                expected_state=request.form.get("expected_state"),
                new_amount=request.form.get("importo"),reason=request.form.get("reason"),
                actor=current_username())
        except (ValueError,RuntimeError,sqlite3.Error) as exc:
            abort(409,description=str(exc))
        finally:con.close()
        return redirect("/amministrazione/rettifiche-quote")
