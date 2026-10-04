from __future__ import annotations
import py_compile, shutil, sqlite3, subprocess, sys
from pathlib import Path

APP=Path('/data/top2_app')
BACK=Path('/data/release_backups/20261004_r139_truth')
BACK.mkdir(parents=True,exist_ok=True)

def patch_file(p):
    s=p.read_text(encoding='utf-8',errors='replace')
    before=s
    helper="""            def _r139_doc_exists(_fn):
                from pathlib import Path as _P
                _raw=_P(str(_fn or '').strip())
                _roots=[_P('/data/tenants/default/media'),_P('/data/top2_app/user_static'),_P('/data/top2_app/static'),_P('/data/top2_app'),_P('/data/tenants/default')]
                _cands=[_raw] if _raw.is_absolute() else [_root/_raw for _root in _roots]
                for _fp in _cands:
                    try:
                        if _fp.is_file(): return True
                    except Exception: pass
                return False
"""
    if "def _r139_doc_exists" not in s and "_mu=bool(conn.execute" in s:
        s=s.replace("            _mu=bool(conn.execute",helper+"            _mu=bool(conn.execute",1)
    if "def _r139_doc_exists" not in s and "__IND__   _mu=bool(c.execute" in s:
        helper2="""__IND__   def _r139_doc_exists(_fn):
__IND__       from pathlib import Path as _P
__IND__       _raw=_P(str(_fn or '').strip())
__IND__       _roots=[_P('/data/tenants/default/media'),_P('/data/top2_app/user_static'),_P('/data/top2_app/static'),_P('/data/top2_app'),_P('/data/tenants/default')]
__IND__       _cands=[_raw] if _raw.is_absolute() else [_root/_raw for _root in _roots]
__IND__       for _fp in _cands:
__IND__           try:
__IND__               if _fp.is_file(): return True
__IND__           except Exception: pass
__IND__       return False
"""
        s=s.replace("__IND__   _mu=bool(c.execute",helper2+"__IND__   _mu=bool(c.execute",1)

    # Mobile: DB presence alone is insufficient. Require an existing file for MU and medical.
    old_mu_mobile="""            _mu=bool(conn.execute("""SELECT 1 FROM documenti WHERE tesserato_id=? AND COALESCE(visibile,1)=1 AND (LOWER(COALESCE(doc_type,''))='modulo_unico_tesseramento' OR LOWER(COALESCE(categoria,'')) LIKE '%modulo iscrizione%' OR LOWER(COALESCE(titolo,'')) LIKE '%modulo unico%' OR LOWER(COALESCE(titolo,'')) LIKE '%domanda iscrizione%') LIMIT 1""",(tid,)).fetchone())"""
    new_mu_mobile="""            _mu_rows=conn.execute("""SELECT filename FROM documenti WHERE tesserato_id=? AND COALESCE(visibile,1)=1 AND (LOWER(COALESCE(doc_type,''))='modulo_unico_tesseramento' OR LOWER(COALESCE(categoria,'')) LIKE '%modulo iscrizione%' OR LOWER(COALESCE(titolo,'')) LIKE '%modulo unico%' OR LOWER(COALESCE(titolo,'')) LIKE '%domanda iscrizione%')""",(tid,)).fetchall()
            _mu=any(_r139_doc_exists(_r['filename']) for _r in _mu_rows)"""
    s=s.replace(old_mu_mobile,new_mu_mobile)
    old_med_mobile="""            _med=bool(conn.execute("""SELECT 1 FROM documenti WHERE tesserato_id=? AND COALESCE(visibile,1)=1 AND LOWER(COALESCE(doc_type,''))='certificato_medico' AND LOWER(COALESCE(titolo,'')) NOT LIKE '%richiesta%' LIMIT 1""",(tid,)).fetchone())"""
    new_med_mobile="""            _med_rows=conn.execute("""SELECT filename FROM documenti WHERE tesserato_id=? AND COALESCE(visibile,1)=1 AND LOWER(COALESCE(doc_type,''))='certificato_medico' AND LOWER(COALESCE(titolo,'')) NOT LIKE '%richiesta%'""",(tid,)).fetchall()
            _med=any(_r139_doc_exists(_r['filename']) for _r in _med_rows)"""
    s=s.replace(old_med_mobile,new_med_mobile)

    # Desktop equivalent.
    old_mu_d="""__IND__   _mu=bool(c.execute("""SELECT 1 FROM documenti WHERE tesserato_id=? AND COALESCE(visibile,1)=1 AND (
__IND__       LOWER(COALESCE(doc_type,''))='modulo_unico_tesseramento' OR
__IND__       LOWER(COALESCE(categoria,'')) LIKE '%modulo iscrizione%' OR
__IND__       LOWER(COALESCE(titolo,'')) LIKE '%modulo unico%' OR LOWER(COALESCE(titolo,'')) LIKE '%domanda iscrizione%'
__IND__   ) LIMIT 1""",(tesserato_id,)).fetchone())"""
    new_mu_d="""__IND__   _mu_rows=c.execute("""SELECT filename FROM documenti WHERE tesserato_id=? AND COALESCE(visibile,1)=1 AND (
__IND__       LOWER(COALESCE(doc_type,''))='modulo_unico_tesseramento' OR
__IND__       LOWER(COALESCE(categoria,'')) LIKE '%modulo iscrizione%' OR
__IND__       LOWER(COALESCE(titolo,'')) LIKE '%modulo unico%' OR LOWER(COALESCE(titolo,'')) LIKE '%domanda iscrizione%'
__IND__   )""",(tesserato_id,)).fetchall()
__IND__   _mu=any(_r139_doc_exists(_r['filename']) for _r in _mu_rows)"""
    s=s.replace(old_mu_d,new_mu_d)
    old_med_d="""__IND__   _med=bool(c.execute("""SELECT 1 FROM documenti WHERE tesserato_id=? AND COALESCE(visibile,1)=1
