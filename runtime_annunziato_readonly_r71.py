# -*- coding: utf-8 -*-
from __future__ import annotations
import json, sqlite3
from pathlib import Path

DB=Path('/data/tenants/default/asd.db')
c=sqlite3.connect(str(DB),timeout=20); c.row_factory=sqlite3.Row
try:
    t=c.execute("SELECT * FROM tesserati WHERE id=13").fetchone()
    m=c.execute("SELECT * FROM minori WHERE tesserato_id=13 LIMIT 1").fetchone() if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='minori'").fetchone() else None
    ib=c.execute("SELECT * FROM inbound_documents WHERE id=173").fetchone() if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inbound_documents'").fetchone() else None
    docs=c.execute("SELECT * FROM documenti WHERE tesserato_id=13 ORDER BY id").fetchall() if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documenti'").fetchone() else []
    def pick(row,names):
        if not row: return {}
        keys=set(row.keys()); out={}
        for k in names:
            if k in keys:
                v=row[k]
                out[k]=v
        return out
    result={
      "tesserato":pick(t,["id","nome","cognome","codice_fiscale","data_nascita","genitore","nome_genitore","telefono_genitore","email_genitore","minorenne","iscrizione_firmata","documenti_onboarding_ok","privacy_ok","liberatoria_ok","regolamento_ok"]),
      "minore":pick(m,["id","tesserato_id","genitore","nome_genitore","telefono_genitore","email_genitore","consenso_firmato","data_consenso"]),
      "inbound173":pick(ib,["id","tesserato_id","document_type","status","document_confidence","match_score","original_filename"]),
      "documenti":[pick(r,["id","titolo","categoria","doc_type","filename","stato","status","visibile"]) for r in docs],
      "integrity":str(c.execute("PRAGMA integrity_check").fetchone()[0]),
      "fk":len(c.execute("PRAGMA foreign_key_check").fetchall())
    }
    print("[r71-annunziato-readonly] "+json.dumps(result,ensure_ascii=False),flush=True)
finally:
    c.close()
