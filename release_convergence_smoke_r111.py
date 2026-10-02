# -*- coding: utf-8 -*-
from __future__ import annotations
import json, os, shutil, sqlite3, sys, tempfile
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
sys.path.insert(0,str(APP))
import app as _full_app
from asd_app.core import app
import asd_app.routes_operator_bodymind as op

result={'operator_create':False,'operator_idempotent':False,'desktop_simple':False,'mobile_simple':False,
        'desktop_no_dossier_default':False,'mobile_no_dossier_default':False,'payment_filter_route':False,
        'integrity':'','fk':None}

# --------------------------------------------------------------
# Integration smoke for "crea tesserato ... e aggiungi allegato"
# on a temporary DB clone. No production business row is created.
# --------------------------------------------------------------
fd,tmpdb=tempfile.mkstemp(prefix='bodymind_r111_',suffix='.db'); os.close(fd)
src=sqlite3.connect(str(DB),timeout=30); dst=sqlite3.connect(tmpdb)
try: src.backup(dst)
finally: dst.close(); src.close()

orig_db=op.db
orig_conv=op._conv_id
orig_backup=op._operator_db_backup
orig_bytes=op._document_bytes_from_row
orig_dup=op._semantic_key_duplicate
orig_prod=op._productionize_inbound
try:
    def _tdb():
        c=sqlite3.connect(tmpdb,timeout=30); c.row_factory=sqlite3.Row; return c
    op.db=_tdb
    op._conv_id=lambda:'r111-fixture-conversation'
    op._operator_db_backup=lambda label:'temp-db-fixture'
    op._inbound_file_bytes=lambda row:('r111_mu.pdf',b'%PDF-1.4\nR111 MU FIXTURE\n%%EOF\n','application/pdf')
    op._semantic_key_duplicate=lambda *a,**k:{'duplicate':False}
    op._productionize_inbound=lambda *a,**k:(True,{'fixture':True,'document_id':999999})

    c=_tdb()
    try:
        op._r107_attachment_schema(c)
        inbound=c.execute('SELECT * FROM inbound_documents ORDER BY id LIMIT 1').fetchone()
        if not inbound: raise RuntimeError('R111 requires one inbound fixture row in temp clone')
        iid=int(inbound['id'])
        sem={
          'document_type':'modulo_unico_tesseramento',
          'person_name':'Mario Rossi','first_name':'Mario','last_name':'Rossi',
          'codice_fiscale':'RSSMRA85T10A562S','birth_date':'10/12/1985',
          'birth_place':'Roma','address':'Via QA 1','city':'Roma','postal_code':'00100',
          'province':'RM','phone':'0000000000','email':'qa-r111@example.invalid',
          'nationality':'Italiana','gender':'M','confidence':0.99,
          'semantic_key':'r111-mario-rossi-fixture'
        }
        now='2026-10-02T18:00:00'
        c.execute("""INSERT OR REPLACE INTO bodymind_operator_attachment_context
          (conversation_id,inbound_id,document_type,semantic_json,status,created_at,updated_at)
          VALUES(?,?,?,?, 'active',?,?)""",
          ('r111-fixture-conversation',iid,'modulo_unico_tesseramento',json.dumps(sem),now,now))
        c.commit()
    finally:c.close()

    with app.test_request_context('/operatore-bodymind/chat',method='POST'):
        first=op._r107_handle_create_from_attachment(_tdb(),'crea tesserato Mario Rossi e aggiungi il modulo appena allegato')
    c=_tdb()
    try:
        n1=int(c.execute("SELECT COUNT(*) FROM tesserati WHERE UPPER(REPLACE(COALESCE(codice_fiscale,''),' ',''))='RSSMRA85T10A562S'").fetchone()[0])
        c.execute("UPDATE bodymind_operator_attachment_context SET status='active' WHERE conversation_id='r111-fixture-conversation'")
        c.commit()
    finally:c.close()
    with app.test_request_context('/operatore-bodymind/chat',method='POST'):
        second=op._r107_handle_create_from_attachment(_tdb(),'crea tesserato Mario Rossi e aggiungi il modulo appena allegato')
    c=_tdb()
    try:
        n2=int(c.execute("SELECT COUNT(*) FROM tesserati WHERE UPPER(REPLACE(COALESCE(codice_fiscale,''),' ',''))='RSSMRA85T10A562S'").fetchone()[0])
    finally:c.close()
    result['operator_create']=bool(first and first.get('created') is True and n1==1 and 'Non trovo' not in str(first.get('text') or ''))
    result['operator_idempotent']=bool(second and second.get('created') is False and n2==1 and 'Non trovo' not in str(second.get('text') or ''))
finally:
    op.db=orig_db; op._conv_id=orig_conv; op._operator_db_backup=orig_backup
    op._document_bytes_from_row=orig_bytes; op._semantic_key_duplicate=orig_dup; op._productionize_inbound=orig_prod
    try: os.unlink(tmpdb)
    except Exception: pass

# --------------------------------------------------------------
# Real rendered UI smoke. No mutation.
# --------------------------------------------------------------
client=app.test_client()
with client.session_transaction() as sess:
    sess.update({'logged':True,'username':'admin','display_name':'R111 QA','role':'admin','tenant_slug':'default'})
desktop=client.get('/tesserati/33/scheda',follow_redirects=False)
mobile=client.get('/mobile/atleta/33',headers={'User-Agent':'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1'},follow_redirects=False)
pay=client.get('/pagamenti?tesserato_id=33',follow_redirects=False)
dh=desktop.get_data(as_text=True); mh=mobile.get_data(as_text=True)
result['desktop_simple']=desktop.status_code==200 and 'bodymind-r110-simple-desktop' in dh and all(x in dh for x in ('Iscrizione','Mese','Modulo Unico','Certificato','Tutela'))
result['mobile_simple']=mobile.status_code==200 and all(x in mh for x in ('Iscrizione','Mese','Modulo Unico','Certificato','Tutela'))
result['desktop_no_dossier_default']='Dossier' not in dh and 'dossier' not in dh.lower()
result['mobile_no_dossier_default']='Dossier' not in mh and 'dossier' not in mh.lower()
result['payment_filter_route']=pay.status_code in (200,302)

c=sqlite3.connect(str(DB),timeout=30)
try:
    result['integrity']=str(c.execute('PRAGMA integrity_check').fetchone()[0])
    result['fk']=len(c.execute('PRAGMA foreign_key_check').fetchall())
finally:c.close()

result['ok']=all(result[k] for k in ('operator_create','operator_idempotent','desktop_simple','mobile_simple',
    'desktop_no_dossier_default','mobile_no_dossier_default','payment_filter_route')) and result['integrity'].lower()=='ok' and result['fk']==0
print('[r111-convergence-smoke] '+json.dumps(result,ensure_ascii=False),flush=True)
if not result['ok']:
    raise RuntimeError('R111 convergence smoke failed '+json.dumps(result,ensure_ascii=False))
print('[r111-selftest] PASS operator-attachment-create-idempotent simple-athlete-no-dossier payment-route db-ok',flush=True)
