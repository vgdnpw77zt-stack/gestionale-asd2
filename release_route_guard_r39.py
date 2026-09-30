# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

APP = Path("/data/top2_app")
DB = Path("/data/tenants/default/asd.db")

if not APP.joinpath(".TOP2_OFFICIAL").exists():
    raise SystemExit("TOP2_OFFICIAL marker missing")

os.chdir(APP)
sys.path.insert(0, str(APP))

import app as app_module
flask_app = app_module.app

required = {
    ("/health", "GET"),
    ("/operatore-bodymind", "GET"),
    ("/operatore-bodymind/chat", "POST"),
    ("/operatore-bodymind/new-chat", "POST"),
    ("/operatore-bodymind/upload", "POST"),
    ("/operatore-bodymind/cloud/status", "GET"),
    ("/operatore-bodymind/voice/transcribe", "POST"),
    ("/operatore-bodymind/voice/speak", "POST"),
    ("/operatore-bodymind/cloud/usage/tts", "POST"),
    ("/operatore-bodymind/smtp/setup", "GET"),
    ("/operatore-bodymind/secure/smtp", "GET"),
    ("/operatore-bodymind/secure/smtp", "POST"),
}

pairs = {}
for rule in flask_app.url_map.iter_rules():
    for method in sorted(set(rule.methods or ()) - {"HEAD", "OPTIONS"}):
        pairs.setdefault((str(rule.rule), method), []).append(str(rule.endpoint))

problems = []
for key in sorted(required):
    endpoints = pairs.get(key, [])
    if len(endpoints) != 1:
        problems.append(f"critical-route:{key[1]} {key[0]} endpoints={endpoints}")

critical_paths = {path for path, _ in required}
for (path, method), endpoints in sorted(pairs.items()):
    if path in critical_paths and len(endpoints) > 1:
        problems.append(f"critical-duplicate:{method} {path} endpoints={endpoints}")

all_duplicates = [
    (path, method, endpoints)
    for (path, method), endpoints in sorted(pairs.items())
    if len(endpoints) > 1
]

integrity = "missing"
tesserati = -1
fk = -1
if DB.exists():
    conn = sqlite3.connect(str(DB), timeout=20)
    try:
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        fk = len(conn.execute("PRAGMA foreign_key_check").fetchall())
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tesserati'").fetchone():
            tesserati = int(conn.execute("SELECT COUNT(*) FROM tesserati").fetchone()[0])
    finally:
        conn.close()

if integrity.lower() != "ok" or fk != 0:
    problems.append(f"db-integrity:{integrity}:fk={fk}")

print(
    "[route-guard-r39] "
    f"routes={len(list(flask_app.url_map.iter_rules()))} "
    f"duplicates={len(all_duplicates)} db={integrity} fk={fk} tesserati={tesserati}",
    flush=True,
)
for path, method, endpoints in all_duplicates[:30]:
    print(
        f"[route-guard-r39-duplicate] {method} {path} endpoints={endpoints}",
        flush=True,
    )

if problems:
    for item in problems:
        print("[route-guard-r39-error] " + item, flush=True)
    raise RuntimeError("R39 route guard failed")

print("[route-guard-r39-selftest] PASS critical-routes unique db-ok", flush=True)
