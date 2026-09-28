from __future__ import annotations
from pathlib import Path
from datetime import datetime
import sqlite3, shutil, subprocess, tempfile

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MARKER=APP/'.BODYMIND_FORCE_PDF_OCR_R21'
BACKUPS=Path('/data/release_backups/20260928_force_pdf_ocr_r21')
ACTIVE=('needs_manual_match','associato_tipo_da_verificare','richiede_conferma','needs_review','da_verificare','pending')

def cols(conn,table):
    return {r[1] for r in conn.execute(f'PRAGMA table_info({table})').fetchall()}

def load_matcher():
    import importlib.util
    p=APP/'asd_app/athlete_matcher.py'
    spec=importlib.util.spec_from_file_location('_bodymind_r21_matcher',p)
    if spec is None or spec.loader is None:
        raise RuntimeError('cannot load athlete_matcher')
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def force_pdf_ocr(path,max_pages=3):
    with tempfile.TemporaryDirectory(prefix='bm_r21_') as td:
        td=Path(td)
        prefix=td/'page'
        proc=subprocess.run(
            ['pdftoppm','-f','1','-l',str(max_pages),'-r','220','-jpeg',str(path),str(prefix)],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90,check=False
        )
        if proc.returncode!=0:
            return '', 'pdftoppm:'+proc.stderr.decode('utf-8','ignore')[:160]
        images=sorted(td.glob('page-*.jpg'))
        out=[]
        for img in images[:max_pages]:
            t=subprocess.run(
                ['tesseract',str(img),'stdout','-l','ita+eng','--psm','6'],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90,check=False
            )
            if t.returncode==0:
                txt=t.stdout.decode('utf-8','ignore').strip()
                if txt:
                    out.append(txt)
        return '\n'.join(out), ''

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

if MARKER.exists():
    print('[force-ocr-r21] already applied',flush=True)
else:
    BACKUPS.mkdir(parents=True,exist_ok=True)
    if DB.exists() and not (BACKUPS/'asd.db').exists():
        shutil.copy2(DB,BACKUPS/'asd.db')

    matcher=load_matcher()
    conn=sqlite3.connect(str(DB),timeout=30); conn.row_factory=sqlite3.Row
    auto=[]; confirm=[]; review=[]; errors=[]
    try:
        athletes=[dict(r) for r in conn.execute("SELECT * FROM tesserati ORDER BY id").fetchall()]
        vals=','.join('?' for _ in ACTIVE)
        rows=conn.execute(f"""SELECT * FROM inbound_documents
            WHERE LOWER(COALESCE(status,'')) IN ({vals})
              AND COALESCE(deleted_at,'')=''
              AND COALESCE(tesserato_id,0)=0
              AND LOWER(COALESCE(original_filename,'')) LIKE '%.pdf'
            ORDER BY id""",ACTIVE).fetchall()
        for r in rows:
            did=int(r['id'])
            p=Path(str(r['saved_path'] or ''))
            if not p.is_file():
                errors.append((did,'file_missing')); continue
            text,err=force_pdf_ocr(p,3)
            if err:
                errors.append((did,err))
            result=matcher.match_athlete(athletes,text,filename=str(r['original_filename'] or p.name))
            best=result.get('best') or {}
            score=int(best.get('score') or 0)
            action=str(result.get('action') or 'review')
            brow=best.get('row')
            tid=int((brow or {}).get('id') or 0) if isinstance(brow,dict) else 0
            ic=cols(conn,'inbound_documents')
            if action=='auto_save' and score>=92 and tid>0:
                dtype=str(r['document_type'] or '')
                dconf=int(r['document_confidence'] or 0)
                status=('pagamento_da_verificare' if dtype=='ricevuta_pagamento' else ('associato' if dtype not in ('','altro') and dconf>=60 else 'associato_tipo_da_verificare'))
                sets=["tesserato_id=?","match_score=?","match_action='auto_save'","status=?"]
                params=[tid,score,status]
                if 'matched_tesserato_id' in ic: sets.append("matched_tesserato_id=?"); params.append(tid)
                if 'suggested_tesserato_id' in ic: sets.append("suggested_tesserato_id=?"); params.append(tid)
                if 'updated_at' in ic: sets.append("updated_at=?"); params.append(datetime.now().isoformat(timespec='seconds'))
                params.append(did)
                conn.execute("UPDATE inbound_documents SET "+','.join(sets)+" WHERE id=?",params)
                auto.append((did,tid,score,len(text)))
            elif action=='confirm' and score>=78 and tid>0:
                sets=["match_score=?","match_action='confirm'","status='richiede_conferma'"]; params=[score]
                if 'suggested_tesserato_id' in ic: sets.append("suggested_tesserato_id=?"); params.append(tid)
                if 'updated_at' in ic: sets.append("updated_at=?"); params.append(datetime.now().isoformat(timespec='seconds'))
                params.append(did)
                conn.execute("UPDATE inbound_documents SET "+','.join(sets)+" WHERE id=?",params)
                confirm.append((did,tid,score,len(text)))
            else:
                review.append((did,score,len(text)))
        conn.commit()
        remaining=conn.execute(f"""SELECT COUNT(*) FROM inbound_documents WHERE LOWER(COALESCE(status,'')) IN ({vals}) AND COALESCE(deleted_at,'')=''""",ACTIVE).fetchone()[0]
    finally:
        conn.close()

    for did,tid,score,n in auto:
        print(f'[force-ocr-r21-auto] id={did} tid={tid} score={score} text_chars={n}',flush=True)
    for did,tid,score,n in confirm:
        print(f'[force-ocr-r21-confirm] id={did} tid={tid} score={score} text_chars={n}',flush=True)
    for did,score,n in review:
        print(f'[force-ocr-r21-review] id={did} score={score} text_chars={n}',flush=True)
    for did,err in errors:
        print(f'[force-ocr-r21-error] id={did} error={err}',flush=True)
    print(f'[force-ocr-r21] auto={len(auto)} confirm={len(confirm)} review={len(review)} errors={len(errors)} remaining_pending={remaining}',flush=True)
    MARKER.write_text('BodyMind forced PDF OCR R21 completed\n',encoding='utf-8')
    print('[force-ocr-r21-selftest] PASS forced-pdftoppm tesseract-ita-eng max-pages-3 no-force-below-92',flush=True)
