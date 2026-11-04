"""A366 — Family Home displays a payment STATUS, not a balance.

Presentation-only adaptation of A362 PORTAL. No database writes, no tariff
changes, no automatic payment reconciliation. Does not remove amounts from
receipts or payment-provider checkout. Reuse only already validated A291 links.
"""

START = '<section id="pagamenti" class="section">'
END = '<div class="stack"><section class="panel receipts">'

PAYMENTS = '''<section id="pagamenti" class="section"><div class="section-heading"><div><h2>Pagamenti e ricevute</h2><p>Consulta lo stato della quota e i metodi di pagamento.</p></div></div>
<div class="financial-grid"><div class="stack">
<section class="panel"><div class="panel-head"><span class="bubble" aria-hidden="true">€</span><div><h3>Quota del mese corrente</h3><p>Stato aggiornato dalla segreteria BodyMind</p></div></div>
{% if quote_current.get('configured') and quote_current.get('state') in ('non_dovuto','esente','sospeso') %}
<div class="settled-card" role="status"><span class="settled-symbol" aria-hidden="true">✓</span><strong>Non dovuto</strong></div>
{% elif quote_current.get('configured') and pending_count %}
<div class="status-line" role="status"><span class="muted">Stato quota</span><strong class="status-chip unpaid">Da pagare</strong></div>
{% elif quote_current.get('configured') %}
<div class="settled-card" role="status"><span class="settled-symbol" aria-hidden="true">✓</span><strong>Pagato</strong></div>
{% else %}<p class="finance-note" role="status">In verifica con la segreteria</p>{% endif %}
</section>
<section class="panel"><div class="panel-head"><span class="bubble" aria-hidden="true">▣</span><div><h3>Come pagare</h3><p>Puoi utilizzare un link SumUp personale verificato o il bonifico.</p></div></div>
{% if pending_count and online_eligible %}
<div class="payment-box"><strong>Quota da pagare</strong><div class="method-list">
{% for pm in payment_methods %}{% if pm.url %}<a class="{{'pay-cta' if pm.key=='sumup' else 'pill'}}" href="{{pm.url}}" target="_blank" rel="noopener noreferrer nofollow" referrerpolicy="no-referrer">{{'Paga con SumUp ↗' if pm.key=='sumup' else pm.label ~ ' ↗'}}</a>{% endif %}{% endfor %}
</div><small class="method-note">Il totale esatto sarà visibile prima di confermare il pagamento online. Aprire un link non registra il pagamento.</small></div>
{% if iban %}<div class="payment-box" style="margin-top:10px"><strong>Bonifico bancario</strong><p>Intestatario: {{beneficiary or 'BodyMind Aerial Studio ASD'}} · IBAN: <code>{{iban}}</code><br>Causale: nome dell'atleta e mese {{payment_period}}.</p></div>{% endif %}
<p class="finance-note">Il bonifico risulterà pagato dopo la verifica della segreteria.</p>
{% elif pending_count %}<div class="payment-box"><strong>Da pagare</strong><p>Per il link SumUp o i dati del bonifico contatta la segreteria: non è disponibile un pagamento online già verificato per questa quota.</p></div>
{% else %}<div class="payment-box"><strong>Nessun pagamento da effettuare in questa schermata</strong><p>Per informazioni sulla tua quota, contatta la segreteria.</p></div>{% endif %}
<!-- BODYMIND_SUMUP_SLOT -->
</section></div>
'''


def replace_payment_panel(portal_html: str) -> str:
    if portal_html.count(START) != 1 or portal_html.count(END) != 1:
        raise RuntimeError('A366 expected unique family-payment anchors unavailable')
    start = portal_html.index(START)
    end = portal_html.index(END, start)
    original = portal_html[start:end]
    # No silent overwrite when template has changed after the A365 audit.
    for sentinel in ('balance-highlight', 'verified_amount', 'family', 'payment_methods'):
        if sentinel != 'family' and sentinel not in original:
            raise RuntimeError('A366 unexpected family payment template; no patch')
    return portal_html[:start] + PAYMENTS + portal_html[end:]


def install(app, portal_module):
    portal_module.PORTAL = replace_payment_panel(portal_module.PORTAL)
    print('BODYMIND A366 FAMILY DUES STATUS ONLY READY — no financial data modified', flush=True)
