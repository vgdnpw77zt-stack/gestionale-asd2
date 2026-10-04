from __future__ import annotations
import py_compile, re, shutil
from pathlib import Path

APP=Path('/data/top2_app')
BACK=Path('/data/release_backups/20261004_r139_truth')
BACK.mkdir(parents=True,exist_ok=True)

matches=[]
for p in (APP/'asd_app').rglob('*.py'):
    try:s=p.read_text(encoding='utf-8',errors='replace')
    except Exception:continue
    if 'BODYMIND_R110_SIMPLE_MOBILE' in s and 'def fix12_mobile_atleta' in s:
        matches.append((p,s))
if len(matches)!=1:
    raise RuntimeError('R139 expected one mobile profile source, got '+repr([str(x[0]) for x in matches]))

p,s=matches[0]
start=s.find('def fix12_mobile_atleta')
end=s.find('\n@app.',start)
if end<0:end=len(s)
block=s[start:end]
before=block

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

if 'def _r139_doc_exists' not in block:
    anchor='            _mu=bool(conn.execute('
    if anchor not in block:
        raise RuntimeError('R139 mobile MU anchor missing')
    block=block.replace(anchor,helper+anchor,1)

mu_pattern=re.compile(r"            _mu=bool\(conn\.execute\(\"\"\"SELECT 1 FROM documenti.*?\"\"\",\(tid,\)\)\.fetchone\(\)\)",re.S)
mu_new='''            _mu_rows=conn.execute("""SELECT filename FROM documenti WHERE tesserato_id=? AND COALESCE(visibile,1)=1 AND (LOWER(COALESCE(doc_type,''))='modulo_unico_tesseramento' OR LOWER(COALESCE(categoria,'')) LIKE '%modulo iscrizione%' OR LOWER(COALESCE(titolo,'')) LIKE '%modulo unico%' OR LOWER(COALESCE(titolo,'')) LIKE '%domanda iscrizione%')""",(tid,)).fetchall()
            _mu=any(_r139_doc_exists(_r['filename']) for _r in _mu_rows)'''
block,n_mu=mu_pattern.subn(mu_new,block,count=1)

med_pattern=re.compile(r"            _med=bool\(conn\.execute\(\"\"\"SELECT 1 FROM documenti.*?\"\"\",\(tid,\)\)\.fetchone\(\)\)",re.S)
med_new='''            _med_rows=conn.execute("""SELECT filename FROM documenti WHERE tesserato_id=? AND COALESCE(visibile,1)=1 AND LOWER(COALESCE(doc_type,''))='certificato_medico' AND LOWER(COALESCE(titolo,'')) NOT LIKE '%richiesta%'""",(tid,)).fetchall()
            _med=any(_r139_doc_exists(_r['filename']) for _r in _med_rows)'''
block,n_med=med_pattern.subn(med_new,block,count=1)

# R120 previously made expiry alone authoritative. Revert that on mobile:
# green certificate requires both a real visible file and a valid expiry.
block=block.replace('            if _cert:\n                try:_certok=', '            if _med and _cert:\n                try:_certok=',1)

# Minor tutela must not be green without a real MU.
block=block.replace('            _tut=(not _minor) or _guard','            _tut=(not _minor) or bool(_mu and _guard)',1)

already_ok=('def _r139_doc_exists' in before and '_mu_rows=conn.execute' in before and '_med_rows=conn.execute' in before and 'if _med and _cert:' in before)
if not already_ok and (block==before or n_mu!=1 or n_med!=1):
    raise RuntimeError('R139 mobile patch incomplete n_mu='+str(n_mu)+' n_med='+str(n_med))
if block!=before:
    shutil.copy2(p,BACK/p.name)
    s=s[:start]+block+s[end:]
    p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('[r139-mobile-profile] PASS real-file MU+medical truth source='+str(p)+' already='+str(already_ok),flush=True)
