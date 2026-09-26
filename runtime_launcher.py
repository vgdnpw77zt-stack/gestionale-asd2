import os, sys, pathlib, runpy

APP = pathlib.Path("/data/top2_app")
MARKER = APP / ".TOP2_OFFICIAL"
if not MARKER.exists():
    raise SystemExit("TOP2_OFFICIAL marker missing; refusing to start")

# Apply the versioned code-only production release before importing the application.
runpy.run_path("/opt/bodymind/release_apply.py", run_name="__main__")

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

port = os.environ.get("PORT", "8080")
args = ["gunicorn","--bind",f"0.0.0.0:{port}","--workers","1","--threads","4","--timeout","300","--access-logfile","-","--error-logfile","-","app:app"]
os.execvp("gunicorn", args)
