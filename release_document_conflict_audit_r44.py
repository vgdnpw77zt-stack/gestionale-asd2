# -*- coding: utf-8 -*-
from pathlib import Path
import sqlite3, os

DB=Path('/data/tenants/default/asd.db')
MEDIA=Path('/data/tenants/default/media')

def norm(v):
    return str(v or '').strip().lower()

def kind(r):
    hay=' '.join(norm(r[k]) for k in ('doc_type','categoria','titolo','original_filename','filename') if k in r.keys())
    if any(x in hay for x in ('certificato_medico','certificato medico','certificato',' cm ','_cm_','cm.pdf','cm.jpg','cm.jpeg','cm.png')):
        return 'certificato_medico'
    if any(x in hay for x in ('modulo_unico_tesseramento','modulo unico','modulo_unico','mu-2026','mu 2026','modulo iscrizione','domanda iscrizione','iscrizione manleva')):
        return 'modulo_unico_tesseramento'
    return norm(r['doc_type']) if 'doc_type' in r.keys() and norm(r['doc_type']) else (norm(r['categoria']) if 'categoria' in r.keys() else 'altro')

conn=sqlite3.connect(str(DB),timeout=20); conn.row_factory=sqlite3.Row
try:
    rows=conn.execute("SELECT * FROM documenti WHERE coalesce(visibile,1)=1 ORDER BY tesserato_id,id").fetchall()
    by_path={}
    for r in rows:
        path=os.path.normpath(str(r['filename'] or '')) if 'filename' in r.keys() else ''
        if not path: continue
        by_path.setdefault((int(r['tesserato_id'] or 0),path),[]).append(r)
    conflicts=[]
    dup_same_type=[]
    for (tid,path),items in by_path.items():
        if len(items)<2: continue
        kinds=sorted(set(kind(r) for r in items))
        serial=[{
          'id':int(r['id']),
          'kind':kind(r),
          'doc_type':str((r['doc_type'] if 'doc_type' in r.keys() else '') or ''),
          'categoria':str((r['categoria'] if 'categoria' in r.keys() else '') or ''),
          'titolo':str((r['titolo'] if 'titolo' in r.keys() else '') or ''),
          'original_filename':str((r['original_filename'] if 'original_filename' in r.keys() else '') or ''),
          'status':str((r['status'] if 'status' in r.keys() else '') or ''),
        } for r in items]
        a=conn.execute("SELECT nome,cognome FROM tesserati WHERE id=?",(tid,)).fetchone()
        name=((str(a['nome'] or '')+' '+str(a['cognome'] or '')).strip() if a else '')
        entry={'tesserato_id':tid,'name':name,'path':path,'kinds':kinds,'docs':serial}
        if len(kinds)>1: conflicts.append(entry)
        else: dup_same_type.append(entry)
    print('[document-conflict-r44] different_type_same_path='+repr(conflicts),flush=True)
    print('[document-conflict-r44] same_type_same_path='+repr(dup_same_type),flush=True)
    print('[document-conflict-r44] conflict_count='+str(len(conflicts))+' same_type_groups='+str(len(dup_same_type)),flush=True)
finally:
    conn.close()
