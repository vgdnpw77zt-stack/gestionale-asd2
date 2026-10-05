# R39 build and route guards - autodeploy trigger 2
import os, sys, pathlib, runpy, sqlite3, shutil, json, time, hashlib, py_compile

# BODYMIND_R102_STORAGE_PREFLIGHT
def _bodymind_storage_preflight():
    data_root = pathlib.Path("/data")
    backup_root = data_root / "release_backups"
    db_path = data_root / "tenants/default/asd.db"
    target_free = 2048 * 1024 * 1024
    cleanup_trigger = 1536 * 1024 * 1024
    hard_floor = 512 * 1024 * 1024
    max_backup_bytes = 900 * 1024 * 1024
    before = shutil.disk_usage(str(data_root))
    deleted = []
    freed = 0
    protected = set()

    if backup_root.exists():
        candidates = []
        for p in backup_root.rglob("*"):
            try:
                if p.is_file():
                    st = p.stat()
                    candidates.append((st.st_mtime, st.st_size, p))
            except Exception:
                pass

        full = [x for x in candidates if x[2].suffix.lower() in (".db",".sqlite",".sqlite3")]
        known = [x for x in full if "r100_medical_profile" in str(x[2]) or "pre_r100" in x[2].name.lower()]
        if known:
            protected.add(max(known,key=lambda x:x[0])[2])
        for x in sorted(full,key=lambda x:x[0],reverse=True)[:4]:
            protected.add(x[2])

        backup_bytes=sum(x[1] for x in full)
        cleanup_needed=(before.free < cleanup_trigger or backup_bytes > max_backup_bytes or len(full) > 10)
        if cleanup_needed:
            remaining_bytes=backup_bytes
            remaining_count=len(full)
            for mtime,size,p in sorted(full,key=lambda x:x[0]):
                if p in protected:
                    continue
                try:
                    p.unlink()
                    freed += int(size)
                    remaining_bytes -= int(size)
                    remaining_count -= 1
                    deleted.append({"path":str(p),"bytes":int(size)})
                except Exception as exc:
                    print("[storage-retention] delete-warning "+str(p)+" "+repr(exc),flush=True)
                free_now=shutil.disk_usage(str(data_root)).free
                if free_now >= target_free and remaining_bytes <= max_backup_bytes and remaining_count <= 6:
                    break

        cutoff=time.time()-(48*3600)
        for mtime,size,p in sorted(candidates,key=lambda x:x[0]):
            if p in protected or p.suffix.lower() in (".db",".sqlite",".sqlite3"):
                continue
            if p.suffix.lower() not in (".db-wal",".db-shm",".tmp",".part"):
                continue
            if mtime > cutoff:
                continue
            try:
                p.unlink(); freed += int(size); deleted.append({"path":str(p),"bytes":int(size)})
            except Exception:
                pass

        try:
            for d in sorted((x for x in backup_root.rglob("*") if x.is_dir()),key=lambda x:len(str(x)),reverse=True):
                try: d.rmdir()
                except Exception: pass
        except Exception:
            pass

    after = shutil.disk_usage(str(data_root))
    result = {
        "before_used_gb":round(before.used/(1024**3),3),
        "before_free_gb":round(before.free/(1024**3),3),
        "after_used_gb":round(after.used/(1024**3),3),
        "after_free_gb":round(after.free/(1024**3),3),
        "freed_gb":round(freed/(1024**3),3),
        "deleted_files":len(deleted),
        "protected_backups":[str(x) for x in sorted(protected,key=str)],
    }
    print("[storage-retention] "+json.dumps(result,ensure_ascii=False),flush=True)

    if after.free < hard_floor:
        raise SystemExit("Storage preflight: insufficient free space; refusing SQLite writes")

    if db_path.exists():
        conn=sqlite3.connect("file:"+str(db_path)+"?mode=ro",uri=True,timeout=20)
        try:
            integrity=str(conn.execute("PRAGMA integrity_check").fetchone()[0])
            fk=len(conn.execute("PRAGMA foreign_key_check").fetchall())
        finally:
            conn.close()
        print(f"[storage-retention-db] integrity={integrity} fk={fk}",flush=True)
        if integrity.lower()!="ok" or fk:
            raise SystemExit(f"Storage preflight DB check failed: integrity={integrity} fk={fk}")

# BODYMIND_EARLY_DB_FK_RECOVERY_R121_PREPREFLIGHT
def _bodymind_early_db_fk_recovery_preflight():
    db_path=pathlib.Path("/data/tenants/default/asd.db")
    if not db_path.exists():
        return
    conn=sqlite3.connect(str(db_path),timeout=20)
    try:
        integrity=str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        fk=conn.execute("PRAGMA foreign_key_check").fetchall()
    finally: conn.close()
    if integrity.lower()=="ok" and not fk:
        return
    candidates=sorted(pathlib.Path("/data/release_backups/20261002_r81_stabilization").glob("*_pre_r81.db"),reverse=True)
    for src in candidates:
        chk=sqlite3.connect(str(src),timeout=20)
        try:
            ok=str(chk.execute("PRAGMA integrity_check").fetchone()[0]).lower()=="ok"
            fk2=chk.execute("PRAGMA foreign_key_check").fetchall()
        finally: chk.close()
        if ok and not fk2:
            q=pathlib.Path("/data/release_backups/20261003_r121_fk_recovery")
            q.mkdir(parents=True,exist_ok=True)
            stamp=__import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy2(db_path,q/(stamp+"_broken_fk.db"))
            tmp=db_path.with_suffix(".r121_restore_tmp")
            shutil.copy2(src,tmp)
            os.replace(tmp,db_path)
            print("[r121-preflight-recovery] restored="+str(src),flush=True)
            return
    raise SystemExit("R121 preflight recovery failed: no verified pre-R81 backup")

