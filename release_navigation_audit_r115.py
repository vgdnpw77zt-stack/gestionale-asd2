# -*- coding: utf-8 -*-
from __future__ import annotations
import json, py_compile, shutil, sqlite3, subprocess, sys
from datetime import datetime
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
BACK=Path('/data/release_backups/20261003_r115_navigation_convergence')
BACK.mkdir(parents=True,exist_ok=True)

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

def backup_file(p: Path):
    try: rel=p.relative_to(APP)
    except Exception: rel=Path(p.name)
    dst=BACK/rel
    if p.exists() and not dst.exists():
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(p,dst)

CORE=APP/'asd_app/core.py'
if not CORE.exists():
    raise RuntimeError('R115 core.py missing')

cs=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R115_NAV_CONVERGENCE' not in cs:
    backup_file(CORE)
    cs += r'''

# BODYMIND_R115_NAV_CONVERGENCE
# Daily secretary navigation shows only canonical areas. Technical/legacy routes
# remain available by direct URL and keep all write actions/data unchanged.
_BODYMIND_R115_ADVANCED_PREFIXES = (
    # Keep only technical/duplicate routes hidden. Business-critical modules
    # (Centro operativo, Document Hub, generator) must remain navigable.
    '/risolvi-automatico',
    '/motore-automazioni',
    '/timeline-tesserati',
    '/tesserati/timeline',
    '/pagamenti-pro',
    '/pagamenti/online',
    '/pagamenti-online-legacy',
    '/pagamenti-automatici',
    '/pagamenti/automatici',
    '/pagamenti/stripe',
    '/pagamenti/automazioni',
    '/dossier',
)

@app.after_request
def _bodymind_r115_navigation_convergence(resp):
    try:
        from flask import request as _r115_request
        import re as _r115_re
        if _r115_request.method != 'GET' or int(getattr(resp,'status_code',200) or 200) != 200:
            return resp
        ctype=str(resp.headers.get('Content-Type','')).lower()
        if 'text/html' not in ctype:
            return resp
        path=str(_r115_request.path or '')
        # When an advanced page is intentionally opened directly, do not alter
        # its own page controls. The simplification only applies to normal work.
        if any(path==p or path.startswith(p+'/') for p in _BODYMIND_R115_ADVANCED_PREFIXES):
            return resp
        html=resp.get_data(as_text=True)
        if not html:
            return resp
        alts='|'.join(_r115_re.escape(x) for x in _BODYMIND_R115_ADVANCED_PREFIXES)
        pat=r"<a\b[^>]*href=['\"](?:"+alts+r")(?:[/?#][^'\"]*)?['\"][^>]*>.*?</a>"
        html=_r115_re.sub(pat,'',html,flags=_r115_re.I|_r115_re.S)
        if 'BODYMIND_R115_NAV_CONVERGENCE_RENDERED' not in html:
            marker='<!-- BODYMIND_R115_NAV_CONVERGENCE_RENDERED -->'
            html=html.replace('</body>',marker+'</body>',1) if '</body>' in html else html+marker
        resp.set_data(html)
    except Exception:
        # Navigation simplification must never break a business page.
        return resp
    return resp
'''
    CORE.write_text(cs,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r115-core] PASS canonical daily navigation filter installed',flush=True)
else:
    print('[r115-core] already applied',flush=True)

# Rename the old Dossier button in the active document-review queue. It already
# points to canonical /documenti, so only the misleading legacy label changes.
A202=APP/'asd_app/routes_a202_operational_integrity.py'
if A202.exists():
    s=A202.read_text(encoding='utf-8',errors='replace')
    old="""dossier=f"<a class='r11-btn ghost' href='/documenti?tesserato_id={tid}'>Dossier</a>" if tid else ''"""
    new="""dossier=f"<a class='r11-btn ghost' href='/documenti?tesserato_id={tid}'>Documenti</a>" if tid else ''"""
    if old in s:
        backup_file(A202)
        s=s.replace(old,new,1)
        A202.write_text(s,encoding='utf-8')
        py_compile.compile(str(A202),doraise=True)
        print('[r115-doc-label] PASS Dossier -> Documenti on operational queue',flush=True)
    elif new in s:
        print('[r115-doc-label] already applied',flush=True)
    else:
        print('[r115-doc-label] queue label anchor not present; no change',flush=True)

# Fresh-process QA so we test what Gunicorn will import, not this release process.
qa=r'''
import json, sqlite3, sys
sys.path.insert(0,"/data/top2_app")
import app as _full_app
from asd_app.core import app
app.config["TESTING"]=True
client=app.test_client()
with client.session_transaction() as sess:
    sess.update({"logged":True,"username":"admin","display_name":"R115 QA","role":"admin","tenant_slug":"default"})

canonical={}
for path in ("/dashboard","/tesserati","/pagamenti","/documenti","/operatore-bodymind"):
    rr=client.get(path,follow_redirects=False)
    body=rr.get_data(as_text=True)
    canonical[path]={"status":rr.status_code,"marker":"BODYMIND_R115_NAV_CONVERGENCE_RENDERED" in body}
    forbidden=(
      "/risolvi-automatico","/motore-automazioni","/timeline-tesserati",
      "/pagamenti-pro","/pagamenti/online","/pagamenti-automatici"
    )
    canonical[path]["advanced_links_visible"]=sorted(x for x in forbidden if ("href='"+x) in body or ('href="'+x) in body)

advanced={}
for path in ("/cuore-operativo","/risolvi-automatico","/motore-automazioni","/onboarding-tesserati","/document-hub"):
    rr=client.get(path,follow_redirects=False)
    advanced[path]=rr.status_code

conn=sqlite3.connect("/data/tenants/default/asd.db",timeout=20)
try:
    integrity=str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    fk=len(conn.execute("PRAGMA foreign_key_check").fetchall())
finally: conn.close()

ok=all(v["status"] in (200,302) and not v["advanced_links_visible"] for v in canonical.values())
ok=ok and all(v in (200,302) for v in advanced.values()) and integrity.lower()=="ok" and fk==0
obj={"canonical":canonical,"advanced_direct":advanced,"integrity":integrity,"fk":fk,"ok":ok}
print("[r115-navigation-convergence] "+json.dumps(obj,ensure_ascii=False),flush=True)
if not ok:
    raise RuntimeError("R115 navigation convergence QA failed "+repr(obj))
'''
proc=subprocess.run([sys.executable,'-c',qa],capture_output=True,text=True,timeout=120)
if proc.returncode!=0:
    raise RuntimeError('R115 child QA failed '+((proc.stderr or '')+(proc.stdout or ''))[-4000:])
print((proc.stdout or '').strip(),flush=True)

conn=sqlite3.connect(str(DB),timeout=20)
try:
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally: conn.close()
if integrity.lower()!='ok' or fk:
    raise RuntimeError('R115 final DB guard failed')
print('[r115-selftest] PASS business-admin-routes-visible technical-duplicates-hidden db-ok',flush=True)
