"""A375 isolated regression tests: no production database or storage writes."""
import importlib.util
from pathlib import Path
import sqlite3
import sys
import types
import unittest

flask=types.ModuleType('flask')
for x in ('request','redirect','make_response'):setattr(flask,x,None)
sys.modules.setdefault('flask',flask)
src=Path(__file__).parents[1]/'bootstrap'/'a375_uscite_nav.py'
spec=importlib.util.spec_from_file_location('bm375',src)
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.page='''<html><body><aside class='sidebar' id='app-sidebar'><div class='nav-group nav-accordion'><a class='nav-link' href='/pagamenti'>Registra incasso</a><a href='/impostazioni/pagamenti-online'>Impostazioni SumUp e pagamenti online</a><a href='/ricevute'>Ricevute</a></div></aside><main class='content'>Dashboard</main></body></html>'''
    def test_uscite_in_payments(self):
        page=a.nav_html(self.page,'/')
        self.assertIn('href="/pagamenti/uscite"',page)
        self.assertIn('href="/contabilita/verifica"',page)
        self.assertIn('href="/impostazioni/sumup-libero"',page)
        self.assertLess(page.index('/pagamenti/uscite'),page.index("href='/ricevute'"))
        self.assertIn('id="bm375-shortcuts"',page)
    def test_legacy_settings_link_retired(self):
        p=a.nav_html(self.page,'/')
        self.assertNotIn("href='/impostazioni/pagamenti-online'",p)
        self.assertIn('SumUp · Link unico',p)
    def test_idempotent(self):
        p=a.nav_html(self.page,'/')
        pp=a.nav_html(p,'/')
        self.assertEqual(p,pp)
    def test_do_not_modify_family_html(self):
        self.assertEqual(a.nav_html('<body>family page</body>','/app-tesserato/token'),'<body>family page</body>')
    def test_no_shortcuts_on_unrelated_pages(self):
        p=a.nav_html(self.page,'/collaboratori')
        self.assertNotIn('bm375-shortcuts',p)
        self.assertIn('bm375-out-menu',p)
    def test_report_detects_duplicate_no_mutation(self):
        import types
        asd=types.ModuleType('asd_app');asd.__path__=[]
        methods=types.ModuleType('asd_app.bodymind_a253_manual');methods.methods=lambda conn:{}
        sys.modules['asd_app']=asd;sys.modules['asd_app.bodymind_a253_manual']=methods
        try:
            c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row
            c.execute('CREATE TABLE movimenti (id INTEGER PRIMARY KEY,data TEXT,tipo TEXT,descrizione TEXT,importo REAL,auto_generato INTEGER,pagamento_id INTEGER)')
            c.execute('CREATE TABLE bodymind_uscite (id INTEGER PRIMARY KEY,data TEXT,descrizione TEXT,importo REAL,metodo TEXT,allegato_nome TEXT)')
            c.execute("INSERT INTO movimenti VALUES (134313,'2026-11-09','uscita','Compenso Elena',520,0,NULL)")
            c.execute("INSERT INTO bodymind_uscite VALUES (10,'2026-11-09','Elena Mastandrea',520,'bonifico','allegato.pdf')")
            old=c.total_changes
            html=a.review_html(c)
            self.assertIn('uscita #10',html)
            self.assertIn('520,00 €',html)
            self.assertIn('Movimenti da verificare: 1',html)
            self.assertIn('Uscite presenti: 1',html)
            self.assertEqual(old,c.total_changes)
            c.close()
        finally:
            del sys.modules['asd_app.bodymind_a253_manual']
            del sys.modules['asd_app']

if __name__=='__main__':unittest.main()
