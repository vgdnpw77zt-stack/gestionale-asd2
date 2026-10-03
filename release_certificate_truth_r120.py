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

def patch_med_assignment(src, conn_name, id_expr):
    # Do not rewrite control flow/indentation. Only make the existing _med
    # predicate true when the canonical profile already has an expiry date.
    # This preserves the proven R110 rendering code and avoids false "Manca".
    marker='BODYMIND_R120_CERTIFICATE_TRUTH'
    if marker in src:
        return src, False
    needle="_med=bool("+conn_name+".execute("
    pos=src.find(needle)
    if pos<0:
        return src, False
    end=src.find(").fetchone())",pos)
    if end<0:
        return src, False
    end += len(").fetchone())")
    original=src[pos:end]
    # Keep document evidence, but OR it with the canonical profile expiry.
    replacement=(
        "# "+marker+"\n"
        + original
        + " or bool("+conn_name+".execute(\"SELECT 1 FROM tesserati WHERE id=? "
          "AND TRIM(COALESCE(certificato_scadenza,''))<>'' LIMIT 1\",("+id_expr+",)).fetchone())"
    )
    return src[:pos]+replacement+src[end:], True

# Desktop canonical sheet. Recover a valid pre-R120 source first if a previous
# failed deployment left the persistent volume with a syntax-damaged file.
DESK=APP/'asd_app/routes_tesserati.py'
try:
    compile_file(DESK)
except Exception:
    candidate=BACK/'routes_tesserati.py'
    if not candidate.exists():
        raise
    shutil.copy2(candidate,DESK)
    compile_file(DESK)
    print('[r120-recovery] restored valid routes_tesserati.py from pre-R120 backup',flush=True)
ds=DESK.read_text(encoding='utf-8',errors='replace')
ds2,changed=patch_med_assignment(ds,'c','tesserato_id')
if changed:
    backup(DESK); DESK.write_text(ds2,encoding='utf-8'); compile_file(DESK)
elif 'BODYMIND_R120_CERTIFICATE_TRUTH' not in ds:
    raise RuntimeError('R120 desktop certificate assignment not found')

# Mobile canonical sheet + presentation-only surname ordering.
matches=[]
for p in (APP/'asd_app').rglob('*.py'):
    try: s=p.read_text(encoding='utf-8',errors='replace')
    except Exception: continue
    if 'BODYMIND_R110_SIMPLE_MOBILE' in s and 'def fix12_mobile_atleta' in s:
        matches.append((p,s))
if len(matches)!=1:
    raise RuntimeError('R120 expected one mobile athlete source, got '+repr([str(x[0]) for x in matches]))
MOB,ms=matches[0]
ms2,mchanged=patch_med_assignment(ms,'conn','tid')
ms2=ms2.replace("SELECT * FROM tesserati ORDER BY cognome,nome",
                "SELECT * FROM tesserati ORDER BY cognome COLLATE NOCASE,nome COLLATE NOCASE")
if ms2!=ms:
    backup(MOB); MOB.write_text(ms2,encoding='utf-8'); compile_file(MOB)
elif 'BODYMIND_R120_CERTIFICATE_TRUTH' not in ms:
    raise RuntimeError('R120 mobile certificate assignment not found')

# Data/format audit. Do not change certificate dates here.
conn=sqlite3.connect(str(DB),timeout=30); conn.row_factory=sqlite3.Row
try:
    rows=conn.execute("SELECT id,nome,cognome,certificato_scadenza FROM tesserati ORDER BY cognome COLLATE NOCASE,nome COLLATE NOCASE").fetchall()
    valid=[]; malformed=[]
    for r in rows:
        raw=str(r['certificato_scadenza'] or '').strip()
        if not raw: continue
        try:
            exp=datetime.strptime(raw[:10],'%Y-%m-%d').date()
            if exp>=date.today():
                valid.append({'id':int(r['id']),'name':(str(r['cognome'] or '')+' '+str(r['nome'] or '')).strip(),'expiry':raw[:10]})
        except Exception:
            malformed.append({'id':int(r['id']),'value':raw})
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:
    conn.close()

desk_now=DESK.read_text(encoding='utf-8',errors='replace')
mob_now=MOB.read_text(encoding='utf-8',errors='replace')
checks={
 'desktop_truth':'BODYMIND_R120_CERTIFICATE_TRUTH' in desk_now,
 'mobile_truth':'BODYMIND_R120_CERTIFICATE_TRUTH' in mob_now,
 'surname_sort':'ORDER BY cognome COLLATE NOCASE,nome COLLATE NOCASE' in mob_now,
 'db_ok':integrity.lower()=='ok' and fk==0,
}
print('[r120-audit] valid_future_certificates='+repr(valid)+' malformed='+repr(malformed),flush=True)
print('[r120-checks] '+repr(checks)+' integrity='+integrity+' fk='+str(fk),flush=True)
bad=[k for k,v in checks.items() if not v]
if bad: raise RuntimeError('R120 failed '+repr(bad))
print('[r120-selftest] PASS certificate-profile-truth desktop+mobile surname-sort db-ok',flush=True)
