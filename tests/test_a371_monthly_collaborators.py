"""A371 local synthetic checks; never use production records."""
import importlib.util
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest

flask=types.ModuleType('flask')
for n in ['abort','make_response','redirect','send_file']:
    setattr(flask,n,lambda *a,**kw:None)
flask.request=None
sys.modules['flask']=flask

path=Path(__file__).parents[1]/'bootstrap'/'a371_monthly_collaborators.py'
spec=importlib.util.spec_from_file_location('a371_monthly_collaborators',path)
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)

def connect():
    c=sqlite3.connect(':memory:')
    c.row_factory=sqlite3.Row
    c.execute("""CREATE TABLE collaboratori(
      id INTEGER PRIMARY KEY,nome TEXT,cognome TEXT,ruolo TEXT,
      attivo INTEGER,paga_oraria REAL)""")
    c.execute("""CREATE TABLE ore_collaboratori(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      collaboratore_id INTEGER, data TEXT, ore REAL,
      mese INTEGER, anno INTEGER, liquidato INTEGER DEFAULT 0)""")
    c.execute("INSERT INTO collaboratori VALUES (1,'Atleta','Esempio','Istruttore',1,11.17)")
    c.commit()
    return c

class MonthlyTests(unittest.TestCase):
    def setUp(self):
        self.conn=connect()
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)/'documenti_asd'
        self.root.mkdir()
        self.collab=self.conn.execute("SELECT * FROM collaboratori WHERE id=1").fetchone()
    def tearDown(self):
        self.conn.close();self.tmp.cleanup()
    def insert(self,minutes=2865,rate=1089):
        with self.conn:
            a.ensure_tables(self.conn)
            return a.persist_month(self.conn,1,2026,10,minutes,rate)
    def test_first_registration(self):
        i=self.insert()
        row,docs,legacy=a.month_state(self.conn,1,2026,10)
        self.assertEqual(i,row['id'])
        self.assertEqual(row['minuti'],2865)
        self.assertEqual(row['tariffa_centesimi'],1089)
        self.assertEqual(len(docs),0)
        self.assertEqual(len(legacy),0)
        self.assertAlmostEqual(self.conn.execute('SELECT ore FROM ore_collaboratori').fetchone()[0],47.75)
    def test_compensation_is_520_for_october(self):
        self.assertEqual(a.gross_cents(2865,1089),52000)
        self.assertEqual(a.money(52000),'520,00 €')
        self.assertEqual(a.format_hours(2865),'47 ore e 45 minuti')
    def test_rate_from_november(self):
        self.assertEqual(a.gross_cents(2865,1117),53337)
    def test_duplicate_month_not_inserted(self):
        self.insert()
        self.insert()
        self.assertEqual(self.conn.execute('SELECT count(*) FROM ore_collaboratori').fetchone()[0],1)
    def test_month_update_changes_single_row_and_revision(self):
        self.insert()
        self.insert(2880,1117)
        row=self.conn.execute('SELECT * FROM bodymind_collab_monthly').fetchone()
        self.assertEqual((row['revision'],row['minuti']),(2,2880))
        self.assertEqual(self.conn.execute('SELECT count(*) FROM ore_collaboratori').fetchone()[0],1)
    def test_legacy_daily_entries_block_new_month(self):
        self.conn.execute("INSERT INTO ore_collaboratori(collaboratore_id,data,ore,mese,anno) VALUES(1,'2026-10-05',3,10,2026)")
        self.conn.commit()
        with self.assertRaisesRegex(ValueError,'giornaliere'):self.insert()
        self.assertEqual(self.conn.execute('SELECT count(*) FROM ore_collaboratori').fetchone()[0],1)
    def test_paid_month_cannot_be_modified(self):
        self.insert()
        self.conn.execute('UPDATE ore_collaboratori SET liquidato=1')
        self.conn.commit()
        with self.assertRaisesRegex(ValueError,'liquidato'):self.insert(3000)
    def test_signed_month_cannot_be_modified(self):
        self.insert()
        self.conn.execute("""INSERT INTO bodymind_collab_monthly_docs
          (mensile_id,revision,tipo,percorso,sha256,nome_originale,registrato_il)
          VALUES (1,1,'firmato','mock.pdf','hash','mock','now')""")
        self.conn.commit()
        with self.assertRaisesRegex(ValueError,'firmato'):self.insert(2880)
    def test_folder_is_stable_and_tenant_scoped(self):
        f=a.period_folder(self.root,self.collab,2026,10,True)
        self.assertEqual(f,a.period_folder(self.root,self.collab,2026,10,True))
        self.assertIn(self.root.resolve(),f.resolve().parents)
        self.assertTrue(f.exists())
        self.assertIn('Collaboratori',str(f))
    def test_file_creation_refuses_overwrite(self):
        p=a.period_folder(self.root,self.collab,2026,10,True)/'test.pdf'
        a._new_file(p,b'%PDF-1.4 original')
        with self.assertRaises(FileExistsError):a._new_file(p,b'different')
        self.assertEqual(p.read_bytes(),b'%PDF-1.4 original')
    def test_html_folder_create_controls(self):
        page=a.render_page(self.conn,2026,10,'<input name="csrf_token" value="synthetic">',self.root)
        self.assertIn('Ore totali del mese',page)
        self.assertIn('Crea cartella documenti',page)
        self.assertIn('name="csrf_token"',page)
        self.assertNotIn('Registra ore giornaliere',page)
    def test_pdf_is_one_valid_page_with_signature(self):
        self.insert()
        row=self.conn.execute('SELECT * FROM bodymind_collab_monthly').fetchone()
        blob=a.generate_pdf(self.collab,2026,10,row)
        self.assertTrue(blob.startswith(b'%PDF-'))
        self.assertGreater(len(blob),2400)
        (Path(self.tmp.name)/'synthetic_signed_timesheet.pdf').write_bytes(blob)
    def test_invalid_minutes(self):
        for h,m in [('x',0),(47,60),(0,0),(-1,0)]:
            with self.subTest(h=h,m=m),self.assertRaises(ValueError):
                a.valid_hours(h,m,2026,10)
    def test_no_leak_between_periods(self):
        self.insert()
        self.assertIsNone(a.month_state(self.conn,1,2026,11)[0])
        self.assertEqual(a.month_state(self.conn,1,2026,10)[0]['minuti'],2865)

if __name__=='__main__': unittest.main()
