import functools
import os
import sqlite3
import tempfile
import unittest

from fixes.a293.manual_payment_links import amount_to_cents, validate_url, save_link, disable_link, family_link
from fixes.a293.reminder_access import compose_reminder, family_access_url
from fixes.a293.operator_layout_patch import transform

class PureTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE TABLE tesserati(id INTEGER PRIMARY KEY,nome TEXT)")
        self.db.executemany("INSERT INTO tesserati VALUES(?,?)",[(10,"A"),(11,"B")])
    def tearDown(self):
        self.db.close()
    def test_link_isolated_and_no_paid_state(self):
        url = "https://pay.sumup.com/b2c/abc"
        save_link(self.db,tenant_slug="default",athlete_id=10,period="2026-10",kind="mensile",
                  provider="sumup",amount="50.00",url=url,operator="admin")
        args=dict(tenant_slug="default",athlete_id=10,period="2026-10",kind="mensile")
        verified=dict(verified=True,unpaid_cents=5000,paid=False,cancelled=False)
        self.assertEqual(family_link(self.db,**args,due=verified)["checkout_url"],url)
        self.assertIsNone(family_link(self.db,**{**args,"athlete_id":11},due=verified))
        self.assertIsNone(family_link(self.db,**{**args,"tenant_slug":"other"},due=verified))
        for bad in (dict(verified=False),dict(paid=True),dict(cancelled=True),dict(unpaid_cents=4900)):
            self.assertIsNone(family_link(self.db,**args,due={**verified,**bad}))
        disable_link(self.db,**args,operator="admin")
        self.assertIsNone(family_link(self.db,**args,due=verified))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM bodymind_a293_payment_links_audit").fetchone()[0],2)
        self.assertIsNone(self.db.execute("SELECT name FROM sqlite_master WHERE name='pagamenti'").fetchone())
    def test_url_and_amount_validation(self):
        self.assertEqual(amount_to_cents("49,90"),4990)
        for bad in (float("nan"),50.10,"50.999","0","-1","10000.01"):
            with self.assertRaises(ValueError):
                amount_to_cents(bad)
        for bad in ("http://pay.sumup.com/x","https://sumup.com.evil.test/pay/x",
                    "https://evil@pay.sumup.com/x","https://pay.sumup.com:9999/x",
                    "https://pay.sumup.com:invalid/x","javascript:alert(1)"):
            with self.assertRaises(ValueError):
                validate_url(bad,"sumup")
    def test_family_access_and_reminder_consent(self):
        args=dict(athlete_label="Anna Test",family_pin="ABCD1234",subject="Quota ottobre",
                  is_minor=True,recipient_role="guardian",contact_checked=True,send_consent=True)
        self.assertIn("/famiglia/ABCD1234",family_access_url("ABCD1234"))
        msg=compose_reminder(**args)
        self.assertIn("ABCD1234",msg)
        self.assertIn("App Famiglie",msg)
        for bad in (dict(recipient_role="athlete"),dict(contact_checked=False),dict(send_consent=False)):
            with self.assertRaises(ValueError):
                compose_reminder(**{**args,**bad})
    def test_operator_transform_idempotence(self):
        raw='''def view():
    value = f\'\'\'<style>/* BODYMIND_OPERATOR_MOBILE_LAYOUT_CANONICAL */
    .bmo-compose{{color:red}}
    /* BODYMIND_R155_OPERATOR_COMPOSER_ANCHORED */</style><main class="bmo">hello</main>\'\'\'
    return value
'''
        patch=transform(raw.encode())
        self.assertIn(b"BODYMIND_A293_OPERATOR_COMPOSER_LAYOUT",patch)
        with self.assertRaises(ValueError):
            transform(patch)

class FlaskRoutesTests(unittest.TestCase):
    def test_admin_route_and_csrf(self):
        from flask import Flask,request,abort
        from fixes.a293.admin_payment_links import register
        with tempfile.TemporaryDirectory() as td:
            path=os.path.join(td,"x.db")
            with sqlite3.connect(path) as c:
                c.execute("CREATE TABLE tesserati(id INTEGER PRIMARY KEY,nome TEXT,cognome TEXT)")
                c.execute("INSERT INTO tesserati VALUES(10,'Anna','Test')")
            def db():
                conn=sqlite3.connect(path)
                conn.row_factory=sqlite3.Row
                return conn
            app=Flask(__name__)
            app.secret_key="test-only"
            @app.before_request
            def protect_csrf():
                if request.method=="POST" and request.form.get("csrf_token")!="valid":
                    abort(400)
            def protect_admin(fn):
                @functools.wraps(fn)
                def wrapped(*a,**kw):
                    if request.headers.get("X-Test-Admin")!="yes":
                        abort(403)
                    return fn(*a,**kw)
                return wrapped
            register(app, db, protect_admin, lambda:'<input name="csrf_token" value="valid">',
                     lambda:"admin",lambda:"default")
            client=app.test_client()
            route="/amministrazione/link-pagamento-famiglie"
            self.assertEqual(client.get(route).status_code,403)
            self.assertEqual(client.get(route,headers={"X-Test-Admin":"yes"}).status_code,200)
            data=dict(action="save",athlete_id="10",period="2026-10",kind="mensile",
                      provider="sumup",amount="50,00",url="https://pay.sumup.com/b2c/test")
            self.assertEqual(client.post(route,data={**data,"csrf_token":"valid"}).status_code,403)
            self.assertEqual(client.post(route,data=data,headers={"X-Test-Admin":"yes"}).status_code,400)
            self.assertEqual(client.post(route,data={**data,"csrf_token":"valid"},
                         headers={"X-Test-Admin":"yes"}).status_code,302)
            with db() as c:
                self.assertEqual(c.execute("SELECT COUNT(*) FROM bodymind_a293_payment_links").fetchone()[0],1)

if __name__=="__main__":
    unittest.main()
