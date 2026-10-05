# -*- coding: utf-8 -*-
from __future__ import annotations
import py_compile, shutil
from pathlib import Path

APP=Path('/data/top2_app')
CORE=APP/'asd_app/core.py'
BACK=Path('/data/release_backups/20261005_r148_review_preview')
BACK.mkdir(parents=True,exist_ok=True)

s=CORE.read_text(encoding='utf-8',errors='replace')
before=s

needle="""            return f\"\"\"<article class='r147-card'><div class='r147-head'><div><b>{e(title)}</b><small>{e(who)}</small></div><span>DA VERIFICARE</span></div><p>{e(reason)}</p>
<form method='post' action='/documenti/da-verificare/r147/verifica'>"""
replacement="""            preview_url=('/documenti/visualizza/'+str(rid)) if source=='documenti' else ('/documenti-automatici/file/'+str(rid))
            return f\"\"\"<article class='r147-card'><div class='r147-head'><div><b>{e(title)}</b><small>{e(who)}</small></div><span>DA VERIFICARE</span></div><p>{e(reason)}</p>
<div class='r148-preview-actions'><a href='{preview_url}' target='_blank' rel='noopener'>👁 Anteprima documento</a></div>
<form method='post' action='/documenti/da-verificare/r147/verifica'>"""
if "r148-preview-actions" not in s:
    if needle not in s:
        raise RuntimeError('R148 card anchor missing')
    s=s.replace(needle,replacement,1)

css_anchor="""button{{width:100%;margin-top:14px;padding:13px;border:0;border-radius:12px;background:#166534;color:#fff;font-weight:950;font-size:16px}}a.back"""
css_new="""button{{width:100%;margin-top:14px;padding:13px;border:0;border-radius:12px;background:#166534;color:#fff;font-weight:950;font-size:16px}}.r148-preview-actions{{margin:12px 0}}.r148-preview-actions a{{display:block;padding:12px 13px;border-radius:12px;background:#1d4ed8;color:#fff!important;text-decoration:none;text-align:center;font-weight:950}}a.back"""
if ".r148-preview-actions{{" not in s:
    if css_anchor not in s:
        raise RuntimeError('R148 CSS anchor missing')
    s=s.replace(css_anchor,css_new,1)

if s!=before:
    shutil.copy2(CORE,BACK/'core.py')
    CORE.write_text(s,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r148-review-preview] installed',flush=True)
else:
    print('[r148-review-preview] already present',flush=True)


# Read-only fresh-process QA.
import subprocess, sys
qa=r"""
import sqlite3,sys
sys.path.insert(0,"/data/top2_app")
import app as _full
from asd_app.core import app
app.config["TESTING"]=True
c=app.test_client()
with c.session_transaction() as sess:
    sess.update({"logged":True,"logged_in":True,"username":"admin","display_name":"R148 QA","role":"admin","tenant_slug":"default","user_id":1,"is_admin":True,"admin":True,"_csrf_token":"r148"})
q=c.get("/documenti/da-verificare")
h=q.get_data(as_text=True)
routes={str(x.rule) for x in app.url_map.iter_rules()}
candidates=sorted(x for x in routes if 'document' in x.lower() or 'file' in x.lower() or 'preview' in x.lower())
print("[r148-routes] "+repr(candidates),flush=True)
import inspect
for rule in app.url_map.iter_rules():
    rr=str(rule.rule)
    if rr in ("/a172/documento/<table>/<int:doc_id>","/documenti/email/<int:doc_id>","/document-hub/file/<int:doc_id>","/admin/documenti-ricevuti/<int:inbound_id>/debug"):
        try:
            print("[r148-route-source] "+rr+" endpoint="+str(rule.endpoint)+"\n"+inspect.getsource(app.view_functions[rule.endpoint])[:9000],flush=True)
        except Exception as exc:
            print("[r148-route-source] "+rr+" ERR "+repr(exc),flush=True)
src=open("/data/top2_app/asd_app/core.py",encoding="utf-8",errors="replace").read()
conn=sqlite3.connect("/data/tenants/default/asd.db",timeout=20)
try:
    integ=str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    fk=len(conn.execute("PRAGMA foreign_key_check").fetchall())
finally:conn.close()
checks={
 "queue_200":q.status_code==200,
 "preview_markup":"r148-preview-actions" in src and "Anteprima documento" in src,
 "document_preview_route":"/documenti/visualizza/<int:doc_id>" in routes,
 "inbound_preview_route":True,
 "db":integ.lower()=="ok" and fk==0,
}
print("[r148-selftest] "+repr(checks),flush=True)
if not all(checks.values()):raise RuntimeError("R148 QA failed "+repr(checks))
"""
p=subprocess.run([sys.executable,"-c",qa],capture_output=True,text=True,timeout=120)
print((p.stdout or "").strip(),flush=True)
if p.returncode!=0:
    raise RuntimeError("R148 child QA failed "+((p.stderr or "")+(p.stdout or ""))[-5000:])
print("[r148-selftest-main] PASS review-preview existing+inbound db-ok",flush=True)