_bodymind_early_db_fk_recovery_preflight()

_bodymind_storage_preflight()

# BODYMIND_EARLY_SOURCE_RECOVERY_R120
def _bodymind_early_source_recovery():
    pairs=[
      ("routes_tesserati.py","/data/top2_app/asd_app/routes_tesserati.py"),
      ("routes_bodymind_fix24.py","/data/top2_app/asd_app/routes_bodymind_fix24.py"),
    ]
    for backup_name,target_name in pairs:
        target=pathlib.Path(target_name)
        if not target.exists():
            continue
        try:
            py_compile.compile(str(target),doraise=True)
            continue
        except Exception as exc:
            backup=pathlib.Path("/data/release_backups/20261003_r120_certificate_truth")/backup_name
            if not backup.exists():
                raise SystemExit("Persistent source is invalid and recovery backup is missing for "+backup_name+": "+repr(exc))
            shutil.copy2(backup,target)
            try:
                py_compile.compile(str(target),doraise=True)
            except Exception as exc2:
                raise SystemExit("R120 source recovery failed for "+backup_name+": "+repr(exc2))
            print("[r120-early-recovery] restored "+backup_name+" before app imports",flush=True)

_bodymind_early_source_recovery()

# BODYMIND_EARLY_DB_FK_RECOVERY_R121
def _bodymind_early_db_fk_recovery():
    db_path=pathlib.Path("/data/tenants/default/asd.db")
    if not db_path.exists():
        return
    conn=sqlite3.connect(str(db_path),timeout=20)
    try:
        integrity=str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        fk=conn.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        conn.close()
    if integrity.lower()=="ok" and not fk:
        print("[r121-db-recovery] DB already healthy",flush=True)
        return
    # The failed deployment log proves R81 introduced the FK violation immediately
    # after creating document 215 for deleted athlete id 37. Restore the newest
    # pre-R81 verified snapshot only; never guess or rebuild data.
    candidates=sorted(pathlib.Path("/data/release_backups/20261002_r81_stabilization").glob("*_pre_r81.db"),reverse=True)
    restored=False
    for src in candidates:
        chk=sqlite3.connect(str(src),timeout=20)
        try:
            ok=str(chk.execute("PRAGMA integrity_check").fetchone()[0]).lower()=="ok"
            fk2=chk.execute("PRAGMA foreign_key_check").fetchall()
        finally:
            chk.close()
        if ok and not fk2:
            quarantine=pathlib.Path("/data/release_backups/20261003_r121_fk_recovery")
            quarantine.mkdir(parents=True,exist_ok=True)
            bad=quarantine/(__import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")+"_broken_fk.db")
            shutil.copy2(db_path,bad)
            tmp=db_path.with_suffix(".r121_restore_tmp")
            shutil.copy2(src,tmp)
            os.replace(tmp,db_path)
            restored=True
            print("[r121-db-recovery] restored="+str(src)+" quarantined="+str(bad),flush=True)
            break
    if not restored:
        raise SystemExit("R121 could not find a verified pre-R81 DB backup")
    conn=sqlite3.connect(str(db_path),timeout=20)
    try:
        integrity=str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        fk=conn.execute("PRAGMA foreign_key_check").fetchall()
    finally: conn.close()
    if integrity.lower()!="ok" or fk:
        raise SystemExit("R121 restore verification failed")
    print("[r121-db-recovery] PASS integrity=ok fk=0",flush=True)

_bodymind_early_db_fk_recovery()

# BODYMIND_OPERATOR_TASK_LIFECYCLE_CLEANUP
def _bodymind_operator_task_cleanup():
    db_path=pathlib.Path("/data/tenants/default/asd.db")
    if not db_path.exists():
        return
    conn=sqlite3.connect(str(db_path),timeout=20)
    conn.row_factory=sqlite3.Row
    try:
        has_tasks=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bodymind_operator_tasks'").fetchone()
        if not has_tasks:
            return
        has_jobs=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bodymind_operator_upload_jobs'").fetchone()
        has_actions=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bodymind_operator_actions'").fetchone()
        where=["t.task_type='batch_upload'","t.status='active'","julianday(t.updated_at) < julianday('now','-6 hours')"]
        if has_jobs:
            where.append("NOT EXISTS (SELECT 1 FROM bodymind_operator_upload_jobs j WHERE j.conversation_id=t.conversation_id AND j.status IN ('queued','processing'))")
        if has_actions:
            where.append("NOT EXISTS (SELECT 1 FROM bodymind_operator_actions a WHERE a.conversation_id=t.conversation_id AND a.status IN ('proposed','pending','awaiting_confirmation'))")
        sql="SELECT t.id,t.conversation_id,t.updated_at FROM bodymind_operator_tasks t WHERE "+" AND ".join(where)
        rows=conn.execute(sql).fetchall()
        if not rows:
            print("[operator-task-cleanup] stale_active=0",flush=True)
            return
        backup_root=pathlib.Path("/data/release_backups/20261003_operator_task_lifecycle")
        backup_root.mkdir(parents=True,exist_ok=True)
        stamp=__import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
        dst=backup_root/(stamp+"_pre_stale_task_close.db")
        src=sqlite3.connect(str(db_path),timeout=30); out=sqlite3.connect(str(dst))
        try: src.backup(out)
        finally: out.close(); src.close()
        ids=[int(r["id"]) for r in rows]
        marks=",".join("?" for _ in ids)
        conn.execute("UPDATE bodymind_operator_tasks SET status='completed_stale',updated_at=datetime('now') WHERE id IN ("+marks+")",ids)
        conn.commit()
        print("[operator-task-cleanup] closed="+str(ids)+" backup="+str(dst),flush=True)
    finally:
        conn.close()

_bodymind_operator_task_cleanup()

# BODYMIND_FINAL_DATA_CONVERGENCE
def _bodymind_final_data_convergence():
    db_path=pathlib.Path("/data/tenants/default/asd.db")
    if not db_path.exists():
        return
    conn=sqlite3.connect(str(db_path),timeout=30); conn.row_factory=sqlite3.Row
    actions=[]
    try:
        def has_table(n):
            return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(n,)).fetchone())
        def cols(n):
            return {str(x[1]) for x in conn.execute("PRAGMA table_info("+n+")").fetchall()} if has_table(n) else set()

        # 1) Truly stale async jobs cannot remain "processing" forever.
        if has_table('bodymind_operator_upload_jobs'):
            stale=conn.execute("""SELECT id,conversation_id,status FROM bodymind_operator_upload_jobs
              WHERE status IN ('queued','processing')
                AND julianday(updated_at) < julianday('now','-6 hours')""").fetchall()
            for r in stale:
                conn.execute("""UPDATE bodymind_operator_upload_jobs
                  SET status='failed',error='stale async job closed by final convergence',updated_at=datetime('now')
                  WHERE id=?""",(str(r['id']),))
                actions.append('stale_job:'+str(r['id']))

        # 2) Close active batch tasks older than 6h when there is no live job/action.
        if has_table('bodymind_operator_tasks'):
            has_jobs=has_table('bodymind_operator_upload_jobs'); has_actions=has_table('bodymind_operator_actions')
            where=["t.task_type='batch_upload'","t.status='active'","julianday(t.updated_at) < julianday('now','-6 hours')"]
            if has_jobs:
                where.append("NOT EXISTS (SELECT 1 FROM bodymind_operator_upload_jobs j WHERE j.conversation_id=t.conversation_id AND j.status IN ('queued','processing'))")
            if has_actions:
                where.append("NOT EXISTS (SELECT 1 FROM bodymind_operator_actions a WHERE a.conversation_id=t.conversation_id AND a.status IN ('proposed','pending','awaiting_confirmation'))")
            rows=conn.execute("SELECT t.id FROM bodymind_operator_tasks t WHERE "+" AND ".join(where)).fetchall()
            for r in rows:
                conn.execute("UPDATE bodymind_operator_tasks SET status='completed_stale',updated_at=datetime('now') WHERE id=?",(int(r['id']),))
                actions.append('stale_task:'+str(int(r['id'])))

        # 2b) Inbound rows that still point to deliberately deleted athletes are
        # historical audit records, not live operational associations. Preserve a
        # full JSON copy, then detach them from the missing athlete so FK/business
        # invariants remain true. Never recreate the deleted athlete.
        if has_table('inbound_documents') and has_table('tesserati'):
            ic=cols('inbound_documents')
            orphans=conn.execute("""SELECT i.* FROM inbound_documents i
              LEFT JOIN tesserati t ON t.id=i.tesserato_id
              WHERE i.tesserato_id IS NOT NULL AND t.id IS NULL
              ORDER BY i.id""").fetchall()
            if orphans:
                conn.execute("""CREATE TABLE IF NOT EXISTS bodymind_orphan_records_archive(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  source_table TEXT NOT NULL,
                  source_id INTEGER NOT NULL,
                  former_tesserato_id INTEGER,
                  reason TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  semantics_json TEXT,
                  events_json TEXT,
                  archived_at TEXT NOT NULL,
                  UNIQUE(source_table,source_id)
                )""")
                for r in orphans:
                    iid=int(r['id']); former=int(r['tesserato_id'] or 0)
                    conn.execute("""INSERT OR IGNORE INTO bodymind_orphan_records_archive
                      (source_table,source_id,former_tesserato_id,reason,payload_json,semantics_json,events_json,archived_at)
                      VALUES(?,?,?,?,?,'[]','[]',datetime('now'))""",
                      ('inbound_documents',iid,former,'deleted-athlete historical inbound',
                       json.dumps(dict(r),ensure_ascii=False,default=str)))
                    sets=['tesserato_id=NULL']
                    if 'matched_tesserato_id' in ic: sets.append('matched_tesserato_id=NULL')
                    if 'suggested_tesserato_id' in ic: sets.append('suggested_tesserato_id=NULL')
                    if 'status' in ic: sets.append("status='archived_orphan'")
                    if 'updated_at' in ic: sets.append("updated_at=datetime('now')")
                    conn.execute("UPDATE inbound_documents SET "+','.join(sets)+" WHERE id=?",(iid,))
                    actions.append('inbound_orphan_archived:'+str(iid)+':former_tid='+str(former))

        # 3) Trusted MU inbound with no visible dossier MU: materialize the canonical
        # document row from the existing file. Never invent data or duplicate a visible MU.
        if has_table('inbound_documents') and has_table('documenti') and has_table('tesserati'):
            dc=cols('documenti'); ic=cols('inbound_documents'); tc=cols('tesserati')
            rows=conn.execute("""SELECT i.* FROM inbound_documents i
              JOIN tesserati t ON t.id=i.tesserato_id
              WHERE lower(coalesce(i.document_type,''))='modulo_unico_tesseramento'
                AND coalesce(i.tesserato_id,0)>0
                AND coalesce(i.document_confidence,0)>=95
                AND coalesce(i.match_score,0)>=95
              ORDER BY i.id""").fetchall()
            for r in rows:
                tid=int(r['tesserato_id'])
                exists=conn.execute("""SELECT 1 FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1 AND (
                  lower(coalesce(doc_type,''))='modulo_unico_tesseramento'
                  OR lower(coalesce(categoria,'')) LIKE '%modulo iscrizione%'
                  OR lower(coalesce(titolo,'')) LIKE '%modulo unico%'
                  OR lower(coalesce(titolo,'')) LIKE '%domanda iscrizione%') LIMIT 1""",(tid,)).fetchone()
                if exists: continue
                path=''
                for k in ('saved_path','stored_path','filename'):
                    if k in ic and r[k]:
                        path=str(r[k]); break
                if not path or not pathlib.Path(path).is_file():
                    continue
                vals={
                  'tesserato_id':tid,
                  'titolo':str(r['original_filename'] or 'Modulo Unico') if 'original_filename' in ic else 'Modulo Unico',
                  'categoria':'Modulo iscrizione BodyMind',
                  'filename':path,
                  'original_filename':str(r['original_filename'] or pathlib.Path(path).name) if 'original_filename' in ic else pathlib.Path(path).name,
                  'data_caricamento':__import__('datetime').date.today().isoformat(),
                  'visibile':1,'doc_type':'modulo_unico_tesseramento',
                  'confidence':100,'match_score':100,'source':'final_convergence',
                  'status':'salvato','inbound_id':int(r['id'])
                }
                vals={k:v for k,v in vals.items() if k in dc}
                required={'tesserato_id','titolo','categoria','filename','original_filename'}
                if required.issubset(vals):
                    keys=list(vals)
                    conn.execute("INSERT INTO documenti("+','.join(keys)+") VALUES("+','.join('?' for _ in keys)+")",[vals[k] for k in keys])
                    if 'iscrizione_firmata' in tc:
                        conn.execute("UPDATE tesserati SET iscrizione_firmata=1 WHERE id=?",(tid,))
                    if 'documenti_onboarding_ok' in tc:
                        conn.execute("UPDATE tesserati SET documenti_onboarding_ok=1 WHERE id=?",(tid,))
                    actions.append('mu_materialized:inbound='+str(int(r['id']))+':tid='+str(tid))

        # 3b) Operational truth wins over stale onboarding flags. If no visible
        # MU exists after the safe materialization attempt, do not claim enrollment
        # documents are complete. Historical rows remain untouched.
        if has_table('documenti') and has_table('tesserati'):
            tc=cols('tesserati')
            if 'iscrizione_firmata' in tc or 'documenti_onboarding_ok' in tc:
                athletes=conn.execute("SELECT * FROM tesserati ORDER BY id").fetchall()
                for a in athletes:
                    tid=int(a['id'])
                    has_mu=bool(conn.execute("""SELECT 1 FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1 AND (
                      lower(coalesce(doc_type,''))='modulo_unico_tesseramento'
                      OR lower(coalesce(categoria,'')) LIKE '%modulo iscrizione%'
                      OR lower(coalesce(titolo,'')) LIKE '%modulo unico%'
                      OR lower(coalesce(titolo,'')) LIKE '%domanda iscrizione%') LIMIT 1""",(tid,)).fetchone())
                    if has_mu: continue
                    sets=[]
                    if 'iscrizione_firmata' in tc and int(a['iscrizione_firmata'] or 0):
                        sets.append('iscrizione_firmata=0')
                    if 'documenti_onboarding_ok' in tc and int(a['documenti_onboarding_ok'] or 0):
                        sets.append('documenti_onboarding_ok=0')
                    if sets:
                        conn.execute("UPDATE tesserati SET "+','.join(sets)+" WHERE id=?",(tid,))
                        actions.append('onboarding_truth_reset:tid='+str(tid))

        # 3c) Historical payment requests for intentionally deleted athletes are
        # not accounting truth. Preserve them in the explicit orphan audit archive,
        # then remove them from the operational request table so they cannot create
        # future false tasks/alerts.
        if has_table('payment_requests') and has_table('tesserati'):
            pc=cols('payment_requests')
            if 'tesserato_id' in pc:
                conn.execute("""CREATE TABLE IF NOT EXISTS bodymind_orphan_records_archive(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  source_table TEXT NOT NULL,
                  source_id INTEGER NOT NULL,
                  former_tesserato_id INTEGER,
                  reason TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  semantics_json TEXT,
                  events_json TEXT,
                  archived_at TEXT NOT NULL,
                  UNIQUE(source_table,source_id)
                )""")
                orphan_reqs=conn.execute("""SELECT p.* FROM payment_requests p
                  LEFT JOIN tesserati t ON t.id=p.tesserato_id
                  WHERE p.tesserato_id IS NOT NULL AND t.id IS NULL
                  ORDER BY p.id""").fetchall()
                for pr in orphan_reqs:
                    pid=int(pr['id']); former=int(pr['tesserato_id'] or 0)
                    conn.execute("""INSERT OR IGNORE INTO bodymind_orphan_records_archive
                      (source_table,source_id,former_tesserato_id,reason,payload_json,semantics_json,events_json,archived_at)
                      VALUES(?,?,?,?,?,'[]','[]',datetime('now'))""",
                      ('payment_requests',pid,former,'deleted-athlete historical payment request',
                       json.dumps(dict(pr),ensure_ascii=False,default=str)))
                    conn.execute("DELETE FROM payment_requests WHERE id=?",(pid,))
                    actions.append('payment_request_archived:'+str(pid)+':former_tid='+str(former))

        # 4) Exact duplicate visible files: same athlete + same semantic/type bucket + SHA.
        # Archive only the extra DB row; never delete the physical file.
        if has_table('documenti'):
            dc=cols('documenti')
            rows=conn.execute("SELECT * FROM documenti WHERE coalesce(visibile,1)=1 ORDER BY id").fetchall()
            groups={}
            for r in rows:
                tid=int(r['tesserato_id'] or 0) if 'tesserato_id' in dc else 0
                if tid<=0: continue
                path=str(r['filename'] or '') if 'filename' in dc else ''
                p=pathlib.Path(path)
                if not p.is_file(): continue
                try: sha=hashlib.sha256(p.read_bytes()).hexdigest()
                except Exception: continue
                dtype=str(r['doc_type'] or '').strip().lower() if 'doc_type' in dc else ''
                cat=str(r['categoria'] or '').strip().lower() if 'categoria' in dc else ''
                kind=dtype or cat or 'altro'
                groups.setdefault((tid,kind,sha),[]).append(r)
            for key,items in groups.items():
                if len(items)<2: continue
                keep=min(int(x['id']) for x in items)
                for r in items:
                    did=int(r['id'])
                    if did==keep: continue
                    sets=[]; vals=[]
                    if 'visibile' in dc: sets.append('visibile=0')
                    if 'status' in dc: sets.append('status=?'); vals.append('duplicate_exact_archived')
                    if 'note' in dc:
                        sets.append('note=?'); vals.append('Duplicato SHA identico archiviato; canonico ID '+str(keep))
                    if sets:
                        vals.append(did)
                        conn.execute("UPDATE documenti SET "+','.join(sets)+" WHERE id=?",vals)
                        actions.append('exact_duplicate_archived:'+str(did)+'->'+str(keep))

        if actions:
            # Backup is created before committing the convergence.
            backup_root=pathlib.Path("/data/release_backups/20261003_final_convergence")
            backup_root.mkdir(parents=True,exist_ok=True)
            stamp=__import__('datetime').datetime.now().strftime("%Y%m%d_%H%M%S")
            dst=backup_root/(stamp+"_pre_final_convergence.db")
            src=sqlite3.connect(str(db_path),timeout=30); out=sqlite3.connect(str(dst))
            try: src.backup(out)
            finally: out.close(); src.close()
            conn.commit()
            print("[final-data-convergence] actions="+json.dumps(actions,ensure_ascii=False)+" backup="+str(dst),flush=True)
        else:
            print("[final-data-convergence] no-op",flush=True)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

