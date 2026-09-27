from pathlib import Path
import sqlite3, re, json
APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
print('[simp-probe] BEGIN', flush=True)

exact_terms=[
    'documenti da verificare','da verificare','Documenti automatici','Crea documento',
    'Firma documento','In attesa di firma','In attesa firma','Archivio documentale',
    'Archivio operativo','Documenti','dashboard','/documenti'
]
interesting=[]
for p in sorted(APP.rglob('*')):
    if not p.is_file() or p.suffix.lower() not in {'.py','.html','.js'}:
        continue
    try: lines=p.read_text(encoding='utf-8',errors='replace').splitlines()
    except Exception: continue
    hits=[]
    for i,line in enumerate(lines,1):
        low=line.lower()
        if any(t.lower() in low for t in exact_terms):
            if ('document' in low or 'firma' in low or 'dashboard' in low or 'sidebar' in low or 'archivio' in low):
                hits.append(i)
    if hits:
        interesting.append((p,lines,hits))

for p,lines,hits in interesting:
    rel=str(p.relative_to(APP))
    # keep only files most likely involved in dashboard/sidebar/document UX
    if not any(k in rel.lower() for k in ('dashboard','document','core','layout','sidebar','mobile','home','route')):
        continue
    print('[simp-probe] FILE '+rel, flush=True)
    emitted=set()
    for i in hits[:80]:
        a=max(1,i-5); b=min(len(lines),i+8)
        key=(a,b)
        if key in emitted: continue
        emitted.add(key)
        print(f'[simp-probe] CHUNK {rel}:{a}-{b}', flush=True)
        for n in range(a,b+1):
            txt=lines[n-1].replace('\t','    ')
            print(f'[simp-probe] {n}: {txt[:700]}', flush=True)

if DB.exists():
    conn=sqlite3.connect(str(DB)); conn.row_factory=sqlite3.Row
    try:
        tables=[r['name'] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
        for table in tables:
            low=table.lower()
            if not any(k in low for k in ('document','firma','sign','certif','inbound')):
                continue
            try:
                cols=[r['name'] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]
                total=conn.execute(f'SELECT COUNT(*) n FROM "{table}"').fetchone()['n']
                print('[simp-probe] TABLE '+table+' total='+str(total)+' cols='+','.join(cols), flush=True)
                for col in ('status','stato','document_type','doc_type','visibile','confidence','document_confidence','signed','verified'):
                    if col in cols:
                        rows=conn.execute(f'SELECT COALESCE(CAST("{col}" AS TEXT),"<NULL>") v, COUNT(*) n FROM "{table}" GROUP BY "{col}" ORDER BY n DESC LIMIT 30').fetchall()
                        print('[simp-probe] GROUP '+table+'.'+col+' '+json.dumps([dict(x) for x in rows],ensure_ascii=False), flush=True)
            except Exception as exc:
                print('[simp-probe] TABLEERR '+table+' '+repr(exc), flush=True)
    finally:
        conn.close()
print('[simp-probe] END', flush=True)
