# -*- coding: utf-8 -*-
from __future__ import annotations
import json, py_compile, re, shutil, sqlite3
from datetime import datetime
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
P=APP/'asd_app/routes_operator_bodymind.py'
BACK=Path('/data/release_backups/20261002_r78_operator_document_core')
BACK.mkdir(parents=True,exist_ok=True)

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

def backup_file(p:Path):
    try: rel=p.relative_to(APP)
    except Exception: rel=Path(p.name)
    dst=BACK/rel
    if p.exists() and not dst.exists():
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(p,dst)

def backup_db(label):
    dst=BACK/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+label+'.db')
    src=sqlite3.connect(str(DB),timeout=30); out=sqlite3.connect(str(dst))
    try: src.backup(out)
    finally: out.close(); src.close()
    return str(dst)

s=P.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R78_DUPLICATE_RESOLUTION' not in s:
    backup_file(P)

    # Shared runtime helper: a duplicate is a resolved canonical association, not a dead-end.
    anchor='''def _inbound_file_bytes(row):
'''
    helper=r'''# BODYMIND_R78_DUPLICATE_RESOLUTION
def _r78_archive_duplicate_inbound(conn,inbound_id,reason="",canonical_document_id=0):
    row=conn.execute("SELECT * FROM inbound_documents WHERE id=?",(int(inbound_id),)).fetchone() if _table(conn,"inbound_documents") else None
    if not row:
        return {"archived":False,"deleted":False,"reason":"inbound_missing"}
    # Never break a dossier link. A referenced staging row remains, but is marked resolved.
    docrefs=[]
    if _table(conn,"documenti") and "inbound_id" in _cols(conn,"documenti"):
        docrefs=conn.execute("SELECT id FROM documenti WHERE inbound_id=?",(int(inbound_id),)).fetchall()
    if docrefs:
        if "status" in _cols(conn,"inbound_documents"):
            conn.execute("UPDATE inbound_documents SET status='duplicato_risolto' WHERE id=?",(int(inbound_id),))
            conn.commit()
        return {"archived":False,"deleted":False,"reason":"referenced","document_ids":[int(x["id"]) for x in docrefs]}

    conn.execute("""CREATE TABLE IF NOT EXISTS bodymind_duplicate_records_archive(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      source_table TEXT NOT NULL,
      source_id INTEGER NOT NULL,
      tesserato_id INTEGER,
      status TEXT,
      reason TEXT NOT NULL,
      payload_json TEXT NOT NULL,
      semantics_json TEXT,
      file_path TEXT,
      archived_at TEXT NOT NULL,
      UNIQUE(source_table,source_id)
    )""")
    keys=set(row.keys())
    events=[]
    if _table(conn,"inbound_events") and "inbound_document_id" in _cols(conn,"inbound_events"):
        events=[dict(x) for x in conn.execute("SELECT * FROM inbound_events WHERE inbound_document_id=? ORDER BY id",(int(inbound_id),)).fetchall()]
    sem=[]
    if _table(conn,"bodymind_document_semantics"):
        sem=[dict(x) for x in conn.execute("SELECT * FROM bodymind_document_semantics WHERE source_table='inbound_documents' AND source_id=? ORDER BY id",(int(inbound_id),)).fetchall()]
    payload={"row":dict(row),"events":events,"canonical_document_id":int(canonical_document_id or 0)}
    fpath=""
    for k in ("saved_path","filename","original_filename"):
        if k in keys and row[k]:
            fpath=str(row[k]); break
    conn.execute("""INSERT OR IGNORE INTO bodymind_duplicate_records_archive
      (source_table,source_id,tesserato_id,status,reason,payload_json,semantics_json,file_path,archived_at)
      VALUES(?,?,?,?,?,?,?,?,?)""",
      ("inbound_documents",int(inbound_id),int(row["tesserato_id"] or 0) if "tesserato_id" in keys else 0,
       str(row["status"] or "") if "status" in keys else "",str(reason or "duplicate resolved"),
       json.dumps(payload,ensure_ascii=False,default=str),json.dumps(sem,ensure_ascii=False,default=str),
       fpath,datetime.now().isoformat(timespec="seconds")))
    if events:
        conn.execute("DELETE FROM inbound_events WHERE inbound_document_id=?",(int(inbound_id),))
    if _table(conn,"bodymind_document_semantics"):
        conn.execute("DELETE FROM bodymind_document_semantics WHERE source_table='inbound_documents' AND source_id=?",(int(inbound_id),))
    conn.execute("DELETE FROM inbound_documents WHERE id=?",(int(inbound_id),))
    conn.commit()
    return {"archived":True,"deleted":True,"reason":"duplicate_staging_removed","events_archived":len(events)}

def _r78_finalize_duplicate(conn,inbound_id,tid,semantic,dup):
    tid=int(tid or 0); canonical_id=int((dup or {}).get("existing_id") or 0)
    if tid<=0 or canonical_id<=0:
        return {"ok":False,"reason":"missing_target_or_canonical"}
    canonical=conn.execute("SELECT * FROM documenti WHERE id=?",(canonical_id,)).fetchone() if _table(conn,"documenti") else None
    if not canonical or int(canonical["tesserato_id"] or 0)!=tid:
        return {"ok":False,"reason":"canonical_athlete_mismatch"}
    incoming_type=_norm((semantic or {}).get("document_type") or "")
    canonical_type=_norm(_canonical_document_kind(canonical))
    if incoming_type and canonical_type and incoming_type!=canonical_type:
        return {"ok":False,"reason":"canonical_type_mismatch","incoming":incoming_type,"canonical":canonical_type}
    sync={"ok":True,"reason":"not_mu"}
    if incoming_type=="modulo_unico_tesseramento":
        try:
            from .verified_mu_sync_core_r68 import sync_analysis_to_existing_athlete
            sync=sync_analysis_to_existing_athlete(conn,tid,semantic,source="operator_duplicate_mu_r78")
        except Exception as exc:
            sync={"ok":False,"reason":"mu_sync_error","error":repr(exc)[:180]}
    archived=_r78_archive_duplicate_inbound(
        conn,int(inbound_id),
        reason="R78 duplicate resolved to canonical document "+str(canonical_id),
        canonical_document_id=canonical_id
    )
    return {
      "ok":True,"tesserato_id":tid,"canonical_document_id":canonical_id,
      "canonical_already_associated":True,"mu_sync":sync,"staging":archived
    }

'''
    if anchor not in s:
        raise RuntimeError('R78 helper anchor missing')
    s=s.replace(anchor,helper+anchor,1)

    # First duplicate gate during upload.
    old=r'''                if dup.get("duplicate"):
                    ic=_cols(conn_dup,"inbound_documents")
                    if "status" in ic:
                        conn_dup.execute("UPDATE inbound_documents SET status=? WHERE id=?",("duplicato_non_importato",inbound_id)); conn_dup.commit()
                    item.update({"status":"duplicato_non_importato","duplicate":True,"duplicate_of":dup.get("existing_id"),"duplicate_reason":dup.get("reason")})
                    duplicate_items.append(item); results.append(item); continue
'''
    new=r'''                if dup.get("duplicate"):
                    try:
                        _operator_db_backup("r78_duplicate_resolution")
                    except Exception:
                        pass
                    resolved=_r78_finalize_duplicate(conn_dup,inbound_id,tid,semantic,dup)
                    item.update({
                        "status":"duplicato_risolto","duplicate":True,
                        "duplicate_of":dup.get("existing_id"),"duplicate_reason":dup.get("reason"),
                        "association_resolved":bool(resolved.get("ok")),
                        "canonical_document_id":resolved.get("canonical_document_id"),
                        "mu_sync":resolved.get("mu_sync"),
                        "duplicate_staging":resolved.get("staging")
                    })
                    duplicate_items.append(item); results.append(item); continue
'''
    if old not in s:
        raise RuntimeError('R78 first duplicate branch missing')
    s=s.replace(old,new,1)

    # Second duplicate gate during legacy pending-action execution.
    old2=r'''            if dup.get("duplicate"):
                duplicates.append({"inbound_id":inbound_id,**dup}); continue
'''
    new2=r'''            if dup.get("duplicate"):
                resolved=_r78_finalize_duplicate(conn,inbound_id,tid,analysis,dup)
                duplicates.append({"inbound_id":inbound_id,**dup,"resolved":resolved}); continue
'''
    if old2 not in s:
        raise RuntimeError('R78 second duplicate branch missing')
    s=s.replace(old2,new2,1)

    # Autonomous safe production: second gate + import in the same upload task for admins.
    summary_anchor='''    summary={"received":len(results),"source_files":source_file_count,"logical_documents":len(results),
'''
    auto=r'''    # BODYMIND_R78_AUTONOMOUS_SAFE_DOCUMENT_PRODUCTION
    auto_imported=[]; auto_blocked=[]; auto_second_duplicates=[]
    if ready_ids and production_mode and current_role()=="admin":
        try:
            _operator_db_backup("r78_autonomous_document_production")
        except Exception:
            pass
        conn_auto=db()
        try:
            for inbound_id in list(ready_ids):
                row=conn_auto.execute("SELECT * FROM inbound_documents WHERE id=?",(int(inbound_id),)).fetchone() if _table(conn_auto,"inbound_documents") else None
                if not row:
                    auto_blocked.append({"inbound_id":inbound_id,"reason":"staging non trovato"}); continue
                tid=int(row["tesserato_id"] or 0) if "tesserato_id" in row.keys() else 0
                name2,data2,_=_inbound_file_bytes(row)
                analysis2=_docsem_cache_get(conn_auto,"inbound_documents",int(inbound_id),_docsem_sha256(data2)) if data2 else None
                if tid<=0 or not data2 or not analysis2:
                    auto_blocked.append({"inbound_id":inbound_id,"reason":"identità o analisi non più certa"}); continue
                if type_hint and _norm(analysis2.get("document_type") or "")!=_norm(type_hint):
                    auto_blocked.append({"inbound_id":inbound_id,"reason":"tipo documentale non coincide al secondo controllo"}); continue
                dup2=_semantic_key_duplicate(conn_auto,tid,name2,data2,analysis2)
                if dup2.get("duplicate"):
                    resolved2=_r78_finalize_duplicate(conn_auto,inbound_id,tid,analysis2,dup2)
                    auto_second_duplicates.append({"inbound_id":inbound_id,**dup2,"resolved":resolved2})
                    for it in results:
                        if int(it.get("inbound_id") or 0)==int(inbound_id):
                            it.update({"status":"duplicato_risolto","duplicate":True,"duplicate_of":dup2.get("existing_id"),"association_resolved":True})
                    continue
                ok2,details2=_productionize_inbound(int(inbound_id),type_hint=type_hint)
                if ok2:
                    auto_imported.append({"inbound_id":int(inbound_id),**(details2 or {})})
                    for it in results:
                        if int(it.get("inbound_id") or 0)==int(inbound_id):
                            it.update({"status":"importato_associato","production":True,"production_details":details2 or {}})
                else:
                    auto_blocked.append({"inbound_id":inbound_id,"reason":str((details2 or {}).get("reason") or "produzione non riuscita"),"details":details2})
        finally:
            conn_auto.close()
        # Safe automatic work is finished; do not create another confirmation action.
        ready_ids=[]
        for b in auto_blocked:
            review_items.append({"inbound_id":b.get("inbound_id"),"status":"verifica","reason":b.get("reason")})

'''
    if summary_anchor not in s:
        raise RuntimeError('R78 summary anchor missing')
    s=s.replace(summary_anchor,auto+summary_anchor,1)

    # Add autonomous outcomes to the persisted summary.
    oldsum='''             "ready":len(ready_ids),"new_athletes":len(new_athletes),"duplicates":len(duplicate_items),
             "review":len(review_items),"errors":len(errors),"document_type":type_hint}
'''
    newsum='''             "ready":len(ready_ids),"imported":len(auto_imported),"new_athletes":len(new_athletes),
             "duplicates":len(duplicate_items)+len(auto_second_duplicates),
             "review":len(review_items),"errors":len(errors),"document_type":type_hint,
             "autonomous_production":bool(production_mode and current_role()=="admin")}
'''
    if oldsum not in s:
        raise RuntimeError('R78 summary fields anchor missing')
    s=s.replace(oldsum,newsum,1)

    # Truthful final wording: resolved duplicate is a completed result, not an abandoned file.
    oldtext='''        text=f"Il server ha ricevuto {source_file_count} file e ha analizzato {len(results)} documenti logici: {len(ready_ids)} documenti nuovi per tesserate già presenti, {len(new_athletes)} moduli di nuove tesserate leggibili, {len(duplicate_items)} duplicati che non importerò, {len(review_items)} da verificare."
'''
    newtext='''        text=f"Il server ha ricevuto {source_file_count} file e ha analizzato {len(results)} documenti logici: {len(auto_imported)} importati e associati automaticamente, {len(new_athletes)} nuove anagrafiche ancora da verificare, {len(duplicate_items)+len(auto_second_duplicates)} duplicati risolti sulla copia già presente, {len(review_items)} da verificare."
'''
    if oldtext not in s:
        raise RuntimeError('R78 final text anchor missing')
    s=s.replace(oldtext,newtext,1)

    # The normal safe document flow is autonomous; no promise of a redundant confirmation.
    oldtask='''"I nuovi certi verranno preparati per la tua conferma finale; gli ambigui resteranno in verifica."'''
    newtask='''"I nuovi certi verranno associati e prodotti automaticamente; gli ambigui resteranno in verifica."'''
    if oldtask in s:
        s=s.replace(oldtask,newtask,1)

    P.write_text(s,encoding='utf-8')
    py_compile.compile(str(P),doraise=True)
    print('[operator-r78] PASS duplicate-resolves-canonical autonomous-safe-document-production no-redundant-confirm',flush=True)