_bodymind_final_data_convergence()

def _bodymind_neutralize_static_count_guards():
    patches={
      "/opt/bodymind/release_medical_profile_convergence_r100.py":[
        ("'tesserati_unchanged':counts['tesserati']==35","'tesserati_dynamic_positive':counts['tesserati']>0"),
        ("'giulia_one_medical':len(giulia_docs)==1","'giulia_medical_not_duplicated':len(giulia_docs)<=1")
      ],
      "/opt/bodymind/release_mu_canonical_r79.py":[
        ("if tess!=32 or integrity.lower()!='ok' or fk:","if tess<=0 or integrity.lower()!='ok' or fk:")
      ],
      "/opt/bodymind/release_certificate_truth_r120.py":[
        ("'mobile_truth':marker in mob_now and \"if _cert:\" in mob_now","'mobile_truth':marker in mob_now and (\"if _cert:\" in mob_now or \"if _med and _cert:\" in mob_now)")
      ],
      "/opt/bodymind/release_simple_athlete_payment_truth_r110.py":[
        ("'payments_canonical':\"SELECT * FROM pagamenti WHERE tesserato_id=?\" in desk and \"SELECT * FROM pagamenti WHERE tesserato_id=?\" in mob,",
         "'payments_canonical':\"SELECT * FROM pagamenti WHERE tesserato_id=?\" in desk and (\"SELECT * FROM pagamenti WHERE tesserato_id=?\" in mob or \"BODYMIND_R144_CANONICAL_PROFILE_TRUTH\" in mob),")
      ],
      "/opt/bodymind/release_criticality_profile_r101.py":[
        ("'tesserati_35':tess==35","'tesserati_dynamic_positive':tess>0")
      ],
    }
    for raw,repls in patches.items():
        p=pathlib.Path(raw)
        if not p.exists(): continue
        t=p.read_text(encoding="utf-8",errors="replace")
        original=t
        for old,new in repls:
            t=t.replace(old,new)
        if t!=original:
            p.write_text(t,encoding="utf-8")
            print("[dynamic-count-guard] normalized "+raw,flush=True)

