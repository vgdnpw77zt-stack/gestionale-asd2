"""Apply safe reminder-policy settings to a STAGING clone only.

Integrates with existing GET/POST of /motore-automazioni; never sends messages.
Conflicts fail closed instead of guessing at user data or route structure.
"""
from pathlib import Path
import argparse, ast, json

MARKER='BODYMIND_A269_REMINDER_SETTINGS'  # BODYMIND_A270_DUE10_WA_PHONE

def patch(root: Path):
    target=root/'routes_automation_pro.py'
    original=target.read_text(encoding='utf-8')
    if MARKER in original:return {'changed':False}
    source=original
    old="    auto_cfg = cfg.setdefault('automation_engine', {})\n    saved = False"
    new="""    auto_cfg = cfg.setdefault('automation_engine', {})
    # BODYMIND_A269_REMINDER_SETTINGS: no provider send is implied by saving these values.
    from .bodymind_a269_reminders import Policy, normalized_phone
    reminder_cfg = dict(cfg.get('bodymind_reminders') or {})
    reminder_error = ''
    saved = False"""
    if source.count(old)!=1:raise RuntimeError('STOP: automation config anchor changed')
    source=source.replace(old,new,1)
    old="""        cfg['automation_engine'] = auto_cfg
        save_config(cfg)
        saved = True"""
    new="""        try:
            day_raw = (request.form.get('bm_reminder_due_day') or '').strip()
            business_phone_raw = (request.form.get('bm_reminder_whatsapp_business_phone') or '').strip()
            business_phone = normalized_phone(business_phone_raw) if business_phone_raw else ''
            if business_phone_raw and not business_phone:
                raise ValueError('Numero WhatsApp Business non valido')
            candidate = Policy(
                due_day=int(day_raw) if day_raw else 10,
                before_days=int(request.form.get('bm_reminder_before') or '7'),
                repeat_days=int(request.form.get('bm_reminder_repeat') or '3'),
                max_attempts=int(request.form.get('bm_reminder_max') or '3'),
                enabled=bool(request.form.get('bm_reminder_enabled')),
                sumup_url=(request.form.get('bm_reminder_sumup_url') or '').strip(),
            )
            reminder_cfg = dict(due_day=candidate.due_day,before_days=candidate.before_days,
                                repeat_days=candidate.repeat_days,max_attempts=candidate.max_attempts,
                                enabled=candidate.enabled,sumup_url=candidate.sumup_url,
                                whatsapp_business_phone=business_phone)
        except (ValueError, TypeError) as exc:
            reminder_error = 'Promemoria non salvati: ' + str(exc)
        if not reminder_error:
            cfg['bodymind_reminders'] = reminder_cfg
            cfg['automation_engine'] = auto_cfg
            save_config(cfg)
            saved = True"""
    if source.count(old)!=1:raise RuntimeError('STOP: save path changed')
    source=source.replace(old,new,1)
    old="""    saved_msg = "<div class='pro-alert success'>Decisioni del Motore salvate. Risolvi in automatico userà queste regole: non forzerà aree spente o impostate su manuale.</div>" if saved else """""
    new="""    saved_msg = "<div class='pro-alert success'>Impostazioni salvate. Il promemoria WhatsApp resta una bozza: nessun invio automatico abilitato.</div>" if saved else ""
    if reminder_error:
        saved_msg = "<div class='pro-alert danger'>" + e(reminder_error) + "</div>"
    due_day_value = e(str(reminder_cfg.get('due_day') or '10'))
    before_value = e(str(reminder_cfg.get('before_days', 7)))
    repeat_value = e(str(reminder_cfg.get('repeat_days', 3)))
    max_value = e(str(reminder_cfg.get('max_attempts', 3)))
    url_value = e(str(reminder_cfg.get('sumup_url') or ''))
    business_phone_value = e(str(reminder_cfg.get('whatsapp_business_phone') or ''))
    enabled_check = 'checked' if reminder_cfg.get('enabled') else ''
    reminder_controls = f\"\"\"
      <section class='pro-panel a269-reminder-settings' aria-labelledby='a269-h'>
        <h2 id='a269-h'>Promemoria quote</h2>
        <p>Quota mensile entro il <b>10</b>: prima bozza il <b>3</b>, eventuali successive il <b>6</b> e <b>9</b> (solo se non pagata e l'invio precedente è confermato). Le quote pagate, esenti o dubbie non si sollecitano.</p>
        <div class='a269-field-grid'>
          <label>Scadenza del mensile (giorno)<input name='bm_reminder_due_day' type='number' min='1' max='28' value='{due_day_value}'></label>
          <label>Giorni di anticipo<input name='bm_reminder_before' type='number' min='0' max='31' value='{before_value}'></label>
          <label>Ripeti dopo giorni<input name='bm_reminder_repeat' type='number' min='1' max='31' value='{repeat_value}'></label>
          <label>Massimo messaggi<input name='bm_reminder_max' type='number' min='1' max='5' value='{max_value}'></label>
          <label class='a269-wide'>Link SumUp (HTTPS, da configurare)<input name='bm_reminder_sumup_url' type='url' value='{url_value}' placeholder='https://pay.sumup.com/...'></label>
          <label class='a269-wide'>Numero WhatsApp Business ASD (facoltativo, solo contatto)<input name='bm_reminder_whatsapp_business_phone' type='tel' value='{business_phone_value}' placeholder='+39 3...'></label>
          <label class='a269-wide'><input name='bm_reminder_enabled' type='checkbox' value='1' {enabled_check}> Prepara proposte di promemoria (solo anteprima)</label>
        </div>
        <p class='small-muted'>Il numero WhatsApp Business non abilita da solo gli invii: serviranno API ufficiale, consenso e template approvato. Le credenziali API vanno conservate tra i segreti del servizio, mai in questo campo. Il link SumUp non costituisce prova di pagamento.</p>
      </section>
    \"\"\""""
    if source.count(old)!=1:raise RuntimeError('STOP: saved_msg anchor changed')
    source=source.replace(old,new,1)
    old="""<form method='post' class='motor-form'>{csrf_input()}{section_html}"""
    new="""<form method='post' class='motor-form'>{csrf_input()}{reminder_controls}{section_html}"""
    if source.count(old)!=1:raise RuntimeError('STOP: form anchor changed')
    source=source.replace(old,new,1)
    tail="""    </div>
    <style>.motor-page{{display:grid;gap:18px}}"""
    # This style is injected before the existing massive CSS, idempotently.
    replace="""    </div>
    <style>.a269-field-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}}.a269-field-grid label{{display:grid;gap:6px;font-size:13px}}.a269-field-grid input:not([type=checkbox]){{width:100%;max-width:100%;box-sizing:border-box;min-height:44px}}.a269-wide{{grid-column:1/-1}}@media(max-width:650px){{.a269-field-grid{{grid-template-columns:1fr}}}} .motor-page{{display:grid;gap:18px}}"""
    if source.count(tail)!=1:raise RuntimeError('STOP: style anchor changed')
    source=source.replace(tail,replace,1)
    ast.parse(source)
    target.write_text(source,encoding='utf-8')
    return {'changed':True,'bytes':len(source)}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True)
    print(json.dumps(patch(Path(p.parse_args().root)),indent=2))