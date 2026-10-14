import ast
import concurrent.futures
import importlib.util
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import subprocess
import tempfile
import types
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bodymind_cancelled_monthly_repair as repair


class CancelledMonthlyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'test.db'
        c = self.connect()
        c.executescript('''
          CREATE TABLE quote_mensili(tesserato_id,mese,anno,importo_dovuto,stato);
          CREATE TABLE pagamenti(id INTEGER PRIMARY KEY,tesserato_id,mese,anno,
            importo,causale,stato,online_status,ricevuta_id,paid_at,
            UNIQUE(tesserato_id,mese,anno,causale));
          CREATE TABLE ricevute(id INTEGER PRIMARY KEY,pagamento_id,annullata);
          INSERT INTO quote_mensili VALUES(14,10,2026,50,'dovuto');
          INSERT INTO pagamenti VALUES(37,14,10,2026,50,'mensile','annullato','annullato',NULL,NULL);
          INSERT INTO ricevute VALUES(1907,37,1);
        ''')
        c.close()

    def tearDown(self):
        self.tmp.cleanup()

    def connect(self):
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    def test_new_cause_preserves_history_and_index(self):
        with self.connect() as c:
            before = [tuple(r) for r in c.execute('SELECT * FROM pagamenti')]
            old, cause = repair.prepare_monthly(c,14,10,2026,50)
            self.assertIsNone(old)
            self.assertEqual(cause,'mensile_reincasso_1')
            self.assertEqual(before,[tuple(r) for r in c.execute('SELECT * FROM pagamenti')])

    def test_cancelled_with_live_receipt_is_blocked(self):
        with self.connect() as c:
            c.execute('UPDATE ricevute SET annullata=0')
            with self.assertRaises(repair.PaymentReviewRequired):
                repair.prepare_monthly(c,14,10,2026,50)

    def test_explicit_cancelled_id_cannot_be_reactivated(self):
        with self.connect() as c:
            with self.assertRaises(repair.PaymentReviewRequired):
                repair.prepare_monthly(c,14,10,2026,50,37)

    def test_due_zero_partial_nonfinite_and_wrong_period_blocked(self):
        for amount in (0,-1,20,float('nan'),float('inf')):
            with self.connect() as c:
                with self.assertRaises(repair.PaymentReviewRequired):
                    repair.prepare_monthly(c,14,10,2026,amount)
        with self.connect() as c:
            with self.assertRaises(repair.PaymentReviewRequired):
                repair.prepare_monthly(c,14,11,2026,50)
            c.execute("UPDATE quote_mensili SET importo_dovuto=0,stato='non_dovuto'")
            with self.assertRaises(repair.PaymentReviewRequired):
                repair.prepare_monthly(c,14,10,2026,50)

    def test_pending_requires_explicit_matching_id(self):
        with self.connect() as c:
            c.execute("INSERT INTO pagamenti VALUES(40,14,10,2026,50,'mensile_parziale_2','pending','pending',NULL,NULL)")
            with self.assertRaises(repair.PaymentReviewRequired):
                repair.prepare_monthly(c,14,10,2026,50)
            row,cause=repair.prepare_monthly(c,14,10,2026,50,40)
            self.assertEqual(row['id'],40)
            self.assertEqual(cause,'mensile_parziale_2')
            c.execute("UPDATE pagamenti SET online_status='paid_manual' WHERE id=40")
            with self.assertRaises(repair.PaymentReviewRequired):
                repair.prepare_monthly(c,14,10,2026,50,40)

    def test_two_concurrent_requests_create_only_one(self):
        def save(_):
            c=self.connect()
            try:
                _,cause=repair.prepare_monthly(c,14,10,2026,50)
                c.execute("INSERT INTO pagamenti(tesserato_id,mese,anno,importo,causale,stato,online_status) VALUES(14,10,2026,50,?,'paid_manual','paid_manual')",(cause,))
                c.commit()
                return 'saved'
            except repair.PaymentReviewRequired:
                c.rollback()
                return 'blocked'
            finally:
                c.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(save,range(2))),['blocked','saved'])
        with self.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM pagamenti').fetchone()[0],2)
            self.assertEqual(c.execute('SELECT annullata FROM ricevute WHERE id=1907').fetchone()[0],1)


@unittest.skipUnless(os.environ.get('BODYMIND_TEST_CORE') and os.environ.get('BODYMIND_TEST_DB'),
                     'Requires private, isolated runtime snapshot; never production')
