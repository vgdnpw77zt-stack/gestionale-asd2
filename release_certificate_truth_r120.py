# -*- coding: utf-8 -*-
from __future__ import annotations
import py_compile, sqlite3, shutil
from datetime import datetime, date
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
BACK=Path('/data/release_backups/20261003_r120_certificate_truth')
BACK.mkdir(parents=True,exist_ok=True)
if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

def backup(p):
    p=Path(p); dst=BACK/p.name
    if p.exists() and not dst.exists(): shutil.copy2(p,dst)

def compile_file(p):
    py_compile.compile(str(p),doraise=True)

DESK=APP/'asd_app/routes_tesserati.py'
ds=DESK.read_text(encoding='utf-8',errors='replace')
old_d="""   _med=bool(c.execute(\"\"\"SELECT 1 FROM documenti WHERE tesserato_id=? AND COALESCE(visibile,1)=1
       AND LOWER(COALESCE(doc_type,''))='certificato_medico'
       AND LOWER(COALESCE(titolo,'')) NOT LIKE '%richiesta%' LIMIT 1\"\"\",(tesserato_id,)).fetchone())
   _cert_raw=str(r.get('certificato_scadenza') or '')
   _cert_ok=False; _cert_warn=False
   if _med:
       try:
           _exp=datetime.strptime(_cert_raw[:10],'%Y-%m-%d').date() if _cert_raw else None
           _cert_ok=bool(_exp and _exp>=_today)
           _cert_warn=not bool(_exp)
       except Exception:
           _cert_warn=True
"""
new_d="""   # BODYMIND_R120_CERTIFICATE_TRUTH
   _med=bool(c.execute(\"\"\"SELECT 1 FROM documenti WHERE tesserato_id=? AND COALESCE(visibile,1)=1
       AND LOWER(COALESCE(titolo,'')) NOT LIKE '%richiesta%'
       AND LOWER(COALESCE(categoria,'')) NOT LIKE '%richiesta%'
       AND (
         LOWER(COALESCE(doc_type,''))='certificato_medico'
         OR LOWER(COALESCE(categoria,'')) LIKE '%certificat%'
         OR LOWER(COALESCE(titolo,'')) LIKE '%certificat%'
         OR LOWER(COALESCE(original_filename,'')) LIKE '%certificat%'
       ) LIMIT 1\"\"\",(tesserato_id,)).fetchone())
   _cert_raw=str(r.get('certificato_scadenza') or '')
   _cert_ok=False; _cert_warn=False
   try:
       _exp=datetime.strptime(_cert_raw[:10],'%Y-%m-%d').date() if _cert_raw else None
       _cert_ok=bool(_exp and _exp>=_today)
       _cert_warn=bool(_med and not _exp)
   except Exception:
       _cert_warn=bool(_med)
"""
if old_d in ds:
    backup(DESK); ds=ds.replace(old_d,new_d,1); DESK.write_text(ds,encoding='utf-8'); compile_file(DESK)
elif 'BODYMIND_R120_CERTIFICATE_TRUTH' not in ds:
    raise RuntimeError('R120 desktop anchor missing')

matches=[]
for p in (APP/'asd_app').rglob('*.py'):
    try: s=p.read_text(encoding='utf-8',errors='replace')
    except Exception: continue
    if 'BODYMIND_R110_SIMPLE_MOBILE' in s and 'def fix12_mobile_atleta' in s:
        matches.append((p,s))
if len(matches)!=1:
    raise RuntimeError('R120 expected one mobile athlete source, got '+repr([str(x[0]) for x in matches]))
