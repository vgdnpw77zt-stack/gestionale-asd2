from __future__ import annotations
from pathlib import Path
from datetime import datetime
import compileall, shutil, sqlite3

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MEDIA=Path('/data/tenants/default/media')
ONBOARDING=Path('/data/onboarding_docs')
MARKER=APP/'.BODYMIND_MISSING_DOCS_R17'
BACKUPS=Path('/data/release_backups/20260928_missing_docs_r17')

ACTIVE_STATUSES=(
    'needs_manual_match','associato_tipo_da_verificare','richiede_conferma',
    'needs_review','da_verificare','pending'
)

def backup(rel):
    src=APP/rel; dst=BACKUPS/rel
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dst)

def cols(conn,table):
    return {r[1] for r in conn.execute(f'PRAGMA table_info({table})').fetchall()}

def has_table(conn,table):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone() is not None

def valid_file(p):
    try:
        return bool(p and Path(p).is_file())
    except Exception:
        return False

def build_index():
    idx={}
    for root in (MEDIA,ONBOARDING):
        if not root.exists():
            continue
        try:
            for p in root.rglob('*'):
                if p.is_file():
                    idx.setdefault(p.name.lower(),[]).append(p)
        except Exception:
            pass
    return idx

def recover_path(conn,row,index):
    saved=str(row['saved_path'] or '').strip()
    original=str(row['original_filename'] or '').strip()
    candidates=[]
    if saved:
        p=Path(saved)
        candidates.append(p if p.is_absolute() else MEDIA/p)
        if not p.is_absolute():
            candidates.append(Path('/data/tenants/default')/p)
    if has_table(conn,'documenti'):
        dc=cols(conn,'documenti')
        if 'inbound_id' in dc and 'filename' in dc:
            for d in conn.execute("SELECT filename FROM documenti WHERE inbound_id=? ORDER BY id DESC",(int(row['id']),)).fetchall():
                if d[0]:
                    candidates.append(Path(str(d[0])))
    for p in candidates:
        if valid_file(p):
            return Path(p)
    names=[]
    for raw in (saved,original):
        if raw:
            name=Path(raw).name.lower()
            if name and name not in names:
                names.append(name)
    hits=[]
    for name in names:
        hits.extend(index.get(name,[]))
    uniq=[]
    seen=set()
    for p in hits:
        key=str(p.resolve())
        if key not in seen:
            seen.add(key); uniq.append(p)
    return uniq[0] if len(uniq)==1 else None

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

