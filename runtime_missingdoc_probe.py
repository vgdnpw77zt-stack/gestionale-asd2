from pathlib import Path
import sqlite3, json
DB=Path('/data/tenants/default/asd.db')
MEDIA=Path('/data/tenants/default/media')
print('[missingdoc] BEGIN',flush=True)
conn=sqlite3.connect(str(DB)); conn.row_factory=sqlite3.Row
try:
    ids=(20,31,33,38,42,43,46)
    qs=','.join('?' for _ in ids)
    rows=conn.execute(f"""SELECT id,original_filename,saved_path,document_type,status,match_score,match_action,tesserato_id,matched_tesserato_id,suggested_tesserato_id
                         FROM inbound_documents WHERE id IN ({qs}) ORDER BY id""",ids).fetchall()
    for r in rows:
        raw=Path(str(r['saved_path'] or ''))
        fp=raw if raw.is_absolute() else MEDIA/raw
        print('[missingdoc] '+json.dumps({**dict(r),'resolved':str(fp),'exists':fp.is_file()},ensure_ascii=False),flush=True)
    rows=conn.execute("""SELECT id,original_filename,saved_path,document_type,status,match_score,match_action,tesserato_id
                         FROM inbound_documents
                         WHERE lower(coalesce(status,'')) IN ('needs_manual_match','associato_tipo_da_verificare','richiede_conferma','needs_review','da_verificare','pending')
                         AND coalesce(deleted_at,'')='' ORDER BY id""").fetchall()
    missing=[]
    for r in rows:
        raw=Path(str(r['saved_path'] or ''))
        fp=raw if raw.is_absolute() else MEDIA/raw
        if not fp.is_file(): missing.append({'id':r['id'],'file':r['original_filename'],'type':r['document_type'],'status':r['status'],'score':r['match_score'],'action':r['match_action'],'tid':r['tesserato_id'],'path':str(fp)})
    print('[missingdoc] PENDING_TOTAL='+str(len(rows)),flush=True)
    print('[missingdoc] PENDING_MISSING='+json.dumps(missing,ensure_ascii=False),flush=True)
finally:
    conn.close()
print('[missingdoc] END',flush=True)
