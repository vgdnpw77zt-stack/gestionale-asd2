# -*- coding: utf-8 -*-
from __future__ import annotations
import py_compile, shutil, sqlite3
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
BACK=Path('/data/release_backups/20261002_r106_desktop_save')
BACK.mkdir(parents=True,exist_ok=True)
ROUTES=APP/'asd_app/routes_tesserati.py'
CORE=APP/'asd_app/core.py'

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

def backup_file(p):
    dst=BACK/p.name
    if p.exists() and not dst.exists():
        shutil.copy2(p,dst)

# 1) Desktop profile save: prove committed values before reporting success.
s=ROUTES.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R106_DESKTOP_POST_COMMIT_VERIFY' not in s:
    backup_file(ROUTES)
    anchor="""       conn.commit()
       # Se il profilo economico cambia, riallinea il SOLO mese corrente quando
"""
    inject="""       conn.commit()
       # BODYMIND_R106_DESKTOP_POST_COMMIT_VERIFY
       if action == 'update':
           saved = conn.execute('SELECT * FROM tesserati WHERE id=?',(int(tesserato_id),)).fetchone()
           failed = []
           expected_text = {
               'nome': nome, 'cognome': cognome, 'telefono': telefono, 'corso': corso,
               'certificato_scadenza': certificato, 'luogo_nascita': luogo_nascita,
               'data_nascita': data_nascita, 'codice_fiscale': codice_fiscale,
               'residenza': residenza, 'email': email, 'documento_identita': documento_identita,
               'genitore': truncate(str(minor_payload.get('genitore') or '').strip(),140),
               'telefono_genitore': truncate(str(minor_payload.get('telefono_genitore') or '').strip(),40),
               'email_genitore': normalize_email(str(minor_payload.get('email_genitore') or '').strip(),140),
               'quota_tipo': quota_tipo, 'quota_note': quota_note,
           }
           if not saved:
               failed.append('row_missing')
           else:
               for key,val in expected_text.items():
                   if key in saved.keys() and str(saved[key] or '').strip() != str(val or '').strip():
                       failed.append(key)
               if 'minorenne' in saved.keys() and int(saved['minorenne'] or 0) != (1 if is_minor else 0):
                   failed.append('minorenne')
               if 'agonista' in saved.keys() and int(saved['agonista'] or 0) != int(agonista or 0):
                   failed.append('agonista')
               if 'quota_sconto_fisso' in saved.keys():
                   try:
                       if abs(float(saved['quota_sconto_fisso'] or 0)-float(quota_sconto_fisso or 0)) > 0.001:
                           failed.append('quota_sconto_fisso')
                   except Exception:
                       failed.append('quota_sconto_fisso')
               if 'quota_personalizzata' in saved.keys():
                   try:
                       av = saved['quota_personalizzata']
                       if quota_personalizzata is None:
                           if av not in (None,''): failed.append('quota_personalizzata')
                       elif abs(float(av or 0)-float(quota_personalizzata or 0)) > 0.001:
                           failed.append('quota_personalizzata')
                   except Exception:
                       failed.append('quota_personalizzata')
           if failed:
               conn.close()
               return redirect_with_message(f'/tesserati/{int(tesserato_id)}/scheda',
                   'Salvataggio non verificato nel database: ' + ', '.join(failed), 'error')
       # Se il profilo economico cambia, riallinea il SOLO mese corrente quando
"""
    if anchor not in s:
        raise RuntimeError('R106 desktop commit anchor missing')
    s=s.replace(anchor,inject,1)

    old="""       if action == 'update' and ui_mode == 'detail':
           return redirect_with_message(f'/tesserati/{tesserato_id}/scheda', final_msg, 'success')
"""
    new="""       if action == 'update' and ui_mode == 'detail':
           return redirect_with_message('/tesserati', final_msg, 'success', updated=tesserato_id)
"""
    if old not in s:
        raise RuntimeError('R106 desktop success redirect anchor missing')
    s=s.replace(old,new,1)
    ROUTES.write_text(s,encoding='utf-8')
    py_compile.compile(str(ROUTES),doraise=True)
    print('[r106-desktop] PASS post-commit readback + return=/tesserati',flush=True)
else:
    print('[r106-desktop] already applied',flush=True)

# 2) Criticalities always target the canonical athlete sheet.
cs=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R106_CANONICAL_CRITICALITY_SHEET' not in cs:
    backup_file(CORE)
    old='''            tess_url = f"/mobile/atleta/{tid}" if tid else "/tesserati"
'''
    new='''            # BODYMIND_R106_CANONICAL_CRITICALITY_SHEET
            tess_url = f"/tesserati/{tid}/scheda" if tid else "/tesserati"
'''
    if old not in cs:
        raise RuntimeError('R106 criticality URL anchor missing')
    cs=cs.replace(old,new,1)
    CORE.write_text(cs,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r106-criticality] PASS canonical desktop URL; mobile guard remains authoritative',flush=True)
else:
    print('[r106-criticality] already applied',flush=True)

# Read-only release gate.
conn=sqlite3.connect(str(DB),timeout=20)
try:
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
    counts={
      'tesserati':int(conn.execute('SELECT COUNT(*) FROM tesserati').fetchone()[0]),
      'documenti':int(conn.execute('SELECT COUNT(*) FROM documenti').fetchone()[0]),
      'inbound_documents':int(conn.execute('SELECT COUNT(*) FROM inbound_documents').fetchone()[0]),
    }
finally:
    conn.close()

src=ROUTES.read_text(encoding='utf-8',errors='replace')
core=CORE.read_text(encoding='utf-8',errors='replace')
checks={
  'desktop_readback':'BODYMIND_R106_DESKTOP_POST_COMMIT_VERIFY' in src,
  'desktop_return_panel':"redirect_with_message('/tesserati', final_msg, 'success', updated=tesserato_id)" in src,
  'canonical_criticality':'BODYMIND_R106_CANONICAL_CRITICALITY_SHEET' in core and 'f"/tesserati/{tid}/scheda"' in core,
  'integrity':integrity.lower()=='ok' and fk==0,
}
print('[r106-checks] '+repr(checks)+' counts='+repr(counts)+' integrity='+integrity+' fk='+str(fk),flush=True)
failed=[k for k,v in checks.items() if not v]
if failed:
    raise RuntimeError('R106 QA failed '+repr(failed))
print('[r106-selftest] PASS desktop-save-readback canonical-criticality return-tesserati db-ok',flush=True)
