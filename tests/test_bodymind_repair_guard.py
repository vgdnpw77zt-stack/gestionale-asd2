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

if __name__ == "__main__":
    unittest.main()
