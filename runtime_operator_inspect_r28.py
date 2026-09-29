from __future__ import annotations
from pathlib import Path
import inspect, os, sqlite3, sys

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MARKER=APP/'.BODYMIND_OPERATOR_INSPECT_R28'

def out(tag,val):
    print('[operator-inspect-r28-'+tag+'] '+repr(val),flush=True)

if MARKER.exists():
    out('skip','already done')
    raise SystemExit(0)

def snippet(rel, needles, context=10, max_items=30):
    p=APP/rel
    if not p.exists():
        return {'missing':rel}
    lines=p.read_text(encoding='utf-8',errors='replace').splitlines()
    blocks=[]
    for i,line in enumerate(lines):
        if any(n in line for n in needles):
            a=max(0,i-context); b=min(len(lines),i+context+1)
            blocks.append({'line':i+1,'text':'\n'.join(f'{j+1}:{lines[j]}' for j in range(a,b))})
            if len(blocks)>=max_items: break
    return blocks

out('app-py',snippet('app.py',['from asd_app','import asd_app','register','routes_','Flask('],12,40))
out('core-auth',snippet('asd_app/core.py',['def auth(','def current','session.get(','def login_required','def admin_required','def csrf_input','def layout('],8,50))
out('email-docs',snippet('asd_app/routes_email_documents.py',['def process_inbound_attachment','def ','@app.','inbound_documents','saved_path'],8,60))
out('document-upload',snippet('asd_app/routes_documenti.py',['upload','carica','inbound_documents','documenti-automatici'],8,60))
out('quote-routes',snippet('asd_app/routes_quote_incassi.py',['@app.','def ','quota','sconto','pagamento'],6,80))
out('receipts',snippet('asd_app/routes_ricevute.py',['@app.','def ','ricevut','email'],6,80))

conn=sqlite3.connect(str(DB),timeout=20)
conn.row_factory=sqlite3.Row
try:
    for table in ('users','tesserati','inbound_documents','documenti','pagamenti','ricevute','quote_tesserati','quote','incassi','onboarding_document_requests'):
        row=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()
        if not row:
            out('schema-'+table,'missing')
            continue
        info=conn.execute('PRAGMA table_info('+table+')').fetchall()
        out('schema-'+table,[(r[1],r[2],r[3],r[4]) for r in info])
        try:
            sample=conn.execute('SELECT * FROM '+table+' LIMIT 2').fetchall()
            safe=[]
            for s in sample:
                d={}
                for k in s.keys():
                    lk=k.lower()
                    if any(x in lk for x in ('password','token','secret','hash')):
                        d[k]='<redacted>'
                    else:
                        v=s[k]
                        d[k]=v if isinstance(v,(int,float,type(None))) else str(v)[:120]
                safe.append(d)
            out('sample-'+table,safe)
        except Exception as exc:
            out('sample-'+table,'ERR '+repr(exc))
finally:
    conn.close()

# Import runtime and inspect endpoint names for useful canonical actions.
os.chdir(APP); sys.path.insert(0,str(APP))
try:
    import app as app_module
    fa=app_module.app
    useful=[]
    for r in fa.url_map.iter_rules():
        rule=str(r.rule)
        if any(x in rule for x in ('quote','incass','ricevut','document','tesserat','famigl','certificat','onboarding','firma','operativ')):
            useful.append((rule,str(r.endpoint),tuple(sorted(m for m in r.methods if m not in ('HEAD','OPTIONS')))))
    out('useful-routes',useful[:250])
except Exception as exc:
    out('app-import-error',repr(exc))

MARKER.write_text('done\n',encoding='utf-8')
out('done','PASS')
