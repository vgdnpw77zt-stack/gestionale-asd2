"""A350 isolated code and safety tests. No real family account or live DB is accessed."""
import importlib.util
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "bootstrap"
SPEC = importlib.util.spec_from_file_location("a350_clean_launcher", BOOTSTRAP / "clean_runtime_launcher.py")
LAUNCHER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LAUNCHER)


class A350SignatureTests(unittest.TestCase):
    def test_assets_have_exact_git_blob_fingerprints(self):
        css = (BOOTSTRAP / "family_a350_signature.css").read_bytes()
        js = (BOOTSTRAP / "family_a350_verified_gallery.js").read_bytes()
        self.assertEqual(LAUNCHER.a350_git_blob(css), LAUNCHER.A350_CSS_BLOB)
        self.assertEqual(LAUNCHER.a350_git_blob(js), LAUNCHER.A350_JS_BLOB)
        self.assertNotIn(b"</script>", js)
        self.assertNotIn(b"</style>", css)
        self.assertNotIn(b"'''", js)
        self.assertNotIn(b"'''", css)
        self.assertEqual(css.count(b"{"), css.count(b"}"))

    def test_replaces_keyword_guesswork_without_touching_other_content(self):
        old_js = (BOOTSTRAP / "family_a341.js").read_bytes()
        css = (BOOTSTRAP / "family_a350_signature.css").read_bytes()
        new_js = (BOOTSTRAP / "family_a350_verified_gallery.js").read_bytes()
        protected = b"family=TEST_A | athlete=TEST_B | receipt=TEST_C | document=TEST_D"
        # Tiny valid Python fixture models the inline HTML string in the volume source.
        old = (b"PAGE = '''<html>\n<style>\nBODYMIND CORE\n</style>\n</head>\n<body>\n" +
               b'<script id="bodymind-media-links">\n' + old_js +
               b"\n</script>\n" + protected + b"\n</body></html>'''\n")
        candidate = LAUNCHER.a350_transform_html(old, old_js, css, new_js)
        compile(candidate, "mock_family_route.py", "exec")
        self.assertEqual(candidate.count(protected), 1)
        self.assertEqual(candidate.count(css), 1)
        self.assertEqual(candidate.count(new_js), 1)
        self.assertNotIn(old_js, candidate)
        self.assertNotIn(b"targetFor(title)", candidate)
        self.assertIn(b"BODYMIND CORE", candidate)
        self.assertIn(b"bodymind-media-links-a350", candidate)

    def test_missing_or_duplicated_anchors_fail_closed(self):
        js = (BOOTSTRAP / "family_a350_verified_gallery.js").read_bytes()
        css = (BOOTSTRAP / "family_a350_signature.css").read_bytes()
        original = (BOOTSTRAP / "family_a341.js").read_bytes()
        marker = b'<script id="bodymind-media-links">\n' + original + b"\n</script>"
        with self.assertRaises(RuntimeError):
            LAUNCHER.a350_transform_html(b"</style>\n</head>" + marker * 2, original, css, js)
        with self.assertRaises(RuntimeError):
            LAUNCHER.a350_transform_html(b"no family script</style>\n</head>", original, css, js)
        with self.assertRaises(RuntimeError):
            LAUNCHER.a350_transform_html(marker, original, css, js)

    def test_asset_modification_is_detected(self):
        with tempfile.TemporaryDirectory() as dirname:
            altered = Path(dirname) / "modified.css"
            altered.write_bytes((BOOTSTRAP / "family_a350_signature.css").read_bytes() + b"\n/* malicious drift */")
            js = BOOTSTRAP / "family_a350_verified_gallery.js"
            with patch.object(LAUNCHER, "A350_CSS_PATH", altered), patch.object(LAUNCHER, "A350_JS_PATH", js):
                with self.assertRaisesRegex(RuntimeError, "fingerprint"):
                    LAUNCHER.a350_assets()

    def test_clean_boot_includes_a350_and_rollback_only_code(self):
        launcher = (BOOTSTRAP / "clean_runtime_launcher.py").read_text()
        docker = (ROOT / "Dockerfile").read_text()
        for required in (
            "not a350_matches(root,found)",
            "maybe_apply_a350_family_ui(args.root,args.db)",
            "maybe_recover_a350_to_a349(args.root,args.db)",
            "BODYMIND_A350_RECOVER_A349",
            "sqlite_readonly_check(db)",
            "A350_BACKUP",
            "a350_transform_html",
        ):
            self.assertIn(required, launcher)
        for name in ("family_a350_signature.css", "family_a350_verified_gallery.js"):
            self.assertIn("COPY bootstrap/" + name, docker)
        self.assertNotIn("DROP TABLE", launcher)
        self.assertNotIn("DELETE FROM", launcher)

    def test_gallery_never_inferrs_reel_from_caption(self):
        old = (BOOTSTRAP / "family_a341.js").read_text()
        js = (BOOTSTRAP / "family_a350_verified_gallery.js").read_text()
        self.assertIn("targetFor(title)", old)
        self.assertNotIn("targetFor(title)", js)
        self.assertIn("verifiedImageLinks[publicPath(img)]", js)
        self.assertIn("if (!destination) continue;", js)
        self.assertIn("img.currentSrc || url.href", js)
        self.assertIn("https://bodymindaerialstudio.life", js)
        self.assertIn("if (!official.has(shown.origin)) return", js)
        self.assertIn('link.rel = "noopener noreferrer";', js)
        self.assertIn("bodymindaerialstudio.life/#movimento", js)
        self.assertNotIn("localStorage", js)
        self.assertNotIn("fetch(", js)


    def test_atomic_a349_to_a350_and_exact_source_recovery_on_synthetic_volume(self):
        old_js = (BOOTSTRAP / "family_a341.js").read_bytes()
        old = (b"PAGE = '''<html>\n<style>\nCORE\n</style>\n</head>\n" +
               b'<script id="bodymind-media-links">\n' + old_js +
               b"\n</script>\n</html>'''\n")
        old_sha = hashlib.sha256(old).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp)
            root=work/"top2_app"
            target=root/"asd_app"/"routes_bodymind_final.py"
            target.parent.mkdir(parents=True)
            target.write_bytes(old)
            packages=work/"release_packages"
            packages.mkdir()
            original_backup=packages/"A349_TEST_BASE.py"
            original_backup.write_bytes(old)
            a350_backup=packages/"A350_PREUI_TEST.py"
            fake_db=work/"unused.db"
            def inventory(_root):
                result={"asd_app/fake_%03d.py" % n:"known" for n in range(213)}
                result[LAUNCHER.A350_REL]=hashlib.sha256(target.read_bytes()).hexdigest()
                return result
            def is_a349(_root,found):
                return found.get(LAUNCHER.A350_REL)==old_sha
            with patch.object(LAUNCHER,"source_inventory",inventory), \
                 patch.object(LAUNCHER,"a349_matches",is_a349), \
                 patch.object(LAUNCHER,"a349_source_from_a348",
                              lambda old_a348:(old,old_sha)), \
                 patch.object(LAUNCHER,"a350_secure_document_route",side_effect=lambda raw:raw), \
                 patch.object(LAUNCHER,"sqlite_readonly_check",return_value={}) as readonly, \
                 patch.object(LAUNCHER,"A349_BACKUP",original_backup), \
                 patch.object(LAUNCHER,"A350_BACKUP",a350_backup), \
                 patch.object(LAUNCHER,"A350_CSS_PATH",BOOTSTRAP/"family_a350_signature.css"), \
                 patch.object(LAUNCHER,"A350_JS_PATH",BOOTSTRAP/"family_a350_verified_gallery.js"), \
                 patch.object(LAUNCHER,"A341_LINKS_PATH",BOOTSTRAP/"family_a341.js"):
                LAUNCHER.maybe_apply_a350_family_ui(root,fake_db)
                patched=target.read_bytes()
                self.assertNotEqual(patched,old)
                self.assertEqual(a350_backup.read_bytes(),old)
                self.assertTrue(LAUNCHER.a350_matches(root,inventory(root)))
                self.assertGreaterEqual(readonly.call_count,1)
                LAUNCHER.maybe_apply_a350_family_ui(root,fake_db)
                self.assertEqual(target.read_bytes(),patched)
                with patch.dict(os.environ,{"BODYMIND_A350_RECOVER_A349":"1"}):
                    self.assertTrue(LAUNCHER.maybe_recover_a350_to_a349(root,fake_db))
                self.assertEqual(target.read_bytes(),old)
                self.assertEqual(a350_backup.read_bytes(),old)


    def test_hidden_document_guard_requires_exact_source_and_never_writes_db(self):
        source = b'''def abort(code):
    raise ValueError("HTTP 404")
PORTAL = """<main>{% if request.args.get('upload')=='ok' %}<div class="flash">Success</div>{% endif %}</main>"""
def bodymind_doc(token, doc_id):
    dcols = {'visi' + 'bile'}
    d = {'visi' + 'bile': 0}
    if not d: abort(404)
    return d
'''
        checksum=hashlib.sha256(source).hexdigest()
        with self.assertRaisesRegex(RuntimeError, 'SHA mismatch'):
            LAUNCHER.a350_secure_document_route(source)
        rewritten=LAUNCHER.a350_secure_document_route(source, expected_sha=checksum)
        compile(rewritten, "synthetic_security.py", "exec")
        self.assertIn(b"int(d['visibile'] or 0) != 1", rewritten)
        self.assertNotIn(b"request.args.get('upload')", rewritten)
        self.assertEqual(source.count(b"if not d: abort(404)"), 1)
        bad=source.replace(b"if not d: abort(404)", b"if d is None: abort(404)")
        with self.assertRaises(RuntimeError):
            LAUNCHER.a350_secure_document_route(bad,expected_sha=hashlib.sha256(bad).hexdigest())
        namespace={}
        exec(compile(rewritten, "synthetic_security.py", "exec"), namespace)
        with self.assertRaisesRegex(ValueError,"HTTP 404"):
            namespace["bodymind_doc"]("SYNTHETIC",1)


if __name__ == "__main__":
    unittest.main()
