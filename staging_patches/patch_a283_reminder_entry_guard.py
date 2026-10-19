# A283 – safe integration patch to the A269 reminder read model.
# Apply against the verified A281 candidate, not against unrelated or older source.
from pathlib import Path

def update(path: str):
    p=Path(path)
    old=p.read_text('utf-8')
    source="from .bodymind_a269_reminders import MonthlyRecord, money\n"
    pre="from .bodymind_a276_enrollment import start_date, before_start\n"
    marker="        person=people.get(tid)\n        if person is None:continue\n        state=str(q.get('stato') or '').strip().lower()"
    target="        person=people.get(tid)\n        if person is None:continue\n        _, join_confidence = start_date(conn, tid, person)\n        entry_before = before_start(conn, tid, year, month)\n        if entry_before is True:\n            continue  # Never chase September from a verified October entrant.\n        entry_verified = (entry_before is False and join_confidence.startswith('confermata'))\n        state=str(q.get('stato') or '').strip().lower()"
    old_rec="                  reconciled=consistent,credits_verified=credit_safe,waivers_verified=True,\n                  contact_approved=tid in approvals,phone=telephone,given_name=str(person.get('nome') or '')))"
    new_rec="                  reconciled=consistent and entry_verified,credits_verified=credit_safe,waivers_verified=True,\n                  contact_approved=(tid in approvals and entry_verified),phone=telephone,given_name=str(person.get('nome') or '')))"
    if old.count(source)!=1 or old.count(marker)!=1 or old.count(old_rec)!=1:
        raise ValueError("STOP A283: unexpected source revision")
    if pre in old: raise ValueError("STOP A283: already installed")
    new=old.replace(source,source+pre).replace(marker,target).replace(old_rec,new_rec)
    import ast
    ast.parse(new)
    p.write_text(new,'utf-8')
    return True

if __name__=='__main__':
    import sys
    if len(sys.argv)!=2: raise SystemExit("usage: python patch_a283.py /path/to/asd_app/bodymind_a269_read_model.py")
    update(sys.argv[1])
