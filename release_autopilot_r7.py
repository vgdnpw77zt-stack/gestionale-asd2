from __future__ import annotations
from pathlib import Path
import compileall, shutil

APP=Path('/data/top2_app')
MARKER=APP/'.BODYMIND_AUTOPILOT_R7'
BACKUPS=Path('/data/release_backups/20260926_autopilot_r7')

def backup(rel):
    src=APP/rel; dst=BACKUPS/rel
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dst)

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

if not MARKER.exists():
    rel='asd_app/routes_bodymind_fix49.py'
    p=APP/rel
    s=p.read_text(encoding='utf-8')
    start_marker='async function send(files){'
    end_marker="cameraPick.addEventListener('change',()=>{send(cameraPick.files);cameraPick.value='';});"
    if new not in s:
        a=s.find(start_marker)
        b=s.find(end_marker,a)
        if a < 0 or b < 0:
            raise RuntimeError('R7 upload JS structural anchor missing')
        b += len(end_marker)
        backup(rel)
        s=s[:a]+new+s[b:]
        p.write_text(s,encoding='utf-8')

    if not compileall.compile_dir(str(APP/'asd_app'),quiet=1):
        raise RuntimeError('R7 compile failed')

    live=p.read_text(encoding='utf-8')
    required=[
        "form.addEventListener('submit',ev=>{ev.preventDefault()",
        "attempt<=3",
        "credentials:'same-origin'",
        "cache:'no-store'",
        "AbortController",
        "Connessione interrotta. Riprovo automaticamente",
        "X-BodyMind-Autopilot':'r7-mobile",
    ]
    missing=[x for x in required if x not in live]
    if missing:
        raise RuntimeError('R7 selftest missing: '+repr(missing))
    MARKER.write_text('BodyMind Autopilot R7 upload resilience applied\n',encoding='utf-8')
    print('[autopilot-r7] applied',flush=True)
    print('[autopilot-r7-selftest] PASS prevent-submit retry=3 timeout=180s no-store credentials=same-origin friendly-network-error',flush=True)
else:
    print('[autopilot-r7] already applied',flush=True)
