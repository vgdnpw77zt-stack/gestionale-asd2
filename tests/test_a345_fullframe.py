import hashlib
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]

class TestA345FullFrame(unittest.TestCase):
    def test_asset_hashes_and_no_crop(self):
        css=(ROOT/'bootstrap/family_a345_fullframe.css').read_bytes()
        js=(ROOT/'bootstrap/family_a345_fullframe.js').read_bytes()
        self.assertEqual(hashlib.sha256(css).hexdigest(),'3c915aae2b019c0cc495a47dd28f2dd18b3c06cea1fbe9f719e7e21ae0b8e5fc')
        self.assertEqual(hashlib.sha256(js).hexdigest(),'b9580e4586893226471cf07c4dbee0ffa61a369f893622b4847326278c942ab3')
        styles=css.decode()
        self.assertIn('object-fit:contain!important',styles)
        self.assertIn('.hero-media',styles)
        self.assertIn('inset:auto!important',styles)
        self.assertIn('.hero-content',styles)
        self.assertIn('max-width:100%!important',styles)
        self.assertNotIn('object-fit:cover',styles)
        self.assertIn('media.appendChild(button)',js.decode())
    def test_exact_guard_and_rollback(self):
        launcher=(ROOT/'bootstrap/clean_runtime_launcher.py').read_text()
        docker=(ROOT/'Dockerfile').read_text()
        compile(launcher,'clean_runtime_launcher.py','exec')
        self.assertIn('and not a345_matches(root,found)',launcher)
        self.assertIn('maybe_apply_a345_family_ui(args.root,args.db)',launcher)
        self.assertIn('maybe_recover_a345_to_a344(args.root,args.db)',launcher)
        self.assertIn('BODYMIND_A345_RECOVER_A344',launcher)
        self.assertIn('sqlite_readonly_check(db)',launcher)
        self.assertIn('COPY bootstrap/family_a345_fullframe.css',docker)
        self.assertIn('COPY bootstrap/family_a345_fullframe.js',docker)
if __name__=='__main__': unittest.main()
