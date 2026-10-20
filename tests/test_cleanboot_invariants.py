import hashlib
import importlib.util
import json
import pathlib
import sqlite3
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('clean_runtime_launcher',ROOT/'bootstrap/clean_runtime_launcher.py')
boot=importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot)

class TestCleanBoot(unittest.TestCase):
    def test_frozen_inventory(self):
        self.assertEqual(boot.EXPECTED_SOURCE_COUNT,209)
        self.assertEqual(len(boot.EXPECTED_SOURCE_DIGEST),64)
    def test_no_historical_mutation(self):
        source=(ROOT/'bootstrap/clean_runtime_launcher.py').read_text()
        for forbidden in ('runpy.run_path','shutil.rmtree','shutil.copy2','db_path.unlink','os.remove('):
            self.assertNotIn(forbidden,source)
        docker=(ROOT/'Dockerfile').read_text()
        self.assertNotIn('release_',docker)
        self.assertIn('cp /opt/bodymind/clean_runtime_launcher.py /opt/bodymind-migration/migration_upload.py',docker)
    def test_desktop_only_files_are_excluded_from_source_lock(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td)
            (root/'asd_app').mkdir()
            (root/'app.py').write_text('app=object()\n')
            before=boot.source_inventory(root)
            # Files present in actual A301 backup, but never part of the app's 209-lock.
            for filename in ('desktop_boot.py','desktop_webview.py',
                             'desktop_webview_browser_stabile.py','production_preflight.py'):
                (root/filename).write_text('DESKTOP_ONLY=True\n')
            self.assertEqual(boot.source_inventory(root),before)
            self.assertEqual(len(boot.source_inventory(root)),1)
            (root/'accidental_loader.py').write_text('SHOULD_NOT_RUN=True\n')
            with self.assertRaisesRegex(RuntimeError,'unexpected root-level Python source'):
                boot.source_inventory(root)

    def test_source_and_sqlite_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td);app=root/'top2_app';app.mkdir();(app/'asd_app').mkdir()
            (app/'.TOP2_OFFICIAL').write_text('1')
            (app/'app.py').write_text('app = object()\n')
            for i in range(200): (app/'asd_app'/f'm{i}.py').write_text(f'VALUE={i}\n')
            good=boot.source_inventory(app)
            old_count,old_digest=boot.EXPECTED_SOURCE_COUNT,boot.EXPECTED_SOURCE_DIGEST
            try:
                boot.EXPECTED_SOURCE_COUNT=len(good)
                boot.EXPECTED_SOURCE_DIGEST=boot.inventory_digest(good)
                db=root/'asd.db'
                with sqlite3.connect(db) as c:
                    for table in boot.REQUIRED_TABLES:
                        c.execute('CREATE TABLE "'+table+'" (id INTEGER PRIMARY KEY)')
                before=hashlib.sha256(db.read_bytes()).hexdigest()
                self.assertEqual(boot.preflight(app,db)['source_files'],201)
                self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(),before)
                (app/'asd_app'/'extra.py').write_text('x=1\n')
                with self.assertRaisesRegex(RuntimeError,'source lock mismatch'):boot.preflight(app,db)
                (app/'asd_app'/'extra.py').unlink()
                (app/'app.py').write_text('app = None\n')
                with self.assertRaisesRegex(RuntimeError,'source lock mismatch'):boot.preflight(app,db)
                (app/'app.py').write_text('app = object()\n')
                db.unlink()
                with self.assertRaises(RuntimeError):boot.preflight(app,db)
                self.assertFalse(db.exists())
            finally:
                boot.EXPECTED_SOURCE_COUNT=old_count
                boot.EXPECTED_SOURCE_DIGEST=old_digest
if __name__=='__main__':
    unittest.main()
