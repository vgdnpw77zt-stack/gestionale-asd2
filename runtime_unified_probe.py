import sqlite3, json
from pathlib import Path
DB=Path('/data/tenants/default/asd.db')
print('[outbound-probe] BEGIN',flush=True)
if DB.exists():
    c=sqlite3.connect(str(DB)); c.row_factory=sqlite3.Row
    try:
        ok=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='outbound_messages'").fetchone()
        if ok:
            cols=[r[1] for r in c.execute("PRAGMA table_info(outbound_messages)").fetchall()]
            print('[outbound-probe] COLS='+json.dumps(cols),flush=True)
            rows=[dict(r) for r in c.execute("SELECT * FROM outbound_messages WHERE lower(coalesce(message_type,'')) LIKE '%minore%' ORDER BY id DESC LIMIT 100").fetchall()]
            print('[outbound-probe] ROWS='+json.dumps(rows,ensure_ascii=False),flush=True)
    finally:c.close()
print('[outbound-probe] END',flush=True)
