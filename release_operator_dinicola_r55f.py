# -*- coding: utf-8 -*-
from pathlib import Path
import json, sqlite3, sys

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MARK=APP/'.BODYMIND_OPERATOR_DINICOLA_RECONCILE_R55F'
TARGETS=(58,67)

def get_file(op,row):
    stored=""
    for k in ("saved_path","path","filename"):
        if k in row.keys() and str(row[k] or "").strip():
            stored=str(row[k] or "").strip(); break
    name=""
    for k in ("original_filename","filename"):
        if k in row.keys() and str(row[k] or "").strip():
            name=Path(str(row[k] or "")).name; break
    for p in op._document_file_candidates(stored):
        try:
            if p.is_file():
                data=p.read_bytes()
                if len(data)<=40*1024*1024:
                    return name or p.name,data
        except Exception:
            pass
    return name,b""

if MARK.exists():
    print("[operator-r55f-dinicola] already attempted "+MARK.read_text(encoding="utf-8",errors="replace")[:3000],flush=True)
else:
    sys.path.insert(0,str(APP))
    import app as _full_app
    from flask import session
    from asd_app.core import app,db
    import asd_app.routes_operator_bodymind as op
    from asd_app.routes_email_documents import extract_attachment_text

    result={"ok":False,"targets":[],"comparison":None,"produced":None,"duplicate_preserved":None,"errors":[]}
    backup=op._operator_db_backup("r55f_dinicola")
    result["backup"]=backup
    with app.test_request_context('/operatore-bodymind'):
        session.update({'logged':True,'username':'admin','display_name':'BodyMind R55F','role':'admin','tenant_slug':'default',
                        '_csrf_token':'r55f','bodymind_operator_conversation':'r55f','bodymind_operator_identity':'BodyMind R55F'})
        analyses={}
        blobs={}
        conn=db()
        try:
            for iid in TARGETS:
                row=conn.execute("SELECT * FROM inbound_documents WHERE id=?",(iid,)).fetchone()
                if not row:
                    raise RuntimeError("missing inbound "+str(iid))
                if int(row["tesserato_id"] or 0)!=21:
                    raise RuntimeError("R55F refuses target with unexpected athlete id "+str(iid))
                name,data=get_file(op,row)
                if not data:
                    raise RuntimeError("unreadable file "+str(iid))
                try: extracted=str(extract_attachment_text(name,data) or "")
                except Exception: extracted=""
                analysis=op._semantic_for_new_bytes(conn,name,data,extracted,"")
                op._docsem_cache_put(conn,"inbound_documents",iid,analysis)
                athlete,score,reason=op._semantic_match_athlete(conn,analysis)
                analyses[iid]=analysis; blobs[iid]=(name,data)
                result["targets"].append({
                    "id":iid,"name":name,"type":analysis.get("document_type"),
                    "confidence":round(float(analysis.get("confidence") or 0),3),
                    "semantic_person":analysis.get("person_name"),
                    "semantic_tesserato_id":int(athlete["id"]) if athlete else None,
                    "semantic_match":round(float(score or 0),3),"match_reason":reason
                })
            a58=analyses[58]; a67=analyses[67]
            if str(a58.get("document_type") or "")!="modulo_unico_tesseramento" or str(a67.get("document_type") or "")!="modulo_unico_tesseramento":
                raise RuntimeError("R55F types are not both Modulo Unico")
            if min(float(a58.get("confidence") or 0),float(a67.get("confidence") or 0))<.95:
                raise RuntimeError("R55F semantic confidence below 95%")
            n58,d58=blobs[58]; n67,d67=blobs[67]
            cmp=op._semantic_same_pair(conn,n58,d58,a58,n67,d67,a67)
            result["comparison"]={
                "same_document":bool(cmp.get("same_document")),
                "confidence":round(float(cmp.get("confidence") or 0),3),
                "reason":str(cmp.get("reason") or "")[:500],
                "material_differences":list(cmp.get("material_differences") or [])[:10],
                "method":cmp.get("method")
            }
        finally:
            conn.close()

        # Classify both correctly regardless of whether they are duplicate.
        conn=db()
        try:
            cols=op._cols(conn,"inbound_documents")
            for iid,analysis in analyses.items():
                sets=[]; vals=[]
                if "document_type" in cols: sets.append("document_type=?"); vals.append("modulo_unico_tesseramento")
                if "document_confidence" in cols: sets.append("document_confidence=?"); vals.append(int(round(float(analysis.get("confidence") or 0)*100)))
                if sets:
                    vals.append(iid); conn.execute("UPDATE inbound_documents SET "+",".join(sets)+" WHERE id=?",tuple(vals))
            conn.commit()
        finally:
            conn.close()

        cmp=result.get("comparison") or {}
        if cmp.get("same_document") and float(cmp.get("confidence") or 0)>=.95:
            # Produce only one copy; preserve the other file/record and take it out of manual-review queue.
            produced,details=op._productionize_inbound(58,type_hint="modulo_unico_tesseramento")
            result["produced"]={"id":58,"ok":bool(produced),"details":details}
            if not produced:
                raise RuntimeError("R55F primary copy production failed "+repr(details))
            conn=db()
            try:
                cols=op._cols(conn,"inbound_documents")
                sets=["status=?"]; vals=["duplicato_confermato"]
                if "note" in cols:
                    sets.append("note=?"); vals.append("R55F: copia semanticamente confermata del Modulo Unico inbound 58; file preservato, nessuna cancellazione")
                vals.append(67)
                conn.execute("UPDATE inbound_documents SET "+",".join(sets)+" WHERE id=?",tuple(vals))
                conn.commit()
            finally:
                conn.close()
            result["duplicate_preserved"]={"id":67,"status":"duplicato_confermato","file_deleted":False}
        else:
            # Distinct forms: both are legitimate Moduli Unici, so produce both through official route.
            outs=[]
            for iid in TARGETS:
                produced,details=op._productionize_inbound(iid,type_hint="modulo_unico_tesseramento")
                outs.append({"id":iid,"ok":bool(produced),"details":details})
                if not produced:
                    raise RuntimeError("R55F distinct MU production failed "+repr(details))
            result["produced"]=outs

    c=sqlite3.connect(str(DB),timeout=20); c.row_factory=sqlite3.Row
    try:
        pending=int(c.execute("SELECT COUNT(*) FROM inbound_documents WHERE lower(coalesce(status,'')) IN ('needs_manual_match','associato_tipo_da_verificare','richiede_conferma','needs_review','da_verificare','pending')").fetchone()[0])
        integrity=str(c.execute("PRAGMA integrity_check").fetchone()[0])
        fk=len(c.execute("PRAGMA foreign_key_check").fetchall())
        rows=[dict(r) for r in c.execute("SELECT id,status,document_type,document_confidence,match_score,tesserato_id FROM inbound_documents WHERE id IN (58,67) ORDER BY id").fetchall()]
    finally:
        c.close()
    result["pending_after"]=pending; result["final_rows"]=rows; result["integrity"]=integrity; result["foreign_keys"]=fk
    result["ok"]=(integrity.lower()=="ok" and fk==0 and all(str(r.get("document_type") or "")=="modulo_unico_tesseramento" for r in rows))
    MARK.write_text(json.dumps(result,ensure_ascii=False),encoding="utf-8")
    print("[operator-r55f-dinicola] "+json.dumps(result,ensure_ascii=False),flush=True)
