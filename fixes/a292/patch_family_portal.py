"""A292 exact-match transformation of the A291R family portal source.
Pure function: no IO, no DB writes, no deploy. Refuses unknown source versions.
"""
import hashlib

EXPECTED_A291R_SHA256 = "131fe21a57e59684ad63020d2afc10b7457cffaf14378162736f7edf4415f638"

def transform(source: bytes) -> bytes:
    if hashlib.sha256(source).hexdigest() != EXPECTED_A291R_SHA256:
        raise ValueError("Live portal source differs from verified A291R; refusing patch")
    text = source.decode("utf-8")
    a = "        # Pagamenti: schema molto variabile nelle release storiche."
    b = "        # Documenti: supporta note/notes e assenza del flag visibile."
    assert text.count(a) == text.count(b) == 1
    text = text[:text.index(a)] + "        # A292: no raw payments or technical ledger entries in family UI.\n\n" + text[text.index(b):]
    start = "{% for p in pays %}"
    end = "{% endfor %}"
    assert text.count(start) == 1
    p = text.index(start)
    q = text.index(end, p) + len(end)
    text = text[:p] + '<p class="muted">Le rettifiche interne non sono mostrate alle famiglie.</p>' + text[q:]
    needle = "from .bodymind_a250_finance_view import receipts_operational"
    assert text.count(needle) == 1
    text = text.replace(needle, needle + "\n            from .bodymind_a292_receipt_visibility import family_visible_receipts")
    needle = "rawr=receipts_operational(conn,tid=tid,limit=40)"
    assert text.count(needle) == 1
    text = text.replace(needle, "rawr=family_visible_receipts(conn,receipts_operational(conn,tid=tid,limit=40))")
    assert text.count("PORTAL,t=t,pays=pays,") == 1
    text = text.replace("PORTAL,t=t,pays=pays,", "PORTAL,t=t,")
    anchor = "app.add_url_rule('/app-tesserato/<token>/manifest.json','bodymind_manifest',bodymind_manifest,methods=['GET'])"
    assert text.count(anchor) == 1
    text = text.replace(anchor, anchor + """\n\n# A292: admin-only receipt visibility and direct download guard.
from .bodymind_a292_receipt_admin import register as _register_a292_receipts
from .core import admin_required, current_username
_register_a292_receipts(app, db, admin_required, csrf_input, current_username)""")
    return text.encode("utf-8")
