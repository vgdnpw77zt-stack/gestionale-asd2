"""A356: tests for visual-only release, protected migration, and clean rollback."""
import hashlib
import importlib.util
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("bodymind_a356_launcher",ROOT/"bootstrap/clean_runtime_launcher.py")
M=importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

class A356LuminousNebula(unittest.TestCase):
    def test_visual_contract_and_protected_source(self):
        with patch.object(M,"A356_CSS_PATH",ROOT/"bootstrap/family_a356_luminous_nebula.css"):
            css=M.a356_assets()
        for item in (b"bm356-nebula-east",b"bm356-nebula-west",
                     b".hero>.frame.hero-content",b"mask-image:",
                     b"prefers-reduced-motion",b"pointer-events:none",
                     b"#092331"):
            self.assertIn(item,css)
        for forbidden in (b"</style>",b"</script>",b"fetch(",b"XMLHttpRequest(",b"localStorage"):
            self.assertNotIn(forbidden,css)
        self.assertIn(b"grid-area:1 / 1",css)
        self.assertIn(b"background:none!important",css)

    def test_exact_a355_rollback_and_css_only_extension(self):
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
        }
        with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
            for key,path in mapping.items():
                stack.enter_context(patch.object(M,key,ROOT/path))
            css=M.A351_CSS_PATH.read_bytes()
            js=M.A351_JS_PATH.read_bytes()
            a351=b"PORTAL='''"+css+b"\n/*END CSS*/\n"+js+b"\n'''\n"+b"_bm351_album.install_family_gallery(app, db)\n"
            p351=Path(directory)/"a351.py";p351.write_bytes(a351)
            stack.enter_context(patch.object(M,"A352_A351_LIVE_SHA",hashlib.sha256(a351).hexdigest()))
            stack.enter_context(patch.object(M,"A352_BACKUP",p351))
            a352,_=M.a352_expected_from_a351(a351)
            p352=Path(directory)/"a352.py";p352.write_bytes(a352)
            stack.enter_context(patch.object(M,"A353_BACKUP",p352))
            a353,_=M.a353_expected_from_a352(a352)
            p353=Path(directory)/"a353.py";p353.write_bytes(a353)
            stack.enter_context(patch.object(M,"A354_BACKUP",p353))
            a354,_=M.a354_expected_from_a353(a353)
            p354=Path(directory)/"a354.py";p354.write_bytes(a354)
            stack.enter_context(patch.object(M,"A355_BACKUP",p354))
            a355,_=M.a355_expected_from_a354(a354)
            upgraded,sha=M.a356_expected_from_a355(a355)
            self.assertEqual(hashlib.sha256(upgraded).hexdigest(),sha)
            self.assertEqual(upgraded.count(M.A356_CSS_PATH.read_bytes()),1)
            self.assertEqual(upgraded.count(b"BODYMIND A356 LUMINOUS NEBULA"),1)
            self.assertEqual(upgraded.count(b"BODYMIND A355 FILM STUDIO"),a355.count(b"BODYMIND A355 FILM STUDIO"))
            self.assertEqual(len(upgraded)-len(a355),len(M.A356_CSS_PATH.read_bytes())+len(b"\n/* BODYMIND A356 LUMINOUS NEBULA */\n"))
            self.assertIn(b"\n/* BODYMIND A356 LUMINOUS NEBULA */\n",upgraded)
            compile(upgraded,"a356_family.py","exec")
            with self.assertRaisesRegex(RuntimeError,"exact protected A355"):
                M.a356_expected_from_a355(a355+b" ")

if __name__=="__main__":
    unittest.main()
