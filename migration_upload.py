#!/usr/bin/env python3
import os, sys, json, shutil, zipfile, tempfile, hashlib, sqlite3, time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DATA = Path(os.environ.get("ASD_PRO_DATA_DIR", "/data")).resolve()
TOKEN = os.environ.get("BODYMIND_MIGRATION_TOKEN", "").strip()
MAX_BYTES = 600 * 1024 * 1024

def sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1024*1024), b""): h.update(b)
    return h.hexdigest()

def db_check(path):
    con=sqlite3.connect(str(path))
    try:
        integrity=con.execute("PRAGMA integrity_check").fetchone()[0]
        count=con.execute("SELECT COUNT(*) FROM tesserati").fetchone()[0]
        return {"integrity":integrity,"tesserati":count,"bytes":path.stat().st_size}
    finally: con.close()

def safe_extract(zf, dest):
    dest=dest.resolve()
    for m in zf.infolist():
        target=(dest / m.filename).resolve()
        if not str(target).startswith(str(dest)+os.sep) and target != dest:
            raise RuntimeError("unsafe zip path")
    zf.extractall(dest)

def locate_app(root):
    direct=root/"SVILUPPATORE"/"APP"
    if direct.is_dir() and (direct/"app.py").exists(): return direct
    candidates=[]
    for p in root.rglob("APP"):
        if p.is_dir() and (p/"app.py").exists() and p.parent.name=="SVILUPPATORE":
            candidates.append(p)
    if not candidates:
        for p in root.rglob("app.py"):
            if (p.parent/"asd_app").is_dir(): candidates.append(p.parent)
    if not candidates: raise RuntimeError("Top2 APP root not found")
    return candidates[0]

def atomic_install_app(zip_path):
    stage=Path(tempfile.mkdtemp(prefix="top2_app_", dir=str(DATA)))
    try:
        with zipfile.ZipFile(zip_path) as z: safe_extract(z, stage)
        src=locate_app(stage)
        if not (src/"asd_app").is_dir(): raise RuntimeError("invalid Top2 app")
        target=DATA/"top2_app"
        backup_root=DATA/"migration_backups"; backup_root.mkdir(parents=True, exist_ok=True)
        if target.exists():
            old=backup_root/f"top2_app_before_{int(time.time())}"
            target.rename(old)
        shutil.copytree(src, target, dirs_exist_ok=True)
        marker=target/".TOP2_OFFICIAL"
        marker.write_text("Top2 official Railway runtime\n", encoding="utf-8")
        return {"app_path":str(target),"files":sum(1 for p in target.rglob("*") if p.is_file())}
    finally:
        shutil.rmtree(stage, ignore_errors=True)

def restore_backup(zip_path):
    stage=Path(tempfile.mkdtemp(prefix="backup_restore_", dir=str(DATA)))
    backup_root=DATA/"migration_backups"; backup_root.mkdir(parents=True, exist_ok=True)
    stamp=str(int(time.time()))
    try:
        with zipfile.ZipFile(zip_path) as z: safe_extract(z, stage)
        srcdb=stage/"tenants"/"default"/"asd.db"
        if not srcdb.exists(): raise RuntimeError("backup missing tenants/default/asd.db")
        check=db_check(srcdb)
        if check["integrity"]!="ok": raise RuntimeError("backup DB integrity failed")
        live_tenant=DATA/"tenants"/"default"
        if live_tenant.exists():
            shutil.copytree(live_tenant, backup_root/f"tenant_before_restore_{stamp}", dirs_exist_ok=True)
        for rel in ["tenants","media","user_static","onboarding_docs","signatures","pdf","database"]:
            src=stage/rel
            if src.exists():
                dst=DATA/rel
                if dst.exists(): shutil.rmtree(dst)
                shutil.copytree(src,dst)
        for rel in ["asd.db"]:
            src=stage/rel
            if src.exists(): shutil.copy2(src, DATA/rel)
        live=DATA/"tenants"/"default"/"asd.db"
        final=db_check(live)
        marker=DATA/".TOP2_BACKUP_RESTORED"
        marker.write_text(json.dumps({"at":time.time(),"sha256":sha256(live),"db":final},ensure_ascii=False),encoding="utf-8")
        return {"db":final,"db_sha256":sha256(live)}
    finally:
        shutil.rmtree(stage, ignore_errors=True)

class H(BaseHTTPRequestHandler):
    protocol_version="HTTP/1.1"
    def out(self,status,obj):
        b=json.dumps(obj,ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
    def auth(self):
        return TOKEN and self.headers.get("Authorization","")==f"Bearer {TOKEN}"
    def do_GET(self):
        if self.path=="/health":
            return self.out(200,{"ok":True,"mode":"migration","data":str(DATA)})
        if self.path=="/status":
            if not self.auth(): return self.out(403,{"ok":False})
            live=DATA/"tenants"/"default"/"asd.db"
            return self.out(200,{"ok":True,"top2":(DATA/"top2_app"/".TOP2_OFFICIAL").exists(),
                "backup_restored":(DATA/".TOP2_BACKUP_RESTORED").exists(),
                "db":db_check(live) if live.exists() else None})
        self.out(404,{"ok":False})
    def do_POST(self):
        if not self.auth(): return self.out(403,{"ok":False,"error":"forbidden"})
        if self.path not in ("/upload-app","/upload-backup"): return self.out(404,{"ok":False})
        try: n=int(self.headers.get("Content-Length","0"))
        except: n=0
        if n<=0 or n>MAX_BYTES: return self.out(413,{"ok":False,"error":"invalid size"})
        incoming=DATA/"incoming"; incoming.mkdir(parents=True, exist_ok=True)
        tmp=incoming/(("top2.zip" if self.path=="/upload-app" else "backup.zip")+".part")
        with open(tmp,"wb") as f:
            remaining=n
            while remaining:
                chunk=self.rfile.read(min(1024*1024,remaining))
                if not chunk: raise RuntimeError("short upload")
                f.write(chunk); remaining-=len(chunk)
        final=tmp.with_suffix("")
        os.replace(tmp,final)
        if not zipfile.is_zipfile(final): return self.out(400,{"ok":False,"error":"not zip"})
        result=atomic_install_app(final) if self.path=="/upload-app" else restore_backup(final)
        self.out(200,{"ok":True,"sha256":sha256(final),**result})
    def log_message(self,fmt,*args): sys.stdout.write("[migration] "+fmt%args+"\n"); sys.stdout.flush()

if __name__=="__main__":
    if not TOKEN:
        raise SystemExit("BODYMIND_MIGRATION_TOKEN missing")
    DATA.mkdir(parents=True, exist_ok=True)
    port=int(os.environ.get("PORT","8080"))
    print(f"migration server on {port}, data={DATA}", flush=True)
    ThreadingHTTPServer(("0.0.0.0",port),H).serve_forever()
