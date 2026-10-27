"""BodyMind A351 immutable visual-layer and rollback tests; synthetic only."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('bm351',ROOT/'bootstrap/clean_runtime_launcher.py')
M=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)

class A351VisualSafety(unittest.TestCase):
    def test_locked_css_and_javascript(self):
        with patch.object(M,'A351_CSS_PATH',ROOT/'bootstrap/family_a351_sunrise.css'), patch.object(M,'A351_JS_PATH',ROOT/'bootstrap/family_a351_sunrise.js'), patch.object(M,'A350_CSS_PATH',ROOT/'bootstrap/family_a350_signature.css'), patch.object(M,'A350_JS_PATH',ROOT/'bootstrap/family_a350_verified_gallery.js'):
            css,js=M.a351_assets()
        self.assertEqual(M.a350_git_blob(css),M.A351_CSS_BLOB)
        self.assertEqual(M.a350_git_blob(js),M.A351_JS_BLOB)
        self.assertIn(b'bm351-atmosphere',css)
        self.assertIn(b'bm351-dock-toggle',js)
        self.assertIn(b'prefers-reduced-motion',css)
        self.assertIn(b'family-hero-video',css)
        self.assertIn(b'filter:none!important',css)
        self.assertIn(b'fetch(ownBase+\"/status\"',js)
        self.assertNotIn(b'fetch(\"https://',js)
        self.assertNotIn(b'localStorage',js)
        self.assertNotIn(b'document.cookie',js)
        self.assertNotIn(b'innerHTML',js)

    def test_patch_is_additive_and_reversible_on_synthetic_html(self):
        old_css=(ROOT/'bootstrap/family_a350_signature.css').read_bytes()
        old_js=(ROOT/'bootstrap/family_a350_verified_gallery.js').read_bytes()
        old=(b"PAGE = '''<html><head><style>BASE VIDEO\n"+old_css+b"\n</style>\n</head>\n"
             b'<body><main class="main">PRIVATE CONTENT</main>\n'
             b"<script>\n"+old_js+b"\n</script>\n"
             b'<nav class="bottom-nav"><a href="#home">Home</a></nav>\n'
             b"</body></html>'''\n")
        sha=hashlib.sha256(old).hexdigest()
        with patch.object(M,'A351_A350_LIVE_SHA',sha), patch.object(M,'A351_CSS_PATH',ROOT/'bootstrap/family_a351_sunrise.css'), patch.object(M,'A351_JS_PATH',ROOT/'bootstrap/family_a351_sunrise.js'), patch.object(M,'A350_CSS_PATH',ROOT/'bootstrap/family_a350_signature.css'), patch.object(M,'A350_JS_PATH',ROOT/'bootstrap/family_a350_verified_gallery.js'):
            new,newhash=M.a351_expected_from_a350(old)
            compile(new,'a351_mock.py','exec')
            self.assertEqual(hashlib.sha256(new).hexdigest(),newhash)
            self.assertIn(b'PRIVATE CONTENT',new)
            self.assertIn(b'BASE VIDEO',new)
            self.assertEqual(new.count(b'BODYMIND A351 SUNRISE'),1)
            self.assertEqual(new.count(b'BODYMIND A351 DOCK'),1)
            self.assertNotIn(b'ALTER TABLE',new)
            self.assertNotIn(b'DROP TABLE',new)
            self.assertNotEqual(old,new)
            with self.assertRaisesRegex(RuntimeError,'SHA'):
                M.a351_expected_from_a350(new)
            with self.assertRaisesRegex(RuntimeError,'SHA'):
                M.a351_expected_from_a350(old+b' ')

    def test_fails_closed_when_template_anchors_are_missing(self):
        old=b"PAGE = '''<html><body>HELLO</body></html>'''\n"
        with patch.object(M,'A351_A350_LIVE_SHA',hashlib.sha256(old).hexdigest()), patch.object(M,'A351_CSS_PATH',ROOT/'bootstrap/family_a351_sunrise.css'), patch.object(M,'A351_JS_PATH',ROOT/'bootstrap/family_a351_sunrise.js'), patch.object(M,'A350_CSS_PATH',ROOT/'bootstrap/family_a350_signature.css'), patch.object(M,'A350_JS_PATH',ROOT/'bootstrap/family_a350_verified_gallery.js'):
            with self.assertRaisesRegex(RuntimeError,'anchors'):
                M.a351_expected_from_a350(old)

    def test_only_cosmetic_source_changes_are_authorized(self):
        launcher=(ROOT/'bootstrap/clean_runtime_launcher.py').read_text()
        self.assertIn("maybe_apply_a351_sunrise(args.root,args.db)",launcher)
        self.assertIn("BODYMIND_A351_RECOVER_A350",launcher)
        self.assertIn("A351_BACKUP",launcher)
        self.assertIn("sqlite_readonly_check(db)",launcher)
        self.assertIn("if a351_matches(root,found):",launcher)
        self.assertIn("if not a350_matches(root,found):",launcher)
        self.assertNotIn("os.remove('/data/tenants",launcher)
        docker=(ROOT/'Dockerfile').read_text()
        self.assertIn('COPY bootstrap/family_a351_sunrise.css',docker)
        self.assertIn('COPY bootstrap/family_a351_sunrise.js',docker)

if __name__=='__main__':
    unittest.main()
