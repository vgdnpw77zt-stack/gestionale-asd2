import hashlib
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class TestA344LuxuryRelease(unittest.TestCase):
    def test_css_digest_is_pinned(self):
        css = (ROOT / 'bootstrap' / 'family_a344_luxury.css').read_bytes()
        self.assertEqual(hashlib.sha256(css).hexdigest(),
                         '896a7bbfe4c58caee6c85f9ef50409ed675f6ca76d995a6d6d57c9f8e25799eb')
        self.assertNotIn(b'</style>', css)
        self.assertNotIn(b"'''", css)
    def test_visual_only_and_accessible(self):
        css = (ROOT / 'bootstrap' / 'family_a344_luxury.css').read_text()
        for selector in ('main.main::before', '.hero', '.media-card', 'focus-visible', 'prefers-reduced-motion'):
            self.assertIn(selector, css)
        for forbidden in ('@import', 'url(http', 'database', 'DROP TABLE', 'api_key'):
            self.assertNotIn(forbidden, css)
    def test_fail_closed_manifest_and_recovery(self):
        launcher = (ROOT / 'bootstrap' / 'clean_runtime_launcher.py').read_text()
        docker = (ROOT / 'Dockerfile').read_text()
        self.assertIn('and not a344_matches(root,found)', launcher)
        self.assertIn('maybe_apply_a344_family_ui(args.root,args.db)', launcher)
        self.assertIn('maybe_recover_a344_to_a343(args.root,args.db)', launcher)
        self.assertIn('BODYMIND_A344_RECOVER_A343', launcher)
        self.assertIn('sqlite_readonly_check(db)', launcher)
        self.assertIn('COPY bootstrap/family_a344_luxury.css', docker)

if __name__ == '__main__':
    unittest.main()