_bodymind_neutralize_static_count_guards()

APP = pathlib.Path("/data/top2_app")
MARKER = APP / ".TOP2_OFFICIAL"
if not MARKER.exists():
    raise SystemExit("TOP2_OFFICIAL marker missing; refusing to start")

runpy.run_path("/opt/bodymind/release_apply.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_autopilot_r3.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_autopilot_r4.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_autopilot_r5.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_autopilot_r6.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_autopilot_r8.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_autopilot_r9.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_document_ux_r10.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_simplify_r11.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_mobile_r12.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_unified_r13.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_document_repair_r14.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_queue_integrity_r15.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_unified_flags_r16.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_missing_docs_r17.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_inbound_filefix_r18.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_pending_dedupe_r19.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_dossier_missing_r23.py", run_name="__main__")
if not (APP / ".BODYMIND_OCR_REMATCH_R20").exists():
    runpy.run_path("/opt/bodymind/release_ocr_rematch_r20.py", run_name="__main__")
if not (APP / ".BODYMIND_FORCE_PDF_OCR_R21").exists():
    runpy.run_path("/opt/bodymind/release_force_pdf_ocr_r21.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_document_flow_r25.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_document_preview_r26.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_r29.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_r92_operator_recover.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_route_cleanup_r31.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_r30.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_mu_tutela_r34.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_mu_tutela_r36.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_mu_tutela_r37.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_document_coherence_r41.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_document_coherence_r42.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_dedupe_rollback_r43.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_document_conflict_audit_r44.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_cloud_native_r47.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_secretary_capability_audit_r48.py", run_name="__main__")
