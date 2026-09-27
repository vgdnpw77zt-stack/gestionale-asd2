from pathlib import Path
import sqlite3, json
DB=Path('/data/tenants/default/asd.db')
print('[r14-verify] BEGIN',flush=True)
conn=sqlite3.connect(str(DB),timeout=20); conn.row_factory=sqlite3.Row
try:
    pending=conn.execute("""SELECT id,original_filename,saved_path,document_type,document_confidence,
        match_score,match_action,status,tesserato_id,matched_tesserato_id,suggested_tesserato_id
        FROM inbound_documents
        WHERE lower(coalesce(status,'')) IN ('needs_manual_match','associato_tipo_da_verificare','richiede_conferma','needs_review','da_verificare','pending')
          AND coalesce(deleted_at,'')=''
        ORDER BY id""").fetchall()
    for r in pending:
        p=Path(str(r['saved_path'] or ''))
        print('[r14-verify] PENDING '+json.dumps({
          'id':r['id'],'file':r['original_filename'],'saved_path':r['saved_path'],'exists':p.is_file(),
          'type':r['document_type'],'doc_conf':r['document_confidence'],'score':r['match_score'],
          'action':r['match_action'],'status':r['status'],'tid':r['tesserato_id'],
          'matched':r['matched_tesserato_id'],'suggested':r['suggested_tesserato_id']
        },ensure_ascii=False),flush=True)
    print('[r14-verify] PENDING_COUNT='+str(len(pending)),flush=True)
    print('[r14-verify] PENDING_MISSING='+str(sum(1 for r in pending if not Path(str(r['saved_path'] or '')).is_file())),flush=True)
    for did in (20,31,33,38):
        r=conn.execute("SELECT id,original_filename,saved_path,status,document_type,match_score,tesserato_id FROM inbound_documents WHERE id=?",(did,)).fetchone()
        if r:
            p=Path(str(r['saved_path'] or ''))
            print('[r14-verify] CHECK '+json.dumps({
              'id':did,'file':r['original_filename'],'saved_path':r['saved_path'],'exists':p.is_file(),
              'status':r['status'],'type':r['document_type'],'score':r['match_score'],'tid':r['tesserato_id']
            },ensure_ascii=False),flush=True)
    old=conn.execute("SELECT COUNT(*) FROM inbound_documents WHERE saved_path LIKE '/Users/imac/%'").fetchone()[0]
    print('[r14-verify] OLD_PREFIX_LEFT='+str(old),flush=True)
finally:
    conn.close()
print('[r14-verify] END',flush=True)
