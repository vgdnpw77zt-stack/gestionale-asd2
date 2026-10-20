"""Pure, SHA-pinned adaptation of existing /promemoria/whatsapp preview.

No automatic sends. The existing operator manually clicks WhatsApp.
Only inject unique existing family PIN + canonical landing URL for a verified
athlete/phone association. Unverified recipient or PIN disables the send link.
"""
import hashlib
SOURCE_SHA = "0fa38cbedb459d68fac9424fa9a92fb44816c4f832249419e743df464b2c6281"
MARKER = "BODYMIND_A293_VERIFIED_FAMILY_REMINDER"
EXACT = '            msg = _a17_message_for_task(t, mese, anno)\n            wa = f"https://wa.me/{phone}?text={quote(msg, safe=\'\')}" if phone else ""'

HELPER = '''
# BODYMIND_A293_VERIFIED_FAMILY_REMINDER
# Never send a family PIN to an unverified recipient. The existing WhatsApp
# view is a MANUAL preview, not an automated messaging pipeline.
def _a293_reminder_family_access(conn, athlete_id, selected_phone):
    try:
        tid=int(athlete_id or 0)
        if tid<=0 or not selected_phone:return ""
        row=conn.execute("""
            SELECT id,family_pin,online_token,minorenne,telefono,telefono_genitore
            FROM tesserati WHERE id=? AND COALESCE(attivo,1)=1
            """,(tid,)).fetchone()
        if not row:return ""
        keys=set(row.keys())
        code=str(row['family_pin'] or '').strip()
        token=str(row['online_token'] or '').strip()
        if not (code.isdigit() and len(code)==4 and len(token)>=16):return ""
        if conn.execute("SELECT count(*) FROM tesserati WHERE family_pin=?",(code,)).fetchone()[0]!=1:
            return ""
        if conn.execute("SELECT count(*) FROM tesserati WHERE online_token=?",(token,)).fetchone()[0]!=1:
            return ""
        target=_a17_clean_phone(selected_phone)
        parent=_a17_clean_phone(row['telefono_genitore'] or '')
        athlete=_a17_clean_phone(row['telefono'] or '')
        is_minor=bool(int(row['minorenne'] or 0))
        if is_minor:
            if not parent or parent!=target:return ""
        elif not target or target not in (parent,athlete):
            return ""
        # Never put the secret opaque online_token in WhatsApp URL or audit
        # logs. The short PIN is personal but transmitted ONLY to validated
        # family/athlete contact with explicit user click.
        return " App Famiglie: https://app.bodymindaerialstudio.life/area-famiglie — Codice personale: "+code+"."
    except Exception:
        return ""
'''

def transform(source: bytes) -> bytes:
    if hashlib.sha256(source).hexdigest()!=SOURCE_SHA:
        raise ValueError("Unexpected production reminders SHA; refusing patch")
    text=source.decode("utf-8")
    if MARKER in text or text.count(EXACT)!=1:
        raise ValueError("Unexpected reminders location; refusing patch")
    needle='def _a17_phone_for_tesserato(conn, tid: int) -> str:'
    if text.count(needle)!=1:
        raise ValueError("Missing known reminder phone helper")
    replacement=(
      '            msg = _a17_message_for_task(t, mese, anno)\n'
      '            family_ref = _a293_reminder_family_access(conn, tid, phone)\n'
      '            if family_ref:\n'
      '                msg += family_ref\n'
      '            else:\n'
      '                msg += " [Invio sospeso: verificare codice App Famiglie e recapito in scheda atleta.]"\n'
      '            wa = f"https://wa.me/{phone}?text={quote(msg, safe=\'\')}" if phone and family_ref else ""'
    )
    out=text.replace(needle,HELPER+'\n'+needle,1).replace(EXACT,replacement,1).encode("utf-8")
    compile(out,"routes_promemoria.py","exec")
    return out
