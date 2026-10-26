import hashlib
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class TestA349Atelier(unittest.TestCase):
    def test_sha_and_mobile_editorial(self):
        css=(ROOT/'bootstrap/family_a349_atelier.css').read_bytes()
        self.assertEqual(hashlib.sha256(css).hexdigest(),
          'db983b38f78887ef5a7b9593f8199634467f15afd897e20cf734dfcbe2092f96')
        c=css.decode('utf-8')
        for req in (
          'aspect-ratio:auto!important','height:auto!important',
          'object-fit:contain!important','.hero .hero-content',
          '.hero .hero-intro h1','.hero-media .hero-playback',
          'main.main .stat:first-child','grid-column:1 / -1!important',
          '.bottom-nav','transform:none!important',
          'bodymind-media-outbound','prefers-reduced-motion',
        ):
            self.assertIn(req,c)
        self.assertEqual(c.count('{'),c.count('}'))
        self.assertNotIn('</style>',c)
        self.assertNotIn('@import',c)
    def test_full_inplace_css_consolidation(self):
        spec=importlib.util.spec_from_file_location('clean_launcher',ROOT/'bootstrap/clean_runtime_launcher.py')
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        names=['family_a341.css','family_a342_motion.css',
               'family_a343_visible_waves.css','family_a344_luxury.css',
               'family_a345_fullframe.css','family_a346_editorial.css',
               'family_a347_overlay.css','family_a348_navfix.css']
        layers=[(ROOT/'bootstrap'/n).read_bytes() for n in names]
        curated=(ROOT/'bootstrap/family_a349_atelier.css').read_bytes()
        # Use the exact separator sequence the launcher used for each release.
        legacy=b'\n'.join([b'<style>',*[b'\n'+layer+b'\n' for layer in layers],b'</style>\n</head>'])
        sentinel=b'\n<script id="bodymind-media-links">KEEP_SOCIAL_ACTIONS</script>\n'
        converted=module.a349_consolidate_styles(legacy+sentinel,layers,curated)
        self.assertIn(sentinel,converted)
        self.assertIn(b'BODYMIND A349 CONSOLIDATED STYLE',converted)
        self.assertEqual(converted.count(curated),1)
        self.assertEqual(converted.count(layers[0]),1)
        self.assertEqual(converted.count(layers[1]),1)
        for old in layers[2:]:
            self.assertNotIn(old,converted)
        with self.assertRaises(RuntimeError):
            module.a349_consolidate_styles(legacy+sentinel,layers[:7],curated)
        with self.assertRaises(RuntimeError):
            module.a349_consolidate_styles(legacy+sentinel.replace(b'KEEP_SOCIAL_ACTIONS',b'KEEP_SOCIAL_ACTIONS')+b'\n'+layers[3]+b'\n',layers,curated)
    def test_preflight_and_rollback_guard(self):
        launcher=(ROOT/'bootstrap/clean_runtime_launcher.py').read_text()
        compile(launcher,'clean_runtime_launcher.py','exec')
        docker=(ROOT/'Dockerfile').read_text()
        for req in (
            'and not a349_matches(root,found)',
            'maybe_apply_a349_family_ui(args.root,args.db)',
            'maybe_recover_a349_to_a348(args.root,args.db)',
            'BODYMIND_A349_RECOVER_A348',
            'A349_CSS_SHA256',
            'a349_consolidate_styles',
            'sqlite_readonly_check(db)',
        ):
            self.assertIn(req,launcher)
        self.assertIn('COPY bootstrap/family_a349_atelier.css',docker)

if __name__=='__main__':
    unittest.main()
