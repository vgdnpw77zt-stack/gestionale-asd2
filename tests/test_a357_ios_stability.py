"""A357 compositor regression: mobile performance and exact source invariants."""
import hashlib
import importlib.util
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("a357",ROOT/"bootstrap/clean_runtime_launcher.py")
M=importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

class TestA357(unittest.TestCase):
    def test_ios_css_reduces_compositor_pressure(self):
        with patch.object(M,"A357_CSS_PATH",ROOT/"bootstrap/family_a357_ios_stability.css"):
            css=M.a357_assets()
        for item in [b"main.main>.bm352-sky",b"main.main::before",
                     b"-webkit-mask-image:none",b"bm357-cloud-glide",
                     b"prefers-reduced-motion",b"backdrop-filter:none",
                     b".hero .hero-media::after"]:
            self.assertIn(item,css)
        self.assertNotIn(b"fetch(",css)
        self.assertNotIn(b"localStorage",css)

    def test_atomic_append_preserves_a356_and_protected_studio(self):
        mapping={
            "A351_CSS_PATH":"bootstrap/family_a351_sunrise.css",
            "A351_JS_PATH":"bootstrap/family_a351_sunrise.js",
            "A352_CSS_PATH":"bootstrap/family_a352_visible_atmosphere.css",
            "A352_JS_PATH":"bootstrap/family_a352_visible_atmosphere.js",
            "A353_CSS_PATH":"bootstrap/family_a353_stardust.css",
            "A353_JS_PATH":"bootstrap/family_a353_stardust.js",
            "A354_CSS_PATH":"bootstrap/family_a354_luxury_poetic.css",
            "A354_JS_PATH":"bootstrap/family_a354_luxury_poetic.js",
            "A355_CSS_PATH":"bootstrap/family_a355_dark_cinema.css",
            "A355_JS_PATH":"bootstrap/family_a355_studio_link.js",
            "A355_STUDIO_PATH":"bootstrap/bodymind_a355_film_studio.py",
            "A356_CSS_PATH":"bootstrap/family_a356_luminous_nebula.css",
            "A357_CSS_PATH":"bootstrap/family_a357_ios_stability.css"
        }
        with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
            for name,path in mapping.items():stack.enter_context(patch.object(M,name,ROOT/path))
            css=M.A351_CSS_PATH.read_bytes()
            js=M.A351_JS_PATH.read_bytes()
            a351=b"PORTAL='''"+css+b"\n/*END CSS*/\n"+js+b"\n'''\n"+b"_bm351_album.install_family_gallery(app, db)\n"
            p=Path(directory)
            p351=p/"a351.py";p351.write_bytes(a351)
            stack.enter_context(patch.object(M,"A352_A351_LIVE_SHA",hashlib.sha256(a351).hexdigest()))
            stack.enter_context(patch.object(M,"A352_BACKUP",p351))
            a352,_=M.a352_expected_from_a351(a351)
            p352=p/"a352.py";p352.write_bytes(a352)
            stack.enter_context(patch.object(M,"A353_BACKUP",p352))
            a353,_=M.a353_expected_from_a352(a352)
            p353=p/"a353.py";p353.write_bytes(a353)
            stack.enter_context(patch.object(M,"A354_BACKUP",p353))
            a354,_=M.a354_expected_from_a353(a353)
            p354=p/"a354.py";p354.write_bytes(a354)
            stack.enter_context(patch.object(M,"A355_BACKUP",p354))
            a355,_=M.a355_expected_from_a354(a354)
            p355=p/"a355.py";p355.write_bytes(a355)
            stack.enter_context(patch.object(M,"A356_BACKUP",p355))
            a356,_=M.a356_expected_from_a355(a355)
            new,sha=M.a357_expected_from_a356(a356)
            self.assertEqual(hashlib.sha256(new).hexdigest(),sha)
            self.assertEqual(new.count(M.A357_CSS_PATH.read_bytes()),1)
            self.assertEqual(new.count(M.A356_CSS_PATH.read_bytes()),1)
            self.assertIn(b"BODYMIND A355 FILM STUDIO",new)
            compile(new,"test_a357_generated_source.py","exec")
            with self.assertRaisesRegex(RuntimeError,"exact approved A356"):
                M.a357_expected_from_a356(a356+b" ")

if __name__=="__main__":unittest.main()
