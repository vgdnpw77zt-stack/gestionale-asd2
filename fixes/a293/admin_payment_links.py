"""A293 staged admin page for individual manual checkout links.
Registration is explicit and requires app CSRF middleware and authoritative tenant.
"""
from datetime import date
from flask import request, abort, redirect, render_template_string
from .manual_payment_links import save_link, disable_link

_HTML = """
<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>BodyMind · Link pagamenti famiglie</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#0a1727;color:#f2f6ff;font:15px system-ui}
main{max-width:1000px;margin:auto;padding:16px 14px 80px}h1{font-size:clamp(22px,3vw,34px)}
p,small{color:#b8c8db}a{color:#b8e5ff}.panel{background:#142a42;border:1px solid #34516e;
border-radius:16px;padding:18px;margin:14px 0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
label{display:block;font-weight:700}input,select,button{font:inherit;border-radius:10px;min-height:44px;padding:10px}
input,select{display:block;width:100%;min-width:0;margin-top:5px;background:#0b1b30;
color:#fff;border:1px solid #9baec2}button{border:0;background:#c9edfb;color:#081b2c;font-weight:800;
cursor:pointer}.item{border-radius:12px;background:#0d2439;padding:12px;margin:9px 0}
@media(max-width:700px){.grid{grid-template-columns:1fr}.panel{padding:12px}}
</style></head><body><main>
<a href="/impostazioni/pagamenti">← Impostazioni pagamenti</a>
<h1>Link di pagamento per atleta</h1>
<p>Ogni link è per una singola atleta, mese e importo. Creare prima il link dal proprio provider,
poi inserirlo qui. Un link non equivale a un pagamento ricevuto.</p>
<section class="panel"><h2>Imposta link individuale</h2><form method="post">
{{csrf|safe}}<input type="hidden" name="action" value="save">
<div class="grid">
<label>Atleta<select name="athlete_id" required><option value="">Scegli atleta</option>
{% for a in athletes %}<option value="{{a['id']}}">{{a['cognome']}} {{a['nome']}} (#{{a['id']}})</option>{% endfor %}
</select></label>
<label>Provider<select name="provider" required><option value="sumup">SumUp</option>
<option value="stripe">Stripe</option><option value="paypal">PayPal</option></select></label>
<label>Mese / anno<input name="period" type="month" value="{{period}}" required></label>
<label>Tipologia<select name="kind"><option value="mensile">Quota mensile</option>
<option value="iscrizione">Iscrizione</option><option value="evento">Evento</option></select></label>
<label>Importo verificato (€)<input name="amount" inputmode="decimal" placeholder="50,00" required></label>
<label>Link ufficiale HTTPS<input name="url" type="url" placeholder="https://pay.sumup.com/..." required></label>
</div><p><button type="submit">Salva link</button></p></form></section>
<section class="panel"><h2>Link registrati</h2>
{% for r in rows %}<div class="item">
<strong>#{{r['athlete_id']}} · {{r['period']}} · {{r['kind']}}</strong>
<small> · {{r['provider']}} · € {{'%0.2f'|format(r['amount_cents']/100)}}
 · {{'Attivo' if r['active'] else 'Disattivato'}}</small>
<form method="post">{{csrf|safe}}<input type="hidden" name="action" value="disable">
<input type="hidden" name="athlete_id" value="{{r['athlete_id']}}">
<input type="hidden" name="period" value="{{r['period']}}">
<input type="hidden" name="kind" value="{{r['kind']}}">
<button type="submit" {% if not r['active'] %}disabled{% endif %}>Disattiva link</button>
</form></div>{% else %}<p>Nessun link configurato.</p>{% endfor %}
</section><p>Mostrare “Paga” nell'App Famiglie soltanto dopo conferma del residuo dovuto.</p>
</main></body></html>
"""

def register(app, db, admin_required, csrf_input, current_username, tenant_slug):
    """Requires core auth/CSRF; tenant_slug() MUST come from authenticated server context."""
    if not all(callable(f) for f in (db, admin_required, csrf_input, current_username, tenant_slug)):
        raise ValueError("Missing secure Flask integration")
    @app.route("/amministrazione/link-pagamento-famiglie", methods=["GET","POST"])
    @admin_required
    def a293_admin_payment_links():
        slug=tenant_slug()
        if not isinstance(slug,str) or not slug:
            abort(403)
        conn=db()
        try:
            if request.method == "POST":
                try:
                    args=dict(tenant_slug=slug, athlete_id=request.form.get("athlete_id"),
                              period=request.form.get("period"), kind=request.form.get("kind"),
                              operator=current_username())
                    action=request.form.get("action")
                    if action == "save":
                        save_link(conn, **args, provider=request.form.get("provider"),
                                  amount=request.form.get("amount"), url=request.form.get("url"))
                    elif action == "disable":
                        disable_link(conn, **args)
                    else:
                        raise ValueError("Unknown action")
                    conn.commit()
                except (ValueError,TypeError):
                    conn.rollback()
                    abort(400)
                return redirect("/amministrazione/link-pagamento-famiglie")
            athletes=[dict(r) for r in conn.execute("SELECT id,nome,cognome FROM tesserati ORDER BY cognome,nome")]
            exists=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bodymind_a293_payment_links'").fetchone()
            rows=[dict(r) for r in conn.execute("""SELECT athlete_id,period,kind,provider,amount_cents,active
                FROM bodymind_a293_payment_links WHERE tenant_slug=? ORDER BY updated_at DESC LIMIT 150""",
                (slug,))] if exists else []
        finally:
            conn.close()
        return render_template_string(_HTML, csrf=csrf_input(), athletes=athletes,
                                      rows=rows, period=date.today().strftime("%Y-%m"))
