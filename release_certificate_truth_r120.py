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

# Safety: if an earlier failed R120 left the persistent desktop route damaged,
# restore the known-good pre-R120 copy. R120 no longer rewrites desktop control
# flow; the user-facing bug is on the mobile athlete card shown in production.
DESK=APP/'asd_app/routes_tesserati.py'
try:
    compile_file(DESK)
except Exception:
    candidate=BACK/'routes_tesserati.py'
    if not candidate.exists():
        raise
    shutil.copy2(candidate,DESK)
    compile_file(DESK)
    print('[r120-recovery] restored valid routes_tesserati.py',flush=True)

# Locate the canonical mobile athlete source created by R110.
matches=[]
for p in (APP/'asd_app').rglob('*.py'):
    try: s=p.read_text(encoding='utf-8',errors='replace')
    except Exception: continue
    if 'BODYMIND_R110_SIMPLE_MOBILE' in s and 'def fix12_mobile_atleta' in s:
        matches.append((p,s))
if len(matches)!=1:
    raise RuntimeError('R120 expected one mobile athlete source, got '+repr([str(x[0]) for x in matches]))
MOB,ms=matches[0]
changed=False
marker='BODYMIND_R120_CERTIFICATE_TRUTH'

# Fix the exact contradiction shown in production:
# a valid persisted expiry must not be rendered as "Manca" only because
# an older document row has a legacy/non-canonical doc_type.
if marker not in ms:
    old="            if _med and _cert:\n                try:_certok=datetime.strptime(_cert[:10],'%Y-%m-%d').date()>=_today"
    new="            # "+marker+"\n            if _cert:\n                try:_certok=datetime.strptime(_cert[:10],'%Y-%m-%d').date()>=_today"
    if old not in ms:
        raise RuntimeError('R120 mobile certificate condition missing')
    backup(MOB)
    ms=ms.replace(old,new,1)
    changed=True

# Alphabetical athlete list by surname, then name, case-insensitive.
sorted_ms=ms.replace(
    "SELECT * FROM tesserati ORDER BY cognome,nome",
    "SELECT * FROM tesserati ORDER BY cognome COLLATE NOCASE,nome COLLATE NOCASE"
)
if sorted_ms!=ms:
    if not changed: backup(MOB)
    ms=sorted_ms
    changed=True

if changed:
    MOB.write_text(ms,encoding='utf-8')
compile_file(MOB)
compile_file(DESK)

# Audit canonical expiry data and explicitly surface Swanmy in deployment logs.
conn=sqlite3.connect(str(DB),timeout=30); conn.row_factory=sqlite3.Row
try:
    rows=conn.execute("SELECT id,nome,cognome,certificato_scadenza FROM tesserati ORDER BY cognome COLLATE NOCASE,nome COLLATE NOCASE").fetchall()
    valid=[]; malformed=[]; swanmy=[]
    for r in rows:
        raw=str(r['certificato_scadenza'] or '').strip()
        nm=(str(r['nome'] or '')+' '+str(r['cognome'] or '')).strip()
        if 'swanmy' in nm.lower():
            swanmy.append({'id':int(r['id']),'name':nm,'expiry':raw})
        if not raw: continue
        try:
            exp=datetime.strptime(raw[:10],'%Y-%m-%d').date()
            if exp>=date.today():
                valid.append({'id':int(r['id']),'name':nm,'expiry':raw[:10]})
        except Exception:
            malformed.append({'id':int(r['id']),'value':raw})
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:
    conn.close()

mob_now=MOB.read_text(encoding='utf-8',errors='replace')
checks={
 'mobile_truth':marker in mob_now and "if _cert:" in mob_now,
 'surname_sort':'ORDER BY cognome COLLATE NOCASE,nome COLLATE NOCASE' in mob_now,
 'desktop_safe':True,
 'db_ok':integrity.lower()=='ok' and fk==0,
}
print('[r120-audit] swanmy='+repr(swanmy)+' valid_future_certificates='+repr(valid)+' malformed='+repr(malformed),flush=True)
print('[r120-checks] '+repr(checks)+' integrity='+integrity+' fk='+str(fk),flush=True)
bad=[k for k,v in checks.items() if not v]
if bad: raise RuntimeError('R120 failed '+repr(bad))
print('[r120-selftest] PASS mobile certificate-expiry truth surname-sort desktop-safe db-ok',flush=True)
