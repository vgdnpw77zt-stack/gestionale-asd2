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
# R120 is intentionally surgical: a valid canonical expiry can never be
# rendered as missing only because an older document row has a legacy type.
desktop_changed=False
if 'BODYMIND_R120_CERTIFICATE_TRUTH' not in ds:
    if "   if _med:\n       try:\n           _exp=datetime.strptime(_cert_raw[:10],'%Y-%m-%d').date() if _cert_raw else None" in ds:
        backup(DESK)
        ds=ds.replace(
            "   if _med:\n       try:\n           _exp=datetime.strptime(_cert_raw[:10],'%Y-%m-%d').date() if _cert_raw else None",
            "   # BODYMIND_R120_CERTIFICATE_TRUTH\n   if _cert_raw:\n       try:\n           _exp=datetime.strptime(_cert_raw[:10],'%Y-%m-%d').date() if _cert_raw else None",
            1
        )
        DESK.write_text(ds,encoding='utf-8'); compile_file(DESK); desktop_changed=True
    elif "if _med:\n" in ds and "_cert_raw=str(r.get('certificato_scadenza')" in ds:
        backup(DESK)
        pos=ds.find("_cert_raw=str(r.get('certificato_scadenza')")
        j=ds.find("if _med:",pos)
        if j<0: raise RuntimeError('R120 desktop cert condition missing')
        ds=ds[:j]+"# BODYMIND_R120_CERTIFICATE_TRUTH\n   if _cert_raw:"+ds[j+len("if _med:"):]
        DESK.write_text(ds,encoding='utf-8'); compile_file(DESK); desktop_changed=True
    else:
        print('[r120-desktop] warning: canonical simple desktop certificate block not found; mobile truth remains gated',flush=True)

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
if 'BODYMIND_R120_CERTIFICATE_TRUTH' not in ms:
    old_cond="            if _med and _cert:\n                try:_certok=datetime.strptime(_cert[:10],'%Y-%m-%d').date()>=_today"
    if old_cond not in ms:
        raise RuntimeError('R120 mobile certificate condition missing')
    backup(MOB)
    ms=ms.replace(
        old_cond,
        "            # BODYMIND_R120_CERTIFICATE_TRUTH\n            if _cert:\n                try:_certok=datetime.strptime(_cert[:10],'%Y-%m-%d').date()>=_today",
        1
    )
    changed=True
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
 'desktop_truth':("_cert_raw=str(r.get('certificato_scadenza')" in desk_now and ("BODYMIND_R120_CERTIFICATE_TRUTH" in desk_now or "if _cert_raw:" in desk_now)),
 'mobile_truth':'BODYMIND_R120_CERTIFICATE_TRUTH' in mob_now and "if _cert:" in mob_now,
 'surname_sort':'ORDER BY cognome COLLATE NOCASE,nome COLLATE NOCASE' in mob_now,
 'db_ok':integrity.lower()=='ok' and fk==0,
}
print('[r120-audit] valid_future_certificates='+repr(valid)+' malformed='+repr(malformed),flush=True)
print('[r120-checks] '+repr(checks)+' integrity='+integrity+' fk='+str(fk),flush=True)
bad=[k for k,v in checks.items() if not v]
if bad: raise RuntimeError('R120 failed '+repr(bad))
print('[r120-selftest] PASS certificate-expiry truth desktop+mobile surname-sort db-ok',flush=True)
