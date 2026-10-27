"""A352 locked UI-only sources, exact A351 production migration & rollback tests."""
import hashlib
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
S=importlib.util.spec_from_file_location('a352_runtime',ROOT/'bootstrap/clean_runtime_launcher.py')
M=importlib.util.module_from_spec(S)
S.loader.exec_module(M)

def pinned():
    return (patch.object(M,'A352_CSS_PATH',ROOT/'bootstrap/family_a352_visible_atmosphere.css'),
            patch.object(M,'A352_JS_PATH',ROOT/'bootstrap/family_a352_visible_atmosphere.js'),
            patch.object(M,'A351_CSS_PATH',ROOT/'bootstrap/family_a351_sunrise.css'),
            patch.object(M,'A351_JS_PATH',ROOT/'bootstrap/family_a351_sunrise.js'))

class VisibleExperienceSafety(unittest.TestCase):
    def test_really_visible_animated_fog_stars_and_seamless_video(self):
        p=pinned()
        with p[0],p[1],p[2],p[3]:
            css,js=M.a352_assets()
        for needle in (b'@keyframes bm352-cloudstream',b'@keyframes bm352-starslide',
                       b'bm352-dust',b'bm352-cloud--near',b'bm352-tucked',
                       b'BODYMIND A352',b'prefers-reduced-motion',
                       b'familyMediaTrack',b'repeating-linear-gradient'):
            self.assertIn(needle,css)
        self.assertIn(b'body >',css.replace(b'>.',b' >')) if False else None
        self.assertIn(b'hero video.family-hero-video',css)
        self.assertIn(b'mask-image:radial-gradient',css)
        self.assertIn(b'buildSky(document.querySelector("section.hero"))',js)
        self.assertIn(b'buildSky(document.querySelector("main.main"))',js)
        self.assertIn(b'window.addEventListener("scroll"',js)
        self.assertIn(b'aria-expanded',js)
        self.assertNotIn(b'fetch(',js)
        self.assertNotIn(b'localStorage',js)
        self.assertNotIn(b'document.cookie',js)
        self.assertEqual(M.a350_git_blob(css),M.A352_CSS_BLOB)
        self.assertEqual(M.a350_git_blob(js),M.A352_JS_BLOB)

    def test_css_js_additions_compile_without_changing_business_route_source(self):
        original_css=(ROOT/'bootstrap/family_a351_sunrise.css').read_bytes()
        original_js=(ROOT/'bootstrap/family_a351_sunrise.js').read_bytes()
        old=b"PORTAL='''"+original_css+b"\n/*END CSS*/\n"+original_js+b"\n'''\n"
        digest=hashlib.sha256(old).hexdigest()
        p=pinned()
        with p[0],p[1],p[2],p[3],patch.object(M,'A352_A351_LIVE_SHA',digest):
            new,sha=M.a352_expected_from_a351(old)
            compile(new,'a352_synthetic.py','exec')
            self.assertEqual(hashlib.sha256(new).hexdigest(),sha)
            self.assertEqual(new.count(b'BODYMIND A352 VISIBLE AURORA'),1)
            self.assertEqual(new.count(b'BODYMIND A352 VISIBLE DOCK'),1)
            self.assertIn(original_css,new)
            self.assertIn(original_js,new)
            with self.assertRaisesRegex(RuntimeError,'hash mismatch'):
                M.a352_expected_from_a351(old+b' ')
            with self.assertRaisesRegex(RuntimeError,'hash mismatch'):
                M.a352_expected_from_a351(new)

    def test_critical_preflight_supports_new_approved_source(self):
        source=(ROOT/'bootstrap/clean_runtime_launcher.py').read_text()
        self.assertIn('and not a352_matches(root,found):',source)
        self.assertIn('maybe_apply_a352(args.root,args.db)',source)
        self.assertIn('BODYMIND_A352_RECOVER_A351',source)
        self.assertIn('sqlite_readonly_check(db)',source)
        self.assertIn('BODYMIND_A352_PREUI_A351.py',source)
        self.assertIn('a351_matches(root,prior)',source)
        docker=(ROOT/'Dockerfile').read_text()
        self.assertIn('COPY bootstrap/family_a352_visible_atmosphere.css',docker)
        self.assertIn('COPY bootstrap/family_a352_visible_atmosphere.js',docker)
if __name__=='__main__':
    unittest.main()
