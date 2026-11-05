"""A367 synthetic-only tests: no production connections or personal records."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import types
import unittest
from datetime import date

if 'flask' not in sys.modules:
    flask=types.ModuleType('flask')
    flask.abort=lambda *a: None
    flask.make_response=lambda *a: None
    flask.redirect=lambda *a: None
    flask.request=None
    sys.modules['flask']=flask

# Import needs the A364 helper module; create safe stand-ins for pure functions.
if 'a364_monthly_attendance' not in sys.modules:
    import calendar,html,re
    a364=types.ModuleType('a364_monthly_attendance')
    a364.esc=lambda x: html.escape(str(x),quote=True)
    a364.month_name=lambda x: x.strftime('%Y-%m')
    def parse_month(raw):
        if not re.fullmatch(r'20[0-9]{2}-(0[1-9]|1[0-2])',str(raw)):
            raise ValueError('bad')
        return date(int(raw[:4]),int(raw[5:]),1)
    a364.parse_month=parse_month
    a364.next_month=lambda d: date(d.year+int(d.month==12),d.month%12+1,1)
    sys.modules['a364_monthly_attendance']=a364

target=Path(__file__).parents[1]/'bootstrap'/'a367_attendance_corrections.py'
spec=importlib.util.spec_from_file_location('a367_attendance_corrections',target)
a367=importlib.util.module_from_spec(spec)
spec.loader.exec_module(a367)


def connection():
    c=sqlite3.connect(':memory:')
    c.row_factory=sqlite3.Row
    c.execute('''CREATE TABLE presenze (
        id INTEGER PRIMARY KEY,tesserato_id INTEGER,corso_id INTEGER,data TEXT,
        stato TEXT,note TEXT,created_at TEXT,updated_at TEXT,chiusa INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE tesserati (id INTEGER,nome TEXT,cognome TEXT)''')
    c.execute('''CREATE TABLE corsi (id INTEGER,nome TEXT,orario TEXT)''')
    c.execute("INSERT INTO tesserati VALUES (1,'Anna','Prova')")
    c.execute("INSERT INTO tesserati VALUES (2,'Berta','Test')")
    c.execute("INSERT INTO corsi VALUES (8,'Adult 3/4','20:30')")
    c.execute("INSERT INTO presenze VALUES (7,1,8,'2026-10-20','presente','','x','stamp1',0)")
    c.execute("INSERT INTO presenze VALUES (8,2,8,'2026-10-20','presente','','x','stamp2',0)")
    c.commit()
    return c


class TestCorrections(unittest.TestCase):
    def setUp(self):
        self.con=connection()
        self.month=date(2026,10,1)
        self.calls=[]
        def reconcile(cursor,course,day,ids):
            self.calls.append((course,day,ids))
        self.reconciler=reconcile
    def tearDown(self):self.con.close()
    def act(self,**kwargs):
        payload=dict(presenza_id=7,expected_updated_at='stamp1',
            operation='modifica',new_status='assente',month=self.month,
            reason='Correzione riscontro',actor='admin',reconciler=self.reconciler)
        payload.update(kwargs)
        return a367.apply_change(self.con,**payload)
    def test_status_change_in_place_with_audit_and_reconciliation(self):
        self.act()
        self.assertEqual(self.con.execute('SELECT stato FROM presenze WHERE id=7').fetchone()[0],'assente')
        self.assertEqual(self.calls[-1],(8,'2026-10-20',{2}))
        audit=self.con.execute('SELECT * FROM bodymind_a367_attendance_corrections').fetchone()
        self.assertEqual(audit['operazione'],'modifica')
        self.assertEqual(json.loads(audit['precedente_json'])['stato'],'presente')
        self.assertEqual(audit['operatore'],'admin')
    def test_remove_one_not_whole_day(self):
        self.act(operation='elimina',new_status=None)
        self.assertIsNone(self.con.execute('SELECT id FROM presenze WHERE id=7').fetchone())
        self.assertIsNotNone(self.con.execute('SELECT id FROM presenze WHERE id=8').fetchone())
        self.assertEqual(self.calls[-1][-1],{2})
        self.assertEqual(self.con.execute('SELECT operazione FROM bodymind_a367_attendance_corrections').fetchone()[0],'elimina')
    def test_historical_month_listing(self):
        self.assertEqual(len(a367.month_rows(self.con,self.month)),2)
        self.assertEqual(len(a367.month_rows(self.con,date(2026,11,1))),0)
    def test_bad_month_fails_without_write(self):
        with self.assertRaises(ValueError): self.act(month=date(2026,11,1))
        self.assertEqual(self.con.execute('SELECT count(*) FROM presenze').fetchone()[0],2)
    def test_stale_submission_fails(self):
        with self.assertRaisesRegex(ValueError,'cambiata'):self.act(expected_updated_at='old')
    def test_invalid_state_fails(self):
        with self.assertRaises(ValueError):self.act(new_status='not-valid')
    def test_reason_required(self):
        with self.assertRaises(ValueError):self.act(reason='x')
    def test_closed_entries_protected(self):
        self.con.execute("UPDATE presenze SET chiusa=1 WHERE id=7")
        self.con.commit()
        with self.assertRaisesRegex(ValueError,'chiusa'):self.act()
    def test_atomic_rollback_on_reconcile_error(self):
        def broken(*a): raise RuntimeError('synthetic')
        with self.assertRaises(RuntimeError):self.act(reconciler=broken)
        self.assertEqual(self.con.execute('SELECT stato FROM presenze WHERE id=7').fetchone()[0],'presente')
        tab=self.con.execute("SELECT count(*) FROM sqlite_master WHERE name='bodymind_a367_attendance_corrections'").fetchone()[0]
        self.assertEqual(tab,0)
    def test_no_op_rejected(self):
        with self.assertRaises(ValueError): self.act(new_status='presente')
    def test_console_actions_are_explicit(self):
        page=a367.render_console(a367.month_rows(self.con,self.month),self.month,
             '<input type="hidden" name="csrf_token" value="test">',False)
        self.assertIn('/presenze/storico/azione',page)
        self.assertIn('Elimina questa registrazione',page)
        self.assertIn('name="csrf_token"',page)
        self.assertIn('confirm(',page)
        self.assertNotIn('Elimina tutto il mese',page)

if __name__=='__main__':unittest.main()
