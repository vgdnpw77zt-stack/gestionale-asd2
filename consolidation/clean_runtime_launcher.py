#!/usr/bin/env python3
"""BodyMind consolidated clean boot candidate.

NO legacy runpy migrations, automatic DB restore, archive cleanup or writes.
Refuses startup until a manifest from an isolated verified source snapshot matches.
THIS FILE IS STAGING ONLY; not wired into the production Dockerfile.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

TABLES=("tesserati","pagamenti","ricevute","documenti","quote_mensili")
SCHEMA="BODYMIND_SOURCE_LOCK_V1"

def source_inventory(root):
    root=Path(root).resolve(strict=True)
    candidates=list(root.glob("*.py")) + list((root/"asd_app").rglob("*.py"))
    result={}
    for p in sorted(set(candidates)):
        if not p.is_file() or p.is_symlink():
            raise RuntimeError("Invalid or symlinked source: "+p.name)
        parts=p.relative_to(root).parts
        if any(q.startswith(".") or q=="__pycache__" for q in parts):
            continue
        relative=p.relative_to(root).as_posix()
        body=p.read_bytes()
        if len(body)>5_000_000: raise RuntimeError("Unexpectedly large source: "+relative)
        compile(body,relative,"exec")
        result[relative]=hashlib.sha256(body).hexdigest()
    return result

def read_lockfile(path):
    obj=json.loads(Path(path).read_text("utf-8"))
    if obj.get("format")!=SCHEMA or not isinstance(obj.get("files"),dict):
        raise RuntimeError("Missing or untrusted source lockfile format")
    files=obj["files"]
    if len(files)<30 or len(files)>1500:
        raise RuntimeError("Incomplete or unusually large source lockfile")
    for name,sha in files.items():
        if not isinstance(name,str) or not name.endswith(".py") or name.startswith("/") or ".." in Path(name).parts:
            raise RuntimeError("Invalid source lockfile path")
        if not isinstance(sha,str) or len(sha)!=64 or any(c not in "0123456789abcdef" for c in sha):
            raise RuntimeError("Invalid source SHA256")
    return files

def validate_database(db_path):
    path=Path(db_path).resolve(strict=True)
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("Missing or unsafe DB path")
    # Never invoke a recovery or create a missing SQLite file.
    con=sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=20)
    try:
        con.execute("PRAGMA query_only=ON")
        state=con.execute("PRAGMA integrity_check").fetchone()[0]
        if state!="ok": raise RuntimeError("SQLite integrity failure; manual restore required")
        fk=con.execute("PRAGMA foreign_key_check").fetchall()
        if fk: raise RuntimeError("SQLite foreign-key violations: "+str(len(fk)))
        rows={}
        for table in TABLES:
            if con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone() is None:
                raise RuntimeError("Missing table: "+table)
            rows[table]=int(con.execute('SELECT COUNT(*) FROM "'+table+'"').fetchone()[0])
        return rows
    finally:
        con.close()

def preflight(root,db_path,manifest_path):
    root=Path(root).resolve(strict=True)
    if not (root/".TOP2_OFFICIAL").is_file() or not (root/"app.py").is_file():
        raise RuntimeError("BodyMind official source root absent")
    expected=read_lockfile(manifest_path)
    actual=source_inventory(root)
    if actual!=expected:
        missing=sorted(set(expected)-set(actual))
        extra=sorted(set(actual)-set(expected))
        changed=sorted(p for p in expected.keys()&actual.keys() if expected[p]!=actual[p])
        # Do not disclose code contents or paths containing tokens.
        raise RuntimeError("Source lock mismatch: missing="+str(len(missing))+
            ", unexpected="+str(len(extra))+", changed="+str(len(changed)))
    counts=validate_database(db_path)
    return {"source_files":len(actual),"db_integrity":"ok","tables":counts,
            "legacy_migrations_executed":0,"auto_cleanup":False,"auto_database_restore":False}

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("mode",choices=["check","start"])
    parser.add_argument("--root",default="/data/top2_app")
    parser.add_argument("--db",default="/data/tenants/default/asd.db")
    parser.add_argument("--manifest",required=True)
    options=parser.parse_args(argv)
    try:
        info=preflight(options.root,options.db,options.manifest)
    except (ValueError,OSError,RuntimeError,sqlite3.DatabaseError) as exc:
        print("BODYMIND CLEAN BOOT STOP: "+str(exc),file=sys.stderr,flush=True)
        return 2
    print("BODYMIND CLEAN BOOT PASS "+json.dumps(info,sort_keys=True),flush=True)
    if options.mode=="check":return 0
    os.chdir(str(Path(options.root).resolve()))
    port=os.environ.get("PORT","8080")
    if not port.isdigit() or not (1<=int(port)<=65535):
        print("BODYMIND CLEAN BOOT STOP: invalid port",file=sys.stderr)
        return 2
    os.execvp("gunicorn",[
        "gunicorn","--bind","0.0.0.0:"+port,"--workers","1","--threads","4",
        "--timeout","300","--access-logfile","-","--error-logfile","-","app:app"])
    return 0

if __name__=="__main__":
    raise SystemExit(main())