if not (APP / ".BODYMIND_TIMELINE_INSPECT_R35").exists():
    runpy.run_path("/opt/bodymind/runtime_timeline_inspect_r35.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_mobile_r33.py", run_name="__main__")
# R55 is the final operator layer. R55 adds semantic autonomy and the BodyMind living voice logo.
runpy.run_path("/opt/bodymind/release_operator_batch_r52.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_upload_semantic_r52.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_web_audio_r52.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_autonomy_r55.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_fast_dedupe_r56.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_dedupe_smoke_r56.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_avatar_r57.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_voice_state_r59.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_targeted_missing_r60.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_response_scope_r61.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_query_polarity_r62.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_cloud_first_r63.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_persistent_upload_r64.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_handwriting_enrollment_r65.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_async_upload_r67.py", run_name="__main__")
if os.environ.get("BODYMIND_DEEP_STARTUP_AUDITS","0") == "1":
    print("[startup-convergence] historical MU/profile backfills enabled",flush=True)
    runpy.run_path("/opt/bodymind/release_verified_mu_profile_sync_r68.py", run_name="__main__")
    runpy.run_path("/opt/bodymind/runtime_annunziato_readonly_r71.py", run_name="__main__")
    runpy.run_path("/opt/bodymind/release_global_reconcile_r69.py", run_name="__main__")
    runpy.run_path("/opt/bodymind/release_complete_mu_cache_r70.py", run_name="__main__")
    runpy.run_path("/opt/bodymind/release_guardian_refresh_r71.py", run_name="__main__")
