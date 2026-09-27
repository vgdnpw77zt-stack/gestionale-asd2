from pathlib import Path
import sqlite3, json, re
APP=Path('/data/top2_app'); DB=Path('/data/tenants/default/asd.db')
print('[simp2] BEGIN',flush=True)

# 1) counts first, before any source dump
if DB.exists():
    conn=sqlite3.connect(str(DB)); conn.row_factory=sqlite3.Row
    try:
        def table_exists(n):
            return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(n,)).fetchone())
        for table in ('documenti','inbound_documents','document_hub','signature_requests','document_signatures','firma_requests','onboarding_documents'):
            if not table_exists(table): continue
            cols=[r['name'] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]
            total=conn.execute(f'SELECT COUNT(*) n FROM "{table}"').fetchone()['n']
            print('[simp2] TABLE '+table+' total='+str(total)+' cols='+','.join(cols),flush=True)
            for col in ('status','stato','signature_status','document_type','doc_type','confidence','document_confidence','visibile'):
                if col in cols:
                    rows=conn.execute(f'SELECT COALESCE(CAST("{col}" AS TEXT),"<NULL>") v,COUNT(*) n FROM "{table}" GROUP BY "{col}" ORDER BY n DESC').fetchall()
                    print('[simp2] GROUP '+table+'.'+col+' '+json.dumps([dict(x) for x in rows],ensure_ascii=False),flush=True)
        # explicit likely pending counts
        if table_exists('documenti'):
            cols={r['name'] for r in conn.execute('PRAGMA table_info("documenti")').fetchall()}
            clauses=[]
            if 'status' in cols: clauses.append("lower(coalesce(status,'')) in ('da_verificare','needs_review','richiede_conferma','associato_tipo_da_verificare','review','pending')")
            if 'confidence' in cols: clauses.append("coalesce(confidence,0) < 100")
            if 'inbound_id' in cols: clauses.append("inbound_id is not null")
            if clauses:
                # informational combinations, not one authoritative metric
                for label,where in [
                    ('documenti_status_pending',clauses[0] if clauses else '0'),
                    ('documenti_conf_lt100',"coalesce(confidence,0)<100" if 'confidence' in cols else '0'),
                    ('documenti_inbound_linked',"inbound_id is not null" if 'inbound_id' in cols else '0')
                ]:
                    try: print('[simp2] COUNT '+label+'='+str(conn.execute('SELECT COUNT(*) FROM documenti WHERE '+where).fetchone()[0]),flush=True)
                    except Exception: pass
        if table_exists('inbound_documents'):
            print('[simp2] COUNT inbound_needs_action='+str(conn.execute("""SELECT COUNT(*) FROM inbound_documents WHERE lower(coalesce(status,'')) NOT IN ('associato','confermato','ok','verified','verificato','archiviato','deleted','eliminato') OR coalesce(document_confidence,0)<100""").fetchone()[0]),flush=True)
    finally:
        conn.close()

# 2) show exact metric logic + hub implementations + menu document links
targets=[
 ('asd_app/routes_a202_operational_integrity.py',1,120),
 ('asd_app/routes_a158_total_audit_fix.py',1,330),
 ('asd_app/routes_a159_total_audit_fix.py',200,330),
 ('asd_app/routes_a168_document_hub.py',120,380),
 ('asd_app/routes_a172_document_hub.py',1,380),
 ('asd_app/routes_goldmaster_ux.py',80,180),
 ('asd_app/core.py',1,420),
]
for rel,a,b in targets:
    p=APP/rel
    if not p.exists():
        print('[simp2] MISSING '+rel,flush=True); continue
    lines=p.read_text(encoding='utf-8',errors='replace').splitlines()
    print(f'[simp2] TARGET {rel} {a}-{min(b,len(lines))}',flush=True)
    for n in range(a,min(b,len(lines))+1):
        line=lines[n-1]
        low=line.lower()
        keep=False
        if rel.endswith('routes_a202_operational_integrity.py'): keep=True
        elif any(k in low for k in ('@app.route','@app.get','@app.post','def ','document-hub','verificare','da verificare','labels =','counts','a158-tabs','a159','a168','archive','timeline','apri','firma','upload','sidebar','nav-link','documenti-automatici','generatore-documenti','in-attesa','firma-smart')):
            keep=True
        if keep:
            print(f'[simp2] {rel}:{n}:{line[:900]}',flush=True)

# 3) collect all user-facing menu/navigation links related to documents
for p in sorted(APP.rglob('*.py')):
    try: lines=p.read_text(encoding='utf-8',errors='replace').splitlines()
    except Exception: continue
    for n,line in enumerate(lines,1):
        low=line.lower()
        if ('href=' in low or 'nav' in low or 'sidebar' in low) and any(k in low for k in ('/document','firma','generatore-documenti','documenti-automatici','in-attesa')):
            if any(k in low for k in ('href','sidebar','nav-item','nav-link')):
                print(f'[simp2] NAV {p.relative_to(APP)}:{n}:{line[:800]}',flush=True)
print('[simp2] END',flush=True)
