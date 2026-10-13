"""Read-only tests for BodyMind accounting repair; never connects to production."""
import ast
import pathlib
import sqlite3
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def value_of(name, filename):
    tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError("Missing source string: " + name)


def pure_function(source, name):
    tree = ast.parse(source)
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    assert len(nodes) == 1, (name, len(nodes))
    namespace = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "<read-only-test>", "exec"), namespace)
    return namespace[name]


class RepairGuards(unittest.TestCase):
    def test_python_sources_compile(self):
        for filename in ("runtime_launcher.py", "release_secretary_ui_r123.py",
                         "release_operator_review_actions_r156.py"):
            path = ROOT / filename
            compile(path.read_text(encoding="utf-8"), str(path), "exec")

    def test_dynamic_sources_parse(self):
        r123 = (ROOT / "release_secretary_ui_r123.py").read_text(encoding="utf-8")
        for token in ("def _bodymind_payment_register_v7", "def bodymind_quote_incassi_canonical",
                      "BODYMIND_R160_ZERO_DUE_TRUTH", "BODYMIND_R161_EXPLICIT_ANNUAL_NON_DUE"):
            self.assertIn(token, r123)
        for name, filename in (
                ("_r161_src", "release_secretary_ui_r123.py"),
                ("_r159_helpers", "release_operator_review_actions_r156.py"),
                ("_fee_src", "release_operator_review_actions_r156.py")):
            ast.parse(value_of(name, filename))
        payment_patch = value_of("_r159_pay_new", "release_operator_review_actions_r156.py")
        compile("def writer():\n" + payment_patch, "<r159-writer>", "exec")
        self.assertIn("BODYMIND_R159_SAFE_EXISTING_DUE", payment_patch)
        self.assertIn("_r159_predicate", (ROOT / "release_operator_review_actions_r156.py").read_text())

    def test_explicit_annual_waiver_never_creates_cash(self):
        fn = pure_function(value_of("_r161_src", "release_secretary_ui_r123.py"),
                           "bodymind_explicit_annual_non_due")
        c = sqlite3.connect(":memory:"); c.row_factory=sqlite3.Row
        try:
            c.execute("""CREATE TABLE pagamenti(id INTEGER PRIMARY KEY AUTOINCREMENT, tesserato_id INTEGER, anno INTEGER, mese INTEGER,
                         importo REAL, causale TEXT, stato TEXT,
                         online_status TEXT, note_pagamento TEXT)""")
            self.assertFalse(fn(c, 1, 2026))
            c.execute("INSERT INTO pagamenti(tesserato_id,anno,mese,importo,causale,stato,online_status,note_pagamento) VALUES (1,2026,10,0,'iscrizione','paid_manual','paid_manual','Non dovuto')")
            self.assertTrue(fn(c, 1, 2026))
            self.assertFalse(fn(c, 1, 2025))
            self.assertFalse(fn(c, 2, 2026))
            c.execute("INSERT INTO pagamenti(tesserato_id,anno,mese,importo,causale,stato,online_status,note_pagamento) VALUES (1,2026,10,50,'iscrizione','paid_manual','paid_manual','')")
            self.assertFalse(fn(c, 1, 2026))
        finally:
            c.close()

    def test_month_begins_after_september(self):
        fn = pure_function(value_of("_r159_helpers", "release_operator_review_actions_r156.py"),
                           "bodymind_r159_month_before_entry")
        c = sqlite3.connect(":memory:"); c.row_factory=sqlite3.Row
        try:
            c.execute("CREATE TABLE tesserati(id INTEGER, data_iscrizione TEXT, created_at TEXT)")
            c.execute("CREATE TABLE pagamenti(tesserato_id INTEGER, mese INTEGER, anno INTEGER, importo REAL, causale TEXT, stato TEXT)")
            c.execute("INSERT INTO tesserati VALUES(1,'2026-10-01','2026-10-01')")
            self.assertTrue(fn(c,1,2026,9))
            self.assertFalse(fn(c,1,2026,10))
            c.execute("INSERT INTO pagamenti VALUES(1,9,2026,95,'mensile','paid_manual')")
            self.assertFalse(fn(c,1,2026,9))
        finally:
            c.close()


    def test_cash_totals_reject_unpaid_and_zero(self):
        source=(ROOT / "release_secretary_ui_r123.py").read_text(encoding="utf-8")
        tree=ast.parse(source)
        appended=[node.value.value for node in ast.walk(tree)
                  if isinstance(node,ast.AugAssign) and isinstance(node.target,ast.Name)
                  and node.target.id=="_core_qi" and isinstance(node.value,ast.Constant)
                  and isinstance(node.value.value,str)]
        self.assertEqual(len(appended),1)
        runtime=ast.parse(appended[0])
        nested=[n for n in ast.walk(runtime)
                if isinstance(n,ast.FunctionDef) and n.name=="_cash_row"]
        self.assertEqual(len(nested),1)
        scope={}
        exec(compile(ast.Module(body=nested,type_ignores=[]),"<cash-guard>","exec"),scope)
        cash=scope["_cash_row"]
        sample={"importo":95,"data":"2026-10-05"}
        self.assertFalse(cash(dict(sample,stato="unpaid",online_status="unpaid")))
        self.assertFalse(cash(dict(sample,stato="pending",online_status="pending")))
        self.assertFalse(cash(dict(sample,stato="paid_manual",importo=0)))
        self.assertTrue(cash(dict(sample,stato="paid_manual")))
        self.assertTrue(cash(dict(sample,stato="")))

    def test_october_sms_compatible_with_annual_non_due(self):
        r123=(ROOT/"release_secretary_ui_r123.py").read_text(encoding="utf-8")
        old=value_of("_old_actions","release_operator_review_actions_r156.py")
        new=value_of("_new_actions","release_operator_review_actions_r156.py")
        self.assertIn("Iscrizione non dovuta",old)
        self.assertIn(old,r123)
        self.assertEqual(new,old.replace('+"</div>"','+sms_action+"</div>"'))

    def test_positive_unpaid_does_not_count_as_paid(self):
        fn=pure_function(value_of("_fee_src","release_operator_review_actions_r156.py"),
                         "bodymind_r156_settled_monthly")
        c=sqlite3.connect(":memory:");c.row_factory=sqlite3.Row
        try:
            c.execute("""CREATE TABLE pagamenti(tesserato_id INTEGER,mese INTEGER,anno INTEGER,
                importo REAL,causale TEXT,stato TEXT,online_status TEXT,paid_at TEXT)""")
            c.execute("INSERT INTO pagamenti VALUES(14,10,2026,95,'mensile','unpaid','unpaid','')")
            self.assertFalse(fn(c,14,10,2026))
            c.execute("UPDATE pagamenti SET stato='pending',online_status='pending'")
            self.assertFalse(fn(c,14,10,2026))
            c.execute("UPDATE pagamenti SET stato='paid_manual',online_status='paid_manual'")
            self.assertTrue(fn(c,14,10,2026))
            c.execute("UPDATE pagamenti SET stato='annullato',online_status='annullato'")
            self.assertFalse(fn(c,14,10,2026))
        finally:c.close()

    def test_pre_entry_unpaid_is_not_historical_paid(self):
        fn=pure_function(value_of("_r159_helpers","release_operator_review_actions_r156.py"),
                         "bodymind_r159_month_before_entry")
        c=sqlite3.connect(":memory:");c.row_factory=sqlite3.Row
        try:
            c.execute("CREATE TABLE tesserati(id INTEGER,data_iscrizione TEXT,created_at TEXT)")
            c.execute("CREATE TABLE pagamenti(tesserato_id INTEGER,mese INTEGER,anno INTEGER,importo REAL,causale TEXT,stato TEXT)")
            c.execute("INSERT INTO tesserati VALUES(14,'2026-10-01','2026-10-01')")
            c.execute("INSERT INTO pagamenti VALUES(14,9,2026,95,'mensile','unpaid')")
            self.assertTrue(fn(c,14,2026,9))
            c.execute("UPDATE pagamenti SET stato='paid_manual'")
            self.assertFalse(fn(c,14,2026,9))
        finally:c.close()

    def test_startup_never_deletes_backups_or_reverts_database(self):
        src=(ROOT/"runtime_launcher.py").read_text(encoding="utf-8")
        pre=src.split("def _bodymind_storage_preflight():",1)[1].split(
            "# BODYMIND_OPERATOR_TASK_LIFECYCLE_CLEANUP",1)[0]
        self.assertIn('"backup_auto_deletion":"disabled"',pre)
        self.assertIn('manual recovery required',pre)
        self.assertNotIn(".unlink(",pre)
        self.assertNotIn("os.replace(",pre)
        self.assertNotIn("shutil.copy2(db_path",pre)

    def test_october_collision_will_not_replace_settled_or_ambiguous(self):
        src=(ROOT/"release_operator_review_actions_r156.py").read_text(encoding="utf-8")
        self.assertIn("BODYMIND_R159_SAFE_EXISTING_DUE",src)
        self.assertIn("or not any(x in _st",src)
        self.assertIn("if len(_same)!=1",src)
        self.assertIn("_already_paid or _cancelled or _attached or _non_due",src)
        errors=(ROOT/"release_secretary_ui_r123.py").read_text(encoding="utf-8")
        self.assertIn("Esistono più movimenti per questa quota",errors)

    def test_partial_monthly_preserves_existing_due(self):
        import re
        src=(ROOT/"release_secretary_ui_r123.py").read_text(encoding="utf-8")
        match=re.search(r"UPDATE quote_mensili\s+SET stato=CASE WHEN COALESCE\(importo_dovuto,importo_base,0\)>\?[\s\S]*?WHERE id=\?",src)
        self.assertIsNotNone(match)
        c=sqlite3.connect(":memory:")
        try:
            c.execute("""CREATE TABLE quote_mensili(id INTEGER PRIMARY KEY,importo_base REAL,
                    importo_dovuto REAL,stato TEXT,note TEXT,updated_at TEXT)""")
            c.execute("INSERT INTO quote_mensili VALUES(1,95,95,'da_pagare','','')")
            c.execute(match.group(0),(30,'','','2026-10-13',1))
            base,due,state=c.execute("SELECT importo_base,importo_dovuto,stato FROM quote_mensili").fetchone()
            self.assertEqual((base,due,state),(95,95,'parziale'))
            c.execute(match.group(0),(95,'','','2026-10-13',1))
            base,due,state=c.execute("SELECT importo_base,importo_dovuto,stato FROM quote_mensili").fetchone()
            self.assertEqual((base,due,state),(95,95,'pagato'))
        finally:c.close()

    def test_explicit_non_due_cannot_create_receipt(self):
        src=(ROOT/"release_secretary_ui_r123.py").read_text(encoding="utf-8")
        self.assertIn("errore=quota_non_dovuta",src)
        self.assertIn("decisione amministrativa di non dovuto",src)
        self.assertIn("if _due<=0 and any",src)

    def test_r159_legacy_causale_and_contradictory_statuses(self):
        # Exercise the real inserted payment-collision guard on isolated SQLite.
        src=value_of("_r159_pay_new","release_operator_review_actions_r156.py")
        pre=src.split("        now=_dt.now()",1)[0]
        code="def select(c,tid,mese,anno,tipo,payment_id=0):\n        existing=None\n"+pre+"        return existing\n"
        scope={"redirect":lambda uri,code:(uri,code)}
        exec(compile(code,"<r159-collision>", "exec"),scope)
        fn=scope["select"]
        c=sqlite3.connect(":memory:");c.row_factory=sqlite3.Row
        try:
            c.execute("""CREATE TABLE pagamenti(id INTEGER PRIMARY KEY,tesserato_id INTEGER,
                mese INTEGER,anno INTEGER,causale TEXT,stato TEXT,online_status TEXT,
                note_pagamento TEXT,ricevuta_id INTEGER,paid_at TEXT,importo REAL,
                UNIQUE(tesserato_id,mese,anno,causale))""")
            c.execute("CREATE TABLE ricevute(id INTEGER PRIMARY KEY,pagamento_id INTEGER)")
            c.execute("""INSERT INTO pagamenti VALUES
                (11,14,10,2026,'quota','unpaid','unpaid','',NULL,'',95)""")
            self.assertEqual(fn(c,14,10,2026,'mensile')['id'],11)
            c.execute("UPDATE pagamenti SET online_status='paid_manual' WHERE id=11")
            self.assertIn('gia_registrato',fn(c,14,10,2026,'mensile')[0])
            c.execute("UPDATE pagamenti SET stato='paid_manual',online_status='paid_manual' WHERE id=11")
            self.assertIn('gia_registrato',fn(c,14,10,2026,'mensile')[0])
            c.execute("UPDATE pagamenti SET stato='unpaid',online_status='unpaid' WHERE id=11")
            c.execute("INSERT INTO ricevute VALUES(3,11)")
            self.assertIn('gia_registrato',fn(c,14,10,2026,'mensile')[0])
            c.execute("DELETE FROM ricevute")
            c.execute("""INSERT INTO pagamenti VALUES
                (12,14,10,2026,'mensile','unpaid','unpaid','',NULL,'',95)""")
            self.assertIn('movimenti_da_verificare',fn(c,14,10,2026,'mensile')[0])
        finally:c.close()

    def test_r167_desktop_explicit_monthly_non_due_only(self):
        fn=pure_function(value_of("_r167_src","release_secretary_ui_r123.py"),
                         "bodymind_explicit_monthly_non_due_r167")
        c=sqlite3.connect(":memory:");c.row_factory=sqlite3.Row
        try:
            c.execute("""CREATE TABLE pagamenti(id INTEGER PRIMARY KEY,tesserato_id INTEGER,
                mese INTEGER,anno INTEGER,causale TEXT,stato TEXT,online_status TEXT,
                note_pagamento TEXT,importo REAL)""")
            c.execute("""CREATE TABLE quote_mensili(id INTEGER PRIMARY KEY,tesserato_id INTEGER,
                mese INTEGER,anno INTEGER,importo_base REAL,importo_dovuto REAL,stato TEXT)""")
            c.execute("INSERT INTO quote_mensili VALUES(1,26,10,2026,95,0,'esente')")
            self.assertTrue(fn(c,26,10,2026))
            self.assertFalse(fn(c,26,9,2026))
            c.execute("UPDATE quote_mensili SET stato='da_pagare'")
            self.assertFalse(fn(c,26,10,2026))
            c.execute("""INSERT INTO pagamenti VALUES
                (2,26,10,2026,'mensile','paid_manual','paid_manual','',95)""")
            c.execute("UPDATE quote_mensili SET stato='esente'")
            self.assertFalse(fn(c,26,10,2026))
        finally:c.close()
        source=(ROOT/"release_secretary_ui_r123.py").read_text(encoding="utf-8")
        self.assertIn("'/','/dashboard','/centro-operativo','/cuore-operativo'",source)
        self.assertIn("enroll=bool(pr.get('iscrizione_pagata') or bodymind_explicit_annual_non_due",source)

    def test_zero_due_preserved_and_qa_consistent(self):
        s = (ROOT / "release_secretary_ui_r123.py").read_text(encoding="utf-8")
        self.assertEqual(s.count("q['importo_dovuto'] or q['importo_base']"), 1,
                         "Legacy expression should remain only as the migration's match token")
        self.assertIn("q['importo_dovuto'] if q['importo_dovuto'] is not None", s)
        self.assertIn("month_total<=0", s)
        self.assertIn("monthly_residual_eur", s)
        self.assertIn("NON DOVUTA", s)
        r159 = (ROOT / "release_operator_review_actions_r156.py").read_text(encoding="utf-8")
        self.assertIn("BODYMIND_R159_SAFE_EXISTING_DUE", r159)
        self.assertIn("_already_paid or _cancelled or _attached", r159)
        self.assertIn("if payment_id and not existing:", r159)
        self.assertIn("_non_due=any(", r159)
        self.assertIn("_already_paid or _cancelled or _attached or _non_due", r159)

if __name__ == "__main__":
    unittest.main()
