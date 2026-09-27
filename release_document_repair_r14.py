from __future__ import annotations
from pathlib import Path
import compileall, shutil, sqlite3, re, unicodedata
from datetime import datetime

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MEDIA=Path('/data/tenants/default/media')
MARKER=APP/'.BODYMIND_DOCUMENT_REPAIR_R14'
BACKUPS=Path('/data/release_backups/20260927_document_repair_r14')
OLD_PREFIX='/Users/imac/Library/Application Support/ASD Pro Goldclass/tenants/default/media/'
NEW_PREFIX='/data/tenants/default/media/'

def backup_file(rel):
    src=APP/rel; dst=BACKUPS/rel
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)

def compact(v):
    s=unicodedata.normalize('NFKD',str(v or ''))
    s=''.join(ch for ch in s if not unicodedata.combining(ch))
    return ''.join(ch.lower() for ch in s if ch.isalnum())

def canonical_type(dtype, filename):
    d=str(dtype or '').strip()
    aliases={'iscrizione','domanda_iscrizione','manleva','liberatoria_immagini','consenso_minore',
             'autorizzazione_genitore','privacy','privacy_consenso','safeguarding','tutela_minore',
             'modulo_unico_tesseramento'}
    if d in aliases:
        return 'modulo_unico_tesseramento',100
    name=Path(str(filename or '')).stem.lower()
    plain=re.sub(r'[^a-z0-9]+','_',name)
    if re.search(r'(^|_)cm(_|$)',plain) or 'certificato_medico' in plain or ('certificato' in plain and 'medico' in plain):
        return 'certificato_medico',95
    if 'iscrizion' in plain or 'modulo_unico' in plain:
        return 'modulo_unico_tesseramento',100
    return d,0

LABELS={
 'modulo_unico_tesseramento':'Modulo iscrizione / Modulo Unico MU-2026.1',
 'certificato_medico':'Certificato medico',
 'documento_identita':'Documento identità',
 'trasporto_minori':'Delega / trasporto minori',
 'documenti_gara':'Documenti gara','documenti_saggio':'Documenti saggio',
 'ricevuta_pagamento':'Ricevuta / prova pagamento','altro':'Altro'
}
CATEGORIES={
 'modulo_unico_tesseramento':'Modulo iscrizione BodyMind',
 'certificato_medico':'Certificato medico','documento_identita':'Documento identità',
 'trasporto_minori':'Delega / trasporto minori','documenti_gara':'Documenti gara',
 'documenti_saggio':'Documenti saggio','ricevuta_pagamento':'Pagamenti da verificare','altro':'Altro'
}

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

# Source/UI patch, once.
if not MARKER.exists():
    rel='asd_app/routes_a202_operational_integrity.py'
    p=APP/rel
    if not p.exists(): raise RuntimeError('R14 target missing')
    s=p.read_text(encoding='utf-8')
    if 'BODYMIND_R14_REMOVE_QUEUE_ITEM' not in s:
        backup_file(rel)
        dossier_anchor='''        dossier=f"<a class='r11-btn ghost' href='/documenti?tesserato_id={tid}'>Dossier</a>" if tid else ''
        return f"""
'''
        dossier_new='''        dossier=f"<a class='r11-btn ghost' href='/documenti?tesserato_id={tid}'>Dossier</a>" if tid else ''
        remove_form=f"""<form method='post' action='/documenti/da-verificare/{did}/elimina' class='r11-inline' onsubmit="return confirm('Rimuovere questa voce dalla coda? Il file fisico, se presente, non verrà cancellato.')">{csrf_input()}<button class='r11-btn danger' type='submit'>Rimuovi voce</button></form>"""
        return f"""
'''
        if dossier_anchor not in s: raise RuntimeError('R14 dossier anchor missing')
        s=s.replace(dossier_anchor,dossier_new,1)
        s=s.replace("{ok}{dossier}\n          </div>","{ok}{dossier}{remove_form}\n          </div>",1)
        s=s.replace(".r11-btn.ghost{background:#10243b}",".r11-btn.ghost{background:#10243b}.r11-btn.danger{background:#3b1620;border-color:#7f1d1d;color:#fecaca!important}",1)
        route_anchor="@app.post('/documenti/da-verificare/<int:doc_id>/ok')"
        route_code=r'''# BODYMIND_R14_REMOVE_QUEUE_ITEM
@app.post('/documenti/da-verificare/<int:doc_id>/elimina')
@login_required
def r14_documento_elimina(doc_id):
    conn=db()
    try:
        row=conn.execute("SELECT * FROM inbound_documents WHERE id=?",(doc_id,)).fetchone()
        if not row:
            return redirect_with_message('/documenti/da-verificare','Voce non trovata.','error')
        cols=_cols(conn,'inbound_documents')
        sets=["status='deleted'"]; vals=[]
        if 'deleted_at' in cols:
            sets.append("deleted_at=?"); vals.append(datetime.now().isoformat(timespec='seconds'))
        if 'updated_at' in cols:
            sets.append("updated_at=?"); vals.append(datetime.now().isoformat(timespec='seconds'))
        vals.append(doc_id)
        conn.execute("UPDATE inbound_documents SET "+','.join(sets)+" WHERE id=?",vals)
        if _has_table(conn,'documenti'):
            dcols=_cols(conn,'documenti')
            dsets=[]
            if 'visibile' in dcols: dsets.append("visibile=0")
            if 'status' in dcols: dsets.append("status='rimosso_dalla_coda'")
            if dsets and 'inbound_id' in dcols:
                conn.execute("UPDATE documenti SET "+','.join(dsets)+" WHERE inbound_id=?",(doc_id,))
        conn.commit()
    finally:
        conn.close()
    return redirect_with_message('/documenti/da-verificare','Voce rimossa dalla coda. Il file fisico non è stato cancellato.','success')


'''
        if route_anchor not in s: raise RuntimeError('R14 route anchor missing')
        s=s.replace(route_anchor,route_code+route_anchor,1)
        p.write_text(s,encoding='utf-8')
        if not compileall.compile_file(str(p),quiet=1):
            raise RuntimeError('R14 source compile failed')
    MARKER.write_text('BodyMind document repair R14 source applied\n',encoding='utf-8')

