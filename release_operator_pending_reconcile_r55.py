# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import json, sqlite3, sys

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MARK=APP/'.BODYMIND_OPERATOR_PENDING_RECONCILE_R55D'

def table(conn,name):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())

def counts(conn):
    out={}
    for t in ('tesserati','documenti','inbound_documents','pagamenti','ricevute'):
        if table(conn,t):
            out[t]=int(conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0])
    return out

if MARK.exists():
    print('[operator-r55-reconcile] already attempted '+MARK.read_text(encoding='utf-8',errors='replace')[:3000],flush=True)
else:
    report={"ok":False,"considered":0,"produced":0,"duplicates":0,"uncertain":0,"errors":[],"items":[]}
    if not DB.exists():
        report["errors"].append("database_missing")
    else:
        sys.path.insert(0,str(APP))
        import app as _full_app  # registers the complete Flask route set
        from flask import session
        from asd_app.core import app, db, current_username
        import asd_app.routes_operator_bodymind as op
        from asd_app.routes_email_documents import extract_attachment_text

        c0=sqlite3.connect(str(DB),timeout=30); c0.row_factory=sqlite3.Row
        try:
            before=counts(c0)
            pending_before=int(c0.execute(
                "SELECT COUNT(*) FROM inbound_documents WHERE lower(coalesce(status,'')) IN (?,?,?,?,?,?)",
                tuple(op.PENDING_STATUSES)
            ).fetchone()[0]) if table(c0,'inbound_documents') else 0
        finally:
            c0.close()
        report["counts_before"]=before
        report["pending_before"]=pending_before

        try:
            backup_path=op._operator_db_backup("r55_pending_reconcile")
            report["backup"]=backup_path
            with app.test_request_context('/operatore-bodymind'):
                session.update({
                    'logged':True,'username':'admin','display_name':'BodyMind R55',
                    'role':'admin','tenant_slug':'default','_csrf_token':'r55-reconcile',
                    'bodymind_operator_conversation':'r55-reconcile',
                    'bodymind_operator_identity':'BodyMind R55'
                })
                conn=db()
                try:
                    ic=op._cols(conn,'inbound_documents')
                    where=["lower(coalesce(status,'')) IN ("+','.join('?' for _ in op.PENDING_STATUSES)+")"]
                    params=list(op.PENDING_STATUSES)
                    # R55B: process the whole pending queue. Historical uploads do not
                    # consistently preserve the source marker, so source cannot be a trust boundary.
                    # Safety comes from semantic type/person confidence gates below, not metadata origin.
                    if 'deleted_at' in ic:
                        where.append("coalesce(deleted_at,'')=''")
                    rows=conn.execute(
                        "SELECT * FROM inbound_documents WHERE "+" AND ".join(where)+" ORDER BY id DESC LIMIT 80",
                        params
                    ).fetchall()
                finally:
                    conn.close()

                for row0 in reversed(rows):
                    report["considered"]+=1
                    iid=int(row0["id"])
                    item={"inbound_id":iid,"produced":False}
                    try:
                        conn=db()
                        try:
                            row=conn.execute("SELECT * FROM inbound_documents WHERE id=?",(iid,)).fetchone()
                            stored=""
                            for k in ("saved_path","path","filename"):
                                if k in row.keys() and str(row[k] or "").strip():
                                    stored=str(row[k] or "").strip(); break
                            name=""
                            for k in ("original_filename","filename"):
                                if k in row.keys() and str(row[k] or "").strip():
                                    name=Path(str(row[k] or "")).name; break
                            data=b""
                            for p in op._document_file_candidates(stored):
                                try:
                                    if p.is_file():
                                        data=p.read_bytes()
                                        if len(data)<=40*1024*1024:
                                            if not name: name=p.name
                                            break
                                        data=b""
                                except Exception:
                                    continue
                            if not data:
                                raise RuntimeError("file_not_readable")
                            try:
                                extracted=str(extract_attachment_text(name,data) or "")
                            except Exception:
                                extracted=""
                            semantic=op._semantic_for_new_bytes(conn,name,data,extracted,"")
                            op._docsem_cache_put(conn,"inbound_documents",iid,semantic)
                            athlete,match_score,match_reason=op._semantic_match_athlete(conn,semantic)
                            sem_conf=float(semantic.get("confidence") or 0)
                            dtype=str(semantic.get("document_type") or "")
                            item.update({
                                "type":dtype,"semantic_confidence":round(sem_conf,3),
                                "match_score":round(float(match_score or 0),3),
                                "match_reason":match_reason,
                                "tesserato_id":int(athlete["id"]) if athlete else None
                            })
                            if not athlete or float(match_score or 0)<.98 or sem_conf<.95 or dtype in ("","altro"):
                                report["uncertain"]+=1
                                item["reason"]="confidence_gate"
                                report["items"].append(item)
                                continue
                            duplicate=op._same_existing_document(conn,int(athlete["id"]),name,data,semantic,exclude_inbound_id=iid)
                            if duplicate.get("duplicate"):
                                report["duplicates"]+=1
                                item.update({
                                    "reason":"duplicate_confirmed_review_only",
                                    "existing_document_id":duplicate.get("existing_id"),
                                    "duplicate_confidence":duplicate.get("confidence"),
                                    "comparison_method":duplicate.get("method")
                                })
                                report["items"].append(item)
                                continue
                            sets=[]; vals=[]
                            for col in ("tesserato_id","matched_tesserato_id","suggested_tesserato_id"):
                                if col in ic:
                                    sets.append(col+"=?"); vals.append(int(athlete["id"]))
                            if "match_score" in ic:
                                sets.append("match_score=?"); vals.append(int(round(float(match_score)*100)))
                            if "document_type" in ic:
                                sets.append("document_type=?"); vals.append(dtype)
                            if "document_confidence" in ic:
                                sets.append("document_confidence=?"); vals.append(int(round(sem_conf*100)))
                            if sets:
                                vals.append(iid)
                                conn.execute("UPDATE inbound_documents SET "+",".join(sets)+" WHERE id=?",tuple(vals))
                                conn.commit()
                        finally:
                            conn.close()

                        produced,details=op._productionize_inbound(iid,type_hint=dtype)
                        item["produced"]=bool(produced)
                        item["production"]=details
                        if produced:
                            report["produced"]+=1
                        else:
                            report["uncertain"]+=1
                            item["reason"]=str(details.get("reason") or "production_gate")
                        report["items"].append(item)
                        print("[operator-r55-reconcile-progress] "+json.dumps({
                            "inbound_id":iid,
                            "type":item.get("type"),
                            "tesserato_id":item.get("tesserato_id"),
                            "produced":item.get("produced"),
                            "reason":item.get("reason",""),
                            "done":len(report["items"]),
                            "produced_total":report["produced"],
                            "duplicates_total":report["duplicates"],
                            "uncertain_total":report["uncertain"]
                        },ensure_ascii=False),flush=True)
                    except Exception as exc:
                        report["errors"].append({"inbound_id":iid,"error":repr(exc)[:240]})
                        item["reason"]="error"
                        report["items"].append(item)
        except Exception as exc:
            report["errors"].append({"fatal":repr(exc)[:500]})

        c1=sqlite3.connect(str(DB),timeout=30); c1.row_factory=sqlite3.Row
        try:
            after=counts(c1)
            pending_after=int(c1.execute(
                "SELECT COUNT(*) FROM inbound_documents WHERE lower(coalesce(status,'')) IN (?,?,?,?,?,?)",
                tuple(op.PENDING_STATUSES)
            ).fetchone()[0]) if table(c1,'inbound_documents') else 0
            integrity=str(c1.execute('PRAGMA integrity_check').fetchone()[0])
            fk=len(c1.execute('PRAGMA foreign_key_check').fetchall())
        finally:
            c1.close()
        report["counts_after"]=after
        report["pending_after"]=pending_after
        report["db_integrity"]=integrity
        report["foreign_keys"]=fk
        no_loss=(
            after.get("tesserati",0)==before.get("tesserati",0)
            and after.get("inbound_documents",0)==before.get("inbound_documents",0)
            and after.get("documenti",0)>=before.get("documenti",0)
        )
        report["no_business_loss"]=no_loss
        report["ok"]=(integrity.lower()=="ok" and fk==0 and no_loss and not any("fatal" in x for x in report["errors"] if isinstance(x,dict)))

    MARK.write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')
    print('[operator-r55-reconcile] '+json.dumps(report,ensure_ascii=False),flush=True)
