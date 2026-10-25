import hashlib
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class TestA347CinemaHero(unittest.TestCase):
    def test_pinned_asset_and_overlay(self):
        css=(ROOT/'bootstrap/family_a347_overlay.css').read_bytes()
        self.assertEqual(hashlib.sha256(css).hexdigest(),
                         'df14c0503d1a7f85a4f0680f7c7583c9c83753f487c0943941b6218d2ec5870e')
        c=css.decode('utf-8')
        for required in (
            '@media(max-width:760px)',
            '.hero .hero-content',
            'position:absolute!important',
            'transform:translateX(-50%)!important',
            '.hero .hero-intro h1',
            '.hero .hero-intro p',
            'background:linear-gradient(180deg,',
            'object-fit:contain!important',
            '.hero .hero-media .hero-playback',
            '.bottom-nav',
            'main.main .stats',
            'prefers-reduced-motion',
        ):
            self.assertIn(required,c)
        for forbidden in ('object-fit:cover','</style>','@import','url(http','DROP TABLE'):
            self.assertNotIn(forbidden,c)
        self.assertEqual(c.count('{'),c.count('}'))
    def test_source_locks_and_recovery(self):
        s=(ROOT/'bootstrap/clean_runtime_launcher.py').read_text()
        docker=(ROOT/'Dockerfile').read_text()
        compile(s,'clean_runtime_launcher.py','exec')
        for marker in (
            'and not a347_matches(root,found)',
            'maybe_apply_a347_family_ui(args.root,args.db)',
            'maybe_recover_a347_to_a346(args.root,args.db)',
            'BODYMIND_A347_RECOVER_A346',
            'A347_CSS_SHA256',
            'sqlite_readonly_check(db)',
        ):
            self.assertIn(marker,s)
        self.assertIn('COPY bootstrap/family_a347_overlay.css',docker)
if __name__=='__main__':
    unittest.main()
