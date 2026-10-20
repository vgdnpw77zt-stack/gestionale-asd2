"""A293 realistic SQLite and Flask smoke tests; synthetic athletes only."""
import functools
import os
import sqlite3
import tempfile
import unittest
from flask import Flask, request, abort
from fixes.a293.online_payment_settings import (
    _link, _eur, _schema, _row_state, eligible_offer, register,
    safe_monthly_correction,
)

class TestA293Settings(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="a293_unit_")
        self.file=os.path.join(self.tmp.name,"test.db")
        c=self.db()
        c.executescript("""
          CREATE TABLE tesserati(id INTEGER PRIMARY KEY, nome TEXT, cognome TEXT);
          CREATE TABLE quote_mensili(id INTEGER PRIMARY KEY, tesserato_id INTEGER,
            anno INTEGER,mese INTEGER,importo_dovuto REAL,stato TEXT);
          CREATE TABLE pagamenti(id INTEGER PRIMARY KEY, tesserato_id INTEGER,
            anno INTEGER,mese INTEGER,causale TEXT,importo REAL,stato TEXT);
          CREATE TABLE ricevute(id INTEGER PRIMARY KEY,pagamento_id INTEGER);
          INSERT INTO tesserati VALUES(1,'Persona','Test');
          INSERT INTO quote_mensili VALUES(51,1,2026,10,45.00,'da_pagare');
        """)
        c.commit();c.close()

    def tearDown(self):self.tmp.cleanup()

    def db(self):
        c=sqlite3.connect(self.file)
        c.row_factory=sqlite3.Row
        return c

    def test_quota_change_and_audit_are_atomic(self):
        c=self.db()
        q=c.execute("SELECT * FROM quote_mensili WHERE id=51").fetchone()
        r=safe_monthly_correction(c,quota_id=51,expected_state=_row_state(q),
             new_amount="40.00",reason="Rettifica deliberata quota",actor="admin")
        self.assertEqual(r["after"],"40.00")
        self.assertEqual(c.execute("SELECT count(*) FROM bodymind_a293_admin_audit").fetchone()[0],1)
        with self.assertRaises(ValueError):
            safe_monthly_correction(c,quota_id=51,expected_state=_row_state(q),
             new_amount="30.00",reason="Rettifica deliberata quota",actor="admin")
        self.assertEqual(c.execute("SELECT importo_dovuto FROM quote_mensili WHERE id=51").fetchone()[0],40)
        c.close()

    def test_paid_month_and_receipt_cannot_be_rewritten(self):
        c=self.db()
        q=c.execute("SELECT * FROM quote_mensili WHERE id=51").fetchone()
        c.execute("INSERT INTO pagamenti VALUES(99,1,2026,10,'mensile',45,'pagato')")
        c.execute("INSERT INTO ricevute VALUES(91,99)")
        c.commit()
        with self.assertRaises(ValueError):
            safe_monthly_correction(c,quota_id=51,expected_state=_row_state(q),
                new_amount="20.00",reason="Operazione di rettifica test",actor="admin")
        self.assertEqual(c.execute("SELECT importo_dovuto FROM quote_mensili WHERE id=51").fetchone()[0],45)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM ricevute").fetchone()[0],1)
        c.close()

    def test_preview_asks_for_second_confirmation(self):
        app=Flask("a293-preview")
        app.secret_key="test-only"
        def admin(fn):
            return fn
        register(app,self.db,admin,lambda:'<input type="hidden" name="csrf_token" value="yes">',lambda:"admin")
        c=self.db(); q=c.execute("SELECT * FROM quote_mensili WHERE id=51").fetchone();etag=_row_state(q);c.close()
        result=app.test_client().post("/amministrazione/rettifiche-quote/51/anteprima",
              data={"expected_state":etag,"importo":"40.00","reason":"Motivo di rettifica test"})
        self.assertEqual(result.status_code,200)
        self.assertIn(b"Conferma e registra rettifica",result.data)
        c=self.db(); self.assertEqual(c.execute("SELECT importo_dovuto FROM quote_mensili WHERE id=51").fetchone()[0],45);c.close()

    def test_ambiguous_historical_payment_blocks_edit(self):
        c=self.db()
        q=c.execute("SELECT * FROM quote_mensili WHERE id=51").fetchone()
        c.execute("INSERT INTO pagamenti VALUES(100,1,2026,10,'quota_corso',45,'incassato')")
        c.commit()
        with self.assertRaises(ValueError):
            safe_monthly_correction(c,quota_id=51,expected_state=_row_state(q),
                new_amount="30.00",reason="Rettifica della quota in prova",actor="admin")
        c.close()

    def test_invalid_link_host_blocked(self):
        for value in ("http://pay.sumup.com/x","https://sumup.com.evil.test/charge",
                      "https://evil.test/charge","https://user:pwd@pay.sumup.com/x"):
            with self.subTest(url=value),self.assertRaises(ValueError):
                _link(value,"sumup")
        self.assertTrue(_link("https://pay.sumup.com/b2c/example","sumup"))

    def test_flask_routes_and_payment_link_are_not_fake_settlement(self):
        app=Flask("a293-test")
        app.secret_key="test-only"
        @app.before_request
        def check_csrf():
            if request.method=="POST" and request.form.get("csrf_token")!="yes":
                abort(400)
        def admin_required(fn):
            @functools.wraps(fn)
            def wrapped(*a,**k):
                if request.headers.get("X-Isolated-Admin")!="yes":abort(403)
                return fn(*a,**k)
            return wrapped
        register(app,self.db,admin_required,
                 lambda:'<input type="hidden" name="csrf_token" value="yes">',
                 lambda:"test-admin")
        client=app.test_client()
        self.assertEqual(client.get("/impostazioni/pagamenti-online").status_code,403)
        h={"X-Isolated-Admin":"yes"}
        self.assertEqual(client.get("/impostazioni/pagamenti-online",headers=h).status_code,200)
        self.assertEqual(client.post("/impostazioni/pagamenti-online/provider",
                     headers=h,data={"provider":"sumup","enabled":"1"}).status_code,400)
        self.assertEqual(client.post("/impostazioni/pagamenti-online/provider",
                     headers=h,data={"provider":"sumup","enabled":"1","csrf_token":"yes"}).status_code,302)
        link={"provider":"sumup","tesserato_id":"1","anno":"2026","mese":"10",
              "importo":"45.00","url":"https://pay.sumup.com/b2c/example",
              "active":"1","reason":"Pagamento quota ottobre","csrf_token":"yes"}
        self.assertEqual(client.post("/impostazioni/pagamenti-online/link",
                     headers=h,data=link).status_code,302)
        c=self.db()
        offer=eligible_offer(c,token_verified_tesserato_id=1,provider="sumup",year=2026,month=10)
        self.assertEqual(offer["amount"],"45.00")
        self.assertEqual(c.execute("SELECT COUNT(*) FROM pagamenti").fetchone()[0],0)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM ricevute").fetchone()[0],0)
        c.close()
        # Linked due cannot be changed until link is disabled, even by admin.
        self.assertEqual(client.get("/amministrazione/rettifiche-quote",headers=h).status_code,200)
        c=self.db()
        row=c.execute("SELECT * FROM quote_mensili WHERE id=51").fetchone()
        etag=_row_state(row);c.close()
        self.assertEqual(client.post("/amministrazione/rettifiche-quote/51/anteprima",headers=h,
          data={"expected_state":etag,"importo":"40.00","reason":"Correzione quota ottobre",
                "csrf_token":"yes"}).status_code,409)
        self.assertEqual(client.post("/amministrazione/rettifiche-quote/51",headers=h,
          data={"expected_state":etag,"importo":"40.00","reason":"Correzione quota ottobre",
                "csrf_token":"yes"}).status_code,409)

if __name__=="__main__":
    unittest.main()
