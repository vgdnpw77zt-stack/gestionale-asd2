from __future__ import annotations
import hashlib, json, re
from datetime import datetime

DOC_TYPES=(
 "modulo_unico_tesseramento","certificato_medico","documento_identita",
 "trasporto_minori","documenti_gara","documenti_saggio","ricevuta_pagamento",
 "verbale","statuto_atto","affiliazione","assicurazione","contratto","amministrazione","altro"
)

def ensure_schema(conn):
    conn.execute("""
      CREATE TABLE IF NOT EXISTS bodymind_document_semantics(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_table TEXT NOT NULL,
        source_id INTEGER NOT NULL,
        sha256 TEXT NOT NULL,
        document_type TEXT,
        person_name TEXT,
        codice_fiscale TEXT,
        semantic_key TEXT,
        confidence REAL NOT NULL DEFAULT 0,
        analysis_json TEXT NOT NULL,
        model TEXT,
        analyzed_at TEXT NOT NULL,
        UNIQUE(source_table,source_id,sha256)
      )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bodymind_docsem_subject ON bodymind_document_semantics(source_table,source_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bodymind_docsem_sha ON bodymind_document_semantics(sha256)")
    conn.commit()

def sha256_bytes(data):
    return hashlib.sha256(bytes(data or b"")).hexdigest()

def semantic_key(analysis):
    fields=[
      str(analysis.get("document_type") or ""),
      re.sub(r"\s+"," ",str(analysis.get("person_name") or "").lower()).strip(),
      re.sub(r"[^A-Z0-9]","",str(analysis.get("codice_fiscale") or "").upper()),
      str(analysis.get("birth_date") or ""),str(analysis.get("issue_date") or ""),
      str(analysis.get("expiry_date") or ""),str(analysis.get("season_year") or ""),
      str(analysis.get("form_version") or ""),str(analysis.get("guardian_name") or ""),
      str(analysis.get("privacy_consent") or ""),str(analysis.get("image_consent") or ""),
      str(analysis.get("autonomous_exit") or ""),str(analysis.get("delegation") or ""),
      str(analysis.get("athlete_signature") or ""),str(analysis.get("guardian_signature") or "")
    ]
    return hashlib.sha256(json.dumps(fields,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()

def cache_get(conn,source_table,source_id,sha):
    ensure_schema(conn)
    row=conn.execute("SELECT analysis_json FROM bodymind_document_semantics WHERE source_table=? AND source_id=? AND sha256=? ORDER BY id DESC LIMIT 1",
                     (str(source_table),int(source_id),str(sha))).fetchone()
    if not row: return None
    try:
        obj=json.loads(str(row["analysis_json"] or "{}"))
        return obj if isinstance(obj,dict) else None
    except Exception:
        return None

def cache_put(conn,source_table,source_id,analysis):
    ensure_schema(conn)
    conn.execute("""
      INSERT INTO bodymind_document_semantics
      (source_table,source_id,sha256,document_type,person_name,codice_fiscale,semantic_key,confidence,analysis_json,model,analyzed_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(source_table,source_id,sha256) DO UPDATE SET
       document_type=excluded.document_type,person_name=excluded.person_name,
       codice_fiscale=excluded.codice_fiscale,semantic_key=excluded.semantic_key,
       confidence=excluded.confidence,analysis_json=excluded.analysis_json,
       model=excluded.model,analyzed_at=excluded.analyzed_at
    """,(str(source_table),int(source_id),str(analysis.get("sha256") or ""),
         str(analysis.get("document_type") or ""),str(analysis.get("person_name") or ""),
         str(analysis.get("codice_fiscale") or ""),str(analysis.get("semantic_key") or ""),
         float(analysis.get("confidence") or 0),json.dumps(analysis,ensure_ascii=False,separators=(",",":")),
         str(analysis.get("model") or ""),datetime.now().isoformat(timespec="seconds")))
    conn.commit()