__IND__       AND LOWER(COALESCE(doc_type,''))='certificato_medico'
__IND__       AND LOWER(COALESCE(titolo,'')) NOT LIKE '%richiesta%' LIMIT 1""",(tesserato_id,)).fetchone())"""
    new_med_d="""__IND__   _med_rows=c.execute("""SELECT filename FROM documenti WHERE tesserato_id=? AND COALESCE(visibile,1)=1
__IND__       AND LOWER(COALESCE(doc_type,''))='certificato_medico'
__IND__       AND LOWER(COALESCE(titolo,'')) NOT LIKE '%richiesta%'""",(tesserato_id,)).fetchall()
__IND__   _med=any(_r139_doc_exists(_r['filename']) for _r in _med_rows)"""
    s=s.replace(old_med_d,new_med_d)

    if s!=before:
        shutil.copy2(p,BACK/p.name)
        p.write_text(s,encoding='utf-8')
        py_compile.compile(str(p),doraise=True)
        return True
    return False

patched=[]
for p in (APP/'asd_app').rglob('*.py'):
    try:
        if patch_file(p): patched.append(str(p))
    except Exception as exc:
        print('[r139-patch-warning] '+str(p)+' '+repr(exc),flush=True)

print('[r139-patched] '+repr(patched),flush=True)

# Fresh production-state probe and rendered mobile truth for reported athletes.
qa=r'''
import sqlite3,sys,re
sys.path.insert(0,"/data/top2_app")
import app as _full
from asd_app.core import app
app.config["TESTING"]=True
c=app.test_client()
with c.session_transaction() as s:
    s.update({"logged":True,"username":"admin","display_name":"R139 QA","role":"admin","tenant_slug":"default"})
conn=sqlite3.connect("/data/tenants/default/asd.db",timeout=20); conn.row_factory=sqlite3.Row
names=["ANGELUCCI LUDOVICA","ANNUNZIATO LUDOVICA","DI FRANCIA GIULIA"]
try:
    out=[]
    for full in names:
        cognome,nome=full.rsplit(" ",1)
        a=conn.execute("SELECT id,nome,cognome,certificato_scadenza FROM tesserati WHERE upper(cognome)=? AND upper(nome)=?",(cognome,nome)).fetchone()
        if not a: continue
        docs=[dict(x) for x in conn.execute("SELECT id,doc_type,categoria,titolo,filename,visibile,status FROM documenti WHERE tesserato_id=? ORDER BY id",(a['id'],)).fetchall()]
        rr=c.get("/mobile/atleta/"+str(a['id']))
        tx=re.sub(r"\s+"," ",rr.get_data(as_text=True))
        out.append({"id":a['id'],"name":full,"expiry":a['certificato_scadenza'],"docs":docs,"mobile":tx[:12000]})
    print("[r139-probe] "+repr(out),flush=True)
    integ=str(conn.execute("PRAGMA integrity_check").fetchone()[0]); fk=len(conn.execute("PRAGMA foreign_key_check").fetchall())
finally: conn.close()
print("[r139-db] integrity="+integ+" fk="+str(fk),flush=True)
if integ.lower()!="ok" or fk: raise RuntimeError("R139 DB integrity failed")
'''
proc=subprocess.run([sys.executable,'-c',qa],capture_output=True,text=True,timeout=120)
print((proc.stdout or '').strip(),flush=True)
if proc.returncode!=0:
    raise RuntimeError('R139 QA failed '+((proc.stderr or '')+(proc.stdout or ''))[-5000:])