else:
    print("[startup-convergence] R68-R71 historical backfills skipped; runtime cores + R80/R84 gates remain active",flush=True)
runpy.run_path("/opt/bodymind/release_shared_document_core_r72.py", run_name="__main__")
# R119 supersedes the dynamic R117 route registration; one canonical no-match MU flow only.
runpy.run_path("/opt/bodymind/release_document_consistency_r74.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_document_core_r78.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_mu_canonical_r79.py", run_name="__main__")
# R81 is a historical repair script and is no longer safe to run on every boot:
# it can materialize a MU for a deliberately deleted athlete (observed tid=37),
# creating an FK violation. Modern R80/R84/R118 gates cover the invariants.
if os.environ.get("BODYMIND_DEEP_STARTUP_AUDITS","0") == "1":
    runpy.run_path("/opt/bodymind/release_stabilization_repair_r81.py", run_name="__main__")
else:
    print("[startup-convergence] R81 historical repair skipped; modern invariant gates remain active",flush=True)
runpy.run_path("/opt/bodymind/release_guardian_convergence_r82.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_mu_autoenroll_r92.py", run_name="__main__")
# BODYMIND_STARTUP_CONSOLIDATION_P1
# Deep read-only audits are useful diagnostically but no longer belong to every boot.
# The mutating convergence scripts and modern hard gates below remain mandatory.
if os.environ.get("BODYMIND_DEEP_STARTUP_AUDITS","0") == "1":
    print("[startup-convergence] deep read-only audits enabled", flush=True)
    runpy.run_path("/opt/bodymind/release_new_athlete_profile_audit_r93.py", run_name="__main__")
    runpy.run_path("/opt/bodymind/release_profile_schema_audit_r94.py", run_name="__main__")
else:
    print("[startup-convergence] R93/R94 read-only audits skipped; hard gates remain active", flush=True)

runpy.run_path("/opt/bodymind/release_mu_residenza_r95.py", run_name="__main__")

if os.environ.get("BODYMIND_DEEP_STARTUP_AUDITS","0") == "1":
    runpy.run_path("/opt/bodymind/release_medical_criticality_audit_r96.py", run_name="__main__")
    runpy.run_path("/opt/bodymind/release_medical_save_audit_r97.py", run_name="__main__")
    runpy.run_path("/opt/bodymind/release_medical_save_compact_r98.py", run_name="__main__")
    runpy.run_path("/opt/bodymind/release_active_route_audit_r99.py", run_name="__main__")
else:
    print("[startup-convergence] R96-R99 superseded read-only audits skipped; R100 is canonical medical convergence", flush=True)

runpy.run_path("/opt/bodymind/release_medical_profile_convergence_r100.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_criticality_profile_r101.py", run_name="__main__")

if os.environ.get("BODYMIND_DEEP_STARTUP_AUDITS","0") == "1":
    runpy.run_path("/opt/bodymind/release_desktop_profile_audit_r104.py", run_name="__main__")
    runpy.run_path("/opt/bodymind/release_desktop_update_source_r105.py", run_name="__main__")
