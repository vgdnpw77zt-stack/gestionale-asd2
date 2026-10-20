"""Compose an individualized family reminder after verified recipient resolution.

This pure module NEVER resolves tokens from names, calls SMS/email providers,
queries real athlete records or sends anything. A verified family credential is
provided by the existing authorized per-athlete access service.
"""
from dataclasses import dataclass
from urllib.parse import urlsplit
import re

_TOKEN=re.compile(r"^[A-Za-z0-9_-]{16,256}$")
_CODE=re.compile(r"^[A-Za-z0-9_-]{4,128}$")
_HOST="app.bodymindaerialstudio.life"

@dataclass(frozen=True)
class ReminderDraft:
    recipient: str
    channel: str
    body: str
    tesserato_id: int
    # Treat body as secret: contains family token and possibly family code.

def build_family_reminder(*, tesserato_id, resolved_tesserato_id, verified_recipient,
                          verified_channel, family_url, existing_family_code,
                          consent_or_lawful_basis, recipient_matches_athlete,
                          pending_due_verified, already_paid, period_label,
                          amount_eur):
    """Use existing credentials only after caller verifies athlete and recipient.

    Never put ReminderDraft.body into bulk reports, debug logs, or analytics.
    An explicit dispatch action and idempotent per-recipient audit are required
    outside this function before any message is sent.
    """
    if not (consent_or_lawful_basis and recipient_matches_athlete
            and pending_due_verified and not already_paid):
        return None
    try:
        tid=int(tesserato_id)
        resolved=int(resolved_tesserato_id)
    except (TypeError,ValueError):
        return None
    if tid<=0 or resolved!=tid:return None
    recipient=str(verified_recipient or "").strip()
    channel=str(verified_channel or "").strip().lower()
    if channel not in ("sms","email","whatsapp") or not recipient or len(recipient)>254:
        return None
    code=str(existing_family_code or "").strip()
    if not _CODE.fullmatch(code): return None
    if not isinstance(family_url,str) or len(family_url)>500:return None
    try:
        parsed=urlsplit(family_url)
        token=parsed.path.removeprefix("/app-tesserato/").rstrip("/")
        valid=(parsed.scheme=="https" and parsed.hostname==_HOST
             and parsed.username is None and parsed.password is None
             and parsed.port in (None,443)
             and not parsed.query and not parsed.fragment
             and parsed.path.startswith("/app-tesserato/") and _TOKEN.fullmatch(token))
    except (ValueError,AttributeError):
        valid=False
    if not valid:return None
    if not isinstance(period_label,str) or not 3<=len(period_label.strip())<=70:
        return None
    try:
        from decimal import Decimal
        amount=Decimal(str(amount_eur))
        if not amount.is_finite() or amount<=0 or amount!=amount.quantize(Decimal(".01")):
            return None
    except Exception:
        return None
    body=(
        f"BodyMind Aerial Studio – promemoria quota {period_label.strip()}: "
        f"€ {amount:.2f}.\n"
        f"App Famiglie personale: {family_url}\n"
        f"Codice di accesso: {code}\n"
        "Se hai già effettuato il pagamento, contatta la segreteria "
        "per la verifica prima di ripetere il pagamento."
    )
    return ReminderDraft(recipient,channel,body,tid)
