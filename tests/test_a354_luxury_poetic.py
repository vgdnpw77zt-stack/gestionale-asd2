"""BodyMind A354: immutable source delta and motion-only regression suite."""
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('a354_clean',ROOT/'bootstrap/clean_runtime_launcher.py')
M=importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

def assets():
    return [
        patch.object(M,'A351_CSS_PATH',ROOT/'bootstrap/family_a351_sunrise.css'),
        patch.object(M,'A351_JS_PATH',ROOT/'bootstrap/family_a351_sunrise.js'),
        patch.object(M,'A352_CSS_PATH',ROOT/'bootstrap/family_a352_visible_atmosphere.css'),
        patch.object(M,'A352_JS_PATH',ROOT/'bootstrap/family_a352_visible_atmosphere.js'),
        patch.object(M,'A353_CSS_PATH',ROOT/'bootstrap/family_a353_stardust.css'),
        patch.object(M,'A353_JS_PATH',ROOT/'bootstrap/family_a353_stardust.js'),
        patch.object(M,'A354_CSS_PATH',ROOT/'bootstrap/family_a354_luxury_poetic.css'),
        patch.object(M,'A354_JS_PATH',ROOT/'bootstrap/family_a354_luxury_poetic.js')
    ]

class LuxuryPoeticTests(unittest.TestCase):
    def test_cosmetic_assets_and_verified_hashes(self):
        with ExitStack() as stack:
            for ctx in assets(): stack.enter_context(ctx)
            css,js=M.a354_assets()
        for needle in (b'bm354-cloud-sweep',b'bm354-hoop',
                       b'prefers-reduced-motion',b'family-hero-video',
                       b'background:transparent!important'):
            self.assertIn(needle,css)
        self.assertIn(b'aria-hidden',js)
        self.assertIn(b'addEventListener',js)
        for prohibited in (b'fetch(',b'XMLHttpRequest',b'localStorage',
                           b'document.cookie',b'sessionStorage'):
            self.assertNotIn(prohibited,js)

    def test_exact_a353_only_and_byte_precise_upgrade(self):
        with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
            for ctx in assets(): stack.enter_context(ctx)
            original_css=M.A351_CSS_PATH.read_bytes()
            original_js=M.A351_JS_PATH.read_bytes()
            a351=b"PORTAL='''"+original_css+bytes([10])+b'/*END CSS*/'+bytes([10])+original_js+bytes([10])+b"'''"+bytes([10])
            a351_path=Path(tmp)/'a351.py'
            a351_path.write_bytes(a351)
            stack.enter_context(patch.object(M,'A352_A351_LIVE_SHA',hashlib.sha256(a351).hexdigest()))
            stack.enter_context(patch.object(M,'A352_BACKUP',a351_path))
            a352,_=M.a352_expected_from_a351(a351)
            a352_path=Path(tmp)/'a352.py'
            a352_path.write_bytes(a352)
            stack.enter_context(patch.object(M,'A353_BACKUP',a352_path))
            a353,_=M.a353_expected_from_a352(a352)
            a354,new_sha=M.a354_expected_from_a353(a353)
            self.assertEqual(hashlib.sha256(a354).hexdigest(),new_sha)
            self.assertIn(a353[:250],a354)
            self.assertEqual(a354.count(b'BODYMIND A354 LUXURY POETIC VISUAL'),1)
            self.assertEqual(a354.count(b'BODYMIND A354 LUXURY POETIC SCRIPT'),1)
            compile(a354,'synthetic_bodymind_a354.py','exec')
            with self.assertRaisesRegex(RuntimeError,'exact A353'):
                M.a354_expected_from_a353(a353+b'!')
            with self.assertRaisesRegex(RuntimeError,'exact A353'):
                M.a354_expected_from_a353(a354)

    def test_clean_launcher_locks_and_docker_assets(self):
        source=(ROOT/'bootstrap/clean_runtime_launcher.py').read_text()
        docker=(ROOT/'Dockerfile').read_text()
        for text in ('a354_matches(root,found)','maybe_apply_a354(args.root,args.db)',
                     'maybe_recover_a354_to_a353(args.root,args.db)',
                     'sqlite_readonly_check(db)','A354_BACKUP'):
            self.assertIn(text,source)
        for text in ('COPY bootstrap/family_a354_luxury_poetic.css',
                     'COPY bootstrap/family_a354_luxury_poetic.js'):
            self.assertIn(text,docker)

if __name__=='__main__':
    unittest.main()
