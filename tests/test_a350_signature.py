"""A350 isolated code and safety tests. No real family account or live DB is accessed."""
import importlib.util
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
        self.assertIn('link.rel = "noopener noreferrer";', js)
        self.assertIn("bodymindaerialstudio.life/#movimento", js)
        self.assertNotIn("localStorage", js)
        self.assertNotIn("fetch(", js)


if __name__ == "__main__":
    unittest.main()
