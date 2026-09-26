from pathlib import Path
import sqlite3, re, json, hashlib

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
print('[angelucci-diag] begin', flush=True)

conn=sqlite3.connect(str(DB))
conn.row_factory=sqlite3.Row
try:
    people=conn.execute("SELECT id,nome,cognome FROM tesserati WHERE lower(cognome) LIKE '%angelucci%' ORDER BY id").fetchall()
    print('[angelucci-diag] matches='+json.dumps([dict(r) for r in people],ensure_ascii=False), flush=True)
    ids=[int(r['id']) for r in people]
    tables=[r['name'] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
    interesting=[t for t in tables if any(k in t.lower() for k in ('document','media','alleg','certificat','onboard','file','upload','inbound'))]
    print('[angelucci-diag] tables='+json.dumps(interesting,ensure_ascii=False), flush=True)
    for t in interesting:
        try:
            cols=[r['name'] for r in conn.execute("PRAGMA table_info("+t+")").fetchall()]
            print('[angelucci-diag] schema '+t+'='+json.dumps(cols,ensure_ascii=False), flush=True)
            if ids and any(c in cols for c in ('tesserato_id','atleta_id','associato_id')):
                fk='tesserato_id' if 'tesserato_id' in cols else ('atleta_id' if 'atleta_id' in cols else 'associato_id')
                qs=','.join('?' for _ in ids)
                rows=conn.execute("SELECT * FROM "+t+" WHERE "+fk+" IN ("+qs+") ORDER BY rowid DESC LIMIT 20",ids).fetchall()
                safe=[]
                for r in rows:
                    d=dict(r)
                    keep={}
                    for k,v in d.items():
                        if k in ('id',fk,'document_type','document_label','document_confidence','match_score','match_action','status','original_filename','saved_path','category','tipo','nome_file','filename','path','data_scadenza','created_at','updated_at'):
                            keep[k]=v
                    safe.append(keep)
                print('[angelucci-diag] rows '+t+'='+json.dumps(safe,ensure_ascii=False), flush=True)
        except Exception as exc:
            print('[angelucci-diag] table-error '+t+' '+type(exc).__name__, flush=True)
finally:
    conn.close()

terms=('def tesserato','/tesserato/','documenti','allegati','media','save_inbound_attachment','sync_medical_certificate_state','document_type')
for rel in ['asd_app/routes_inbound_documents.py','asd_app/routes_email_documents.py','asd_app/core.py','asd_app/routes_tesserati.py','asd_app/routes_documents.py']:
    p=APP/rel
    if not p.exists():
        continue
    lines=p.read_text(encoding='utf-8',errors='replace').splitlines()
    print('[angelucci-diag] file '+rel+' sha256='+hashlib.sha256(p.read_bytes()).hexdigest()[:16], flush=True)
    hit=set()
    for i,line in enumerate(lines):
        low=line.lower()
        if any(t.lower() in low for t in terms):
            for j in range(max(0,i-5),min(len(lines),i+12)):
                hit.add(j)
    groups=[]; cur=[]; prev=None
    for n in sorted(hit):
        if prev is None or n==prev+1:
            cur.append(n)
        else:
            groups.append(cur); cur=[n]
        prev=n
    if cur: groups.append(cur)
    for g in groups[:24]:
        pieces=[]
        for n in g:
            cleaned=' '.join(lines[n].strip().split())
            pieces.append(str(n+1)+':'+cleaned[:420])
        print('[angelucci-diag] '+rel+' range '+str(g[0]+1)+'-'+str(g[-1]+1)+': '+' || '.join(pieces), flush=True)

print('[angelucci-diag] end', flush=True)
