from pathlib import Path
import sqlite3, json
DB=Path('/data/tenants/default/asd.db')
MEDIA=Path('/data/tenants/default/media')
print('[basename-probe] BEGIN',flush=True)
conn=sqlite3.connect(str(DB)); conn.row_factory=sqlite3.Row
try:
    rows=conn.execute("""SELECT id,original_filename,saved_path FROM inbound_documents
                         WHERE lower(coalesce(status,'')) IN ('needs_manual_match','associato_tipo_da_verificare','richiede_conferma','needs_review','da_verificare','pending')
                         AND coalesce(deleted_at,'')='' ORDER BY id""").fetchall()
    for r in rows:
        raw=Path(str(r['saved_path'] or ''))
        direct=raw if raw.is_absolute() else MEDIA/raw
        if direct.is_file(): continue
        names=[]
        if r['original_filename']: names.append(str(r['original_filename']))
        if raw.name and raw.name not in names: names.append(raw.name)
        found=[]
        for name in names:
            for p in MEDIA.rglob(name):
                if p.is_file() and str(p) not in found: found.append(str(p))
        print('[basename-probe] '+json.dumps({'id':r['id'],'file':r['original_filename'],'saved':r['saved_path'],'found':found[:10]},ensure_ascii=False),flush=True)
finally:
    conn.close()
print('[basename-probe] END',flush=True)
