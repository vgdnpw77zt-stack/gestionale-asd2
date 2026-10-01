# -*- coding: utf-8 -*-
from __future__ import annotations
import io, json, sqlite3, sys, uuid
from pypdf import PdfReader, PdfWriter
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
sys.path.insert(0,str(APP))

from asd_app.enrollment_ingest_core_r65 import (
    enrollment_identity_ready, create_athlete_from_analysis, valid_italian_cf
)
import asd_app.operator_doc_semantic_ai_r52 as docai

before={}
c=sqlite3.connect(str(DB),timeout=20)
c.row_factory=sqlite3.Row
try:
    for t in ("tesserati","documenti","inbound_documents"):
        before[t]=int(c.execute("SELECT COUNT(*) FROM "+t).fetchone()[0])
    analysis={
      "document_type":"modulo_unico_tesseramento","confidence":.99,
      "first_name":"QA"+uuid.uuid4().hex[:6].upper(),"last_name":"R65TEST",
      "person_name":"QA R65TEST","codice_fiscale":"",
      "birth_date":"2012-04-03","birth_place":"Roma","address":"Via Test 1","city":"Roma",
      "postal_code":"00100","province":"RM","phone":"3330000000","email":"qa@example.invalid",
      "guardian_name":"Genitore QA","guardian_phone":"3330000001","guardian_email":"g@example.invalid",
      "nationality":"italiana","gender":"","notes":"R65 rollback smoke"
    }
    ready=enrollment_identity_ready(analysis,require_valid_cf=False)
    c.execute("SAVEPOINT r65_smoke")
    created=create_athlete_from_analysis(c,analysis,source="smoke",require_valid_cf=False)
    inserted=bool(created.get("created") and int(created.get("tesserato_id") or 0)>0)
    c.execute("ROLLBACK TO r65_smoke"); c.execute("RELEASE r65_smoke")
    after={t:int(c.execute("SELECT COUNT(*) FROM "+t).fetchone()[0]) for t in before}
    integrity=str(c.execute("PRAGMA integrity_check").fetchone()[0])
    fk=len(c.execute("PRAGMA foreign_key_check").fetchall())
finally:
    c.close()

sem=(APP/'asd_app/operator_doc_semantic_ai_r52.py').read_text(encoding='utf-8',errors='replace')
op=(APP/'asd_app/routes_operator_bodymind.py').read_text(encoding='utf-8',errors='replace')
email=(APP/'asd_app/routes_email_documents.py').read_text(encoding='utf-8',errors='replace')

# R66 synthetic multi-document PDF segmentation: no network, no business writes.
writer=PdfWriter()
writer.add_blank_page(width=595,height=842)
writer.add_blank_page(width=595,height=842)
bio=io.BytesIO(); writer.write(bio)
fake_pdf=bio.getvalue()
orig_call=docai._call_json
try:
    docai._call_json=lambda *a,**k:{
      "contains_multiple_documents":True,
      "documents":[
        {"page_start":1,"page_end":1,"document_type":"certificato_medico","person_name":"ATLETA UNO","confidence":.99,"evidence":"pagina 1"},
        {"page_start":2,"page_end":2,"document_type":"certificato_medico","person_name":"ATLETA DUE","confidence":.99,"evidence":"pagina 2"}
      ]
    }
    seg=docai.segment_pdf_documents(c,"fascicolo.pdf",fake_pdf,"certificato_medico",None)
finally:
    docai._call_json=orig_call
segments=seg.get("segments") or []
split_ok=bool(seg.get("multiple")) and len(segments)==2 and all(len(PdfReader(io.BytesIO(x["data"])).pages)==1 for x in segments)

checks={
  "ready":ready,
  "insert_rollback":inserted and before==after,
  "cf_validator":valid_italian_cf("RSSMRA80A01H501U"),
  "visual_handwriting":"BODYMIND_R65_HANDWRITING_VISION" in sem and "handwriting_present" in sem and "first_name" in sem and "guardian_phone" in sem,
  "operator_flow":"BODYMIND_R65_HANDWRITING_ENROLLMENT" in op and "process_enrollment_batch" in op and "nuova_tesserata_pronta" in op,
  "autopilot_flow":"BODYMIND_R65_AUTOPILOT_HANDWRITING" in email and "require_valid_cf=True" in email,
  "multidoc_split_r66":split_ok and "def segment_pdf_documents" in sem,
  "truthful_upload_ui_r66":"uploadInFlight" in op and "Ho ricevuto '+files.length+' file" not in op and "Sto inviando '+files.length+' file al server BodyMind" in op,
  "operator_multidoc_flow_r66":"BODYMIND_R66_UPLOAD_TRUTH_MULTIDOC" in op and "physical_file_count" in op and "segment_pdf_documents" in op,
  "integrity":integrity.lower()=="ok",
  "foreign_keys":fk==0,
}
print("[r66-smoke] "+json.dumps({"ok":all(checks.values()),"checks":checks,"counts_before":before,"counts_after":after,"integrity":integrity,"foreign_keys":fk},ensure_ascii=False),flush=True)
if not all(checks.values()):
    raise RuntimeError("R66 smoke failed: "+repr([k for k,v in checks.items() if not v]))
