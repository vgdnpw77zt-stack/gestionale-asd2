"""Narrow, fail-closed repair for full monthly receipts after cancellation.

No database migration, imports of the app, or production writes on import.
The caller owns commit/rollback; BEGIN IMMEDIATE serializes check + insert.
"""
import ast
import math


class PaymentReviewRequired(ValueError):
    pass


def prepare_monthly(conn, tid, month, year, amount, payment_id=0):
    if not math.isfinite(amount) or amount <= 0:
        raise PaymentReviewRequired('Importo non valido')
    if not conn.in_transaction:
        conn.execute('BEGIN IMMEDIATE')
    quota = conn.execute(
        'SELECT * FROM quote_mensili WHERE tesserato_id=? AND mese=? AND anno=?',
        (tid, month, year)).fetchone()
    if not quota or str(quota['stato']).lower() not in ('dovuto', 'pagato'):
        raise PaymentReviewRequired('Quota da verificare prima della registrazione')
    due = quota['importo_dovuto']
    if due is None or not math.isfinite(float(due)) or float(due) <= 0:
        raise PaymentReviewRequired('Quota non dovuta o non configurata')
    if round(amount, 2) != round(float(due), 2):
        raise PaymentReviewRequired('Importo diverso dal dovuto: verificare parziale o decisione quota')
    rows = conn.execute(
        "SELECT * FROM pagamenti WHERE tesserato_id=? AND mese=? AND anno=? "
        "AND (lower(causale) LIKE '%mensil%' OR lower(causale) IN ('quota','quota_mensile'))",
        (tid, month, year)).fetchall()
    cancelled = {'annullato', 'annullata', 'cancelled', 'canceled'}
    pending = {'unpaid', 'non_pagato', 'pending', 'requested', 'da_pagare'}
    active = []
    for row in rows:
        states = [str(row[k] or '').strip().lower() for k in ('stato', 'online_status')]
        receipts = conn.execute(
            'SELECT id,annullata FROM ricevute WHERE pagamento_id=? OR id=?',
            (row['id'], row['ricevuta_id'])).fetchall()
        if all(s in cancelled for s in states):
            if any(r['annullata'] != 1 for r in receipts):
                raise PaymentReviewRequired('Movimento annullato con ricevuta non annullata')
            continue
        active.append((row, states, receipts))
    if payment_id:
        candidates = [x for x in active if x[0]['id'] == payment_id]
        if len(candidates) != 1 or len(active) != 1:
            raise PaymentReviewRequired('Movimento selezionato non idoneo')
        row, states, receipts = candidates[0]
        if (not all(s in pending for s in states) or receipts or row['ricevuta_id']
                or row['paid_at']):
            raise PaymentReviewRequired('Movimento incassato, con ricevuta o da verificare')
        return row, row['causale']
    if active:
        raise PaymentReviewRequired('Movimento gia presente: selezionarlo e verificarne lo stato')
    used = {str(r['causale']) for r in rows}
    cause = 'mensile'
    n = 1
    while cause in used:
        cause = 'mensile_reincasso_' + str(n)
        n += 1
    return None, cause


def patch_core(source):
    """Patch only the monthly branch of the exact canonical writer; no execution."""
    marker = '# BODYMIND_CANCELLED_MONTHLY_REPAIR_1'
    if marker in source:
        return source
    tree = ast.parse(source)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
              and n.name == '_bodymind_payment_register_v7')
    lines = source.splitlines(keepends=True)
    block = ''.join(lines[fn.lineno-1:fn.end_lineno])
    start = block.index('        existing=None\n')
    end = block.index('        now=_dt.now()', start)
    old_selection = block[start:end]
    selection = '''        # BODYMIND_CANCELLED_MONTHLY_REPAIR_1
        payment_causale=tipo
        if tipo=='mensile':
            from .bodymind_cancelled_monthly_repair import prepare_monthly, PaymentReviewRequired
            try:
                existing,payment_causale=prepare_monthly(c,tid,mese,anno,importo,payment_id)
            except PaymentReviewRequired as exc:
                c.rollback()
                return redirect_with_message('/pagamenti?vista=mensili&mese='+str(mese)+'&anno='+str(anno)+'&tesserato_id='+str(tid),str(exc),'error')
        else:
'''+''.join('    '+line if line.strip() else line for line in old_selection.splitlines(keepends=True))
    block = block[:start]+selection+block[end:]
    for old, new in [
        ('(mese,anno,importo,data,tipo,metodo,note,now,now,pid)',
         '(mese,anno,importo,data,payment_causale,metodo,note,now,now,pid)'),
        ('(tid,mese,anno,importo,data,tipo,metodo,note,now,now,now)',
         '(tid,mese,anno,importo,data,payment_causale,metodo,note,now,now,now)'),
    ]:
        if block.count(old) != 1:
            raise ValueError('Writer changed: refusing unverified patch')
        block = block.replace(old,new,1)
    # Preserve the administrative fee and its notes; this guard accepts only
    # the exact full amount, so the existing row becomes paid without repricing.
    old = """SET importo_base=?,importo_dovuto=?,stato='pagato',
                               note=CASE WHEN ?<>'' THEN ? ELSE note END,
                               updated_at=?"""
    if old in block:
        block=block.replace(old,"SET stato='pagato',updated_at=?",1)
        block=block.replace('(importo,importo,note,note,now,int(q[\'id\']))',
                            '(now,int(q[\'id\']))',1)
    result=''.join(lines[:fn.lineno-1])+block+'\n'+''.join(lines[fn.end_lineno:])
    compile(result,'<patched-core>','exec')
    return result


def main():
    import argparse
    import hashlib
    import json
    import os
    from pathlib import Path
    import shutil
    import tempfile
    parser=argparse.ArgumentParser(description='Check/apply a code-only monthly repair; does not restart the app')
    parser.add_argument('--app-dir',required=True)
    parser.add_argument('--expected-core-sha256',required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    package=Path(args.app_dir).resolve()
    core=package/'core.py'
    if core.is_symlink():
        raise SystemExit('Refusing symlink source')
    raw=core.read_bytes()
    digest=hashlib.sha256(raw).hexdigest()
    if digest!=args.expected_core_sha256:
        raise SystemExit('Core differs from tested snapshot; no changes made')
    patched=patch_core(raw.decode('utf-8')).encode('utf-8')
    print('CHECK OK; original SHA256:',digest)
    print('Patched SHA256:',hashlib.sha256(patched).hexdigest())
    if not args.apply:
        print('CHECK ONLY: no files changed; no database changes')
        return
    os.umask(0o077)
    backup=Path(tempfile.mkdtemp(prefix='bodymind-code-rollback-',dir=str(package.parent)))
    (backup/'core.py').write_bytes(raw)
    helper=package/Path(__file__).name
    if helper.exists():
        raise SystemExit('Helper already present; inspect before replacing')
    helper_data=Path(__file__).read_bytes()
    def replace_file(path,data):
        fd,tmp=tempfile.mkstemp(prefix='.'+path.name,dir=str(path.parent))
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(data);stream.flush();os.fsync(stream.fileno())
            os.chmod(tmp,core.stat().st_mode & 0o777)
            os.replace(tmp,path)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
    replace_file(helper,helper_data)
    replace_file(core,patched)
    record={'original_sha256':digest,'patched_sha256':hashlib.sha256(patched).hexdigest(),
            'backup':str(backup/'core.py'),'target':str(core),
            'database_changed':False,'restart_performed':False}
    (backup/'rollback.json').write_text(json.dumps(record,indent=2))
    print(json.dumps(record))


if __name__=='__main__':
    main()
