# -*- coding: utf-8 -*-
from __future__ import annotations
import py_compile, shutil, sqlite3, sys
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
BACK=Path('/data/release_backups/20261002_r112_operator_runtime_helper')
BACK.mkdir(parents=True,exist_ok=True)
OP=APP/'asd_app/routes_operator_bodymind.py'

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

s=OP.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R112_OPERATOR_BYTES_FALLBACK' not in s:
    dst=BACK/'routes_operator_bodymind.py'
    if not dst.exists(): shutil.copy2(OP,dst)
    marker='''# BODYMIND_R112_OPERATOR_BYTES_FALLBACK
'''
    # R107 must call the helper that actually exists in the current semantic document core.
    if 'name,data,_=_inbound_file_bytes(inbound)' in s:
        s=s.replace('name,data,_=_inbound_file_bytes(inbound)',
                    'name,data,_=_document_bytes_from_row(inbound)',1)
    elif '_inbound_file_bytes(inbound)' in s:
        s=s.replace('_inbound_file_bytes(inbound)','_document_bytes_from_row(inbound)',1)
    elif '_r107_read_inbound_bytes(inbound)' in s or '_document_bytes_from_row(inbound)' in s:
        # Earlier convergence already removed the stale helper call.
        pass
    else:
        raise RuntimeError('R112 could not verify R107 inbound byte call')
    s=marker+s
    tmp=OP.with_name(OP.name+'.r112.tmp')
    try:
        tmp.write_text(s,encoding='utf-8')
        py_compile.compile(str(tmp),doraise=True)
        tmp.replace(OP)
        py_compile.compile(str(OP),doraise=True)
    finally:
        try:
            if tmp.exists(): tmp.unlink()
        except Exception: pass
    print('[r112-operator] PASS R107 uses live document-bytes helper',flush=True)
else:
    print('[r112-operator] already applied',flush=True)

# Read-only symbol/runtime gate.
sys.path.insert(0,str(APP))
import app as _full_app
import asd_app.routes_operator_bodymind as op
checks={
  'r107_handler':hasattr(op,'_r107_handle_create_from_attachment'),
  'bytes_helper':hasattr(op,'_document_bytes_from_row'),
  'stale_helper_not_called':'_inbound_file_bytes(inbound)' not in OP.read_text(encoding='utf-8',errors='replace'),
}
conn=sqlite3.connect(str(DB),timeout=20)
try:
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally: conn.close()
checks['db_ok']=integrity.lower()=='ok' and fk==0
print('[r112-checks] '+repr(checks)+' integrity='+integrity+' fk='+str(fk),flush=True)
failed=[k for k,v in checks.items() if not v]
if failed: raise RuntimeError('R112 failed '+repr(failed))
print('[r112-selftest] PASS operator attachment byte-helper runtime-safe db-ok',flush=True)