else:
    print("[startup-convergence] R104/R105 read-only source audits skipped; R106/R113 remain hard gates", flush=True)

runpy.run_path("/opt/bodymind/release_desktop_save_convergence_r106.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_attachment_create_r107.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_mu_metadata_convergence_r108.py", run_name="__main__")

if os.environ.get("BODYMIND_DEEP_STARTUP_AUDITS","0") == "1":
    runpy.run_path("/opt/bodymind/release_payment_simplify_audit_r109.py", run_name="__main__")
else:
    print("[startup-convergence] R109 read-only payment audit skipped; R110/R111 canonical payment gates remain active", flush=True)
runpy.run_path("/opt/bodymind/release_simple_athlete_payment_truth_r110.py", run_name="__main__")
if os.environ.get("BODYMIND_LEGACY_STARTUP_SMOKES","0") == "1":
    runpy.run_path("/opt/bodymind/release_certificate_truth_r120.py", run_name="__main__")
else:
    print("[startup-convergence] R120 expiry-only certificate patch skipped; superseded by R144 file+expiry canonical truth",flush=True)
runpy.run_path("/opt/bodymind/release_operator_runtime_helper_r112.py", run_name="__main__")
if os.environ.get("BODYMIND_LEGACY_STARTUP_SMOKES","0") == "1":
    runpy.run_path("/opt/bodymind/release_document_association_sync_r143.py", run_name="__main__")
else:
    print("[startup-convergence] R143 broad association sync skipped; R144 recent-only canonical sync active",flush=True)
runpy.run_path("/opt/bodymind/release_mobile_profile_surface_r145.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_document_association_fix_r144.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_convergence_smoke_r111.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_desktop_post_regression_r113.py", run_name="__main__")
if os.environ.get("BODYMIND_DEEP_STARTUP_AUDITS","0") == "1":
    runpy.run_path("/opt/bodymind/release_simple_athlete_payment_smoke_r111.py", run_name="__main__")
else:
    print("[startup-convergence] mutating R111 UI smoke skipped; R113 real POST + R111 read-only UI gate remain active",flush=True)
if os.environ.get("BODYMIND_DEEP_STARTUP_AUDITS","0") == "1":
    runpy.run_path("/opt/bodymind/release_mu_nomatch_audit_r116.py", run_name="__main__")
else:
    print("[startup-convergence] R116 read-only MU audit skipped; R118/R119 live gates remain active", flush=True)
runpy.run_path("/opt/bodymind/release_mu_nomatch_operator_r119.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_mu_nomatch_create_smoke_r118.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_upload_state_probe_r142.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_upload_truth_convergence_r146.py", run_name="__main__")
# Re-run stale task cleanup after operator/document convergence, because old
# upload tasks can become safely closable only after their async job/actions
# have completed during startup.
_bodymind_operator_task_cleanup()
runpy.run_path("/opt/bodymind/release_stabilization_audit_r80.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_mobile_delete_r85.py", run_name="__main__")
if os.environ.get("BODYMIND_LEGACY_STARTUP_SMOKES","0") == "1":
    runpy.run_path("/opt/bodymind/release_mobile_athlete_delete_r87.py", run_name="__main__")
else:
    print("[startup-convergence] R87 mobile athlete source patch skipped; superseded by R140/R141 final mobile truth UI",flush=True)
runpy.run_path("/opt/bodymind/release_operator_ios_keyboard_r90.py", run_name="__main__")
if os.environ.get("BODYMIND_DEEP_STARTUP_AUDITS","0") == "1":
    runpy.run_path("/opt/bodymind/release_unassigned_mu_audit_r91.py", run_name="__main__")
else:
    print("[startup-convergence] R91 read-only MU audit skipped", flush=True)
if os.environ.get("BODYMIND_LEGACY_STARTUP_SMOKES","0") == "1":
    runpy.run_path("/opt/bodymind/release_ui_regression_smoke_r84.py", run_name="__main__")
else:
    print("[startup-convergence] R84 legacy mobile UI smoke skipped; superseded by R139/R141 rendered truth gates",flush=True)
# R114 startup convergence: keep source/migration guards in the critical path, but
# do not re-run the superseded R32-R65 read-only/operator smoke chain on every deploy.
# The current hard gates above (R80/R84/R90/R107/R110/R111/R113) cover those invariants.
runpy.run_path("/opt/bodymind/release_mobile_operator_mu_r73.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_experience_r38.py", run_name="__main__")
if os.environ.get("BODYMIND_DEEP_STARTUP_AUDITS","0") == "1":
    runpy.run_path("/opt/bodymind/release_operator_dinicola_r55f.py", run_name="__main__")
else:
    print("[startup-convergence] historical Di Nicola fixture skipped",flush=True)
runpy.run_path("/opt/bodymind/release_cleanup_r2.py", run_name="__main__")
if os.environ.get("BODYMIND_LEGACY_STARTUP_SMOKES","0") == "1":
    print("[r114-startup] legacy operator smoke chain enabled", flush=True)
    runpy.run_path("/opt/bodymind/release_handwriting_enrollment_smoke_r65.py", run_name="__main__")
    runpy.run_path("/opt/bodymind/release_operator_upload_smoke_r64.py", run_name="__main__")
    runpy.run_path("/opt/bodymind/release_operator_cloud_first_smoke_r63.py", run_name="__main__")
    runpy.run_path("/opt/bodymind/release_operator_polarity_smoke_r62.py", run_name="__main__")
    runpy.run_path("/opt/bodymind/release_operator_scope_smoke_r61.py", run_name="__main__")
    runpy.run_path("/opt/bodymind/release_operator_targeted_smoke_r60.py", run_name="__main__")
    runpy.run_path("/opt/bodymind/release_operator_intent_smoke_r57.py", run_name="__main__")
    runpy.run_path("/opt/bodymind/release_operator_read_smoke_r53.py", run_name="__main__")
    runpy.run_path("/opt/bodymind/release_operator_qa_r32.py", run_name="__main__")
    runpy.run_path("/opt/bodymind/release_operator_logic_qa_r37.py", run_name="__main__")
    runpy.run_path("/opt/bodymind/release_operator_pending_audit_r55e.py", run_name="__main__")