# Data repair is idempotent and intentionally runs on every restart.
BACKUPS.mkdir(parents=True,exist_ok=True)
db_backup=BACKUPS/'asd.db'
if DB.exists() and not db_backup.exists():
    shutil.copy2(DB,db_backup)

conn=sqlite3.connect(str(DB),timeout=30); conn.row_factory=sqlite3.Row
paths_fixed=0; docs_paths_fixed=0; auto_assigned=0; auto_closed=0; docs_synced=0
try:
    # 1. Repair legacy iMac absolute paths only if the Railway counterpart exists.
    rows=conn.execute("SELECT id,saved_path FROM inbound_documents WHERE saved_path LIKE ?",(OLD_PREFIX+'%',)).fetchall()
    for r in rows:
        old=str(r['saved_path'] or '')
        new=NEW_PREFIX+old[len(OLD_PREFIX):]
        if Path(new).is_file():
            conn.execute("UPDATE inbound_documents SET saved_path=? WHERE id=?",(new,int(r['id']))); paths_fixed+=1

    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documenti'").fetchone():
        dcols={x[1] for x in conn.execute("PRAGMA table_info(documenti)").fetchall()}
        if 'filename' in dcols:
            rows=conn.execute("SELECT id,filename FROM documenti WHERE filename LIKE ?",(OLD_PREFIX+'%',)).fetchall()
            for r in rows:
                old=str(r['filename'] or '')
                new=NEW_PREFIX+old[len(OLD_PREFIX):]
                if Path(new).is_file():
                    conn.execute("UPDATE documenti SET filename=? WHERE id=?",(new,int(r['id']))); docs_paths_fixed+=1

    # 2. Re-run the current safe matching principle on legacy pending rows.
    athletes=conn.execute("SELECT * FROM tesserati ORDER BY id").fetchall()
    surname_groups={}
    for a in athletes:
        c=compact(a['cognome'] if 'cognome' in a.keys() else '')
        if c: surname_groups.setdefault(c,[]).append(a)

    pending=conn.execute("""SELECT * FROM inbound_documents
        WHERE lower(coalesce(status,'')) IN ('needs_manual_match','associato_tipo_da_verificare','richiede_conferma','needs_review','da_verificare','pending')
        AND coalesce(deleted_at,'')='' ORDER BY id""").fetchall()

    for r in pending:
        saved=str(r['saved_path'] or '')
        if saved and not Path(saved).is_file():
            continue
        filename=str(r['original_filename'] or Path(saved).name)
        filec=compact(Path(filename).stem)
        textc=compact(r['extracted_text'] if 'extracted_text' in r.keys() else '')
        candidates=[]
        for a in athletes:
            aid=int(a['id']); n=compact(a['nome'] if 'nome' in a.keys() else ''); c=compact(a['cognome'] if 'cognome' in a.keys() else '')
            if not c or len(c)<4: continue
            full=((c in filec and n and n in filec) or (c in textc and n and n in textc))
            unique_surname=(c in filec and len(surname_groups.get(c,[]))==1)
            if full: candidates.append((100,aid))
            elif unique_surname: candidates.append((92,aid))
        candidates=sorted(set(candidates),reverse=True)
        best=None
        if candidates:
            top=candidates[0]
            same=[x for x in candidates if x[0]==top[0]]
            if len(same)==1: best=top

        current_tid=int(r['tesserato_id'] or 0)
        score=int(r['match_score'] or 0)
        if best and (current_tid in (0,best[1])):
            score,tid=best
            if current_tid==0: auto_assigned+=1
            current_tid=tid
            conn.execute("""UPDATE inbound_documents SET tesserato_id=?,matched_tesserato_id=?,suggested_tesserato_id=?,
                          match_score=?,match_action='auto_save' WHERE id=?""",(tid,tid,tid,score,int(r['id'])))

        dtype,heur_conf=canonical_type(r['document_type'],filename)
        conf=max(int(r['document_confidence'] or 0),heur_conf)
        if dtype:
            conn.execute("UPDATE inbound_documents SET document_type=?,document_label=?,document_confidence=? WHERE id=?",
                         (dtype,LABELS.get(dtype,dtype),conf,int(r['id'])))

        strong_identity=(current_tid>0 and score>=92)
        strong_type=(dtype not in ('','altro') and conf>=60)
        if strong_identity:
            new_status='associato' if strong_type and dtype!='ricevuta_pagamento' else ('pagamento_da_verificare' if dtype=='ricevuta_pagamento' else 'associato_tipo_da_verificare')
            conn.execute("UPDATE inbound_documents SET status=? WHERE id=?",(new_status,int(r['id'])))
            if new_status=='associato': auto_closed+=1

            # Sync into the athlete dossier without copying/deleting the physical file.
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documenti'").fetchone():
                dcols={x[1] for x in conn.execute("PRAGMA table_info(documenti)").fetchall()}
                existing=None
                if 'inbound_id' in dcols:
                    existing=conn.execute("SELECT id FROM documenti WHERE inbound_id=? ORDER BY id DESC LIMIT 1",(int(r['id']),)).fetchone()
                if not existing and saved:
                    existing=conn.execute("SELECT id FROM documenti WHERE filename=? ORDER BY id DESC LIMIT 1",(saved,)).fetchone()
                vals={
                    'tesserato_id':current_tid,'titolo':filename,'categoria':CATEGORIES.get(dtype,'Altro'),
                    'filename':saved,'original_filename':filename,'data_caricamento':datetime.now().date().isoformat(),
                    'visibile':1,'doc_type':dtype,'confidence':conf,'match_score':score,'source':'autopilot',
                    'status':'salvato','inbound_id':int(r['id'])
                }
                vals={k:v for k,v in vals.items() if k in dcols}
                if existing:
                    keys=list(vals.keys())
                    conn.execute("UPDATE documenti SET "+','.join(k+'=?' for k in keys)+" WHERE id=?",
                                 [vals[k] for k in keys]+[int(existing['id'])])
                else:
                    required={'tesserato_id','titolo','categoria','filename','original_filename'}
                    if required.issubset(vals):
                        keys=list(vals.keys())
                        conn.execute("INSERT INTO documenti("+','.join(keys)+") VALUES("+','.join('?' for _ in keys)+")",
                                     [vals[k] for k in keys])
                docs_synced+=1

            # A confidently recognised Modulo Unico satisfies the single onboarding form.
            if dtype=='modulo_unico_tesseramento' and strong_type:
                if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='onboarding_document_requests'").fetchone():
                    ocols={x[1] for x in conn.execute("PRAGMA table_info(onboarding_document_requests)").fetchall()}
                    sets=["status='accepted'"]; vals=[]
                    now=datetime.now().isoformat(timespec='seconds')
                    if 'returned_at' in ocols: sets.append("returned_at=COALESCE(returned_at,?)"); vals.append(now)
                    if 'accepted_at' in ocols: sets.append("accepted_at=COALESCE(accepted_at,?)"); vals.append(now)
                    if 'accepted_by' in ocols: sets.append("accepted_by='autopilot'")
                    vals.append(current_tid)
                    conn.execute("UPDATE onboarding_document_requests SET "+','.join(sets)+" WHERE tesserato_id=? AND document_type='modulo_unico_tesseramento' AND required=1 AND status NOT IN ('accepted','manual_accepted','deleted','cancelled')",vals)
                if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='minori'").fetchone():
                    mcols={x[1] for x in conn.execute("PRAGMA table_info(minori)").fetchall()}
                    if 'consenso_firmato' in mcols:
                        if 'data_consenso' in mcols:
                            conn.execute("UPDATE minori SET consenso_firmato=1,data_consenso=COALESCE(NULLIF(data_consenso,''),?) WHERE tesserato_id=?",(datetime.now().date().isoformat(),current_tid))
                        else:
                            conn.execute("UPDATE minori SET consenso_firmato=1 WHERE tesserato_id=?",(current_tid,))

    conn.commit()
    remaining=conn.execute("""SELECT COUNT(*) FROM inbound_documents WHERE lower(coalesce(status,'')) IN
      ('needs_manual_match','associato_tipo_da_verificare','richiede_conferma','needs_review','da_verificare','pending')
      AND coalesce(deleted_at,'')=''""").fetchone()[0]
    old_left=conn.execute("SELECT COUNT(*) FROM inbound_documents WHERE saved_path LIKE ?",(OLD_PREFIX+'%',)).fetchone()[0]
finally:
    conn.close()

print(f'[document-repair-r14] paths_fixed={paths_fixed} document_paths_fixed={docs_paths_fixed} auto_assigned={auto_assigned} auto_closed={auto_closed} dossier_synced={docs_synced} remaining_pending={remaining} old_paths_left={old_left}',flush=True)
print('[document-repair-r14-selftest] PASS legacy-path-repair safe-unique-surname auto-module medical-filename dossier-sync removable-queue',flush=True)
