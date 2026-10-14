"""Synthetic archive verification tests: production database is never opened."""
import sqlite3
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from bodymind_archive_guard import audit, create, verify, restore_into_empty


class ArchiveGuardTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.live = self.root / "live"
        path = self.live / "tenants/default/asd.db"
        path.parent.mkdir(parents=True)
        con = sqlite3.connect(path)
        con.executescript("""
            CREATE TABLE tesserati(id INTEGER PRIMARY KEY,nome TEXT);
            CREATE TABLE pagamenti(id INTEGER PRIMARY KEY,tesserato_id INTEGER REFERENCES tesserati(id));
            CREATE TABLE ricevute(id INTEGER PRIMARY KEY,pagamento_id INTEGER REFERENCES pagamenti(id));
            CREATE TABLE documenti(id INTEGER PRIMARY KEY,filename TEXT,visibile INTEGER);
            CREATE TABLE inbound_documents(id INTEGER PRIMARY KEY);
            INSERT INTO tesserati VALUES(14,'Test');
            INSERT INTO pagamenti VALUES(1,14);
            INSERT INTO ricevute VALUES(1,1);
            INSERT INTO documenti VALUES(1,'tesserati/14/certificato.pdf',1);
        """)
        con.commit()
        con.close()
        self.document = self.live / "tenants/default/media/tesserati/14/certificato.pdf"
        self.document.parent.mkdir(parents=True)
        self.document.write_bytes(b"%PDF-1.4-test")

    def test_missing_visible_document_prevents_certified_export(self):
        self.assertEqual(audit(self.live)["document_references_missing"]["visible"], [])
        self.document.unlink()
        self.assertEqual(audit(self.live)["document_references_missing"]["visible"], [1])
        with self.assertRaises(ValueError):
            create(self.live, self.root / "out.zip")

    def test_complete_backup_verified_and_restored_only_to_empty_volume(self):
        archive = self.root / "backup.zip"
        created = create(self.live, archive)
        self.assertTrue(created["verified"])
        self.assertEqual(verify(archive)["database"]["ricevute"], 1)
        copy = self.root / "offline_restore"
        restore_into_empty(archive, copy)
        self.assertEqual((copy / self.document.relative_to(self.live)).read_bytes(),
                         self.document.read_bytes())
        with self.assertRaises(FileExistsError):
            restore_into_empty(archive, self.live)

    def test_refuse_untracked_user_directories(self):
        unknown = self.live / "unknown_private_docs"
        unknown.mkdir()
        (unknown / "verbale.pdf").write_bytes(b"%PDF-hidden")
        self.assertIn("unknown_private_docs", audit(self.live)["untracked_directories"])
        with self.assertRaisesRegex(ValueError, "Untracked"):
            create(self.live, self.root / "backup.zip")

    def test_no_in_place_backup_or_corruption(self):
        with self.assertRaises(ValueError):
            create(self.live, self.live / "release_backups/archive.zip")
        archive = self.root / "good.zip"
        create(self.live, archive)
        bad = self.root / "tampered.zip"
        with zipfile.ZipFile(archive) as src, zipfile.ZipFile(bad, "w") as dst:
            for member in src.namelist():
                data = src.read(member)
                if member.endswith("certificato.pdf"):
                    data = b"damaged"
                dst.writestr(member, data)
        with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
            verify(bad)

    def test_historical_roots_and_literal_dots_survive_round_trip(self):
        extra = ['pdf/receipt.pdf', 'release_backups/pre_release.db',
                 'migration_backups/old.db', 'operator_upload_jobs/queued.pdf',
                 'operator_backups/old.db', 'release_packages/runtime.zip',
                 'database/asd.db', 'asd.db', '.secret_key']
        for name in extra:
            p = self.live / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b'historical bytes: ' + name.encode())
        renamed = self.document.with_name('Name..pdf')
        self.document.rename(renamed)
        con = sqlite3.connect(self.live / 'tenants/default/asd.db')
        con.execute("UPDATE documenti SET filename=?", ('/data/' + renamed.relative_to(self.live).as_posix(),))
        con.commit(); con.close()
        (self.live / 'backups').mkdir()
        (self.live / 'backups/previous.zip').write_bytes(b'excluded backup')
        archive = self.root / 'roundtrip.zip'
        create(self.live, archive)
        report = verify(archive)
        self.assertEqual(report['audit']['excluded_directories'], ['backups'])
        restored = self.root / 'restored'
        restore_into_empty(archive, restored)
        for name in extra:
            self.assertEqual((restored / name).read_bytes(), (self.live / name).read_bytes())
        self.assertEqual((restored / renamed.relative_to(self.live)).read_bytes(), renamed.read_bytes())
        self.assertEqual(audit(restored)['document_references_missing']['visible'], [])
        self.assertEqual(report['database']['pagamenti'], 1)

    def test_wal_transactions_are_in_active_database_snapshot(self):
        con = sqlite3.connect(self.live / 'tenants/default/asd.db')
        self.addCleanup(con.close)
        con.execute('PRAGMA journal_mode=WAL')
        con.execute('INSERT INTO pagamenti VALUES(2,14)')
        con.commit()
        archive = self.root / 'wal.zip'
        create(self.live, archive)
        self.assertEqual(verify(archive)['database']['pagamenti'], 2)
        restored = self.root / 'wal_restore'
        restore_into_empty(archive, restored)
        check = sqlite3.connect(restored / 'tenants/default/asd.db')
        self.assertEqual(check.execute('SELECT count(*) FROM pagamenti').fetchone()[0], 2)
        check.close()

    def test_invalid_restore_namespace_rejected_before_target_creation(self):
        good = self.root / 'good.zip'; create(self.live, good)
        for name in ['evil.txt', 'data/tenants/default/asd.db', 'data/../escape',
                     'data//ambiguous', 'data/./ambiguous']:
            with self.subTest(name=name):
                bad = self.root / 'bad.zip'
                with zipfile.ZipFile(good) as src, zipfile.ZipFile(bad, 'w') as dst:
                    m = json.loads(src.read('manifest.json'))
                    for member in src.namelist():
                        if member != 'manifest.json': dst.writestr(member, src.read(member))
                    data = b'bad'
                    dst.writestr(name, data)
                    m['files'].append({'name': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
                    dst.writestr('manifest.json', json.dumps(m))
                target = self.root / 'must_not_exist'
                with self.assertRaises(ValueError): restore_into_empty(bad, target)
                self.assertFalse(target.exists())

    def test_symlinked_restore_destination_is_rejected(self):
        archive = self.root / 'safe.zip'; create(self.live, archive)
        actual = self.root / 'actual'; actual.mkdir()
        link = self.root / 'link'; link.symlink_to(actual, target_is_directory=True)
        with self.assertRaises(ValueError): restore_into_empty(archive, link)
        self.assertEqual(list(actual.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
