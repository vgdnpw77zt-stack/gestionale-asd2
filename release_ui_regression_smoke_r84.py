# -*- coding: utf-8 -*-
from __future__ import annotations
import json, sqlite3, subprocess, sys

code=r'''
import inspect, json, re, sqlite3, sys
sys.path.insert(0,"/data/top2_app")
import app as _full_app
from asd_app.core import app

DB="/data/tenants/default/asd.db"
conn=sqlite3.connect(DB,timeout=20); conn.row_factory=sqlite3.Row
try:
    mu_tids=[int(x[0]) for x in conn.execute("""SELECT DISTINCT tesserato_id FROM documenti
      WHERE coalesce(visibile,1)=1 AND coalesce(tesserato_id,0)>0
        AND (lower(coalesce(doc_type,''))='modulo_unico_tesseramento'
          OR lower(coalesce(categoria,'')) LIKE '%modulo iscrizione%'
          OR lower(coalesce(titolo,'')) LIKE '%modulo unico%'
          OR lower(coalesce(titolo,'')) LIKE '%modulo_unico%')
      ORDER BY tesserato_id""").fetchall()]
    hidden=conn.execute("""SELECT id,tesserato_id FROM documenti
      WHERE coalesce(visibile,1)=0 ORDER BY id DESC LIMIT 20""").fetchall()
    guardian_tids=[]
    rows=conn.execute("SELECT * FROM tesserati ORDER BY id").fetchall()
    for a in rows:
        ks=set(a.keys()); tid=int(a["id"])
        minor=int(a["minorenne"] or 0)==1 if "minorenne" in ks else False
        guardian=""
        phone=""
        for k in ("genitore","nome_genitore"):
            if k in ks and a[k]:
                guardian=str(a[k]).strip()
                if guardian: break
        if "telefono_genitore" in ks and a["telefono_genitore"]:
            phone=str(a["telefono_genitore"]).strip()
        if minor and guardian and phone and tid in mu_tids:
            guardian_tids.append(tid)
finally:
    conn.close()

client=app.test_client()
with client.session_transaction() as s:
    s["logged"]=True
    s["username"]="admin"
    s["display_name"]="R84 QA"
    s["role"]="admin"
    s["tenant_slug"]="default"
    s["_csrf_token"]="r84"

iphone="Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
result={"operator_ui":False,"mobile_delete":False,"mu_pages":[],"guardian_pages":[],"hidden_docs":[]}
result["delete_routes"]=[
  {"rule":str(rule.rule),"endpoint":str(rule.endpoint),"methods":sorted(set(rule.methods or ())-{"HEAD","OPTIONS"})}
  for rule in app.url_map.iter_rules()
  if ("tesser" in (str(rule.rule)+" "+str(rule.endpoint)).lower())
     and any(x in (str(rule.rule)+" "+str(rule.endpoint)).lower() for x in ("elimina","delete","remove","cancella"))
]

for ep in ("fix12_mobile_atlete","tesserati_delete"):
    try:
        result[ep+"_source"]=inspect.getsource(app.view_functions[ep])[:12000]
    except Exception as exc:
        result[ep+"_source"]="ERR:"+repr(exc)

r=client.get("/operatore-bodymind",headers={"User-Agent":iphone},follow_redirects=True)
html=r.get_data(as_text=True)
result["operator_status"]=r.status_code
result["operator_ui"]=(r.status_code==200 and "BODYMIND_R74_IPHONE_COMPOSER" in html and "visualViewport" in html and "bmo-compose-shell" in html)

r=client.get("/tesserati",headers={"User-Agent":iphone},follow_redirects=True)
mhtml=r.get_data(as_text=True)
result["mobile_status"]=r.status_code
result["mobile_final_path"]=str(getattr(r.request,"path",""))
clean=re.sub(r"(?is)<style id=['\"]BODYMIND_R73_MOBILE_DELETE_VISIBILITY['\"].*?</script>","",mhtml)
actual_delete=bool(re.search(r"(?is)(?:action|href|data-action|onclick)\s*=\s*['\"][^'\"]*(?:elimina|delete|remove|cancella)|>\s*(?:elimina|cancella|rimuovi)\b",clean))
result["mobile_delete_control"]=actual_delete
result["mobile_delete"]=(r.status_code==200 and "BODYMIND_R73_MOBILE_DELETE_VISIBILITY" in mhtml and actual_delete)

# Exercise the real delete POST with an invalid id: must reach the route without mutating data.
rp=client.post("/tesserati/delete",data={"id":"0"},headers={"User-Agent":iphone},follow_redirects=False)
result["delete_post_status"]=rp.status_code
result["delete_post_body"]=rp.get_data(as_text=True)[:800]
result["delete_post_route_reachable"]=(rp.status_code in (302,303,400))
try:
    csrf_func=app.jinja_env.globals.get("csrf_input")
    result["csrf_global_present"]=bool(csrf_func)
    result["csrf_global_source"]=inspect.getsource(csrf_func)[:4000] if csrf_func else ""
except Exception as exc:
    result["csrf_global_source"]="ERR:"+repr(exc)
result["mobile_delete"]=bool(result["mobile_delete"] and result["delete_post_route_reachable"])
result["mobile_links"]=[x for x in re.findall(r"(?i)href\\s*=\\s*['\\\"]([^'\\\"]+)['\\\"]",clean) if any(k in x.lower() for k in ("tesser","atlet","scheda","profil"))][:80]
result["mobile_form_actions"]=re.findall(r"(?i)<form[^>]+action\\s*=\\s*['\\\"]([^'\\\"]+)['\\\"]",clean)[:80]
result["mobile_data_ids"]=re.findall(r"(?i)data-(?:id|tesserato-id|athlete-id)\\s*=\\s*['\\\"]?([^'\\\" >]+)",clean)[:80]
result["mobile_endpoint"]=""
try:
    adapter=app.url_map.bind("localhost")
    result["mobile_endpoint"]=str(adapter.match(result["mobile_final_path"],method="GET")[0])
except Exception as exc:
    result["mobile_endpoint"]="ERR:"+repr(exc)

for tid in mu_tids:
    rr=client.get("/documenti?tesserato_id="+str(tid),headers={"User-Agent":iphone},follow_redirects=True)
    h=rr.get_data(as_text=True)
    bad=("modulo unico non ancora generato" in h.lower())
    result["mu_pages"].append({"tid":tid,"status":rr.status_code,"false_missing_mu":bad})

for tid in guardian_tids:
    rr=client.get("/documenti?tesserato_id="+str(tid),headers={"User-Agent":iphone},follow_redirects=True)
    h=rr.get_data(as_text=True).lower()
    bad=("serve genitore" in h or "attenzione tutela minori" in h)
    result["guardian_pages"].append({"tid":tid,"status":rr.status_code,"false_guardian_alert":bad})

for row in hidden:
    did=int(row["id"]); tid=int(row["tesserato_id"] or 0)
    if tid<=0: continue
    rr=client.get("/documenti?tesserato_id="+str(tid),headers={"User-Agent":iphone},follow_redirects=True)
    h=rr.get_data(as_text=True)
    needle="/documenti/preview/"+str(did)
    result["hidden_docs"].append({"document_id":did,"tid":tid,"status":rr.status_code,"leaked":needle in h})

result["mu_false_alerts"]=[x for x in result["mu_pages"] if x["status"]!=200 or x["false_missing_mu"]]
result["guardian_false_alerts"]=[x for x in result["guardian_pages"] if x["status"]!=200 or x["false_guardian_alert"]]
result["hidden_leaks"]=[x for x in result["hidden_docs"] if x["status"]!=200 or x["leaked"]]
result["ok"]=bool(result["operator_ui"] and result["mobile_delete"] and not result["mu_false_alerts"] and not result["guardian_false_alerts"] and not result["hidden_leaks"])
print(json.dumps(result,ensure_ascii=False))
'''
p=subprocess.run([sys.executable,"-c",code],capture_output=True,text=True,timeout=120)
if p.returncode!=0:
    raise RuntimeError("R84 UI child failed: "+(p.stderr or p.stdout)[-2000:])
lines=[x for x in (p.stdout or "").splitlines() if x.strip()]
obj=json.loads(lines[-1])
print("[r84-ui-smoke] "+json.dumps(obj,ensure_ascii=False),flush=True)
if not obj.get("ok"):
    raise RuntimeError("R84 UI regression failed: "+json.dumps(obj,ensure_ascii=False))
print("[r84-selftest] PASS rendered-UI MU-alert guardian-alert hidden-doc mobile-delete iphone-composer",flush=True)
