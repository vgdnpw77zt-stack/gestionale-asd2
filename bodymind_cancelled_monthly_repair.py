"""Monthly settlement at the administrator's explicitly agreed amount.

No database migration, imports of the app, or production writes on import.
The caller owns commit/rollback; BEGIN IMMEDIATE serializes check + insert.
"""
import ast
import math
from datetime import datetime


class PaymentReviewRequired(ValueError):
    pass


HEALTH_HOOK = '''

@app.after_request
def _bodymind_monthly_amount_release_v2(response):
    response.headers['X-BodyMind-Monthly-Repair'] = '2'
    return response
'''


def prepare_monthly(conn, tid, month, year, amount, payment_id=0, note=''):
    if not math.isfinite(amount) or amount <= 0 or round(amount, 2) != amount:
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
    changed = round(amount, 2) != round(float(due), 2)
    note = str(note or '').strip()[:1000]
    if changed and not note:
        raise PaymentReviewRequired('Indica nelle note la motivazione dell’importo concordato (sconto, presenze o altro).')
    def agree_amount():
        if not changed:
            return
        stamp = datetime.now().isoformat(timespec='seconds')
        entry = f'[{stamp}] Importo mensile concordato: {float(due):.2f} -> {amount:.2f} EUR. Motivo: {note}'
        conn.execute("""UPDATE quote_mensili SET importo_dovuto=?,
            sconto=MAX(0,COALESCE(importo_base,0)-?),
            note=CASE WHEN TRIM(COALESCE(note,''))='' THEN ? ELSE note || char(10) || ? END,
            updated_at=? WHERE tesserato_id=? AND mese=? AND anno=?""",
            (amount,amount,entry,entry,stamp,tid,month,year))
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
        agree_amount()
        return row, row['causale']
    if active:
        raise PaymentReviewRequired('Movimento gia presente: selezionarlo e verificarne lo stato')
    used = {str(r['causale']) for r in rows}
    cause = 'mensile'
    n = 1
    while cause in used:
        cause = 'mensile_reincasso_' + str(n)
        n += 1
    agree_amount()
    return None, cause


