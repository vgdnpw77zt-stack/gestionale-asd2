"""A293: side-effect-free family payment offer and reminder policy.

Not wired to live Flask routes. No credentials, DB writes, checkout creation,
messages, payment settlements, or outbound HTTP calls.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit
import re

_ALLOWED_PROVIDERS = frozenset(("sumup", "stripe", "paypal"))
_ACCESS_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{16,256}$")


@dataclass(frozen=True)
class FamilyPaymentOffer:
    eligible: bool
    reason: str
    provider: str = ""
    checkout_url: str = ""
    amount_eur: str = ""


def _amount(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not amount.is_finite() or amount < 0 or amount != amount.quantize(Decimal("0.01")):
        return None
    return amount


def _safe_link(value):
    if not isinstance(value, str) or len(value) > 2048:
        return False
    try:
        parts = urlsplit(value)
        return (parts.scheme == "https" and bool(parts.hostname)
                and parts.username is None and parts.password is None
                and parts.port in (None, 443)
                and not any(c in value for c in "\r\n\t\\")
                and parts.hostname not in ("localhost", "127.0.0.1", "::1"))
    except (ValueError, AttributeError):
        return False


def family_payment_offer(*, provider, enabled, checkout_url, amount_due,
                         athlete_matches, season_matches, paid, canceled,
                         configured_amount=None):
    """Return a link only when backed by an athlete/period/amount-specific obligation.

    A provider's generic payment link is NOT sufficient evidence that the
    amount and athlete match; caller must provide these verified booleans.
    No internal payment or receipt may be marked paid by opening the URL.
    """
    provider = str(provider or "").strip().lower()
    due = _amount(amount_due)
    expected = _amount(configured_amount)
    if not enabled or provider not in _ALLOWED_PROVIDERS:
        return FamilyPaymentOffer(False, "provider_disabled")
    if paid or canceled:
        return FamilyPaymentOffer(False, "not_payable")
    if due is None or due <= 0:
        return FamilyPaymentOffer(False, "no_positive_due")
    if not athlete_matches or not season_matches:
        return FamilyPaymentOffer(False, "scope_mismatch")
    if expected is None or expected != due:
        return FamilyPaymentOffer(False, "amount_mismatch")
    if not _safe_link(checkout_url):
        return FamilyPaymentOffer(False, "invalid_link")
    return FamilyPaymentOffer(True, "verified_link_only", provider, checkout_url,
                              format(due, ".2f"))


def reminder_access_reference(*, access_code, access_url, consent_verified,
                              recipient_verified, audience_matches):
    """Never invent or regenerate family tokens; use an existing valid reference.

    A reminder MUST be sent by the application's established authenticated
    notification pipeline, with opt-in/recipient safeguards applied there.
    This function does NOT send anything.
    """
    if not (consent_verified and recipient_verified and audience_matches):
        return None
    code = str(access_code or "")
    if not _ACCESS_CODE_RE.fullmatch(code) or not _safe_link(access_url):
        return None
    return {"access_url": access_url, "access_code": code}