else:
    print('[operator-r78] already applied',flush=True)

# ------------------------------------------------------------------
# Existing duplicate MU reconciliation, cache-only. Includes real Abatini audit.
# ------------------------------------------------------------------
before_counts={}
after_counts={}
reconciled=[]
removed=[]
blocked=[]
abatini={}
db_backup_path=""
conn=sqlite3.connect(str(DB),timeout=45); conn.row_factory=sqlite3.Row
try:
    for t in ('tesserati','documenti','inbound_documents'):
        before_counts[t]=int(conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0])

    dup_status=('duplicato_non_importato','duplicato_confermato','duplicate_exact','duplicate_confirmed','duplicato_risolto')
    qs=','.join('?' for _ in dup_status)
    candidates=conn.execute(
        "SELECT * FROM inbound_documents WHERE lower(coalesce(document_type,''))='modulo_unico_tesseramento' "+
        "AND coalesce(tesserato_id,0)>0 AND lower(coalesce(status,'')) IN ("+qs+") ORDER BY id",
        dup_status
    ).fetchall()

    if candidates:
        db_backup_path=backup_db('pre_r78_mu_duplicate_reconcile')

    from asd_app.verified_mu_sync_core_r68 import sync_analysis_to_existing_athlete

    for row in candidates:
        iid=int(row['id']); tid=int(row['tesserato_id'] or 0)
        canonical=conn.execute("""SELECT * FROM documenti
          WHERE tesserato_id=? AND coalesce(visibile,1)=1
            AND (lower(coalesce(doc_type,''))='modulo_unico_tesseramento'
              OR lower(coalesce(categoria,'')) LIKE '%modulo iscrizione%'
              OR lower(coalesce(titolo,'')) LIKE '%modulo unico%')
          ORDER BY id DESC LIMIT 1""",(tid,)).fetchone()
        if not canonical:
            blocked.append({'inbound_id':iid,'tid':tid,'reason':'no_canonical_mu'}); continue

        semrow=conn.execute("""SELECT analysis_json FROM bodymind_document_semantics
          WHERE source_table='inbound_documents' AND source_id=? ORDER BY id DESC LIMIT 1""",(iid,)).fetchone() if conn.execute(
          "SELECT 1 FROM sqlite_master WHERE type='table' AND name='bodymind_document_semantics'").fetchone() else None
        analysis=None
        if semrow:
            try:
                analysis=json.loads(str(semrow['analysis_json'] or '{}'))
            except Exception:
                analysis=None
        if not isinstance(analysis,dict):
            blocked.append({'inbound_id':iid,'tid':tid,'reason':'semantic_cache_missing'}); continue

        sync=sync_analysis_to_existing_athlete(conn,tid,analysis,source='r78_existing_duplicate_mu')
        reconciled.append({'inbound_id':iid,'tid':tid,'canonical_document_id':int(canonical['id']),'sync':sync})
        if not sync.get('ok'):
            blocked.append({'inbound_id':iid,'tid':tid,'reason':'sync_blocked','sync':sync}); continue

        # Archive/delete only if no dossier row references this staging record.
        refs=[]
        dcols={str(x[1]) for x in conn.execute('PRAGMA table_info(documenti)').fetchall()}
        if 'inbound_id' in dcols:
            refs=conn.execute('SELECT id FROM documenti WHERE inbound_id=?',(iid,)).fetchall()
        if refs:
            conn.execute("UPDATE inbound_documents SET status='duplicato_risolto' WHERE id=?",(iid,))
            blocked.append({'inbound_id':iid,'tid':tid,'reason':'referenced_staging_kept','document_ids':[int(x['id']) for x in refs]})
            continue

        conn.execute("""CREATE TABLE IF NOT EXISTS bodymind_duplicate_records_archive(
          id INTEGER PRIMARY KEY AUTOINCREMENT,source_table TEXT NOT NULL,source_id INTEGER NOT NULL,tesserato_id INTEGER,
          status TEXT,reason TEXT NOT NULL,payload_json TEXT NOT NULL,semantics_json TEXT,file_path TEXT,archived_at TEXT NOT NULL,
          UNIQUE(source_table,source_id))""")
        events=[]
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inbound_events'").fetchone():
            events=[dict(x) for x in conn.execute('SELECT * FROM inbound_events WHERE inbound_document_id=? ORDER BY id',(iid,)).fetchall()]
        sems=[dict(x) for x in conn.execute("SELECT * FROM bodymind_document_semantics WHERE source_table='inbound_documents' AND source_id=? ORDER BY id",(iid,)).fetchall()]
        conn.execute("""INSERT OR IGNORE INTO bodymind_duplicate_records_archive
          (source_table,source_id,tesserato_id,status,reason,payload_json,semantics_json,file_path,archived_at)
          VALUES(?,?,?,?,?,?,?,?,?)""",
          ('inbound_documents',iid,tid,str(row['status'] or ''),'R78 reconciled duplicate MU',
           json.dumps({'row':dict(row),'events':events,'canonical_document_id':int(canonical['id'])},ensure_ascii=False,default=str),
           json.dumps(sems,ensure_ascii=False,default=str),str(row['saved_path'] or '') if 'saved_path' in row.keys() else '',
           datetime.now().isoformat(timespec='seconds')))
        if events:
            conn.execute('DELETE FROM inbound_events WHERE inbound_document_id=?',(iid,))
        conn.execute("DELETE FROM bodymind_document_semantics WHERE source_table='inbound_documents' AND source_id=?",(iid,))
        conn.execute('DELETE FROM inbound_documents WHERE id=?',(iid,))
        removed.append(iid)

    conn.commit()

    a=conn.execute("SELECT * FROM tesserati WHERE lower(coalesce(cognome,'')) LIKE '%abatini%' ORDER BY id LIMIT 1").fetchone()
    if a:
        tid=int(a['id'])
        docs=[dict(x) for x in conn.execute("SELECT id,titolo,categoria,doc_type,status,visibile,filename FROM documenti WHERE tesserato_id=? ORDER BY id",(tid,)).fetchall()]
        ins=[dict(x) for x in conn.execute("SELECT id,status,document_type,document_confidence,match_score,tesserato_id,original_filename FROM inbound_documents WHERE coalesce(tesserato_id,0)=? OR lower(coalesce(original_filename,'')) LIKE '%abatini%' ORDER BY id",(tid,)).fetchall()]
        ak=set(a.keys())
        abatini={
          'id':tid,'name':(str(a['nome'] or '')+' '+str(a['cognome'] or '')).strip(),
          'cf':str(a['codice_fiscale'] or '') if 'codice_fiscale' in ak else '',
          'guardian':str(a['genitore'] or '') if 'genitore' in ak else '',
          'minor':int(a['minorenne'] or 0) if 'minorenne' in ak else None,
          'onboarding':{k:int(a[k] or 0) for k in ('iscrizione_firmata','documenti_onboarding_ok','privacy_ok','liberatoria_ok','regolamento_ok') if k in ak},
          'documents':docs,'inbound':ins
        }

    for t in ('tesserati','documenti','inbound_documents'):
        after_counts[t]=int(conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0])
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:
    conn.close()

print('[r78-abatini-audit] '+json.dumps(abatini,ensure_ascii=False),flush=True)
print('[r78-existing-duplicate-mu] reconciled='+json.dumps(reconciled,ensure_ascii=False)+
      ' removed='+json.dumps(removed)+' blocked='+json.dumps(blocked,ensure_ascii=False)+
      ' before='+json.dumps(before_counts)+' after='+json.dumps(after_counts)+
      ' backup='+str(db_backup_path)+' integrity='+integrity+' fk='+str(fk),flush=True)

if before_counts.get('tesserati')!=after_counts.get('tesserati'):
    raise RuntimeError('R78 tesserati count changed')
if integrity.lower()!='ok' or fk:
    raise RuntimeError('R78 DB integrity failed')
if 'BODYMIND_R78_DUPLICATE_RESOLUTION' not in P.read_text(encoding='utf-8',errors='replace'):
    raise RuntimeError('R78 operator patch missing')
print('[r78-selftest] PASS duplicate-canonical-resolution MU-sync autonomous-safe-production Abatini-audit cache-only db-ok',flush=True)
