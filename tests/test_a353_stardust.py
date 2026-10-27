"""A353: visual overlay safety and deterministic A352 -> A353 migration tests."""
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('a353_runtime',ROOT/'bootstrap/clean_runtime_launcher.py')
M=importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

def pinned():
    return [
        patch.object(M,'A351_CSS_PATH',ROOT/'bootstrap/family_a351_sunrise.css'),
        patch.object(M,'A351_JS_PATH',ROOT/'bootstrap/family_a351_sunrise.js'),
        patch.object(M,'A352_CSS_PATH',ROOT/'bootstrap/family_a352_visible_atmosphere.css'),
        patch.object(M,'A352_JS_PATH',ROOT/'bootstrap/family_a352_visible_atmosphere.js'),
        patch.object(M,'A353_CSS_PATH',ROOT/'bootstrap/family_a353_stardust.css'),
        patch.object(M,'A353_JS_PATH',ROOT/'bootstrap/family_a353_stardust.js')
    ]

class StardustVisualTests(unittest.TestCase):
    def test_assets_pinned_and_animated(self):
        with pinned()[0],pinned()[1],pinned()[2],pinned()[3],pinned()[4],pinned()[5]:
            css,js=M.a353_assets()
        for needle in [b'@keyframes bm353-river-a',b'@keyframes bm353-river-b',
                       b'@keyframes bm353-river-c',b'bm353-vapor--peach',
                       b'prefers-reduced-motion',b'.hero .hero-content',
                       b'background:transparent!important',b'mask-image:radial-gradient']:
            self.assertIn(needle,css)
        self.assertIn(b'addVapor(hero)',js)
        self.assertIn(b'addVapor(main)',js)
        for unsafe in [b'fetch(',b'localStorage',b'document.cookie',b'XMLHttpRequest']:
            self.assertNotIn(unsafe,js)
        self.assertIn(b'playsinline',js)

    def test_transform_byte_exact_and_idempotence_guard(self):
        from contextlib import ExitStack
        with ExitStack() as stack, tempfile.TemporaryDirectory() as td:
            for ctx in pinned():stack.enter_context(ctx)
            original_css=M.A351_CSS_PATH.read_bytes()
            original_js=M.A351_JS_PATH.read_bytes()
            a351=b"PORTAL='''"+original_css+b'\\n/*END CSS*/\\n'+original_js+b"\\n'''\\n"
            stack.enter_context(patch.object(M,'A352_A351_LIVE_SHA',hashlib.sha256(a351).hexdigest()))
            baseline=Path(td)/'a351.py'
            baseline.write_bytes(a351)
            stack.enter_context(patch.object(M,'A352_BACKUP',baseline))
            a352,_=M.a352_expected_from_a351(a351)
            new,sha=M.a353_expected_from_a352(a352)
            compile(new,'synthetic_a353.py','exec')
            self.assertEqual(hashlib.sha256(new).hexdigest(),sha)
            self.assertEqual(new.count(b'BODYMIND A353 STARDUST VISUAL'),1)
            self.assertEqual(new.count(b'BODYMIND A353 STARDUST SCRIPT'),1)
            self.assertIn(a352[:450],new)
            self.assertIn(original_css,new)
            self.assertIn(original_js,new)
            with self.assertRaisesRegex(RuntimeError,'exact approved A352'):
                M.a353_expected_from_a352(a352+b'!')
            with self.assertRaisesRegex(RuntimeError,'exact approved A352'):
                M.a353_expected_from_a352(new)

    def test_launcher_guards_live_data(self):
        code=(ROOT/'bootstrap/clean_runtime_launcher.py').read_text()
        for expected in ['sqlite_readonly_check(db)','A353_BACKUP','a353_matches(root,found)',
                         'maybe_apply_a353(args.root,args.db)','BODYMIND_A353_RECOVER_A352']:
            self.assertIn(expected,code)
        docker=(ROOT/'Dockerfile').read_text()
        self.assertIn('COPY bootstrap/family_a353_stardust.css',docker)
        self.assertIn('COPY bootstrap/family_a353_stardust.js',docker)

if __name__=='__main__':
    unittest.main()
