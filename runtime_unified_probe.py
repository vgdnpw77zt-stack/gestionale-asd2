from pathlib import Path
import sqlite3, re, json
APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
print('[unified-probe] BEGIN', flush=True)
if DB.exists():
    c=sqlite3.connect(str(DB)); c.row_factory=sqlite3.Row
    try:
        for table in ('tesserati','minori','onboarding_document_requests','inbound_documents','documenti'):
            ok=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()
            if ok:
                cols=[x[1] for x in c.execute("PRAGMA table_info("+table+")").fetchall()]
                print('[unified-probe] COLUMNS '+table+'='+json.dumps(cols,ensure_ascii=False),flush=True)
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='minori'").fetchone():
            cols=[x[1] for x in c.execute("PRAGMA table_info(minori)").fetchall()]
            wanted=[x for x in cols if any(k in x.lower() for k in ('consens','privacy','immagin','foto','tutela','genitor','minor','liberatoria'))]
            print('[unified-probe] MINORI_RELEVANT='+json.dumps(wanted,ensure_ascii=False),flush=True)
            if wanted:
                q="SELECT tesserato_id,"+",".join(wanted)+" FROM minori ORDER BY tesserato_id"
                rows=[dict(r) for r in c.execute(q).fetchall()]
                print('[unified-probe] MINORI_ROWS='+json.dumps(rows,ensure_ascii=False),flush=True)
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='onboarding_document_requests'").fetchone():
            rows=[dict(r) for r in c.execute("SELECT * FROM onboarding_document_requests WHERE document_type='modulo_unico_tesseramento' ORDER BY tesserato_id").fetchall()]
            print('[unified-probe] MU_REQUESTS='+json.dumps(rows,ensure_ascii=False),flush=True)
    finally:
        c.close()
for p in APP.joinpath('asd_app').glob('*.py'):
    txt=p.read_text(encoding='utf-8',errors='replace')
    if re.search(r'consenso_firmato|liberatoria.?immagini|privacy|tutela.?minore|alert.*minor|minore.*alert',txt,re.I):
        print('[unified-probe] SOURCE '+p.name,flush=True)
        lines=txt.splitlines()
        for i,line in enumerate(lines,1):
            if re.search(r'consenso_firmato|liberatoria.?immagini|privacy|tutela.?minore|alert.*minor|minore.*alert',line,re.I):
                a=max(1,i-4); b=min(len(lines),i+6)
                for n in range(a,b+1):
                    print(f'[unified-probe] {p.name}:{n}:{lines[n-1][:1000]}',flush=True)
print('[unified-probe] END',flush=True)
