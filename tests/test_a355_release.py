"""A355 immutable migration tests: exact A354 baseline, CSS and Python studio appending."""
import hashlib
import importlib.util
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('a355_launcher',ROOT/'bootstrap/clean_runtime_launcher.py')
M=importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

def patched_paths():
    mapping={
        'A351_CSS_PATH':'bootstrap/family_a351_sunrise.css',
        'A351_JS_PATH':'bootstrap/family_a351_sunrise.js',
        'A352_CSS_PATH':'bootstrap/family_a352_visible_atmosphere.css',
        'A352_JS_PATH':'bootstrap/family_a352_visible_atmosphere.js',
        'A353_CSS_PATH':'bootstrap/family_a353_stardust.css',
        'A353_JS_PATH':'bootstrap/family_a353_stardust.js',
        'A354_CSS_PATH':'bootstrap/family_a354_luxury_poetic.css',
        'A354_JS_PATH':'bootstrap/family_a354_luxury_poetic.js',
        'A355_CSS_PATH':'bootstrap/family_a355_dark_cinema.css',
        'A355_JS_PATH':'bootstrap/family_a355_studio_link.js',
        'A355_STUDIO_PATH':'bootstrap/bodymind_a355_film_studio.py',
    }
    return [patch.object(M,key,ROOT/path) for key,path in mapping.items()]

class A355ProductionGuard(unittest.TestCase):
    def test_visual_directly_over_movie(self):
        with ExitStack() as stack:
            for ctx in patched_paths():stack.enter_context(ctx)
            css,js,studio=M.a355_assets()
        self.assertIn(b'grid-area:1 / 1',css)
        self.assertIn(b'.hero .hero-content',css)
        self.assertIn(b'background:none!important',css)
        self.assertIn(b'#030e18',css)
        self.assertIn(b'bm355-film-card',js)
        self.assertIn(b'install_family_film_studio',studio)
        self.assertIn(b'ffprobe',studio)
        for forbidden in (b'openai.',b'https://',b'XMLHttpRequest('):
            self.assertNotIn(forbidden,studio)

    def test_exact_source_update_and_rollback_guards(self):
        with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
            for ctx in patched_paths():stack.enter_context(ctx)
            css=M.A351_CSS_PATH.read_bytes()
            js=M.A351_JS_PATH.read_bytes()
            a351=b"PORTAL='''"+css+bytes([10])+b'/*END CSS*/'+bytes([10])+js+bytes([10])+b"'''"+bytes([10])+b'_bm351_album.install_family_gallery(app, db)'+bytes([10])
            p351=Path(directory)/'a351.py';p351.write_bytes(a351)
            stack.enter_context(patch.object(M,'A352_A351_LIVE_SHA',hashlib.sha256(a351).hexdigest()))
            stack.enter_context(patch.object(M,'A352_BACKUP',p351))
            a352,_=M.a352_expected_from_a351(a351)
            p352=Path(directory)/'a352.py';p352.write_bytes(a352)
            stack.enter_context(patch.object(M,'A353_BACKUP',p352))
            a353,_=M.a353_expected_from_a352(a352)
            p353=Path(directory)/'a353.py';p353.write_bytes(a353)
            stack.enter_context(patch.object(M,'A354_BACKUP',p353))
            a354,_=M.a354_expected_from_a353(a353)
            a355,sha=M.a355_expected_from_a354(a354)
            self.assertEqual(hashlib.sha256(a355).hexdigest(),sha)
            self.assertIn(a354[:500],a355)
            self.assertIn(M.A355_CSS_PATH.read_bytes(),a355)
            self.assertIn(M.A355_JS_PATH.read_bytes(),a355)
            self.assertEqual(a355.count(b'BODYMIND A355 FILM STUDIO'),2)
            compile(a355,'a355_private_release.py','exec')
            with self.assertRaisesRegex(RuntimeError,'exact approved A354'):
                M.a355_expected_from_a354(a354+b' ')
            with self.assertRaisesRegex(RuntimeError,'exact approved A354'):
                M.a355_expected_from_a354(a355)

if __name__=='__main__':
    unittest.main()
