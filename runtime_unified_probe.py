from pathlib import Path
import sqlite3, json
APP=Path('/data/top2_app'); DB=Path('/data/tenants/default/asd.db')
print('[alert-probe] BEGIN',flush=True)
p=APP/'asd_app'/'routes_a151_final_ops.py'
if p.exists():
    lines=p.read_text(encoding='utf-8',errors='replace').splitlines()
    for n in range(1,min(180,len(lines))+1):
        print(f'[alert-probe] a151:{n}:{lines[n-1][:1400]}',flush=True)
if DB.exists():
    c=sqlite3.connect(str(DB)); c.row_factory=sqlite3.Row
    try:
        tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
        alert_tables=[t for t in tables if 'alert' in t.lower() or 'task' in t.lower() or 'review' in t.lower()]
        print('[alert-probe] TABLES='+json.dumps(alert_tables),flush=True)
        for t in alert_tables:
            cols=[r[1] for r in c.execute('PRAGMA table_info('+t+')').fetchall()]
            print('[alert-probe] COLS '+t+'='+json.dumps(cols),flush=True)
            try:
                if 'message_type' in cols:
                    rows=[dict(r) for r in c.execute("SELECT * FROM "+t+" WHERE lower(coalesce(message_type,'')) LIKE '%minore%' ORDER BY id DESC LIMIT 50").fetchall()]
                    print('[alert-probe] MINOR '+t+'='+json.dumps(rows,ensure_ascii=False),flush=True)
                elif 'category' in cols:
                    rows=[dict(r) for r in c.execute("SELECT * FROM "+t+" WHERE lower(coalesce(category,'')) LIKE '%minor%' ORDER BY id DESC LIMIT 50").fetchall()]
                    print('[alert-probe] MINOR '+t+'='+json.dumps(rows,ensure_ascii=False),flush=True)
            except Exception as e:
                print('[alert-probe] ERR '+t+'='+repr(e),flush=True)
    finally:c.close()
print('[alert-probe] END',flush=True)
