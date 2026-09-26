import os, sys, pathlib, runpy, sqlite3

APP = pathlib.Path("/data/top2_app")
MARKER = APP / ".TOP2_OFFICIAL"
if not MARKER.exists():
    raise SystemExit("TOP2_OFFICIAL marker missing; refusing to start")

runpy.run_path("/opt/bodymind/release_apply.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_autopilot_r3.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_autopilot_r4.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_autopilot_r5.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_autopilot_r6.py", run_name="__main__")
runpy.run_path("/opt/bodymind/runtime_upload_probe.py", run_name="__main__")
runpy.run_path("/opt/bodymind/release_cleanup_r2.py", run_name="__main__")

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
