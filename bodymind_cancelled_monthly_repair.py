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
    response.headers['X-BodyMind-Monthly-Repair'] = '3'
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
            'SELECT id,annullata,pagamento_id FROM ricevute WHERE pagamento_id=? OR id=?',
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
        settled = {'paid_manual','closed_manual','pagato_online_verificato'}
        if all(s in settled for s in states):
            if not note:
                raise PaymentReviewRequired('Indica nelle note la motivazione della correzione.')
            if (len(receipts)!=1 or receipts[0]['pagamento_id']!=payment_id
                    or receipts[0]['annullata']!=0):
                raise PaymentReviewRequired('Collegamento ricevuta da verificare prima della correzione')
            stamp=datetime.now().isoformat(timespec='seconds')
            reason=f'Rettifica automatica pagamento #{payment_id}: {row["importo"]} -> {amount:.2f} EUR. {note}'
            conn.execute("UPDATE pagamenti SET stato='annullato',online_status='annullato',updated_at=?,note_pagamento=COALESCE(note_pagamento,'') || char(10) || ? WHERE id=?",(stamp,reason,payment_id))
            conn.execute('UPDATE ricevute SET annullata=1,annullata_motivo=?,updated_at=? WHERE id=?',(reason,stamp,receipts[0]['id']))
            # Continue below to create a replacement with a fresh receipt and
            # progressive, without modifying the original amounts or PDF.
            active=[]
        elif (not all(s in pending for s in states) or receipts or row['ricevuta_id']
              or row['paid_at']):
            raise PaymentReviewRequired('Movimento incassato, con ricevuta o da verificare')
        else:
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


def payment_form_error(message):
    """Keep rejected input visible, without putting private notes in a URL/cookie."""
    from flask import request, make_response
    from html import escape
    from urllib.parse import urlencode
    def value(name):
        return escape(str(request.form.get(name) or '')[:1000], quote=True)
    hidden=''.join("<input type='hidden' name='"+name+"' value='"+value(name)+"'>"
                   for name in ('csrf_token','tesserato_id','tipo','payment_id','stagione','mese','anno'))
    target='/pagamenti?'+urlencode(dict(vista='mensili',mese=request.form.get('mese',''),
        anno=request.form.get('anno',''),tesserato_id=request.form.get('tesserato_id',''),
        payment_id=request.form.get('payment_id',''),azione='registra',tipo='mensile'))
    options=''.join("<option"+(" selected" if request.form.get('metodo_pagamento')==x else "")+">"+escape(x)+"</option>"
                    for x in ('contanti','bonifico','carta/SumUp','altro'))
    html=f"""<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Correggi pagamento · BodyMind</title>
<style>body{{font:17px system-ui;background:#f5f2f7;color:#292032;margin:0}}main{{max-width:640px;margin:24px auto;padding:24px;background:white;border-radius:16px}}label{{display:block;margin:16px 0}}input,textarea,select,button{{box-sizing:border-box;width:100%;padding:12px;font:inherit}}[role=alert]{{border-left:5px solid #b42318;padding:16px;background:#fff0ed}}button{{background:#612e76;color:white;border:0;border-radius:8px}}a{{display:block;margin-top:20px}}</style></head>
<body><main><h1>Pagamento non salvato</h1><p role="alert">{escape(str(message))}</p>
<p>I dati inseriti sono conservati qui sotto. Controlla il messaggio e correggi i dati prima di salvare.</p>
<form method="post" action="/pagamenti/registra-unico">{hidden}
<label>Importo concordato €<input name="importo" type="number" step="0.01" min="0.01" required value="{value('importo')}"></label>
<label>Data<input name="data" type="date" required value="{value('data')}"></label>
<label>Metodo<select name="metodo_pagamento">{options}</select></label>
<label>Causale / motivazione (obbligatoria per una correzione)<textarea name="note_pagamento" rows="3" maxlength="1000" required placeholder="Es. accordo presenze, sconto concordato">{value('note_pagamento')}</textarea></label>
<p>La rettifica sostituisce automaticamente il pagamento e la ricevuta, conservando gli originali annullati nello storico.</p>
<button type="submit">Salva pagamento e ricevuta</button></form>
<a href="{escape(target,quote=True)}">Torna al modulo pagamento</a></main></body></html>"""
    response=make_response(html,422)
    response.headers['Cache-Control']='no-store'
    return response


def patch_core(source):
    marker='# BODYMIND_CANCELLED_MONTHLY_REPAIR_4'
    if marker in source:
        return source
    result=_patch_core_v3(source)
    old="return redirect_with_message('/pagamenti?vista=mensili&mese='+str(mese)+'&anno='+str(anno)+'&tesserato_id='+str(tid),str(exc),'error')"
    if result.count(old)!=1:
        raise ValueError('Unexpected validation handler; no patch applied')
    result=result.replace(old,"from .bodymind_cancelled_monthly_repair import payment_form_error\n                return payment_form_error(str(exc))",1)
    result=result.replace('# BODYMIND_CANCELLED_MONTHLY_REPAIR_3',marker,1)
    result=result.replace("response.headers['X-BodyMind-Monthly-Repair'] = '3'", "response.headers['X-BodyMind-Monthly-Repair'] = '4'")
    result=result.replace("Motivazione importo / note<textarea name='note_pagamento' rows='2'",
        "Causale / motivazione<textarea name='note_pagamento' rows='2' maxlength='1000' {'required' if action_tipo=='mensile' and pid else ''}")
    compile(result,'<monthly-form-validation-v4>','exec')
    return result


def _patch_core_v3(source):
    marker='# BODYMIND_CANCELLED_MONTHLY_REPAIR_3'
    if marker in source:
        return source
    result=_patch_core_v2(source)
    result=result.replace('# BODYMIND_CANCELLED_MONTHLY_REPAIR_2',marker,1)
    result=result.replace("response.headers['X-BodyMind-Monthly-Repair'] = '2'", "response.headers['X-BodyMind-Monthly-Repair'] = '3'")
    call='existing,payment_causale=prepare_monthly(c,tid,mese,anno,importo,payment_id,note)'
    if result.count(call)!=1:
        raise ValueError('Ambiguous monthly writer')
    result=result.replace(call,call+"\n                if payment_id and existing is None:\n                    note='Rettifica pagamento #'+str(payment_id)+' · '+note",1)
    anchor='        c.execute("UPDATE pagamenti SET ricevuta_id=? WHERE id=?",(rid,pid))'
    link='''
        if tipo=='mensile' and payment_id and payment_id!=pid:
            c.execute("UPDATE pagamenti SET note_pagamento=COALESCE(note_pagamento,'') || char(10) || ? WHERE id=?",
                ('Sostituito da pagamento #'+str(pid)+' e ricevuta #'+str(rid),payment_id))
'''
    if result.count(anchor)!=1:
        raise ValueError('Receipt linkage changed')
    result=result.replace(anchor,anchor+link,1)
    compile(result,'<monthly-correction-v3>','exec')
    return result


def _patch_core_v2(source):
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
                    if response.status==200 and response.headers.get('X-BodyMind-Monthly-Repair')=='4':
                        print('ONLINE: HTTP 200, modulo pagamento versione 4 caricato; salvataggio reale da verificare',flush=True)
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
                    if response.status==200 and response.headers.get('X-BodyMind-Monthly-Repair')!='4':
                        raise SystemExit('ROLLBACK verificato: sito precedente HTTP 200')
            except (OSError,TimeoutError):
                pass
        raise SystemExit('ROLLBACK codice eseguito, salute del servizio da verificare immediatamente')


if __name__=='__main__':
    main()