MOB,ms=matches[0]
old_m="""            _med=bool(conn.execute(\"\"\"SELECT 1 FROM documenti WHERE tesserato_id=? AND COALESCE(visibile,1)=1 AND LOWER(COALESCE(doc_type,''))='certificato_medico' AND LOWER(COALESCE(titolo,'')) NOT LIKE '%richiesta%' LIMIT 1\"\"\",(tid,)).fetchone())
            _cert=str(row['certificato_scadenza'] or '') if 'certificato_scadenza' in row.keys() else ''
            _certok=False
            if _med and _cert:
                try:_certok=datetime.strptime(_cert[:10],'%Y-%m-%d').date()>=_today
                except Exception:pass
"""
new_m="""            # BODYMIND_R120_CERTIFICATE_TRUTH
            _med=bool(conn.execute(\"\"\"SELECT 1 FROM documenti WHERE tesserato_id=? AND COALESCE(visibile,1)=1
              AND LOWER(COALESCE(titolo,'')) NOT LIKE '%richiesta%'
              AND LOWER(COALESCE(categoria,'')) NOT LIKE '%richiesta%'
              AND (
                LOWER(COALESCE(doc_type,''))='certificato_medico'
                OR LOWER(COALESCE(categoria,'')) LIKE '%certificat%'
                OR LOWER(COALESCE(titolo,'')) LIKE '%certificat%'
                OR LOWER(COALESCE(original_filename,'')) LIKE '%certificat%'
              ) LIMIT 1\"\"\",(tid,)).fetchone())
            _cert=str(row['certificato_scadenza'] or '') if 'certificato_scadenza' in row.keys() else ''
            _certok=False
            if _cert:
                try:_certok=datetime.strptime(_cert[:10],'%Y-%m-%d').date()>=_today
                except Exception:pass
"""
changed=False
if old_m in ms:
    backup(MOB); ms=ms.replace(old_m,new_m,1); changed=True
elif 'BODYMIND_R120_CERTIFICATE_TRUTH' not in ms:
    raise RuntimeError('R120 mobile anchor missing')
sorted_ms=ms.replace("SELECT * FROM tesserati ORDER BY cognome,nome","SELECT * FROM tesserati ORDER BY cognome COLLATE NOCASE,nome COLLATE NOCASE")
if sorted_ms!=ms: ms=sorted_ms; changed=True
if changed:
    MOB.write_text(ms,encoding='utf-8'); compile_file(MOB)

conn=sqlite3.connect(str(DB),timeout=30); conn.row_factory=sqlite3.Row
try:
    rows=conn.execute("SELECT id,nome,cognome,certificato_scadenza FROM tesserati ORDER BY cognome COLLATE NOCASE,nome COLLATE NOCASE").fetchall()
    valid=[]; malformed=[]
    for r in rows:
        raw=str(r['certificato_scadenza'] or '').strip()
        if not raw: continue
        try:
            exp=datetime.strptime(raw[:10],'%Y-%m-%d').date()
            if exp>=date.today(): valid.append({'id':int(r['id']),'name':(str(r['cognome'] or '')+' '+str(r['nome'] or '')).strip(),'expiry':raw[:10]})
        except Exception:
            malformed.append({'id':int(r['id']),'value':raw})
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0]); fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:
    conn.close()

desk_now=DESK.read_text(encoding='utf-8',errors='replace'); mob_now=MOB.read_text(encoding='utf-8',errors='replace')
checks={
 'desktop_truth':'BODYMIND_R120_CERTIFICATE_TRUTH' in desk_now and "_cert_ok=bool(_exp and _exp>=_today)" in desk_now,
 'mobile_truth':'BODYMIND_R120_CERTIFICATE_TRUTH' in mob_now and "if _cert:" in mob_now,
 'surname_sort':'ORDER BY cognome COLLATE NOCASE,nome COLLATE NOCASE' in mob_now,
 'db_ok':integrity.lower()=='ok' and fk==0,
}
print('[r120-audit] valid_future_certificates='+repr(valid)+' malformed='+repr(malformed),flush=True)
print('[r120-checks] '+repr(checks)+' integrity='+integrity+' fk='+str(fk),flush=True)
bad=[k for k,v in checks.items() if not v]
if bad: raise RuntimeError('R120 failed '+repr(bad))
print('[r120-selftest] PASS certificate-expiry truth desktop+mobile surname-sort db-ok',flush=True)
