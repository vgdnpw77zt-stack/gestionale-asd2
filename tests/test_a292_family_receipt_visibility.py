import sqlite3
import unittest
from fixes.a292.family_receipt_visibility import hidden, family_visible_receipts, set_hidden

class TestFamilyReceiptVisibility(unittest.TestCase):
    def setUp(self):
        self.conn=sqlite3.connect(":memory:")
        self.conn.row_factory=sqlite3.Row
        self.conn.execute("CREATE TABLE ricevute(id INTEGER PRIMARY KEY, importo REAL)")
        self.conn.executemany("INSERT INTO ricevute VALUES (?,?)",[(1,50),(2,90)])
    def tearDown(self):
        self.conn.close()
    def test_hide_restore_preserves_ledger(self):
        before=list(self.conn.execute("SELECT * FROM ricevute"))
        self.assertFalse(hidden(self.conn,1))
        set_hidden(self.conn,1,True,"Duplicato storico","admin")
        self.assertTrue(hidden(self.conn,1))
        self.assertEqual([r["id"] for r in family_visible_receipts(self.conn,self.conn.execute("SELECT * FROM ricevute"))],[2])
        set_hidden(self.conn,1,False,"Ripristino verificato","admin")
        self.assertFalse(hidden(self.conn,1))
        self.assertEqual([tuple(x) for x in before],[tuple(x) for x in self.conn.execute("SELECT * FROM ricevute")])
        self.assertEqual(self.conn.execute("SELECT count(*) FROM bodymind_family_receipt_visibility_audit").fetchone()[0],2)
    def test_invalid_input(self):
        with self.assertRaises(ValueError):
            set_hidden(self.conn,99,True,"Motivazione valida","admin")
        with self.assertRaises(ValueError):
            set_hidden(self.conn,1,True,"breve","admin")

if __name__=="__main__":
    unittest.main()