def patch_core(source):
    """Patch only the monthly branch of the exact canonical writer; no execution."""
    marker = '# BODYMIND_CANCELLED_MONTHLY_REPAIR_2'
    if marker in source:
        return source
    if '# BODYMIND_CANCELLED_MONTHLY_REPAIR_1' in source:
        old = 'prepare_monthly(c,tid,mese,anno,importo,payment_id)'
        if source.count(old) != 1:
            raise ValueError('Unexpected monthly writer; no patch applied')
        result = source.replace(old, 'prepare_monthly(c,tid,mese,anno,importo,payment_id,note)', 1)
        result = result.replace('# BODYMIND_CANCELLED_MONTHLY_REPAIR_1', marker, 1)
        result = result.replace('Note / eccezione<textarea', 'Motivazione importo / note<textarea')
        result += HEALTH_HOOK
        compile(result, '<patched-core-v2>', 'exec')
        return result
    tree = ast.parse(source)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
              and n.name == '_bodymind_payment_register_v7')
    lines = source.splitlines(keepends=True)
    block = ''.join(lines[fn.lineno-1:fn.end_lineno])
    start = block.index('        existing=None\n')
    end = block.index('        now=_dt.now()', start)
    old_selection = block[start:end]
    selection = '''        # BODYMIND_CANCELLED_MONTHLY_REPAIR_2
        payment_causale=tipo
        if tipo=='mensile':
            from .bodymind_cancelled_monthly_repair import prepare_monthly, PaymentReviewRequired
            try:
                existing,payment_causale=prepare_monthly(c,tid,mese,anno,importo,payment_id,note)
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
    # The helper records any explicitly agreed amount in the same transaction.
    # Keep that audit trail and the original base price in the canonical writer.
    old = """SET importo_base=?,importo_dovuto=?,stato='pagato',
                               note=CASE WHEN ?<>'' THEN ? ELSE note END,
                               updated_at=?"""
    if old in block:
        block=block.replace(old,"SET stato='pagato',updated_at=?",1)
        block=block.replace('(importo,importo,note,note,now,int(q[\'id\']))',
                            '(now,int(q[\'id\']))',1)
    result=''.join(lines[:fn.lineno-1])+block+'\n'+''.join(lines[fn.end_lineno:])
    result=result.replace('Note / eccezione<textarea', 'Motivazione importo / note<textarea')
    result += HEALTH_HOOK
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
    import signal
    import time
    from urllib.request import urlopen
    parser=argparse.ArgumentParser(description='Check/apply a code-only monthly repair; does not restart the app')
    parser.add_argument('--app-dir',required=True)
    parser.add_argument('--expected-core-sha256',required=True)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--reload',action='store_true',help='Reload verified Gunicorn and roll back code if health verification fails')
    args=parser.parse_args()
    package=Path(args.app_dir).resolve()
    core=package/'core.py'
    if core.is_symlink():
        raise SystemExit('Refusing symlink source')
    raw=core.read_bytes()
    digest=hashlib.sha256(raw).hexdigest()
    if digest!=args.expected_core_sha256:
        raise SystemExit('Core differs from tested snapshot; no changes made')
    master=None
    if args.reload:
        if not args.apply:
            raise SystemExit('--reload requires --apply')
        processes={}
        for p in Path('/proc').iterdir():
            if not p.name.isdigit():
                continue
            try:
                cmd=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode()
                if 'gunicorn' not in cmd or Path(os.readlink(p/'cwd')).resolve()!=package.parent:
                    continue
                parent=int(next(s.split()[1] for s in (p/'status').read_text().splitlines() if s.startswith('PPid:')))
                processes[int(p.name)]=parent
            except (OSError,StopIteration,ValueError):
                continue
        masters=[pid for pid,parent in processes.items() if parent not in processes]
        if len(masters)!=1:
            raise SystemExit('Cannot identify unique Gunicorn master; no code changed')
        master=masters[0]
    patched=patch_core(raw.decode('utf-8')).encode('utf-8')
    print('CHECK OK; original SHA256:',digest)
    print('Patched SHA256:',hashlib.sha256(patched).hexdigest())
    if not args.apply:
        print('CHECK ONLY: no files changed; no database changes')
        return
    os.umask(0o077)
    backup=Path(tempfile.mkdtemp(prefix='bodymind-code-rollback-',dir=str(package.parent)))
    (backup/'core.py').write_bytes(raw)
    helper=package/'bodymind_cancelled_monthly_repair.py'
    if helper.is_symlink():
        raise SystemExit('Refusing symlink helper')
    if helper.exists():
        shutil.copy2(helper,backup/helper.name)
    old_helper=helper.read_bytes() if helper.exists() else None
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
    if master is not None:
        os.kill(master,signal.SIGHUP)
        print('Ricarica avviata; verifica versione online...',flush=True)
        for _ in range(25):
            time.sleep(1)
            try:
                with urlopen('http://127.0.0.1:8080/login',timeout=1) as response:
                    if response.status==200 and response.headers.get('X-BodyMind-Monthly-Repair')=='2':
                        print('ONLINE: HTTP 200, correzione importo libero versione 2 caricata',flush=True)
                        return
            except Exception:
                pass
        replace_file(core,raw)
        if old_helper is not None:
            replace_file(helper,old_helper)
        os.kill(master,signal.SIGHUP)
        print('Verifica fallita: codice precedente ripristinato, database NON ripristinato',flush=True)
        for _ in range(15):
            time.sleep(1)
            try:
                with urlopen('http://127.0.0.1:8080/login',timeout=1) as response:
                    if response.status==200 and response.headers.get('X-BodyMind-Monthly-Repair')!='2':
                        raise SystemExit('ROLLBACK verificato: sito precedente HTTP 200')
            except (OSError,TimeoutError):
                pass
        raise SystemExit('ROLLBACK codice eseguito, salute del servizio da verificare immediatamente')


if __name__=='__main__':
    main()
