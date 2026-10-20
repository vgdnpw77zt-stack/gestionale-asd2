"""Fail-closed patch to register A293 settings after verified live A292.

Pure code transformation. It does not touch the database or filesystem.
Full release requires separate verified backups, runtime tests and rollback.
"""
import hashlib

A292_SHA256 = "59d7d068b98dd567f885c408c8a57cd4e12216a26f04295892bcf3e9827f2e7b"
REGISTRATION_ANCHOR = "_register_a292_receipts(app, db, admin_required, csrf_input, current_username)"

def transform(source: bytes) -> bytes:
    if hashlib.sha256(source).hexdigest() != A292_SHA256:
        raise ValueError("Live portal is not the verified A292 version; installation blocked")
    text=source.decode("utf-8")
    if text.count(REGISTRATION_ANCHOR)!=1:
        raise ValueError("Missing or ambiguous A292 route-registration anchor")
    if "register_a293_payment_settings" in text:
        raise ValueError("A293 already registered or unknown upgrade state")
    extra = (
      "\n\n# A293: admin payment links and audited unpaid quota corrections.\n"
      "from .a293_online_payment_settings import register as register_a293_payment_settings\n"
      "register_a293_payment_settings(app, db, admin_required, csrf_input, current_username)\n"
    )
    return text.replace(REGISTRATION_ANCHOR,REGISTRATION_ANCHOR+extra).encode("utf-8")
