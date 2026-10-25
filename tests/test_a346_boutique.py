import hashlib
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class TestA346BoutiqueRelease(unittest.TestCase):
    def test_exact_stylesheet_and_mobile_flow(self):
        css=(ROOT/'bootstrap/family_a346_editorial.css').read_bytes()
        self.assertEqual(hashlib.sha256(css).hexdigest(),
                         'd3f105233e1496dded3aaea599c7361e513dcc4987fa3b662d330a8df1d566ab')
        content=css.decode('utf-8')
        for rule in ('.hero-intro .pill','top:auto!important','position:relative!important',
                     '.hero-media','object-fit:contain!important','.bottom-nav',
                     'main.main .stat','.section-heading h2','main.main .media-card',
                     '@media(max-width:760px)','prefers-reduced-motion'):
            self.assertIn(rule,content)
        for bad in ('object-fit:cover','</style>', '@import','url(http', 'DROP TABLE'):
            self.assertNotIn(bad,content)
    def test_launcher_fail_closed_version_and_recovery(self):
        src=(ROOT/'bootstrap/clean_runtime_launcher.py').read_text()
        docker=(ROOT/'Dockerfile').read_text()
        compile(src,'clean_runtime_launcher.py','exec')
        self.assertIn('and not a346_matches(root,found)',src)
        self.assertIn('maybe_apply_a346_family_ui(args.root,args.db)',src)
        self.assertIn('maybe_recover_a346_to_a345(args.root,args.db)',src)
        self.assertIn("BODYMIND_A346_RECOVER_A345",src)
        self.assertIn("sqlite_readonly_check(db)",src)
        self.assertIn('COPY bootstrap/family_a346_editorial.css',docker)

if __name__=='__main__':unittest.main()
