# -*- coding: utf-8 -*-
from pathlib import Path
import sqlite3
APP=Path("/data/top2_app")
DB=Path("/data/tenants/default/asd.db")
p=APP/"asd_app/routes_tesserati.py"
if not p.exists():
    raise RuntimeError("routes_tesserati.py missing")
s=p.read_text(encoding="utf-8",errors="replace")
start=-1
for needle in ('if action == "update"', "if action == 'update'", 'if action != "update"', "if action != 'update'"):
    i=s.find(needle)
    if i>=0:
        start=i; break
if start<0:
    raise RuntimeError("desktop update branch not found")
end=s.find("\n   if request.method == \"GET\"",start)
if end<0:end=min(len(s),start+14000)
print("[r105-desktop-update-source]\n"+s[max(0,start-2200):end],flush=True)
conn=sqlite3.connect(str(DB),timeout=20)
try:
    integrity=str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    fk=len(conn.execute("PRAGMA foreign_key_check").fetchall())
finally: conn.close()
print("[r105-selftest] PASS desktop-update-source audit integrity="+integrity+" fk="+str(fk),flush=True)
if integrity.lower()!="ok" or fk: raise RuntimeError("R105 DB check failed")