class RuntimeSnapshotTests(unittest.TestCase):
    def test_full_core_permissions_csrf_and_real_save(self):
        program = r'''
import os,tempfile,pathlib,shutil,sys,socket,sqlite3
from bodymind_cancelled_monthly_repair import patch_core
with tempfile.TemporaryDirectory(prefix='bodymind-full-test-') as tmp:
    root=pathlib.Path(tmp)
    shutil.copytree(pathlib.Path(os.environ['BODYMIND_TEST_CORE']).parent,root/'asd_app')
    shutil.copy2(pathlib.Path(__import__('bodymind_cancelled_monthly_repair').__file__),root/'asd_app/bodymind_cancelled_monthly_repair.py')
    p=root/'asd_app/core.py';p.write_text(patch_core(p.read_text()))
    data=root/'data';(data/'tenants/default').mkdir(parents=True)
    shutil.copy2(os.environ['BODYMIND_TEST_DB'],data/'tenants/default/asd.db')
    (root/'app.py').write_text('from asd_app.core import app\n')
    os.environ['ASDPRO_RUNTIME_DIR']=str(data);os.environ['ASD_PRO_DATA_DIR']=str(data)
    sys.path.insert(0,str(root))
    def deny(*a,**k):raise RuntimeError('Outbound network disabled in test')
    socket.socket.connect=deny;socket.create_connection=deny
    import asd_app.core as core
    assert core.DATA_DIR==data
    core.current_license_status=lambda:(True,{'test_fixture':True},data/'license.json')
    core.wizard_required=lambda:False
    core.app.config['TESTING']=True
    client=core.app.test_client()
    form={'tipo':'mensile','tesserato_id':'14','mese':'10','anno':'2026','importo':'50','data':'2026-10-14','metodo_pagamento':'contanti','csrf_token':'test-csrf'}
    with client.session_transaction() as s:s.update(_csrf_token='test-csrf')
    r=client.post('/pagamenti/registra-unico',data=form)
    assert r.status_code==302 and '/login' in r.location
    with client.session_transaction() as s:s.update(logged=True,role='admin',username='isolated-test',tenant_slug='default')
    r=client.post('/pagamenti/registra-unico',data={**form,'csrf_token':'invalid'})
    assert r.status_code==400
    for tid in (14,19):
        form['tesserato_id']=str(tid)
        r=client.post('/pagamenti/registra-unico',data=form)
        assert r.status_code==303 and 'salvato=1' in r.location
        r=client.post('/pagamenti/registra-unico',data=form)
        assert 'salvato=1' not in r.location
    c=sqlite3.connect(data/'tenants/default/asd.db')
    assert c.execute('select count(*) from pagamenti').fetchone()[0]==129
    assert c.execute('select count(*) from ricevute').fetchone()[0]==121
    c.close()
print('Full core / authentication / CSRF / duplicate requests: OK')
'''
        env=os.environ.copy()
        env['PYTHONPATH']=str(Path(repair.__file__).parent)+os.pathsep+env.get('PYTHONPATH','')
        run=subprocess.run([sys.executable,'-c',program],env=env,text=True,capture_output=True,timeout=60)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)

    def test_real_writer_preserves_cancelled_rows_and_receipts(self):
        # Extract one function via AST. Never import core or run startup migrations.
        from flask import Flask, request, redirect
        source=Path(os.environ['BODYMIND_TEST_CORE']).read_text()
        patched=repair.patch_core(source)
        self.assertEqual(repair.patch_core(patched),patched)
        fn=next(n for n in ast.parse(patched).body if isinstance(n,ast.FunctionDef)
                and n.name=='_bodymind_payment_register_v7')
        fn.decorator_list=[]
        package=types.ModuleType('isolated_bodymind');package.__path__=[]
        sys.modules['isolated_bodymind']=package
        sys.modules['isolated_bodymind.bodymind_cancelled_monthly_repair']=repair
        with tempfile.TemporaryDirectory() as tmp:
            dbpath=Path(tmp)/'isolated.db'
            shutil.copy2(os.environ['BODYMIND_TEST_DB'],dbpath)
            def db():
                c=sqlite3.connect(dbpath);c.row_factory=sqlite3.Row;return c
            app=Flask(__name__)
            scope={'__name__':'isolated_bodymind.core','__package__':'isolated_bodymind',
                   'request':request,'redirect':redirect,'sqlite3':sqlite3,'db':db,
                   'parse_int':lambda v,d=0:int(v) if v else d,
                   'redirect_with_message':lambda url,msg,kind:redirect(url+'&errore=verifica',303),
                   '_bodymind_reconcile_athlete_status_v10':lambda c,tid:None}
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'<actual-writer>','exec'),scope)
            app.add_url_rule('/pagamenti/registra-unico',view_func=scope[fn.name],methods=['POST'])
            with db() as c:
                oldpayments=[tuple(r) for r in c.execute('SELECT * FROM pagamenti ORDER BY id')]
                oldreceipts=[tuple(r) for r in c.execute('SELECT * FROM ricevute ORDER BY id')]
                maxprogress=c.execute('SELECT MAX(numero_progressivo) FROM ricevute WHERE anno_progressivo=2026').fetchone()[0]
            client=app.test_client()
            for tid in (14,19):
                data={'tesserato_id':str(tid),'tipo':'mensile','mese':'10','anno':'2026',
                      'importo':'50','metodo_pagamento':'contanti','data':'2026-10-14','payment_id':'0'}
                response=client.post('/pagamenti/registra-unico',data=data)
                self.assertEqual(response.status_code,303)
                self.assertIn('salvato=1',response.location)
                response=client.post('/pagamenti/registra-unico',data=data)
                self.assertIn('errore=verifica',response.location)
            with db() as c:
                self.assertEqual(oldpayments,[tuple(r) for r in c.execute('SELECT * FROM pagamenti ORDER BY id LIMIT ?',(len(oldpayments),))])
                self.assertEqual(oldreceipts,[tuple(r) for r in c.execute('SELECT * FROM ricevute ORDER BY id LIMIT ?',(len(oldreceipts),))])
                self.assertEqual(c.execute('SELECT COUNT(*) FROM pagamenti').fetchone()[0],len(oldpayments)+2)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM ricevute').fetchone()[0],len(oldreceipts)+2)
                self.assertEqual(c.execute('SELECT MAX(numero_progressivo) FROM ricevute WHERE anno_progressivo=2026').fetchone()[0],maxprogress+2)
                self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])


if __name__=='__main__':
    unittest.main()
