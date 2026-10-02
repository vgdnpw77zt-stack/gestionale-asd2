# -*- coding: utf-8 -*-
from __future__ import annotations
import py_compile, shutil, sqlite3
from pathlib import Path

APP=Path("/data/top2_app")
DB=Path("/data/tenants/default/asd.db")
BACK=Path("/data/release_backups/20261002_r106_desktop_save")
BACK.mkdir(parents=True,exist_ok=True)
PROFILE=APP/"asd_app/routes_tesserati.py"
CORE=APP/"asd_app/core.py"

if not APP.joinpath(".TOP2_OFFICIAL").exists():
    raise SystemExit("TOP2_OFFICIAL marker missing")

def backup_file(p):
    dst=BACK/p.name
    if p.exists() and not dst.exists(): shutil.copy2(p,dst)

ps=PROFILE.read_text(encoding="utf-8",errors="replace")
if "BODYMIND_R106_DESKTOP_SAVE_VERIFY" not in ps:
    backup_file(PROFILE)

    row_anchor='''           tesserato_id = rec_id
           msg = "Tesserato aggiornato correttamente."
'''
    row_new='''           tesserato_id = rec_id
           if rec_id <= 0 or c.rowcount != 1:
               conn.rollback()
               conn.close()
               return redirect_with_message('/tesserati', 'Aggiornamento non eseguito: tesserato non trovato.', 'error')
           msg = "Tesserato aggiornato correttamente."
'''
    if row_anchor not in ps:
        raise RuntimeError("R106 update rowcount anchor missing")
    ps=ps.replace(row_anchor,row_new,1)

    commit_anchor='''       conn.commit()
       # Se il profilo economico cambia, riallinea il SOLO mese corrente quando
'''
    verify='''       if action == 'update':
           try:
               conn.execute("UPDATE tesserati SET updated_at=? WHERE id=?",(now_iso_dt(),int(tesserato_id)))
           except Exception:
               pass
       conn.commit()
       # BODYMIND_R106_DESKTOP_SAVE_VERIFY
       if action == 'update':
           saved=conn.execute("SELECT * FROM tesserati WHERE id=?",(int(tesserato_id),)).fetchone()
           verify_fields=['nome','cognome','telefono','corso','certificato_scadenza','luogo_nascita',
                          'data_nascita','codice_fiscale','residenza','email','documento_identita',
                          'genitore','telefono_genitore','email_genitore']
           failed=[]
           if not saved:
               failed=['missing_row']
           else:
               for f in verify_fields:
                   expected=str(tesserato_row.get(f) or '').strip()
                   actual=str(saved[f] or '').strip() if f in saved.keys() else ''
                   if actual != expected: failed.append(f)
           if failed:
               conn.close()
               return redirect_with_message(f'/tesserati/{int(tesserato_id)}/scheda',
                                            'Salvataggio non verificato per: '+', '.join(failed),
                                            'error')
       # Se il profilo economico cambia, riallinea il SOLO mese corrente quando
'''
    if commit_anchor not in ps:
        raise RuntimeError("R106 commit anchor missing")
    ps=ps.replace(commit_anchor,verify,1)

    redirect_anchor='''       if action == 'update' and ui_mode == 'detail':
           return redirect_with_message(f'/tesserati/{tesserato_id}/scheda', final_msg, 'success')
'''
    redirect_new='''       if action == 'update' and ui_mode == 'detail':
           return redirect_with_message('/tesserati', final_msg, 'success', updated=int(tesserato_id))
'''
    if redirect_anchor not in ps:
        raise RuntimeError("R106 desktop redirect anchor missing")
    ps=ps.replace(redirect_anchor,redirect_new,1)

    PROFILE.write_text(ps,encoding="utf-8")
    py_compile.compile(str(PROFILE),doraise=True)
    print("[r106-desktop] PASS rowcount post-commit-readback return=/tesserati",flush=True)
else:
    print("[r106-desktop] already applied",flush=True)

cs=CORE.read_text(encoding="utf-8",errors="replace")
if "BODYMIND_R106_CROSS_DEVICE_CRITICALITY" not in cs:
    backup_file(CORE)
    changed=False
    pairs=[
      ('tess_url = f"/mobile/atleta/{tid}"','tess_url = f"/tesserati/{tid}"'),
      ("tess_url = f'/mobile/atleta/{tid}'","tess_url = f'/tesserati/{tid}'"),
      ('"Completa tutela", tess_url, "Torna alle atlete", "/mobile/atlete"',
       '"Completa tutela", tess_url, "Torna alle atlete", "/tesserati"')
    ]
    for old,new in pairs:
        if old in cs:
            cs=cs.replace(old,new)
            changed=True
    marker='\n# BODYMIND_R106_CROSS_DEVICE_CRITICALITY\n'
    cs=marker+cs
    CORE.write_text(cs,encoding="utf-8")
    py_compile.compile(str(CORE),doraise=True)
    print("[r106-criticality] PASS cross-device athlete/panel destinations changed="+str(changed),flush=True)
else:
    print("[r106-criticality] already applied",flush=True)

ptext=PROFILE.read_text(encoding="utf-8",errors="replace")
ctext=CORE.read_text(encoding="utf-8",errors="replace")
checks={
  "desktop_verify":"BODYMIND_R106_DESKTOP_SAVE_VERIFY" in ptext,
  "desktop_return":"'/tesserati'" not in "" and "updated=int(tesserato_id)" in ptext,
  "criticality_marker":"BODYMIND_R106_CROSS_DEVICE_CRITICALITY" in ctext,
  "criticality_panel":'"Torna alle atlete", "/tesserati"' in ctext,
}
conn=sqlite3.connect(str(DB),timeout=20)
try:
    integrity=str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    fk=len(conn.execute("PRAGMA foreign_key_check").fetchall())
    tess=int(conn.execute("SELECT COUNT(*) FROM tesserati").fetchone()[0])
finally: conn.close()
checks["db_ok"]=integrity.lower()=="ok" and fk==0
checks["tesserati_35"]=tess==35
print("[r106-checks] "+repr(checks)+" integrity="+integrity+" fk="+str(fk),flush=True)
failed=[k for k,v in checks.items() if not v]
if failed: raise RuntimeError("R106 QA failed "+repr(failed))
print("[r106-selftest] PASS desktop-save-verified return-tesserati cross-device-criticality db-ok",flush=True)
