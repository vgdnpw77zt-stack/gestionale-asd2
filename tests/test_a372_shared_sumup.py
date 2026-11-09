"""Synthetic tests for shared SumUp link validation and family presentation."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest

flask=types.ModuleType('flask')
for name in ('abort','make_response','redirect'):
    setattr(flask,name,lambda *args,**kwargs:None)
flask.request=None
sys.modules.setdefault('flask',flask)

target=Path(__file__).parents[1]/'bootstrap'/'a372_sumup_shared.py'
spec=importlib.util.spec_from_file_location('a372_sumup_shared',target)
a=importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class SumUpSharedTests(unittest.TestCase):
    def test_allowed_pay_sumup(self):
        self.assertEqual(a.validate_url('https://pay.sumup.com/b2c/exampleToken'),
                         'https://pay.sumup.com/b2c/exampleToken')
    def test_allowed_sumup_me(self):
        self.assertEqual(a.validate_url('https://sumup.me/p/test'),
                         'https://sumup.me/p/test')
    def test_malicious_host_rejected(self):
        for u in ['https://pay.sumup.com.attacker.net/b2c/x','http://pay.sumup.com/b2c/x',
                  'https://fake.sumup.net/b2c/x','https://pay.sumup.com@evil.com/link']:
            with self.subTest(u=u),self.assertRaises(ValueError):a.validate_url(u)
    def test_scripts_and_crlf_rejected(self):
        for u in ['https://pay.sumup.com/b2c/a\nX','https://pay.sumup.com/b2c/a" onmouseover="x',
                  'javascript:alert(1)']:
            with self.subTest(u=u),self.assertRaises(ValueError):a.validate_url(u)
    def test_disabled_unavailable(self):
        self.assertEqual(a.stored_link({'bodymind_sumup_open_amount':{'url':'https://sumup.me/p/abc','enabled':False}}),'')
    def test_no_amount_shown(self):
        html=a.family_button('https://pay.sumup.com/b2c/a')
        self.assertIn('inserisci l’importo',html.lower())
        for number in ['50 €','70 €','90 €']:
            self.assertNotIn(number,html)
        self.assertIn('non cambia automaticamente',html)
    def test_only_due_families_are_shown_link(self):
        self.assertTrue(a.family_due('<strong class="status-chip unpaid">Da pagare</strong>'))
        self.assertFalse(a.family_due('<strong>Pagato</strong>'))
        self.assertFalse(a.family_due('<strong>Da verificare</strong>'))
    def test_original_athlete_token_not_in_shared_link(self):
        html=a.family_button('https://sumup.me/p/unique')
        self.assertNotIn('tesserato',html.lower())
        self.assertIn('https://sumup.me/p/unique',html)

if __name__=='__main__':unittest.main()
