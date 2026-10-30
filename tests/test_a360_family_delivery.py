"""A360: verify actual family HTML stylesheet delivery without personal data."""
import importlib.util,unittest
from pathlib import Path
from unittest.mock import patch
from flask import Flask
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('a360',ROOT/'bootstrap/clean_runtime_launcher.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)
sr=importlib.util.spec_from_file_location('runtime',ROOT/'bootstrap/family_a360_runtime.py')
R=importlib.util.module_from_spec(sr);sr.loader.exec_module(R)
class A360Delivery(unittest.TestCase):
    def test_family_css_in_html_and_private_routes_unchanged(self):
        app=Flask(__name__)
        @app.get('/app-tesserato/fake-test-only')
        def family():return '<html><head></head><body><section class="hero">Sample</section></body></html>'
        @app.get('/health')
        def health():return {'ok':True}
        @app.get('/app-tesserato/fake-test-only/album/status')
        def album():return {'private':True}
        R.install(app,lambda:b'/* BODYMIND A360 */')
        client=app.test_client()
        page=client.get('/app-tesserato/fake-test-only')
        self.assertEqual(page.status_code,200)
        self.assertIn('id="bodymind-a360-style"',page.get_data(as_text=True))
        self.assertEqual(page.headers['X-BodyMind-Family-UI'],'A360')
        self.assertEqual(page.headers['Cache-Control'],'no-store, max-age=0')
        page_second=client.get('/app-tesserato/fake-test-only').get_data(as_text=True)
        self.assertEqual(page_second.count('bodymind-a360-style'),1)
        css=client.get('/_bodymind_family_a360.css?v=20261030-a360')
        self.assertEqual(css.status_code,200)
        self.assertIn('BODYMIND A360',css.get_data(as_text=True))
        self.assertEqual(css.headers['Cache-Control'],'no-store, max-age=0')
        self.assertEqual(client.get('/health').json,{'ok':True})
        self.assertEqual(client.get('/app-tesserato/fake-test-only/album/status').json,{'private':True})
    def test_integrity_and_parent_safety(self):
        with patch.object(M,'A360_CSS_PATH',ROOT/'bootstrap/family_a360_cinematic_delivery.css'),patch.object(M,'A360_RUNTIME_PATH',ROOT/'bootstrap/family_a360_runtime.py'):
            css,runtime=M.a360_assets()
        for token in (b'.hero::before',b'.hero .hero-intro',b'@keyframes bm360-cloud-flow',b'prefers-reduced-motion'):
            self.assertIn(token,css)
        self.assertIn(b"request.path",runtime)
        self.assertEqual(M.A360_REL,M.A359_REL)
        self.assertNotEqual(M.A360_BACKUP,M.A359_BACKUP)
        with patch.object(M,'A359_BACKUP',ROOT/'tests/nonexistent_a360_parent.py'):
            with self.assertRaisesRegex(RuntimeError,'immutable A358'):
                M.a360_expected_from_a359(b'unknown')
if __name__=='__main__':unittest.main()
