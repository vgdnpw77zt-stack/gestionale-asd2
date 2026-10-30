"""A359 mobile cinematic atmosphere: integrity, no remote assets, rollback isolation."""
import importlib.util, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('a359',ROOT/'bootstrap/clean_runtime_launcher.py')
M=importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
class A359Home(unittest.TestCase):
    def test_css_integrity(self):
        with patch.object(M,'A359_CSS_PATH',ROOT/'bootstrap/family_a359_cinematic_home.css'):
            css=M.a359_assets()
        for signal in (b'.hero::before',b'.hero::after',b'.hero .hero-content',
                       b'main.main>.bm352-sky::after',b'@keyframes bm359-clouds',
                       b'prefers-reduced-motion',b'forced-colors:active'):
            self.assertIn(signal,css)
        for forbidden in (b'url(https://',b'background-position:',b'filter:blur(',
                          b'<script',b'</style>',b'localStorage',b'fetch('):
            self.assertNotIn(forbidden,css)
    def test_immutable_parent(self):
        self.assertEqual(M.A359_REL,M.A358_REL)
        self.assertNotEqual(M.A359_BACKUP,M.A358_BACKUP)
        with patch.object(M,'A358_BACKUP',ROOT/'tests/nonexistent_a359_parent.py'):
            with self.assertRaisesRegex(RuntimeError,'immutable A357'):
                M.a359_expected_from_a358(b'invalid')
if __name__=='__main__':
    unittest.main()
