"""Apply user-confirmed 10th-day policy and optional contact settings to an A269 STAGING clone.
Never use this script directly on live Railway. Does not enable/send any messages.
"""
from __future__ import annotations
from pathlib import Path
import ast
import hashlib
import json
import os

def sub(text, old, new, label):
    if text.count(old) != 1:
        raise RuntimeError(f'A270 STOP: {label} expected exactly once; found {text.count(old)}')
    return text.replace(old,new,1)

def patch(app_root):
    root=Path(app_root)
    ui=root/'routes_automation_pro.py'
    rules=root/'bodymind_a269_reminders.py'
    original={p:p.read_text('utf-8') for p in (ui,rules)}
    u=original[ui]; r=original[rules]
    # Previews A269 / A270 may have been assembled separately in staging.
    # Reconcile each source only when it matches an explicitly recognized variant.
    ui_ready = all(x in u for x in (
        'bm_reminder_whatsapp_business_phone',
        'from .bodymind_a269_reminders import Policy, normalized_phone',
        'due_day=int(day_raw) if day_raw else 10,',
        'whatsapp_business_phone=business_phone)',
    ))
    rules_ready = 'due_day: int | None = 10' in r
    if not (ui_ready or 'BODYMIND_A269_REMINDER_SETTINGS' in u):
        raise RuntimeError('A270 STOP: missing A269 UI')
    if not (rules_ready or 'due_day: int | None = None' in r):
        raise RuntimeError('A270 STOP: unknown policy variant')
    if ui_ready and rules_ready:
        return {'changed': False}
    if not rules_ready:
        r=sub(r,'due_day: int | None = None',
              'due_day: int | None = 10  # BODYMIND_A270_DUE10','policy default')
    if not ui_ready:
        u=sub(u,'from .bodymind_a269_reminders import Policy','from .bodymind_a269_reminders import Policy, normalized_phone','phone validator')
        u=sub(u,"day_raw = (request.form.get('bm_reminder_due_day') or '').strip()", "day_raw = (request.form.get('bm_reminder_due_day') or '').strip()\n            raw_business = (request.form.get('bm_reminder_whatsapp_business_phone') or '').strip()\n            business_phone = normalized_phone(raw_business) if raw_business else ''\n            if raw_business and not business_phone:\n                raise ValueError('Numero WhatsApp Business non valido')", 'contact field')
        u=sub(u,'due_day=int(day_raw) if day_raw else None,','due_day=int(day_raw) if day_raw else 10,','due date post')
        u=sub(u,'enabled=candidate.enabled,sumup_url=candidate.sumup_url)','enabled=candidate.enabled,sumup_url=candidate.sumup_url,\n                                whatsapp_business_phone=business_phone)','contact persistence')
        u=sub(u,"due_day_value = e(str(reminder_cfg.get('due_day') or ''))","due_day_value = e(str(reminder_cfg.get('due_day') or '10'))  # BODYMIND_A270_DUE10",'due date get')
        u=sub(u,"url_value = e(str(reminder_cfg.get('sumup_url') or ''))", "url_value = e(str(reminder_cfg.get('sumup_url') or ''))\n    business_phone_value = e(str(reminder_cfg.get('whatsapp_business_phone') or ''))",'contact get')
        u=sub(u,"value='{due_day_value}' placeholder='Da impostare'","value='{due_day_value}'",'due placeholder')
        u=sub(u,"<label class='a269-wide'>Link SumUp (HTTPS)<input name='bm_reminder_sumup_url' type='url' value='{url_value}' placeholder='https://...'></label>","<label class='a269-wide'>Link SumUp HTTPS (da configurare)<input name='bm_reminder_sumup_url' type='url' value='{url_value}' placeholder='https://pay.sumup.com/...'></label>\n          <label class='a269-wide'>Numero WhatsApp Business ASD (solo recapito)<input name='bm_reminder_whatsapp_business_phone' type='tel' value='{business_phone_value}' placeholder='+39 3...'></label>",'SumUp and Business fields')
        u=sub(u,'<p>Imposta le scadenze. Il programma propone messaggi WhatsApp da confermare; non li spedisce da solo. Le quote pagate, esenti e dubbie non vengono sollecitate.</p>',"<p>Mensile entro il <b>10</b>. Con anticipo 7 giorni e ripetizione 3 giorni: proposte il <b>3, 6 e 9</b>, soltanto se la quota e il recapito sono verificati. Nessun invio automatico abilitato.</p>",'description')
        u=sub(u,"<p class='small-muted'>L'invio programmato WhatsApp richiederà API ufficiale, consenso e modello approvato. Pagamento SumUp da confermare prima di registrare l'incasso.</p>","<p class='small-muted'>Il numero WhatsApp non abilita l'invio: servono API ufficiali, consenso e template approvati. Inserire le credenziali SOLO nei segreti del servizio, non in questa pagina. Il click sul link SumUp non costituisce incasso.</p>",'provider description')
    for name,text in [(ui,u),(rules,r)]:
        ast.parse(text,filename=str(name))
    # Write only after all anchor checks pass; rollback copies remain in dedicated staging.
    for name,text in [(ui,u),(rules,r)]:
        tmp=name.with_suffix('.a270_tmp')
        tmp.write_text(text,'utf-8')
        os.replace(tmp,name)
    return {'changed':True,'source_sha256':{p.name:hashlib.sha256(body.encode()).hexdigest() for p,body in ((ui,u),(rules,r))}}

if __name__=='__main__':
    import argparse
    a=argparse.ArgumentParser();a.add_argument('--root',required=True)
    opt=a.parse_args()
    print(json.dumps(patch(opt.root),indent=2))