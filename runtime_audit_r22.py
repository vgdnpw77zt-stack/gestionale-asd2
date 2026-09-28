from __future__ import annotations
from pathlib import Path
import compileall, sqlite3, re, sys, os

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MEDIA=Path('/data/tenants/default/media')
ACTIVE=('needs_manual_match','associato_tipo_da_verificare','richiede_conferma','needs_review','da_verificare','pending')

def cols(conn,t):
    return {r[1] for r in conn.execute(f'PRAGMA table_info({t})').fetchall()}

def has_table(conn,t):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone() is not None

print('[audit-r22] BEGIN',flush=True)
ok_compile=compileall.compile_dir(str(APP/'asd_app'),quiet=1)
print(f'[audit-r22] compileall={ok_compile}',flush=True)

conn=sqlite3.connect(str(DB),timeout=30); conn.row_factory=sqlite3.Row
try:
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=conn.execute('PRAGMA foreign_key_check').fetchall()
    tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
    print(f'[audit-r22] db_integrity={integrity} foreign_key_issues={len(fk)} tables={len(tables)}',flush=True)
    for t in ('tesserati','documenti','inbound_documents','pagamenti','ricevute','onboarding_document_requests','minori','users'):
        if has_table(conn,t):
            n=int(conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0])
            print(f'[audit-r22-table] {t}={n}',flush=True)

    if has_table(conn,'inbound_documents'):
        ic=cols(conn,'inbound_documents')
        vals=','.join('?' for _ in ACTIVE)
        pending=int(conn.execute(f"SELECT COUNT(*) FROM inbound_documents WHERE LOWER(COALESCE(status,'')) IN ({vals}) AND COALESCE(deleted_at,'')=''",ACTIVE).fetchone()[0])
        missing=int(conn.execute("SELECT COUNT(*) FROM inbound_documents WHERE LOWER(COALESCE(status,''))='file_missing' AND COALESCE(deleted_at,'')=''").fetchone()[0]) if 'deleted_at' in ic else 0
        dup=int(conn.execute("SELECT COUNT(*) FROM inbound_documents WHERE LOWER(COALESCE(status,''))='duplicate_exact'").fetchone()[0])
        deleted=int(conn.execute("SELECT COUNT(*) FROM inbound_documents WHERE LOWER(COALESCE(status,''))='deleted'").fetchone()[0])
        total=int(conn.execute("SELECT COUNT(*) FROM inbound_documents").fetchone()[0])
        physical_missing=[]
        rows=conn.execute("SELECT id,saved_path,status FROM inbound_documents WHERE COALESCE(deleted_at,'')='' AND LOWER(COALESCE(status,'')) NOT IN ('deleted','removed','cancelled','duplicate_exact')").fetchall()
        for r in rows:
            p=Path(str(r['saved_path'] or ''))
            if not p.is_file():
                physical_missing.append(int(r['id']))
        print(f'[audit-r22-inbound] total={total} pending={pending} file_missing_state={missing} duplicate_exact={dup} deleted={deleted} physical_missing={len(physical_missing)} ids={physical_missing[:30]}',flush=True)

    if has_table(conn,'documenti'):
        dc=cols(conn,'documenti')
        where="WHERE COALESCE(visibile,1)=1" if 'visibile' in dc else ''
        rows=conn.execute(f"SELECT id,filename FROM documenti {where}").fetchall()
        missing_docs=[int(r['id']) for r in rows if str(r['filename'] or '') and not Path(str(r['filename'])).is_file()]
        print(f'[audit-r22-documenti] visible={len(rows)} physical_missing={len(missing_docs)} ids={missing_docs[:30]}',flush=True)

    if has_table(conn,'tesserati'):
        tc=cols(conn,'tesserati')
        if {'nome','cognome'}.issubset(tc):
            dups=conn.execute("""SELECT lower(trim(nome)) n,lower(trim(cognome)) c,COUNT(*) k
                                 FROM tesserati GROUP BY lower(trim(nome)),lower(trim(cognome)) HAVING COUNT(*)>1""").fetchall()
            print(f'[audit-r22-tesserati] duplicate_name_groups={len(dups)}',flush=True)

    # Common orphan checks, only when the expected columns exist.
    orphan_checks=[]
    for table,col in [('documenti','tesserato_id'),('pagamenti','tesserato_id'),('inbound_documents','tesserato_id'),('minori','tesserato_id')]:
        if has_table(conn,table) and col in cols(conn,table) and has_table(conn,'tesserati'):
            n=int(conn.execute(f"SELECT COUNT(*) FROM {table} x LEFT JOIN tesserati t ON t.id=x.{col} WHERE COALESCE(x.{col},0)>0 AND t.id IS NULL").fetchone()[0])
            orphan_checks.append((table,n))
    print('[audit-r22-orphans] '+' '.join(f'{t}={n}' for t,n in orphan_checks),flush=True)
finally:
    conn.close()

# Route-map and literal action audit.
os.chdir(APP); sys.path.insert(0,str(APP))
import app as entry
flask_app=entry.app
rules=list(flask_app.url_map.iter_rules())
route_methods={}
for r in rules:
    for m in r.methods:
        if m in ('HEAD','OPTIONS'): continue
        route_methods.setdefault((r.rule,m),[]).append(r.endpoint)
duplicates=[(rule,method,eps) for (rule,method),eps in route_methods.items() if len(eps)>1]
critical=[
    ('/','GET'),('/mobile','GET'),('/documenti/da-verificare','GET'),('/documenti/file-mancanti','GET'),
    ('/documenti-automatici/file/<int:doc_id>','GET'),('/documenti/file/<int:doc_id>','GET')
]
missing_critical=[f'{m} {p}' for p,m in critical if (p,m) not in route_methods]
print(f'[audit-r22-routes] rules={len(rules)} duplicate_rule_methods={len(duplicates)} missing_critical={missing_critical}',flush=True)
for rule,method,eps in duplicates[:20]:
    print(f'[audit-r22-route-duplicate] {method} {rule} endpoints={eps}',flush=True)

literal_actions=set()
literal_hrefs=set()
pat_action=re.compile(r"""<form[^>]+method=['\"]post['\"][^>]+action=['\"](/[^'\"?#]+)['\"]""",re.I)
pat_href=re.compile(r"""href=['\"](/[^'\"?#]+)['\"]""",re.I)
for p in (APP/'asd_app').rglob('*.py'):
    try: s=p.read_text(encoding='utf-8',errors='ignore')
    except Exception: continue
    literal_actions.update(pat_action.findall(s))
    literal_hrefs.update(pat_href.findall(s))
route_paths={r.rule for r in rules}
unresolved_actions=sorted(a for a in literal_actions if '<' not in a and '{' not in a and a not in route_paths)
unresolved_hrefs=sorted(h for h in literal_hrefs if '<' not in h and '{' not in h and h not in route_paths)
print(f'[audit-r22-links] literal_post_actions={len(literal_actions)} unresolved_post_actions={len(unresolved_actions)} values={unresolved_actions[:30]}',flush=True)
print(f'[audit-r22-links] literal_hrefs={len(literal_hrefs)} unresolved_hrefs={len(unresolved_hrefs)} values={unresolved_hrefs[:30]}',flush=True)

print('[audit-r22] END',flush=True)