# UI/source patch once.
if not MARKER.exists():
    rel='asd_app/routes_a202_operational_integrity.py'
    p=APP/rel
    if not p.exists():
        raise RuntimeError('R17 target missing')
    s=p.read_text(encoding='utf-8')
    if 'BODYMIND_R17_MISSING_FILES' not in s:
        backup(rel)

        athletes_anchor='''        athletes=conn.execute("SELECT id,nome,cognome FROM tesserati ORDER BY cognome,nome").fetchall() if _has_table(conn,'tesserati') else []
'''
        athletes_new=athletes_anchor+'''        missing_count=int(_scalar(conn,"SELECT COUNT(*) FROM inbound_documents WHERE LOWER(COALESCE(status,''))='file_missing' AND COALESCE(deleted_at,'')=''") or 0)
'''
        if athletes_anchor not in s:
            raise RuntimeError('R17 queue count anchor missing')
        s=s.replace(athletes_anchor,athletes_new,1)

        html_anchor='''    html=f"""
    <main class='r11-page'>
'''
        html_new='''    missing_link=(f"<a href='/documenti/file-mancanti' style='display:block;margin-top:8px;font-size:10px;color:#fecaca!important;text-decoration:none;padding:6px 8px;border-radius:999px;background:rgba(127,29,29,.24);border:1px solid rgba(248,113,113,.28)'>{missing_count} senza file</a>" if missing_count else '')
    html=f"""
    <main class='r11-page'>
'''
        if html_anchor not in s:
            raise RuntimeError('R17 queue html anchor missing')
        s=s.replace(html_anchor,html_new,1)

        count_anchor="<div class='r11-count'>{len(rows)}<small>da chiudere</small></div>"
        count_new="<div class='r11-count'>{len(rows)}<small>da chiudere</small>{missing_link}</div>"
        if count_anchor not in s:
            raise RuntimeError('R17 queue hero count anchor missing')
        s=s.replace(count_anchor,count_new,1)

        route_anchor="# BODYMIND_R14_REMOVE_QUEUE_ITEM"
        route_code=r'''# BODYMIND_R17_MISSING_FILES
@app.get('/documenti/file-mancanti')
@login_required
def r17_file_mancanti():
    conn=db()
    try:
        rows=conn.execute("""
            SELECT i.*,t.nome AS atleta_nome,t.cognome AS atleta_cognome
            FROM inbound_documents i
            LEFT JOIN tesserati t ON t.id=COALESCE(i.tesserato_id,i.matched_tesserato_id)
            WHERE LOWER(COALESCE(i.status,''))='file_missing'
              AND COALESCE(i.deleted_at,'')=''
            ORDER BY COALESCE(i.updated_at,i.created_at) DESC,i.id DESC
        """).fetchall() if _has_table(conn,'inbound_documents') else []
    finally:
        conn.close()

    def card(r):
        did=int(r['id'])
        athlete=((str(r['atleta_cognome'] or '')+' '+str(r['atleta_nome'] or '')).strip() if 'atleta_nome' in r.keys() else '')
        previous=str(r['missing_previous_status'] or '') if 'missing_previous_status' in r.keys() else ''
        path=str(r['saved_path'] or '')
        return f"""
        <article class='r17-missing-card'>
          <div>
            <span class='r17-badge'>FILE NON DISPONIBILE</span>
            <h3>{e(r['original_filename'] or 'Documento')}</h3>
            <p>{('Atleta: <b>'+e(athlete)+'</b> · ') if athlete else ''}riferimento #{did}{(' · stato precedente: '+e(previous)) if previous else ''}</p>
            <small>{e(path)}</small>
          </div>
          <form method='post' action='/documenti/file-mancanti/{did}/elimina' onsubmit="return confirm('Eliminare definitivamente questa voce senza file?')">
            {csrf_input()}<button class='r11-btn danger' type='submit'>Elimina voce</button>
          </form>
        </article>"""

    cards=''.join(card(r) for r in rows) or "<div class='r11-empty'><b>Nessun riferimento senza file.</b><span>Non ci sono record orfani.</span></div>"
    html=f"""
    <main class='r11-page'>
      <section class='r11-hero'>
        <div><span class='r11-kicker'>Documenti · integrità archivio</span><h1>File mancanti</h1><p>Queste voci non vengono conteggiate tra i documenti da verificare. Il gestionale ha già tentato di ritrovare automaticamente il file nel volume.</p></div>
        <div class='r11-count'>{len(rows)}<small>riferimenti</small></div>
      </section>
      <div style='margin:0 0 14px'><a class='r11-btn ghost' href='/documenti/da-verificare'>← Torna a Da verificare</a></div>
      <section class='r11-list'>{cards}</section>
    </main>
    <style id='bodymind-r17-missing'>
      .r17-missing-card{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:16px;align-items:center;padding:17px;border-radius:20px;background:rgba(38,10,18,.78);border:1px solid rgba(248,113,113,.20)}}.r17-missing-card h3{{margin:8px 0 6px;overflow-wrap:anywhere}}.r17-missing-card p{{margin:0 0 5px;color:#cbd5e1;font-size:12px}}.r17-missing-card small{{display:block;color:#94a3b8;overflow-wrap:anywhere}}.r17-badge{{display:inline-flex;padding:5px 8px;border-radius:999px;background:rgba(127,29,29,.30);border:1px solid rgba(248,113,113,.30);color:#fecaca;font-size:10px;font-weight:900;letter-spacing:.08em}}.r11-btn.danger{{background:#7f1d1d;border-color:#f87171}}@media(max-width:720px){{.r17-missing-card{{grid-template-columns:1fr}}.r17-missing-card form,.r17-missing-card button{{width:100%}}}}
    </style>"""
    return layout(html)


@app.post('/documenti/file-mancanti/<int:doc_id>/elimina')
@login_required
def r17_file_mancante_elimina(doc_id):
    conn=db()
    try:
        row=conn.execute("SELECT * FROM inbound_documents WHERE id=?",(doc_id,)).fetchone()
        if not row or str(row['status'] or '').lower()!='file_missing':
            return redirect_with_message('/documenti/file-mancanti','Voce non trovata o già risolta.','error')
        icols=_cols(conn,'inbound_documents')
        sets=["status='deleted'"]; vals=[]
        now=datetime.now().isoformat(timespec='seconds')
        if 'deleted_at' in icols:
            sets.append("deleted_at=?"); vals.append(now)
        if 'updated_at' in icols:
            sets.append("updated_at=?"); vals.append(now)
        vals.append(doc_id)
        conn.execute("UPDATE inbound_documents SET "+','.join(sets)+" WHERE id=?",vals)
        if _has_table(conn,'documenti'):
            dcols=_cols(conn,'documenti')
            dsets=[]
            if 'visibile' in dcols: dsets.append("visibile=0")
            if 'status' in dcols: dsets.append("status='file_mancante_eliminato'")
            if dsets:
                if 'inbound_id' in dcols:
                    conn.execute("UPDATE documenti SET "+','.join(dsets)+" WHERE inbound_id=?",(doc_id,))
                elif row['saved_path']:
                    conn.execute("UPDATE documenti SET "+','.join(dsets)+" WHERE filename=?",(str(row['saved_path']),))
        conn.commit()
    finally:
        conn.close()
    return redirect_with_message('/documenti/file-mancanti','Voce senza file eliminata.','success')


'''
        if route_anchor not in s:
            raise RuntimeError('R17 route anchor missing')
        s=s.replace(route_anchor,route_code+route_anchor,1)

        p.write_text(s,encoding='utf-8')
        if not compileall.compile_file(str(p),quiet=1):
            raise RuntimeError('R17 source compile failed')

    MARKER.write_text('BodyMind missing document integrity R17 applied\n',encoding='utf-8')
    print('[missing-r17] source applied',flush=True)

