# -*- coding: utf-8 -*-
from pathlib import Path
import json, sqlite3
DB=Path('/data/tenants/default/asd.db')
PENDING=("needs_manual_match","associato_tipo_da_verificare","richiede_conferma","needs_review","da_verificare","pending")
report={"pending":[],"counts":{},"integrity":"","foreign_keys":None}
if DB.exists():
    c=sqlite3.connect(str(DB),timeout=20); c.row_factory=sqlite3.Row
    try:
        def table(n): return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(n,)).fetchone())
        for t in ("tesserati","documenti","inbound_documents","pagamenti","ricevute"):
            if table(t): report["counts"][t]=int(c.execute("SELECT COUNT(*) FROM "+t).fetchone()[0])
        if table("inbound_documents"):
            cols={str(r[1]) for r in c.execute("PRAGMA table_info(inbound_documents)").fetchall()}
            rows=c.execute("SELECT * FROM inbound_documents WHERE lower(coalesce(status,'')) IN ("+",".join("?" for _ in PENDING)+") ORDER BY id",PENDING).fetchall()
            for r in rows:
                item={"id":int(r["id"]),"status":str(r["status"] or "")}
                for k in ("original_filename","filename","document_type","document_confidence","match_score","tesserato_id","matched_tesserato_id","suggested_tesserato_id"):
                    if k in cols: item[k]=r[k]
                report["pending"].append(item)
        report["integrity"]=str(c.execute("PRAGMA integrity_check").fetchone()[0])
        report["foreign_keys"]=len(c.execute("PRAGMA foreign_key_check").fetchall())
    finally:
        c.close()
print("[operator-r55e-pending-audit] "+json.dumps(report,ensure_ascii=False),flush=True)
if report["integrity"].lower()!="ok" or report["foreign_keys"]:
    raise RuntimeError("R55E pending audit DB integrity failed")
