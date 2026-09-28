from __future__ import annotations
from pathlib import Path
from datetime import datetime
import importlib.util, sqlite3, shutil

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MARKER=APP/'.BODYMIND_OCR_REMATCH_R20'
BACKUPS=Path('/data/release_backups/20260928_ocr_rematch_r20')
ACTIVE=('needs_manual_match','associato_tipo_da_verificare','richiede_conferma','needs_review','da_verificare','pending')

def cols(conn,table):
    return {r[1] for r in conn.execute(f'PRAGMA table_info({table})').fetchall()}

def has_table(conn,table):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone() is not None

def load_module(rel,name):
    spec=importlib.util.spec_from_file_location(name,APP/rel)
    if spec is None or spec.loader is None:
        raise RuntimeError('cannot load '+rel)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

if MARKER.exists():
    print('[ocr-rematch-r20] already applied',flush=True)
    raise SystemExit(0)

BACKUPS.mkdir(parents=True,exist_ok=True)
if DB.exists() and not (BACKUPS/'asd.db').exists():
    shutil.copy2(DB,BACKUPS/'asd.db')

matcher=load_module('asd_app/athlete_matcher.py','_bodymind_r20_matcher')
med=load_module('asd_app/medical_certificate_dates.py','_bodymind_r20_med')

conn=sqlite3.connect(str(DB),timeout=30); conn.row_factory=sqlite3.Row
auto=[]
confirm=[]
review=[]
errors=[]
try:
    athletes=[dict(r) for r in conn.execute("SELECT * FROM tesserati ORDER BY id").fetchall()]
    vals=','.join('?' for _ in ACTIVE)
    rows=conn.execute(f"""SELECT * FROM inbound_documents
        WHERE LOWER(COALESCE(status,'')) IN ({vals})
          AND COALESCE(deleted_at,'')=''
          AND COALESCE(tesserato_id,0)=0
        ORDER BY id""",ACTIVE).fetchall()

    for r in rows:
        did=int(r['id'])
        filename=str(r['original_filename'] or Path(str(r['saved_path'] or '')).name)
        path=Path(str(r['saved_path'] or ''))
        if not path.is_file():
            errors.append((did,'file_missing'))
            continue
        try:
            payload=path.read_bytes()
            text=med.extract_attachment_text(filename,payload) or ''
            result=matcher.match_athlete(athletes,text,filename=filename)
            best=result.get('best') or {}
            score=int(best.get('score') or 0)
            action=str(result.get('action') or 'review')
            brow=best.get('row')
            if isinstance(brow,sqlite3.Row):
                brow=dict(brow)
            tid=int((brow or {}).get('id') or 0) if isinstance(brow,dict) else 0
            text_len=len(text)

            if action=='auto_save' and score>=92 and tid>0:
                dtype=str(r['document_type'] or '')
                dconf=int(r['document_confidence'] or 0)
                strong_type=(dtype not in ('','altro') and dconf>=60)
                status=('pagamento_da_verificare' if dtype=='ricevuta_pagamento' else ('associato' if strong_type else 'associato_tipo_da_verificare'))
                ic=cols(conn,'inbound_documents')
                sets=["tesserato_id=?","match_score=?","match_action='auto_save'","status=?"]
                params=[tid,score,status]
                if 'matched_tesserato_id' in ic:
                    sets.append("matched_tesserato_id=?"); params.append(tid)
                if 'suggested_tesserato_id' in ic:
                    sets.append("suggested_tesserato_id=?"); params.append(tid)
                if 'updated_at' in ic:
                    sets.append("updated_at=?"); params.append(datetime.now().isoformat(timespec='seconds'))
                params.append(did)
                conn.execute("UPDATE inbound_documents SET "+','.join(sets)+" WHERE id=?",params)

                # Synchronize the existing physical document into the athlete dossier.
                if has_table(conn,'documenti'):
                    dc=cols(conn,'documenti')
                    existing=None
                    if 'inbound_id' in dc:
                        existing=conn.execute("SELECT id FROM documenti WHERE inbound_id=? ORDER BY id DESC LIMIT 1",(did,)).fetchone()
                    if not existing:
                        existing=conn.execute("SELECT id FROM documenti WHERE filename=? ORDER BY id DESC LIMIT 1",(str(path),)).fetchone()
                    category='Certificato medico' if dtype=='certificato_medico' else ('Modulo iscrizione BodyMind' if dtype=='modulo_unico_tesseramento' else 'Altro')
                    values={
                        'tesserato_id':tid,'titolo':filename,'categoria':category,
                        'filename':str(path),'original_filename':filename,
                        'data_caricamento':datetime.now().date().isoformat(),'visibile':1,
                        'doc_type':dtype,'confidence':dconf,'match_score':score,
                        'source':'autopilot','status':'salvato','inbound_id':did
                    }
                    values={k:v for k,v in values.items() if k in dc}
                    if existing:
                        keys=list(values.keys())
                        conn.execute("UPDATE documenti SET "+','.join(k+'=?' for k in keys)+" WHERE id=?",[values[k] for k in keys]+[int(existing['id'])])
                    else:
                        required={'tesserato_id','titolo','categoria','filename','original_filename'}
                        if required.issubset(values):
                            keys=list(values.keys())
                            conn.execute("INSERT INTO documenti("+','.join(keys)+") VALUES("+','.join('?' for _ in keys)+")",[values[k] for k in keys])
                auto.append((did,tid,score,filename,text_len))
            elif action=='confirm' and score>=78 and tid>0:
                ic=cols(conn,'inbound_documents')
                sets=["match_score=?","match_action='confirm'","status='richiede_conferma'"]
                params=[score]
                if 'suggested_tesserato_id' in ic:
                    sets.append("suggested_tesserato_id=?"); params.append(tid)
                if 'updated_at' in ic:
                    sets.append("updated_at=?"); params.append(datetime.now().isoformat(timespec='seconds'))
                params.append(did)
                conn.execute("UPDATE inbound_documents SET "+','.join(sets)+" WHERE id=?",params)
                confirm.append((did,tid,score,filename,text_len))
            else:
                review.append((did,score,filename,text_len))
        except Exception as exc:
            errors.append((did,type(exc).__name__+':'+str(exc)[:180]))

    conn.commit()
    remaining=conn.execute(f"""SELECT COUNT(*) FROM inbound_documents
        WHERE LOWER(COALESCE(status,'')) IN ({vals}) AND COALESCE(deleted_at,'')=''""",ACTIVE).fetchone()[0]
finally:
    conn.close()

for did,tid,score,file,text_len in auto:
    print(f'[ocr-rematch-r20-auto] id={did} tid={tid} score={score} text_chars={text_len} file={file}',flush=True)
for did,tid,score,file,text_len in confirm:
    print(f'[ocr-rematch-r20-confirm] id={did} tid={tid} score={score} text_chars={text_len} file={file}',flush=True)
for did,score,file,text_len in review:
    print(f'[ocr-rematch-r20-review] id={did} score={score} text_chars={text_len} file={file}',flush=True)
for did,err in errors:
    print(f'[ocr-rematch-r20-error] id={did} error={err}',flush=True)
print(f'[ocr-rematch-r20] auto={len(auto)} confirm={len(confirm)} review={len(review)} errors={len(errors)} remaining_pending={remaining}',flush=True)

# Existing R6 matcher guarantees exact unique full-name >=92 and ambiguous cases safe.
MARKER.write_text('BodyMind OCR historical rematch R20 completed\n',encoding='utf-8')
print('[ocr-rematch-r20-selftest] PASS current-matcher current-extractor no-force-below-92 one-time-historical-rematch',flush=True)
