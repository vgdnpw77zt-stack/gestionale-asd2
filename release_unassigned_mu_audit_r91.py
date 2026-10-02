# -*- coding: utf-8 -*-
import json, sqlite3, sys
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
sys.path.insert(0,str(APP))
from asd_app.enrollment_ingest_core_r65 import enrollment_identity_ready, valid_italian_cf, norm_cf

conn=sqlite3.connect(str(DB),timeout=30); conn.row_factory=sqlite3.Row
out=[]
try:
    rows=conn.execute("""SELECT * FROM inbound_documents
      WHERE lower(coalesce(document_type,''))='modulo_unico_tesseramento'
        AND coalesce(tesserato_id,0)=0
      ORDER BY id""").fetchall()
    for r in rows:
        iid=int(r['id'])
        sem=None
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bodymind_document_semantics'").fetchone():
            sr=conn.execute("""SELECT analysis_json,confidence,document_type,semantic_key,sha256
              FROM bodymind_document_semantics
              WHERE source_table='inbound_documents' AND source_id=?
              ORDER BY id DESC LIMIT 1""",(iid,)).fetchone()
            if sr:
                try: sem=json.loads(str(sr['analysis_json'] or '{}'))
                except Exception: sem=None
        a=sem if isinstance(sem,dict) else {}
        cf=norm_cf(a.get('codice_fiscale'))
        out.append({
          'id':iid,
          'filename':str(r['original_filename'] or ''),
          'status':str(r['status'] or ''),
          'document_type':str(r['document_type'] or ''),
          'document_confidence':int(r['document_confidence'] or 0),
          'match_score':int(r['match_score'] or 0),
          'semantic_present':bool(a),
          'semantic_document_type':str(a.get('document_type') or ''),
          'semantic_confidence':a.get('confidence'),
          'first_name':str(a.get('first_name') or ''),
          'last_name':str(a.get('last_name') or ''),
          'birth_date':str(a.get('birth_date') or ''),
          'codice_fiscale':cf,
          'valid_cf':valid_italian_cf(cf) if cf else False,
          'identity_ready_loose':enrollment_identity_ready(a,require_valid_cf=False) if a else False,
          'identity_ready_strict':enrollment_identity_ready(a,require_valid_cf=True) if a else False,
          'guardian_name':str(a.get('guardian_name') or ''),
          'guardian_phone':str(a.get('guardian_phone') or ''),
          'handwriting_legibility':a.get('handwriting_legibility'),
          'notes':str(a.get('notes') or '')[:240],
        })
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:
    conn.close()
print('[r91-unassigned-mu-audit] '+json.dumps(out,ensure_ascii=False),flush=True)
print('[r91-selftest] PASS read-only unassigned-MU identity audit integrity='+integrity+' fk='+str(fk),flush=True)
if integrity.lower()!='ok' or fk:
    raise RuntimeError('R91 DB integrity failed')
