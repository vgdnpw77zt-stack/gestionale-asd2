"""A293 staged manual payment links. No writes to pagamenti, ricevute or quote."""
import hashlib
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

_ALLOWED_HOSTS = {
    "sumup": {"pay.sumup.com", "checkout.sumup.com", "pay.sumup.me", "sumup.me"},
    "stripe": {"buy.stripe.com", "checkout.stripe.com"},
    "paypal": {"paypal.me", "www.paypal.com", "www.paypal.me"},
}
_KINDS = {"mensile", "iscrizione", "evento"}
_PERIOD = re.compile(r"^20\\d{2}-(0[1-9]|1[0-2])$")
_TENANT = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

def amount_to_cents(value):
    if isinstance(value, (float, bool)):
        raise ValueError("Importo non preciso")
    try:
        d = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        raise ValueError("Importo non valido") from None
    if not d.is_finite() or not (0 < d <= 10000) or d * 100 != (d * 100).to_integral_value():
        raise ValueError("Importo fuori limite o con troppi decimali")
    return int(d * 100)

def validate_url(raw, provider):
    provider = str(provider or "").strip().lower()
    if provider not in _ALLOWED_HOSTS:
        raise ValueError("Provider non valido")
    url = str(raw or "").strip()
    if len(url) > 1800 or any(ord(ch) < 33 or ord(ch) > 126 for ch in url):
        raise ValueError("URL non valido")
    try:
        p = urlsplit(url)
        port_ok = p.port in (None, 443)
    except ValueError:
        raise ValueError("URL non valido") from None
    if (p.scheme != "https" or not port_ok or p.username or p.password or
            p.hostname not in _ALLOWED_HOSTS[provider] or not p.path.strip("/") or p.fragment):
        raise ValueError("Richiesto URL HTTPS ufficiale del provider")
    return url

def _keys(tenant_slug, athlete_id, period, kind):
    slug = str(tenant_slug or "").strip().lower()
    if not _TENANT.fullmatch(slug):
        raise ValueError("Tenant non valido")
    try:
        tid = int(athlete_id)
    except (TypeError, ValueError):
        raise ValueError("Atleta non valido") from None
    if tid <= 0 or not _PERIOD.fullmatch(str(period or "")) or kind not in _KINDS:
        raise ValueError("Atleta, mese o tipo non validi")
    return slug, tid, str(period), kind

def ensure_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bodymind_a293_payment_links(
        tenant_slug TEXT NOT NULL, athlete_id INTEGER NOT NULL,
        period TEXT NOT NULL, kind TEXT NOT NULL, provider TEXT NOT NULL,
        amount_cents INTEGER NOT NULL CHECK(amount_cents>0),
        checkout_url TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1 CHECK(active IN(0,1)),
        updated_by TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY(tenant_slug,athlete_id,period,kind))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS bodymind_a293_payment_links_audit(
        id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_slug TEXT NOT NULL,
        athlete_id INTEGER NOT NULL, period TEXT NOT NULL, kind TEXT NOT NULL,
        action TEXT NOT NULL, provider TEXT, amount_cents INTEGER, url_sha256 TEXT,
        operator TEXT NOT NULL, timestamp TEXT NOT NULL DEFAULT (datetime('now')))""")

def save_link(conn, *, tenant_slug, athlete_id, period, kind, provider, amount, url, operator):
    """Admin only + real CSRF, caller owns transaction; does not create a payment."""
    slug, tid, period, kind = _keys(tenant_slug, athlete_id, period, kind)
    actor = str(operator or "").strip()
    if not actor or len(actor) > 120:
        raise ValueError("Operatore mancante")
    cents = amount_to_cents(amount)
    url = validate_url(url, provider)
    if not conn.execute("SELECT 1 FROM tesserati WHERE id=?", (tid,)).fetchone():
        raise ValueError("Atleta assente")
    ensure_schema(conn)
    conn.execute("""INSERT INTO bodymind_a293_payment_links
        (tenant_slug,athlete_id,period,kind,provider,amount_cents,checkout_url,active,updated_by)
        VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(tenant_slug,athlete_id,period,kind)
        DO UPDATE SET provider=excluded.provider,amount_cents=excluded.amount_cents,
          checkout_url=excluded.checkout_url,active=1,updated_by=excluded.updated_by,
          updated_at=datetime('now')""",
        (slug, tid, period, kind, provider, cents, url, 1, actor))
    conn.execute("""INSERT INTO bodymind_a293_payment_links_audit
        (tenant_slug,athlete_id,period,kind,action,provider,amount_cents,url_sha256,operator)
        VALUES(?,?,?,?,?,?,?,?,?)""",
        (slug, tid, period, kind, "save", provider, cents, hashlib.sha256(url.encode()).hexdigest(), actor))

def disable_link(conn, *, tenant_slug, athlete_id, period, kind, operator):
    slug, tid, period, kind = _keys(tenant_slug, athlete_id, period, kind)
    actor = str(operator or "").strip()
    if not actor:
        raise ValueError("Operatore mancante")
    ensure_schema(conn)
    conn.execute("""UPDATE bodymind_a293_payment_links SET active=0,updated_by=?,
        updated_at=datetime('now') WHERE tenant_slug=? AND athlete_id=? AND period=? AND kind=?""",
        (actor,slug,tid,period,kind))
    conn.execute("""INSERT INTO bodymind_a293_payment_links_audit
        (tenant_slug,athlete_id,period,kind,action,operator) VALUES(?,?,?,?,?,?)""",
        (slug,tid,period,kind,"disable",actor))

def family_link(conn, *, tenant_slug, athlete_id, period, kind, due):
    """The caller must verify family access and supply canonical due from core.
    due={'verified':True,'unpaid_cents':NN,'paid':False,'cancelled':False}
    """
    slug, tid, period, kind = _keys(tenant_slug, athlete_id, period, kind)
    if (not isinstance(due, dict) or due.get("verified") is not True or
            due.get("paid") is not False or due.get("cancelled") is not False):
        return None
    exists = conn.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
        AND name='bodymind_a293_payment_links'""").fetchone()
    if not exists:
        return None
    r = conn.execute("""SELECT provider,amount_cents,checkout_url,active FROM
        bodymind_a293_payment_links WHERE tenant_slug=? AND athlete_id=? AND period=? AND kind=?""",
        (slug,tid,period,kind)).fetchone()
    if not r or r[3] != 1 or int(due.get("unpaid_cents") or 0) != int(r[1]):
        return None
    try:
        url = validate_url(r[2],r[0])
    except ValueError:
        return None
    return {"provider":r[0],"amount_cents":int(r[1]),"checkout_url":url}
