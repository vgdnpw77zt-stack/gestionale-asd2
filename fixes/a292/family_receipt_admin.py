"""A292 admin UI: receipt visibility in family app; does not alter issued receipts.
Requires explicit integration at app boot, after normal authentication/CSRF setup.
"""
import re
from flask import request, abort, redirect, render_template_string
from .family_receipt_visibility import hidden, set_hidden

_RECEIPT_PATH = re.compile(r"^/app-tesserato/[^/]+/ricevuta/([0-9]+)$")

def register(app, db, admin_required, csrf_input, current_username):
    @app.before_request
    def a292_guard_hidden_family_pdf():
        if request.method not in ("GET", "HEAD"):
            return None
        m = _RECEIPT_PATH.fullmatch(request.path)
        if m is None:
            return None
        conn = db()
        try:
            if hidden(conn, int(m.group(1))):
                abort(404)
        finally:
            conn.close()

    @app.route("/amministrazione/ricevute-famiglie", methods=["GET"])
    @admin_required
    def a292_receipt_visibility_page():
        conn = db()
        try:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ricevute'").fetchone()
            rows = []
            if exists:
                cols = {r[1] for r in conn.execute("PRAGMA table_info(ricevute)")}
                if {"id", "pagamento_id"}.issubset(cols):
                    # Verified live schema: ricevute -> pagamenti -> tesserati.
                    q = """SELECT r.id, r.importo, r.descrizione, p.tesserato_id,
                                  t.nome AS tesserata_nome, t.cognome AS tesserata_cognome
                           FROM ricevute r
                           LEFT JOIN pagamenti p ON p.id=r.pagamento_id
                           LEFT JOIN tesserati t ON t.id=p.tesserato_id
                           ORDER BY r.id DESC LIMIT 100"""
                    rows = [dict(r) for r in conn.execute(q)]
                elif "id" in cols:
                    wanted = [c for c in ("id", "importo", "descrizione") if c in cols]
                    q = "SELECT " + ",".join('"' + c + '"' for c in wanted) + " FROM ricevute ORDER BY id DESC LIMIT 100"
                    rows = [dict(r) for r in conn.execute(q)]
                for row in rows:
                    row["hidden"] = hidden(conn, row["id"])
        finally:
            conn.close()
        return render_template_string("""
<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ricevute famiglie · BodyMind</title>
<style>body{font:15px system-ui;background:#0b1627;color:#f8fafc;margin:0}main{max-width:840px;margin:auto;padding:20px}article{background:#162941;border:1px solid #3b5874;padding:16px;margin:12px 0;border-radius:14px}input,button{font:inherit;padding:12px;border-radius:9px}input{width:100%;box-sizing:border-box;background:#0b1627;border:1px solid #789;color:white;margin:8px 0}button{background:#c6edff;border:0;font-weight:750}a{color:#aee0ff}</style>
</head><body><main><a href="/ricevute">← Ricevute</a><h1>Ricevute nell'App Famiglie</h1>
<p>Nascondere non cancella il documento originale, il PDF o l'incasso. Ogni azione è reversibile e tracciata.</p>
{% for r in rows %}<article><strong>Ricevuta #{{r.id}}</strong> · Tesserata: {{((r.get('tesserata_nome') or '') ~ ' ' ~ (r.get('tesserata_cognome') or ''))|trim or ('#' ~ r.get('tesserato_id')) if r.get('tesserato_id') else 'Da verificare'}} · {{r.get('importo','—')}} €
<p>{{'Nascosta alle famiglie' if r.hidden else 'Visibile se operativa'}}</p>
<form method="post" action="/amministrazione/ricevute-famiglie/{{r.id}}/visibilita">
{{csrf|safe}}<input type="hidden" name="hide" value="{{'0' if r.hidden else '1'}}">
<label>Motivo obbligatorio<input name="reason" minlength="8" maxlength="500" required></label>
<button type="submit">{{'Ripristina nell’App Famiglie' if r.hidden else 'Elimina dall’App Famiglie'}}</button>
</form></article>{% else %}<p>Nessuna ricevuta.</p>{% endfor %}
</main></body></html>""", rows=rows, csrf=csrf_input())

    @app.route("/amministrazione/ricevute-famiglie/<int:receipt_id>/visibilita", methods=["POST"])
    @admin_required
    def a292_receipt_visibility_update(receipt_id):
        hide = request.form.get("hide")
        if hide not in ("0", "1"):
            abort(400)
        conn = db()
        try:
            try:
                set_hidden(conn, receipt_id, hide == "1", request.form.get("reason"), current_username())
                conn.commit()
            except ValueError:
                conn.rollback()
                abort(400)
        finally:
            conn.close()
        return redirect("/amministrazione/ricevute-famiglie")
