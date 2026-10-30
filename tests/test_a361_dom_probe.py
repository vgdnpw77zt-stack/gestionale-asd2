"""A361: verify authenticated-route-only structural probe, no PII and no side effects."""
import importlib.util,unittest
from pathlib import Path
from unittest.mock import patch
from flask import Flask
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('a361',ROOT/'bootstrap/clean_runtime_launcher.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)
s=importlib.util.spec_from_file_location('diag',ROOT/'bootstrap/family_a361_runtime.py')
R=importlib.util.module_from_spec(s);s.loader.exec_module(R)
class A361Probe(unittest.TestCase):
    def test_markup_delivery_and_json_safety(self):
        app=Flask(__name__)
        @app.get('/app-tesserato/fake-only')
        def family():return '<html><head></head><body><section class="hero"></section></body></html>'
        @app.get('/private')
        def priv():return '<html><body>unchanged</body></html>'
        R.install(app,lambda:b'(function(){})();')
        c=app.test_client()
        page=c.get('/app-tesserato/fake-only')
        self.assertEqual(page.status_code,200)
        self.assertIn(b'id="bodymind-a361-probe"',page.data)
        self.assertNotIn(b'bodymind-a361-probe',c.get('/private').data)
        self.assertEqual(c.get('/_bodymind_a361_probe.js').status_code,200)
        self.assertEqual(c.post('/_bodymind_a361_probe',json={'family':True,'hero':{'found':True},'name':'DO_NOT_LOG'}).status_code,204)
    def test_immutable_parent(self):
        with patch.object(M,'A361_JS_PATH',ROOT/'bootstrap/family_a361_probe.js'),patch.object(M,'A361_RUNTIME_PATH',ROOT/'bootstrap/family_a361_runtime.py'):
            js,code=M.a361_assets()
        self.assertIn(b'getComputedStyle',js)
        self.assertEqual(M.A361_REL,M.A360_REL)
        self.assertNotEqual(M.A361_BACKUP,M.A360_BACKUP)
if __name__=='__main__':unittest.main()
