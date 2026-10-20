"""Remove A291 generic payment checkout fallback on verified A293 rollout.

Generic SumUp links cannot be tied to an exact athlete/month/amount and may
cause accidental duplicate/incorrect payments. Leave individually reconciled
payment_requests entries and IBAN/office payment methods intact.
"""
import hashlib
SOURCE_SHA="89bbce5b851fec696c1a5a3f67f0494e22ad1773e3a50c7e7c4a1a865a8be2d3"
MARKER="# BODYMIND_A293_NO_GENERIC_SUMUP"
OLD="""    # Preserve the already-configured generic SumUp checkout only when there
    # is a verified unpaid balance; label clearly that it is NOT an individual
    # reconciliation link. Never treat its opening as payment confirmation.
    reminders=config.get('bodymind_reminders') if isinstance(config,dict) else {}
    reminders=reminders if isinstance(reminders,dict) else {}
    general_sumup=safe_checkout_url(reminders.get('sumup_url'),'sumup')
    if 'sumup' not in choices and general_sumup:choices['sumup']=general_sumup
"""
NEW="""    # BODYMIND_A293_NO_GENERIC_SUMUP
    # A293: only payment_requests that match athlete/month/verified outstanding
    # can be shown. A general SumUp URL must NEVER be a family checkout.
    general_sumup=''
"""

def transform(source: bytes) -> bytes:
    if hashlib.sha256(source).hexdigest()!=SOURCE_SHA:
        raise ValueError("Unknown A291 provider policy version")
    text=source.decode("utf-8")
    if text.count(OLD)!=1 or MARKER in text:raise ValueError("A291 generic checkout anchor changed")
    newtext=text.replace(OLD,NEW)
    compile(newtext,"bodymind_a291_family_methods.py","exec")
    return newtext.encode("utf-8")
