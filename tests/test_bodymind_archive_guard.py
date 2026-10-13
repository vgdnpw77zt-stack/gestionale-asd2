"""Synthetic archive verification tests: production database is never opened."""
import sqlite3
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


if __name__ == "__main__":
    unittest.main()
