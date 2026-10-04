# -*- coding: utf-8 -*-
import sqlite3, sys
from pathlib import Path
DB=Path('/data/tenants/default/asd.db')
c=sqlite3.connect(str(DB),timeout=20); c.row_factory=sqlite3.Row
try:
    courses=[dict(x) for x in c.execute("SELECT * FROM corsi ORDER BY id").fetchall()]
    sample=[dict(x) for x in c.execute("SELECT id,nome,cognome,corso FROM tesserati ORDER BY cognome,nome LIMIT 50").fetchall()]
    pres=[dict(x) for x in c.execute("SELECT corso_id,COUNT(*) n FROM presenze GROUP BY corso_id ORDER BY corso_id").fetchall()]
    print('[r132-courses] '+repr(courses),flush=True)
    print('[r132-athlete-courses] '+repr(sample),flush=True)
    print('[r132-presence-by-course] '+repr(pres),flush=True)
    print('[r132-db] '+str(c.execute("PRAGMA integrity_check").fetchone()[0])+' fk='+str(len(c.execute("PRAGMA foreign_key_check").fetchall())),flush=True)
finally:c.close()
