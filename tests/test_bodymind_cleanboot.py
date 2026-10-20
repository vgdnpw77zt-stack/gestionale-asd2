"""Test the new launcher ONLY on synthetic files and SQLite.

No Railway connection, no production data, no historical migrations.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from consolidation.clean_runtime_launcher import (
    SCHEMA, TABLES, preflight, source_inventory, validate_database
)

class CleanBootTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="bodymind-cleanboot-")
        self.base=Path(self.tmp.name)
        self.root=self.base/"top2_app"
        (self.root/"asd_app").mkdir(parents=True)
        (self.root/".TOP2_OFFICIAL").touch()
        (self.root/"app.py").write_text("app=None\n")
        for i in range(33):
            (self.root/"asd_app"/("fixture_%02d.py"%i)).write_text("FLAG=%d\n"%i)
        self.dbpath=self.base/"test.db"
        conn=sqlite3.connect(self.dbpath)
        for t in TABLES:
            conn.execute('CREATE TABLE "'+t+'"(id INTEGER PRIMARY KEY)')
        conn.commit();conn.close()
        self.lock=self.base/"verified-source-lock.json"
        self.save_manifest()
    def tearDown(self):
        self.tmp.cleanup()
    def save_manifest(self):
        self.lock.write_text(json.dumps({"format":SCHEMA,"files":source_inventory(self.root)}))
    def test_all_source_and_db_checks_pass_on_clone(self):
        result=preflight(self.root,self.dbpath,self.lock)
        self.assertEqual(result["legacy_migrations_executed"],0)
        self.assertEqual(result["db_integrity"],"ok")
        self.assertFalse(result["auto_cleanup"])
        self.assertFalse(result["auto_database_restore"])
        self.assertGreater(result["source_files"],30)
    def test_changes_and_unexpected_files_block_start(self):
        (self.root/"asd_app"/"fixture_00.py").write_text("FLAG=100\n")
        with self.assertRaisesRegex(RuntimeError,"changed=1"):
            preflight(self.root,self.dbpath,self.lock)
        self.save_manifest()
        (self.root/"asd_app"/"unreviewed.py").write_text("print('wrong source')\n")
        with self.assertRaisesRegex(RuntimeError,"unexpected=1"):
            preflight(self.root,self.dbpath,self.lock)
    def test_old_hidden_rollbacks_cannot_pollute_active_manifest(self):
        old=self.root/"asd_app"/".a292_rollback_private"
        old.mkdir()
        (old/"some_file.py").write_text("broken=;\n")
        self.assertEqual(len(source_inventory(self.root)),34)
    def test_db_does_not_get_recovered_or_modified(self):
        before=self.dbpath.read_bytes()
        self.assertEqual(validate_database(self.dbpath)["pagamenti"],0)
        self.assertEqual(self.dbpath.read_bytes(),before)
        self.dbpath.unlink()
        with self.assertRaises(FileNotFoundError):
            preflight(self.root,self.dbpath,self.lock)
        self.assertFalse(self.dbpath.exists())
    def test_bad_manifest_or_broken_python_cannot_start(self):
        self.lock.write_text(json.dumps({"format":SCHEMA,"files":{"app.py":"f"*64}}))
        with self.assertRaisesRegex(RuntimeError,"Incomplete"):
            preflight(self.root,self.dbpath,self.lock)
        (self.root/"asd_app"/"fixture_00.py").write_text("if :\n")
        with self.assertRaises(SyntaxError):
            source_inventory(self.root)

if __name__=="__main__":
    unittest.main()
