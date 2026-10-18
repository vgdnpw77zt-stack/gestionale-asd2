"""A271 staging ONLY: optional safe SumUp link in existing authenticated family portal.
Never creates payments, receipts, tokens or messages; no DB writes.
"""
from pathlib import Path
import ast
import hashlib
import json
import os

MARKER='BODYMIND_A271_FAMILY_SUMUP_LINK'

def one(s, old, new, name):
    n=s.count(old)
    if n!=1:
        raise RuntimeError(f'A271 STOP {name}: expected 1 anchor, got {n}')
    return s.replace(old,new,1)

def patch(root):
    target=Path(root)/'routes_bodymind_final.py'
    src=target.read_text('utf-8')
    if MARKER in src:
        return {'changed':False, 'sha256':hashlib.sha256(src.encode('utf-8')).hexdigest()}
    old_html="""{% if quote_current.get('motivo_non_dovuto') %}<div class=\"muted\">Motivo: {{quote_current.get('motivo_non_dovuto')}}</div>{% endif %}</div>{% for p in pays %}"""
    new_html="""{% if quote_current.get('motivo_non_dovuto') %}<div class=\"muted\">Motivo: {{quote_current.get('motivo_non_dovuto')}}</div>{% endif %}{% if sumup_link %}<div class=\"a271-pay-link\"><a class=\"btn pay\" href=\"{{ sumup_link }}\" target=\"_blank\" rel=\"noopener noreferrer nofollow\">Paga online con SumUp</a><small class=\"muted\">Se hai già pagato, verifica la registrazione con la segreteria prima di ripetere il pagamento.</small></div>{% endif %}</div>{% for p in pays %}"""
    src=one(src,old_html,new_html,'template payment link')
    old_css='</style></head><body><header id="top" class="hero">'
    new_css='''.a271-pay-link{display:grid;gap:7px;margin-top:12px}.a271-pay-link .btn{min-height:45px;width:100%;text-align:center}.a271-pay-link small{font-size:12px;line-height:1.45}
</style></head><body><header id="top" class="hero">'''
    src=one(src,old_css,new_css,'template CSS')
    old="""    cert=str(t.get('certificato_scadenza') or '').strip()"""
    new="""    # BODYMIND_A271_FAMILY_SUMUP_LINK: payment CTA, NEVER payment confirmation.
    # A269 checks actual reconciled payments/receipts/waivers and old credits.
    # If a receipt or historic credit is ambiguous, hide the link rather than
    # encouraging an athlete to pay twice.
    sumup_link = ''
    if (pending and str(quote_current.get('state') or '').casefold() == 'dovuto'
            and not quote_current.get('motivo_non_dovuto')):
        try:
            from .bodymind_a269_reminders import Policy
            from .bodymind_a269_read_model import collect
            from .core import current_month_year
            mm, yy = current_month_year()
            audit = db()
            try:
                audit.execute('PRAGMA query_only=ON')
                candidates = collect(audit,year=yy,month=mm)
                current = next((r for r in candidates if r.athlete_id == tid),None)
            finally:
                audit.close()
            if (current is not None and current.state in ('da_pagare','parziale')
                    and current.reconciled and current.credits_verified
                    and current.waivers_verified and current.outstanding > 0):
                url = str((load_config().get('bodymind_reminders') or {}).get('sumup_url') or '').strip()
                if url:
                    Policy(sumup_url=url)  # Validate HTTPS; never call provider.
                    sumup_link = url
        except (ValueError, TypeError, AttributeError, ImportError, RuntimeError):
            pass
    cert=str(t.get('certificato_scadenza') or '').strip()"""
    src=one(src,old,new,'URL and due-state guard')
    old='cert_label=cert_label,cert_class=cert_class)'
    new='cert_label=cert_label,cert_class=cert_class,sumup_link=sumup_link)'
    src=one(src,old,new,'template context')
    ast.parse(src,filename=str(target))
    # Caller applies only to an isolated working clone, NEVER online.
    tmp=target.with_suffix('.a271.tmp')
    tmp.write_text(src,encoding='utf-8')
    os.replace(tmp,target)
    return {'changed':True,'sha256':hashlib.sha256(src.encode('utf-8')).hexdigest()}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',required=True)
    args=p.parse_args();print(json.dumps(patch(args.root),indent=2))