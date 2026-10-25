import hashlib
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class TestA348Navbar(unittest.TestCase):
    def test_nav_geometry_fixes_original_offset(self):
        css=(ROOT/'bootstrap/family_a348_navfix.css').read_bytes()
        self.assertEqual(hashlib.sha256(css).hexdigest(),
                         'b12c5790a43972eb621ac8f42d2cc6b6ccae6e77ed6d4eca56dc793854a7a2fe')
        s=css.decode('utf-8')
        for rule in ('@media(max-width:760px)','position:fixed!important',
                     'left:12px!important','right:12px!important','transform:none!important',
                     'width:calc(100vw - 24px)!important','max-width:none!important',
                     'box-sizing:border-box!important','display:flex!important',
                     'flex-wrap:nowrap!important','flex:1 1 0!important',
                     '.hero .hero-content','padding-bottom:clamp(92px,13svh,114px)!important',
                     'env(safe-area-inset-bottom)'):
            self.assertIn(rule,s)
        for forbidden in ('object-fit:cover','</style>', '@import','url(http','DROP TABLE'):
            self.assertNotIn(forbidden,s)
        self.assertEqual(s.count('{'),s.count('}'))
    def test_rollback_and_preflight_source_guard(self):
        s=(ROOT/'bootstrap/clean_runtime_launcher.py').read_text()
        compile(s,'clean_runtime_launcher.py','exec')
        for required in ('and not a348_matches(root,found)',
                         'maybe_apply_a348_family_ui(args.root,args.db)',
                         'maybe_recover_a348_to_a347(args.root,args.db)',
                         'BODYMIND_A348_RECOVER_A347','sqlite_readonly_check(db)'):
            self.assertIn(required,s)
        self.assertIn('COPY bootstrap/family_a348_navfix.css',
                      (ROOT/'Dockerfile').read_text())
if __name__=='__main__':unittest.main()
