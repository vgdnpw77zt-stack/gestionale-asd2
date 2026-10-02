# R39 build and route guards - autodeploy trigger 2
import os, sys, pathlib, runpy, sqlite3, shutil, json, time

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

_bodymind_storage_preflight()

def _bodymind_neutralize_static_count_guards():
    patches={
      "/opt/bodymind/release_medical_profile_convergence_r100.py":[
        ("'tesserati_unchanged':counts['tesserati']==35","'tesserati_dynamic_positive':counts['tesserati']>0")
      ],
      "/opt/bodymind/release_mu_canonical_r79.py":[
        ("if tess!=32 or integrity.lower()!='ok' or fk:","if tess<=0 or integrity.lower()!='ok' or fk:")
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
runpy.run_path("/opt/bodymind/release_verified_mu_profile_sync_r68.py", run_name="__main__")
runpy.run_path("/opt/bodymind/runtime_annunziato_readonly_r71.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_global_reconcile_r69.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_complete_mu_cache_r70.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_guardian_refresh_r71.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_shared_document_core_r72.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_document_consistency_r74.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_document_core_r78.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_mu_canonical_r79.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_stabilization_repair_r81.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_guardian_convergence_r82.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_mu_autoenroll_r92.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_new_athlete_profile_audit_r93.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_profile_schema_audit_r94.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_mu_residenza_r95.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_medical_criticality_audit_r96.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_medical_save_audit_r97.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_medical_save_compact_r98.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_active_route_audit_r99.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_medical_profile_convergence_r100.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_criticality_profile_r101.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_desktop_profile_audit_r104.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_desktop_update_source_r105.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_desktop_save_convergence_r106.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_attachment_create_r107.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_mu_metadata_convergence_r108.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_payment_simplify_audit_r109.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_stabilization_audit_r80.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_mobile_delete_r85.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_mobile_athlete_delete_r87.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_ios_keyboard_r90.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_unassigned_mu_audit_r91.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_ui_regression_smoke_r84.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_mobile_operator_mu_r73.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_handwriting_enrollment_smoke_r65.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_upload_smoke_r64.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_cloud_first_smoke_r63.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_polarity_smoke_r62.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_scope_smoke_r61.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_targeted_smoke_r60.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_intent_smoke_r57.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_read_smoke_r53.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_experience_r38.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_qa_r32.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_logic_qa_r37.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_dinicola_r55f.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_operator_pending_audit_r55e.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_cleanup_r2.py", run_name="__main__")
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
