# -*- coding: utf-8 -*-
from __future__ import annotations
import compileall, shutil
from pathlib import Path

APP=Path('/data/top2_app')
P=APP/'asd_app/routes_inbound_documents.py'
BACK=Path('/data/release_backups/20261005_r149_inbound_preview')
BACK.mkdir(parents=True,exist_ok=True)

s=P.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R149_INBOUND_PREVIEW' not in s:
    if '_safe_inbound_file_path' not in s:
        raise RuntimeError('R149 safe inbound file helper missing')
    anchor="# BODYMIND_R9_DOCUMENT_FILE"
    route=r"""# BODYMIND_R149_INBOUND_PREVIEW
@app.route('/documenti-automatici/file/<int:doc_id>')
@admin_required
def inbound_document_file_r149(doc_id: int):
    conn=db()
    try:
        row=conn.execute("SELECT id,saved_path,original_filename FROM inbound_documents WHERE id=?",(int(doc_id),)).fetchone()
    finally:
        conn.close()
    if not row:
        abort(404)
    fp=_safe_inbound_file_path(row['saved_path'] or '')
    if not fp or not fp.exists() or not fp.is_file():
        abort(404)
    return send_file(fp,as_attachment=False,download_name=(row['original_filename'] or fp.name))


"""
    if anchor not in s:
        raise RuntimeError('R149 insertion anchor missing')
    shutil.copy2(P,BACK/'routes_inbound_documents.py')
    s=s.replace(anchor,route+anchor,1)
    P.write_text(s,encoding='utf-8')
    if not compileall.compile_file(str(P),quiet=1):
        raise RuntimeError('R149 compile failed')
    print('[r149-inbound-preview] installed',flush=True)
else:
    print('[r149-inbound-preview] already installed',flush=True)
