"""BodyMind A358: light moving wave regression guard."""
import hashlib
import importlib.util
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('a358',ROOT/'bootstrap/clean_runtime_launcher.py')
M=importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

class A358Waves(unittest.TestCase):
    def test_mobile_wave_design_and_gpu_guard(self):
        with patch.object(M,'A358_CSS_PATH',ROOT/'bootstrap/family_a358_mobile_waves.css'):
            css=M.a358_assets()
        for signal in (b'main.main>.bm352-sky',b'position:sticky!important',
                       b'height:100svh!important',b'margin:0 0 -100svh!important',
                       b'bm358-ribbon-drift',b'bm358-hero-ribbon',
                       b'prefers-reduced-motion',b'mix-blend-mode:normal'):
            self.assertIn(signal,css)
        for forbidden in (b'filter:blur(',b'background-position',b'url(https://',
                          b'fetch(',b'localStorage',b'opacity:0!important'):
            self.assertNotIn(forbidden,css)
        self.assertEqual(css.count(b'<script'),0)

    def test_exact_a357_only_appended(self):
        mapping={
            'A351_CSS_PATH':'bootstrap/family_a351_sunrise.css',
            'A351_JS_PATH':'bootstrap/family_a351_sunrise.js',
            'A352_CSS_PATH':'bootstrap/family_a352_visible_atmosphere.css',
            'A352_JS_PATH':'bootstrap/family_a352_visible_atmosphere.js',
            'A353_CSS_PATH':'bootstrap/family_a353_stardust.css',
            'A353_JS_PATH':'bootstrap/family_a353_stardust.js',
            'A354_CSS_PATH':'bootstrap/family_a354_luxury_poetic.css',
            'A354_JS_PATH':'bootstrap/family_a354_luxury_poetic.js',
            'A355_CSS_PATH':'bootstrap/family_a355_dark_cinema.css',
            'A355_JS_PATH':'bootstrap/family_a355_studio_link.js',
            'A355_STUDIO_PATH':'bootstrap/bodymind_a355_film_studio.py',
            'A356_CSS_PATH':'bootstrap/family_a356_luminous_nebula.css',
            'A357_CSS_PATH':'bootstrap/family_a357_ios_stability.css',
            'A358_CSS_PATH':'bootstrap/family_a358_mobile_waves.css'
        }
        with tempfile.TemporaryDirectory() as d,ExitStack() as stack:
            for key,path in mapping.items():
                stack.enter_context(patch.object(M,key,ROOT/path))
            a351=b"PORTAL='''"+M.A351_CSS_PATH.read_bytes()+b"\n/*END CSS*/\n"+M.A351_JS_PATH.read_bytes()+b"\n'''\n"+b"_bm351_album.install_family_gallery(app, db)\n"
            directory=Path(d)
            def save(name,payload):
                dest=directory/name;dest.write_bytes(payload);return dest
            stack.enter_context(patch.object(M,'A352_A351_LIVE_SHA',hashlib.sha256(a351).hexdigest()))
            stack.enter_context(patch.object(M,'A352_BACKUP',save('a351.py',a351)))
            a352,_=M.a352_expected_from_a351(a351)
            stack.enter_context(patch.object(M,'A353_BACKUP',save('a352.py',a352)))
            a353,_=M.a353_expected_from_a352(a352)
            stack.enter_context(patch.object(M,'A354_BACKUP',save('a353.py',a353)))
            a354,_=M.a354_expected_from_a353(a353)
            stack.enter_context(patch.object(M,'A355_BACKUP',save('a354.py',a354)))
            a355,_=M.a355_expected_from_a354(a354)
            stack.enter_context(patch.object(M,'A356_BACKUP',save('a355.py',a355)))
            a356,_=M.a356_expected_from_a355(a355)
            stack.enter_context(patch.object(M,'A357_BACKUP',save('a356.py',a356)))
            a357,_=M.a357_expected_from_a356(a356)
            new,sha=M.a358_expected_from_a357(a357)
            self.assertEqual(hashlib.sha256(new).hexdigest(),sha)
            self.assertEqual(new.count(M.A358_CSS_PATH.read_bytes()),1)
            self.assertIn(M.A357_CSS_PATH.read_bytes(),new)
            self.assertIn(b'BODYMIND A355 FILM STUDIO',new)
            self.assertEqual(len(new)-len(a357),len(M.A358_CSS_PATH.read_bytes())+len(b'\n/* BODYMIND A358 MOBILE WAVES */\n'))
            compile(new,'a358_family.py','exec')
            with self.assertRaisesRegex(RuntimeError,'exact protected A357'):
                M.a358_expected_from_a357(a357+b' ')

if __name__=='__main__':
    unittest.main()