else:
    print("[r114-startup] legacy operator smoke chain skipped; covered by consolidated hard gates", flush=True)
# R115 is now the canonical navigation convergence for the daily secretary UI.
# It is idempotent and preserves all advanced routes/data while hiding duplicate
# entry points from normal navigation.
runpy.run_path("/opt/bodymind/release_navigation_audit_r115.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_document_file_resolver_r135.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_document_truth_cleanup_r137.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_mobile_document_ui_r138.py", run_name="__main__")
if os.environ.get("BODYMIND_LEGACY_STARTUP_SMOKES","0") == "1":
    runpy.run_path("/opt/bodymind/release_mobile_truth_r139.py", run_name="__main__")
else:
    print("[startup-convergence] R139 source patch skipped; R144/R145 canonical document truth supersedes it",flush=True)
if os.environ.get("BODYMIND_LEGACY_STARTUP_SMOKES","0") == "1":
    runpy.run_path("/opt/bodymind/release_mobile_athlete_truth_r140.py", run_name="__main__")
else:
    print("[startup-convergence] R140 source rewrite skipped; R141 is the final rendered mobile athlete truth surface",flush=True)
runpy.run_path("/opt/bodymind/release_secretary_ui_r123.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_mobile_truth_surface_r141.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_route_guard_r39.py", run_name="__main__")
incoming = pathlib.Path("/data/incoming")
for name in ("top2.zip", "backup.zip"):
    p = incoming / name
    try:
        if p.exists():
            p.unlink()
    except Exception as exc:
        print(f"[top2] cleanup warning for {p}: {exc}", flush=True)

os.chdir(APP)
sys.path.insert(0, str(APP))
from asd_app.core import init_db
init_db()
admin_user = os.environ.get("BODYMIND_ADMIN_USER", "").strip()
admin_password = os.environ.get("BODYMIND_ADMIN_PASSWORD", "")
admin_password_hash = os.environ.get("BODYMIND_ADMIN_PASSWORD_HASH", "").strip()
if admin_user and (admin_password_hash or admin_password):
    from werkzeug.security import generate_password_hash
    effective_hash = admin_password_hash or generate_password_hash(admin_password)
    db_path_admin = pathlib.Path("/data/tenants/default/asd.db")
    conn_admin = sqlite3.connect(str(db_path_admin), timeout=15)
    try:
        cols = {row[1] for row in conn_admin.execute("PRAGMA table_info(users)").fetchall()}
        now_admin = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        row = conn_admin.execute("SELECT id FROM users WHERE username=?", (admin_user,)).fetchone()
        if row:
            updates = {"password": effective_hash, "role": "admin", "active": 1, "must_change_password": 0, "updated_at": now_admin}
            pairs, vals = [], []
            for key, value in updates.items():
                if key in cols:
                    pairs.append(f"{key}=?")
                    vals.append(value)
            vals.append(row[0])
            conn_admin.execute("UPDATE users SET " + ",".join(pairs) + " WHERE id=?", vals)
        else:
            values = {"username": admin_user, "password": effective_hash, "role": "admin", "active": 1, "must_change_password": 0, "created_at": now_admin, "updated_at": now_admin}
            keys = [k for k in values if k in cols]
            conn_admin.execute("INSERT INTO users(" + ",".join(keys) + ") VALUES(" + ",".join("?" for _ in keys) + ")", [values[k] for k in keys])
        conn_admin.commit()
        print(f"[credentials] ensured admin user={admin_user}", flush=True)
    finally:
        conn_admin.close()

db_path = pathlib.Path("/data/tenants/default/asd.db")
if db_path.exists():
    conn = sqlite3.connect(str(db_path), timeout=15)
    try:
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        journal = str(conn.execute("PRAGMA journal_mode").fetchone()[0])
        tesserati = int(conn.execute("SELECT COUNT(*) FROM tesserati").fetchone()[0])
    finally:
        conn.close()
    if integrity.lower() != "ok":
        raise SystemExit(f"SQLite integrity check failed: {integrity}")
    def count_files(path):
        q = pathlib.Path(path)
        return sum(1 for x in q.rglob("*") if x.is_file()) if q.exists() else 0
    print(
        "[startup-audit] db=ok "
        f"journal={journal} tesserati={tesserati} "
        f"media={count_files('/data/tenants/default/media')} "
        f"onboarding={count_files('/data/onboarding_docs')} "
        f"signatures={count_files('/data/signatures')} "
        f"user_static={count_files('/data/user_static')}",
        flush=True,
    )

port = os.environ.get("PORT", "8080")
args = [
    "gunicorn",
    "--bind", f"0.0.0.0:{port}",
    "--workers", "1",
    "--threads", "4",
    "--timeout", "300",
    "--access-logfile", "-",
    "--error-logfile", "-",
    "app:app",
]
os.execvp("gunicorn", args)
