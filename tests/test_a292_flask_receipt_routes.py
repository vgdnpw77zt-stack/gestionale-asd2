import functools
import os
import sqlite3
import tempfile
import unittest

from flask import Flask, abort, request
from fixes.a292.family_receipt_admin import register


class TestA292FlaskRoutes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "test.sqlite")
        with sqlite3.connect(self.path) as conn:
            conn.execute("CREATE TABLE ricevute(id INTEGER PRIMARY KEY,pagamento_id INTEGER,importo REAL,descrizione TEXT)")
            conn.execute("CREATE TABLE pagamenti(id INTEGER PRIMARY KEY,tesserato_id INTEGER)")
            conn.execute("CREATE TABLE tesserati(id INTEGER PRIMARY KEY,nome TEXT,cognome TEXT)")
            conn.execute("INSERT INTO tesserati VALUES (14,'Test','Atleta')")
            conn.execute("INSERT INTO pagamenti VALUES (77,14)")
            conn.execute("INSERT INTO ricevute VALUES (1,77,50.0,'Quota mensile')")
        self.app = Flask(__name__)
        self.app.secret_key = "test-secret"

        def db():
            conn = sqlite3.connect(self.path)
            conn.row_factory = sqlite3.Row
            return conn

        @self.app.before_request
        def csrf_guard():
            if request.method == "POST" and request.form.get("csrf_token") != "test-csrf":
                abort(400)

        def admin_required(fn):
            @functools.wraps(fn)
            def protected(*args, **kwargs):
                if request.headers.get("X-Test-Admin") != "yes":
                    abort(403)
                return fn(*args, **kwargs)
            return protected

        @self.app.route("/app-tesserato/<token>/ricevuta/<int:receipt_id>")
        def existing_pdf_route(token, receipt_id):
            return "PDF stub"

        register(self.app, db, admin_required,
                 lambda: '<input name="csrf_token" value="test-csrf">',
                 lambda: "admin")
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_admin_page_uses_actual_receipt_payment_athlete_relation(self):
        response = self.client.get("/amministrazione/ricevute-famiglie", headers={"X-Test-Admin":"yes"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Test Atleta", response.data)
        self.assertIn(b"Ricevuta #1", response.data)

    def test_admin_auth_csrf_and_pdf_hide_restore(self):
        self.assertEqual(self.client.get("/amministrazione/ricevute-famiglie").status_code, 403)
        self.assertEqual(self.client.get("/app-tesserato/abc/ricevuta/1").status_code, 200)
        url = "/amministrazione/ricevute-famiglie/1/visibilita"
        self.assertEqual(self.client.post(url, data={"hide":"1","reason":"Duplicato storico","csrf_token":"test-csrf"}).status_code, 403)
        self.assertEqual(self.client.post(url, headers={"X-Test-Admin":"yes"}, data={"hide":"1","reason":"Duplicato storico"}).status_code, 400)
        result = self.client.post(url, headers={"X-Test-Admin":"yes"}, data={"hide":"1","reason":"Duplicato storico","csrf_token":"test-csrf"})
        self.assertEqual(result.status_code, 302)
        self.assertEqual(self.client.get("/app-tesserato/abc/ricevuta/1").status_code, 404)
        self.assertEqual(self.client.get("/app-tesserato/abc/ricevuta/2").status_code, 200)
        result = self.client.post(url, headers={"X-Test-Admin":"yes"}, data={"hide":"0","reason":"Ricevuta ripristinata","csrf_token":"test-csrf"})
        self.assertEqual(result.status_code, 302)
        self.assertEqual(self.client.get("/app-tesserato/abc/ricevuta/1").status_code, 200)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM ricevute").fetchone()[0],1)
            self.assertEqual(conn.execute("SELECT count(*) FROM bodymind_family_receipt_visibility_audit").fetchone()[0],2)


if __name__ == "__main__":
    unittest.main()
