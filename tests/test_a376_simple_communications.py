"""A376 UI checks: legacy queue retired, active shared payment link shown, read-only."""
import importlib.util,sys,types,unittest
from pathlib import Path
flask=types.ModuleType('flask')
flask.redirect=lambda *args:None
flask.request=None
sys.modules.setdefault('flask',flask)
p=Path(__file__).parents[1]/'bootstrap'/'a376_simple_communications.py'
spec=importlib.util.spec_from_file_location('bm376',p)
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)

class SimplifyTests(unittest.TestCase):
    def setUp(self):
        self.page="""<html><body><aside class='sidebar' id='app-sidebar'><div class='nav-group nav-accordion'>
<a href='/motore-automazioni' class='nav-link'>Automazioni · SMS</a>
<a href='/segreteria/comunicazioni' class='nav-link'>Invii e comunicazioni</a>
<a href='/segreteria/whatsapp' class='nav-link'>WhatsApp · Coda invii</a>
<a href='/pagamenti' class='nav-link'>Pagamenti</a></div></aside><main class='content'>Ciao</main></body></html>"""
    def test_old_menu_removed(self):
        n=a.remove_obsolete_links(self.page)
        self.assertNotIn("href='/segreteria/whatsapp'",n)
        self.assertNotIn("href='/motore-automazioni'",n)
        self.assertIn("href='/segreteria/comunicazioni'",n)
        self.assertIn('Comunicazioni e promemoria',n)
        self.assertIn("href='/pagamenti'",n)
    def test_clean_non_admin_html(self):
        v='<body>Area Famiglie</body>'
        self.assertEqual(a.remove_obsolete_links(v),v)
    def test_shared_link_active(self):
        s=a.shared_banner('https://pay.sumup.com/b2c/QO5TN5OX')
        self.assertIn('https://pay.sumup.com/b2c/QO5TN5OX',s)
        self.assertNotIn('Link SumUp condiviso attivato',s)
    def test_shared_link_missing(self):
        s=a.shared_banner('')
        self.assertIn('Nessun link SumUp condiviso attivato',s)
        self.assertNotIn('link SumUp assente',s)
    def test_no_backups_or_send_controls(self):
        s=a.shared_banner('https://pay.sumup.com/b2c/QO5TN5OX')
        self.assertNotIn('<form',s)
        self.assertNotIn('name="backup_confirmed"',s)
        self.assertNotIn('type="submit"',s)
        self.assertNotIn('name="offsets"',s)
if __name__=='__main__':unittest.main()