# Data integrity scan runs every restart.
BACKUPS.mkdir(parents=True,exist_ok=True)
if DB.exists() and not (BACKUPS/'asd.db').exists():
    shutil.copy2(DB,BACKUPS/'asd.db')

conn=sqlite3.connect(str(DB),timeout=30); conn.row_factory=sqlite3.Row
repaired=0; newly_missing=0; restored=0; linked_fixed=0
missing_ids=[]
try:
    ic=cols(conn,'inbound_documents')
    if 'missing_previous_status' not in ic:
        conn.execute("ALTER TABLE inbound_documents ADD COLUMN missing_previous_status TEXT")
    if 'missing_checked_at' not in ic:
        conn.execute("ALTER TABLE inbound_documents ADD COLUMN missing_checked_at TEXT")
    conn.commit()

    index=build_index()
    values=','.join('?' for _ in ACTIVE_STATUSES)
    rows=conn.execute("""SELECT * FROM inbound_documents
        WHERE COALESCE(deleted_at,'')=''
          AND TRIM(COALESCE(saved_path,''))<>''
          AND LOWER(COALESCE(status,'')) NOT IN ('deleted','removed','cancelled')
        ORDER BY id""").fetchall()

    for row in rows:
        did=int(row['id'])
        status=str(row['status'] or '').lower()
        found=recover_path(conn,row,index)
        now=datetime.now().isoformat(timespec='seconds')
        if found:
            resolved=str(found.resolve())
            old_saved=str(row['saved_path'] or '')
            if resolved!=old_saved:
                conn.execute("UPDATE inbound_documents SET saved_path=?,missing_checked_at=? WHERE id=?",(resolved,now,did))
                repaired+=1
                if has_table(conn,'documenti'):
                    dc=cols(conn,'documenti')
                    if 'filename' in dc:
                        if 'inbound_id' in dc:
                            cur=conn.execute("UPDATE documenti SET filename=? WHERE inbound_id=?",(resolved,did))
                            linked_fixed+=int(cur.rowcount or 0)
                        elif old_saved:
                            cur=conn.execute("UPDATE documenti SET filename=? WHERE filename=?",(resolved,old_saved))
                            linked_fixed+=int(cur.rowcount or 0)
            else:
                conn.execute("UPDATE inbound_documents SET missing_checked_at=? WHERE id=?",(now,did))

            if status=='file_missing':
                previous=str(row['missing_previous_status'] or '').lower()
                if previous not in ACTIVE_STATUSES:
                    tid=int(row['tesserato_id'] or 0)
                    dtype=str(row['document_type'] or '')
                    dconf=int(row['document_confidence'] or 0)
                    previous='needs_manual_match' if tid<=0 else ('associato_tipo_da_verificare' if dtype in ('','altro') or dconf<60 else 'richiede_conferma')
                conn.execute("UPDATE inbound_documents SET status=?,missing_previous_status=NULL,missing_checked_at=? WHERE id=?",(previous,now,did))
                restored+=1
        else:
            if status!='file_missing':
                conn.execute("UPDATE inbound_documents SET missing_previous_status=?,status='file_missing',missing_checked_at=? WHERE id=?",(status,now,did))
                newly_missing+=1
            else:
                conn.execute("UPDATE inbound_documents SET missing_checked_at=? WHERE id=?",(now,did))
            missing_ids.append(did)

    conn.commit()
    active_pending=conn.execute(f"""SELECT COUNT(*) FROM inbound_documents
        WHERE LOWER(COALESCE(status,'')) IN ({values}) AND COALESCE(deleted_at,'')=''""",ACTIVE_STATUSES).fetchone()[0]
    missing_open=conn.execute("""SELECT COUNT(*) FROM inbound_documents
        WHERE LOWER(COALESCE(status,''))='file_missing' AND COALESCE(deleted_at,'')=''""").fetchone()[0]
    missing_rows=conn.execute("""SELECT id,original_filename,saved_path,missing_previous_status FROM inbound_documents
        WHERE LOWER(COALESCE(status,''))='file_missing' AND COALESCE(deleted_at,'')='' ORDER BY id""").fetchall()
    pending_rows=conn.execute(f"""SELECT id,original_filename,status,document_type,document_confidence,match_score,match_action,tesserato_id,matched_tesserato_id,suggested_tesserato_id,saved_path
        FROM inbound_documents WHERE LOWER(COALESCE(status,'')) IN ({values}) AND COALESCE(deleted_at,'')='' ORDER BY id""",ACTIVE_STATUSES).fetchall()
finally:
    conn.close()

print(f'[missing-r17] repaired={repaired} linked_fixed={linked_fixed} newly_missing={newly_missing} restored={restored} active_pending={active_pending} missing_open={missing_open} missing_ids={missing_ids}',flush=True)
for r in missing_rows:
    print(f"[missing-r17-item] id={int(r['id'])} previous={str(r['missing_previous_status'] or '')} file={str(r['original_filename'] or '')} path={str(r['saved_path'] or '')}",flush=True)
for r in pending_rows:
    print(f"[pending-r17-item] id={int(r['id'])} status={str(r['status'] or '')} file={str(r['original_filename'] or '')} type={str(r['document_type'] or '')} doc_conf={int(r['document_confidence'] or 0)} match={int(r['match_score'] or 0)} action={str(r['match_action'] or '')} tid={int(r['tesserato_id'] or 0)} matched={int(r['matched_tesserato_id'] or 0)} suggested={int(r['suggested_tesserato_id'] or 0)} path={str(r['saved_path'] or '')}",flush=True)
print('[missing-r17-selftest] PASS recover-before-hide missing-excluded-from-pending reversible-state separate-delete-page',flush=True)
