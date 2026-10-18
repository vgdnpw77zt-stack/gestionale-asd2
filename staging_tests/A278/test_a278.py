import importlib,sqlite3,sys,tempfile,unittest,shutil,ast,hashlib
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BASE=Path('/mnt/data/A270_integrated/asd_app')

class A278(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();cls.parent=Path(cls.temp.name);cls.pkg=cls.parent/'asd_app';cls.pkg.mkdir()
  (cls.pkg/'__init__.py').write_text('')
  for name in ('bodymind_a237_finance_truth.py','bodymind_a253_manual.py'):
   shutil.copyfile(BASE/name,cls.pkg/name)
  for name in ('a278_quote_rules.py','a278_fee_settings.py'):
   shutil.copyfile(ROOT/name,cls.pkg/name)
  sys.path.insert(0,str(cls.parent))
  cls.rule=importlib.import_module('asd_app.a278_quote_rules');cls.ui=importlib.import_module('asd_app.a278_fee_settings')
 @classmethod
 def tearDownClass(cls):
  sys.path.remove(str(cls.parent));cls.temp.cleanup()
 def setUp(self):
  self.db=tempfile.TemporaryDirectory();self.path=Path(self.db.name)/'asd.db'
  self.c=sqlite3.connect(self.path);self.c.row_factory=sqlite3.Row
  self.c.executescript('''
  CREATE TABLE tesserati (id INTEGER PRIMARY KEY,nome TEXT,cognome TEXT,attivo INTEGER DEFAULT 1,quota_tipo TEXT,quota_personalizzata REAL,quota_sconto_fisso REAL,agonista INTEGER);
  CREATE TABLE quote_listino(codice TEXT PRIMARY KEY,importo NUMERIC,attivo INTEGER DEFAULT 1,updated_at TEXT);
  CREATE TABLE quote_mensili(id INTEGER PRIMARY KEY,tesserato_id INTEGER,mese INTEGER,anno INTEGER,tariffa_codice TEXT,importo_base NUMERIC,sconto NUMERIC,importo_dovuto NUMERIC,stato TEXT,note TEXT);
  CREATE TABLE bodymind_quota_decisioni(id INTEGER PRIMARY KEY,tesserato_id INTEGER,mese INTEGER,anno INTEGER,decisione TEXT,importo_dovuto NUMERIC);
  CREATE TABLE bodymind_a276_ingressi(tesserato_id INTEGER PRIMARY KEY,data_inizio TEXT);
  CREATE TABLE pagamenti(id INTEGER PRIMARY KEY,tesserato_id INTEGER,mese INTEGER,anno INTEGER,importo NUMERIC,causale TEXT,stato TEXT,online_status TEXT,metodo_pagamento TEXT);
  CREATE TABLE payment_requests(id INTEGER PRIMARY KEY,tesserato_id INTEGER,anno INTEGER,mese INTEGER,amount NUMERIC,status TEXT,motivo TEXT,deleted_at TEXT);
  CREATE TABLE ricevute(id INTEGER PRIMARY KEY,pagamento_id INTEGER,numero_progressivo INTEGER);
  CREATE TABLE movimenti(id INTEGER PRIMARY KEY,pagamento_id INTEGER,importo NUMERIC,tipo TEXT);
  ''')
  self.c.executemany('INSERT INTO tesserati VALUES(?,?,?,?,?,?,?,?)',[(1,'Lia','Test',1,'standard',None,0,0),
    (2,'Anna','Test',1,'personalizzata',45,0,0),(3,'Bia','Test',1,'standard',None,10,0),
    (4,'Tea','Test',1,'standard',None,0,0)])
  self.c.executemany('INSERT INTO quote_listino(codice,importo) VALUES (?,?)',
      [('standard',70),('agonista',85),('sorelle',60),('personalizzata',0)])
  self.c.execute('INSERT INTO bodymind_a276_ingressi VALUES(1,"2026-10-01")')
  self.c.execute('INSERT INTO quote_mensili VALUES(1,1,10,2026,"standard",70,0,70,"dovuto","")')
  self.c.commit()
 def tearDown(self):self.c.close();self.db.cleanup()
 def test_preview_listino_70(self):
  self.assertEqual(self.rule.fee_suggestion(self.c,4,10,2026)['value'],Decimal('70'))
 def test_stored_month_priority(self):
  self.assertEqual(self.rule.fee_suggestion(self.c,1,10,2026)['source'],'mensilita_salvata')
 def test_custom_and_sibling(self):
  self.assertEqual(self.rule.fee_suggestion(self.c,2,10,2026)['value'],Decimal('45'))
  self.c.execute("UPDATE tesserati SET quota_tipo='sorelle' WHERE id=4")
  self.assertEqual(self.rule.fee_suggestion(self.c,4,10,2026)['value'],Decimal('60'))
 def test_discount(self):self.assertEqual(self.rule.fee_suggestion(self.c,3,10,2026)['value'],Decimal('60'))
 def test_prior_period_no_due(self):
  data=self.rule.monthly_explanation(self.c,1,9,2026)
  self.assertEqual(data['stato'],'non_dovuto');self.assertEqual(data['residuo'],Decimal(0))
 def test_october_september_edit(self):
  self.c.execute("UPDATE bodymind_a276_ingressi SET data_inizio='2026-09-01' WHERE tesserato_id=1")
  # A corrected start changes eligibility but doesn't fabricate Sept's due or a cash entry.
  p=self.rule.monthly_explanation(self.c,1,9,2026)
  self.assertEqual(p['stato'],'da_verificare');self.assertIsNone(p['dovuto'])
  self.assertEqual(self.c.execute('SELECT COUNT(*) FROM pagamenti').fetchone()[0],0)
 def test_zero_paid_and_pending_request_150_not_debt(self):
  self.c.execute('INSERT INTO payment_requests VALUES(1,1,2026,10,150,"pending","mensile",null)')
  e=self.rule.monthly_explanation(self.c,1,10,2026)
  self.assertEqual(e['dovuto'],Decimal('70'))
  self.assertEqual(e['residuo'],Decimal('70'))
  self.assertEqual(e['richieste_aperte'],Decimal('150'))
  self.assertEqual(e['richieste_nota'],'richieste_non_coincidenti_con_residuo')
  self.assertFalse(e['sollecito_automatico_sicuro'])
 def test_paid_70_with_open_150_request_is_zero_debt(self):
  self.c.execute('INSERT INTO payment_requests VALUES(1,1,2026,10,150,"pending","mensile",null)')
  self.c.execute('INSERT INTO pagamenti VALUES(1,1,10,2026,70,"mensile","paid_manual","paid_manual","bonifico")')
  e=self.rule.monthly_explanation(self.c,1,10,2026)
  self.assertEqual(e['stato'],'pagato');self.assertEqual(e['residuo'],Decimal(0))
  self.assertEqual(e['richieste_aperte'],Decimal('150'))
 def test_partial_reduces_residual(self):
  self.c.execute('INSERT INTO pagamenti VALUES(1,1,10,2026,20,"mensile","paid_manual","paid_manual","contanti")')
  e=self.rule.monthly_explanation(self.c,1,10,2026)
  self.assertEqual(e['residuo'],Decimal('50'));self.assertEqual(e['stato'],'parziale')
 def test_unexplained_150_due_override_must_not_be_certified(self):
  self.c.execute('UPDATE quote_mensili SET importo_base=150,importo_dovuto=150 WHERE id=1')
  e=self.rule.monthly_explanation(self.c,1,10,2026)
  self.assertEqual(e['stato'],'da_verificare')
  self.assertEqual(e['provenienza'],'mensilita_diversa_dal_listino_senza_motivo')
  self.assertIsNone(e['residuo'])
 def test_explained_override_allowed(self):
  self.c.execute('UPDATE quote_mensili SET importo_base=150,importo_dovuto=150,note="Accordo economico motivato" WHERE id=1')
  e=self.rule.monthly_explanation(self.c,1,10,2026)
  self.assertEqual(e['dovuto'],Decimal('150'))
 def test_void_ignored(self):
  self.c.execute('INSERT INTO pagamenti VALUES(1,1,10,2026,70,"mensile","cancelled","cancelled","contanti")')
  self.assertEqual(self.rule.monthly_explanation(self.c,1,10,2026)['pagato'],Decimal(0))
 def test_credit_prior_marked_review(self):
  self.c.execute('INSERT INTO pagamenti VALUES(1,1,9,2026,90,"mensile","paid_manual","paid_manual","contanti")')
  e=self.rule.monthly_explanation(self.c,1,10,2026)
  self.assertEqual(e['stato'],'da_verificare_crediti_precedenti')
 def test_motivated_exception(self):
  self.c.execute('INSERT INTO bodymind_quota_decisioni VALUES(1,1,10,2026,"ridotta",35)')
  self.assertEqual(self.rule.fee_suggestion(self.c,1,10,2026)['value'],Decimal('35'))
 def test_exempt_month_no_receipt_created(self):
  self.c.execute('INSERT INTO bodymind_quota_decisioni VALUES(1,1,10,2026,"esente",0)')
  # An exemption must be stored in BOTH sources; a mismatch is not silently settled.
  self.assertEqual(self.rule.monthly_explanation(self.c,1,10,2026)['stato'],'da_verificare')
  self.c.execute('UPDATE quote_mensili SET stato="non_dovuto",importo_dovuto=0 WHERE id=1')
  self.assertEqual(self.rule.monthly_explanation(self.c,1,10,2026)['stato'],'non_dovuto')
  self.assertEqual(self.c.execute('SELECT COUNT(*) FROM ricevute').fetchone()[0],0)
 def test_update_tariff_only_listino_and_audit(self):
  before=[self.c.execute('SELECT COUNT(*) FROM '+s).fetchone()[0] for s in ('quote_mensili','pagamenti','ricevute','movimenti')]
  r=self.ui.update_tariff(self.c,code='standard',amount='75.00',expected='70.00',reason='Aggiornamento listino per prossimo periodo',operator='Katia')
  after=[self.c.execute('SELECT COUNT(*) FROM '+s).fetchone()[0] for s in ('quote_mensili','pagamenti','ricevute','movimenti')]
  self.assertEqual(before,after)
  self.assertEqual(r['precedente'],Decimal('70'));self.assertEqual(r['nuovo'],Decimal('75'))
  self.assertEqual(self.c.execute('SELECT importo_dovuto FROM quote_mensili WHERE id=1').fetchone()[0],70)
  self.assertEqual(self.c.execute('SELECT COUNT(*) FROM bodymind_a278_tariffe_audit').fetchone()[0],1)
 def test_stale_update_blocked(self):
  with self.assertRaisesRegex(ValueError,'modificato'):self.ui.update_tariff(self.c,code='standard',amount='75',expected='65',reason='Aggiornamento concordato per novembre',operator='Katia')
 def test_invalid_money_decimals(self):
  with self.assertRaises(ValueError):self.ui.update_tariff(self.c,code='standard',amount='70.005',expected='70',reason='Motivazione economica obbligatoria',operator='Katia')
 def test_missing_reason(self):
  with self.assertRaises(ValueError):self.ui.update_tariff(self.c,code='standard',amount='75',expected='70',reason='no',operator='Katia')
 def test_report_request_not_added_to_dues(self):
  self.c.execute('INSERT INTO payment_requests VALUES(1,1,2026,10,150,"pending","mensile",null)')
  r=self.ui.report_for_period(self.c,10,2026)
  self.assertEqual(r['richieste_aperte'],Decimal('150'))
  self.assertEqual(r['residui_calcolati'],Decimal('70'))
  self.assertGreaterEqual(r['quote_da_verificare'],1)
  self.assertIn('€ 150.00',self.ui.render_audit(r,'csrf'))
 def test_mobile(self):
  html=self.ui.render_rates({'standard':70},csrf='abc')
  self.assertIn('max-width:710px',html)
  self.assertIn('70.00',html)
  self.assertIn('Tariffe e quote',html)
 def test_read_only_explanation(self):
  self.c.commit();before=hashlib.sha256(self.path.read_bytes()).digest()
  self.rule.monthly_explanation(self.c,1,10,2026)
  self.assertEqual(before,hashlib.sha256(self.path.read_bytes()).digest())
 def test_missing_tariff_not_fabricated_due(self):
  self.c.execute('UPDATE quote_listino SET importo=0 WHERE codice="standard"')
  self.assertIsNone(self.rule.fee_suggestion(self.c,4,10,2026)['value'])
 def test_flask_settings_and_audit_get_post(self):
  try:
   from flask import Flask,request,session,redirect
  except ImportError:
   self.skipTest("Flask non installato in ambiente test locale: effettuare QA autenticato su staging reale")
  app=Flask(__name__);app.secret_key='only-synthetic-test-key'
  def conn():
   c=sqlite3.connect(self.path);c.row_factory=sqlite3.Row;return c
  self.ui.install({'app':app,'db':conn,'admin_required':lambda f:f,'request':request,
                   'csrf_token':lambda:'unit-test-csrf','layout':lambda html:html,'session':session,'redirect':redirect})
  with app.test_client() as client:
   first=client.get('/impostazioni/quote')
   self.assertEqual(first.status_code,200)
   self.assertIn(b'Standard',first.data)
   invalid=client.post('/impostazioni/quote',data={'csrf_token':'bad','codice':'standard','importo':'75','expected':'70','motivo':'Listino cambiato a novembre'})
   self.assertEqual(invalid.status_code,400)
   with client.session_transaction() as ss:ss['username']='Katia'
   good=client.post('/impostazioni/quote',data={'csrf_token':'unit-test-csrf','codice':'standard','importo':'75','expected':'70','motivo':'Aggiornamento concordato dal mese successivo'})
   self.assertEqual(good.status_code,303)
   report=client.get('/segreteria/quote-verifica?mese=10&anno=2026')
   self.assertEqual(report.status_code,200)
   self.assertIn(b'Quote per atleta',report.data)
   self.assertIn(b'Richieste da riconciliare',report.data)
   self.assertEqual(report.headers['Cache-Control'],'no-store, max-age=0')
  self.assertEqual(self.c.execute('SELECT importo_dovuto FROM quote_mensili WHERE id=1').fetchone()[0],70)
 def test_patch_A277_compat_syntax(self):
  import importlib.util
  spec=importlib.util.spec_from_file_location('a276patch','/mnt/data/A277_RC/patch_a276.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
  spec2=importlib.util.spec_from_file_location('a278patch',str(ROOT/'patch_a278.py'));p=importlib.util.module_from_spec(spec2);spec2.loader.exec_module(p)
  with tempfile.TemporaryDirectory() as d:
   dest=Path(d)
   for n in ('core.py','routes_quote_incassi.py','routes_pagamenti.py','routes_tesserati.py','bodymind_a237_finance_truth.py'):shutil.copyfile(BASE/n,dest/n)
   mod.patch(dest,Path('/mnt/data/A277_RC'))
   out=p.patch(dest,ROOT)
   self.assertTrue(out['changed'])
   text=(dest/'core.py').read_text('utf-8');self.assertNotIn("'70.00' if selected_tid not",text)
   self.assertIn('BODYMIND_A278_LISTINO_UNICO',text)
   with self.assertRaisesRegex(RuntimeError,'already'):p.patch(dest,ROOT)
if __name__=='__main__':unittest.main(verbosity=2)