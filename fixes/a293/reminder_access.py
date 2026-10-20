"""A293: build personalized reminders only; no network delivery or PIN rotation.

Existing reminder automation must check verified destination, consent and channel.
Do not print PINs, contact details or the generated message in logs.
"""
import re
from urllib.parse import quote

_PIN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$")
_FAMILY_BASE = "https://app.bodymindaerialstudio.life"

def family_access_url(pin):
    pin = str(pin or "").strip()
    if not _PIN.fullmatch(pin):
        raise ValueError("Codice famiglia assente o non valido")
    return _FAMILY_BASE + "/famiglia/" + quote(pin, safe="")

def compose_reminder(*, athlete_label, family_pin, subject, is_minor,
                     recipient_role, contact_checked, send_consent, payment_url=None):
    """The authenticated caller MUST provide canonical athlete PIN, not user input."""
    role = "guardian" if is_minor is True else "athlete"
    if recipient_role != role or contact_checked is not True or send_consent is not True:
        raise ValueError("Destinatario/consenso non verificato: invio bloccato")
    label = " ".join(str(athlete_label or "").split())
    subject = " ".join(str(subject or "").split())
    if not label or not subject or len(label) > 160 or len(subject) > 180:
        raise ValueError("Promemoria incompleto")
    url = family_access_url(family_pin)
    msg = ("BodyMind Aerial Studio\\nPromemoria per " + label + ": " + subject +
           ".\\nCodice personale App Famiglie: " + str(family_pin).strip() +
           "\\nAccesso: " + url)
    if payment_url:
        from .manual_payment_links import validate_url
        candidates = ("sumup", "stripe", "paypal")
        for provider in candidates:
            try:
                safe_url = validate_url(payment_url, provider)
            except ValueError:
                continue
            msg += "\\nPagamento online, se ancora dovuto: " + safe_url
            break
        else:
            raise ValueError("Link di pagamento non ufficiale")
    return msg
