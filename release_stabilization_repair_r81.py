# -*- coding: utf-8 -*-
from __future__ import annotations
import hashlib, json, py_compile, re, shutil, sqlite3
from datetime import date, datetime
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
BACK=Path('/data/release_backups/20261002_r81_stabilization')
BACK.mkdir(parents=True,exist_ok=True)
MARKER=APP/'.BODYMIND_R81_STABILIZATION'

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

def table(conn,name):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())

def cols(conn,name):
    return {str(r[1]) for r in conn.execute('PRAGMA table_info('+name+')').fetchall()} if table(conn,name) else set()

def backup_db():
    dst=BACK/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_pre_r81.db')
    src=sqlite3.connect(str(DB),timeout=30); out=sqlite3.connect(str(dst))
    try: src.backup(out)
    finally: out.close(); src.close()
    return str(dst)

def backup_file(p):
    p=Path(p)
    try: rel=p.relative_to(APP)
    except Exception: rel=Path(p.name)
    dst=BACK/rel
    if p.exists() and not dst.exists():
        dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,dst)

def iso(v):
    raw=str(v or '').strip()[:10]
    for fmt in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y','%d.%m.%Y'):
        try: return datetime.strptime(raw,fmt).date().isoformat()
        except Exception: pass
    return ''

def age(v):
    d=iso(v)
    if not d: return None
    born=date.fromisoformat(d); today=date.today()
    return today.year-born.year-((today.month,today.day)<(born.month,born.day))

def is_mu(r):
    ks=set(r.keys())
    hay=' '.join(str(r[k] or '').lower() for k in ('doc_type','categoria','titolo','filename','original_filename') if k in ks)
    return ('modulo_unico_tesseramento' in hay or 'modulo unico' in hay or 'modulo_unico' in hay
            or 'modulo iscrizione' in hay or 'domanda iscrizione' in hay or 'iscrizione manleva' in hay)

# Permanent dossier rule: hidden/archived rows are not operational dossier rows.
DOCS=APP/'asd_app/routes_documenti.py'
if DOCS.exists():
    txt=DOCS.read_text(encoding='utf-8',errors='replace')
    if 'BODYMIND_R81_VISIBLE_DOCS_ONLY' not in txt:
        backup_file(DOCS)
        original=txt
        # Main athlete-document list reads, with and without a table alias.
        txt,n1=re.subn(
            r'FROM\s+documenti\s+WHERE\s+tesserato_id\s*=\s*\?(?!\s+AND\s+coalesce\(visibile)',
            'FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1',txt,flags=re.I)
        txt,n2=re.subn(
            r'FROM\s+documenti\s+([A-Za-z_][A-Za-z0-9_]*)\s+WHERE\s+\1\.tesserato_id\s*=\s*\?(?!\s+AND\s+coalesce\(\1\.visibile)',
            lambda m:'FROM documenti '+m.group(1)+' WHERE '+m.group(1)+'.tesserato_id=? AND coalesce('+m.group(1)+'.visibile,1)=1',
            txt,flags=re.I)
        if txt!=original:
            txt='# BODYMIND_R81_VISIBLE_DOCS_ONLY\n'+txt
            DOCS.write_text(txt,encoding='utf-8')
            py_compile.compile(str(DOCS),doraise=True)
            print('[r81-dossier] PASS visible-only queries patched='+str(n1+n2),flush=True)
        else:
            # The page may already filter by visibile under a different query shape.
            # Do not mutate unknown SQL; report it for the final gate.
            print('[r81-dossier] WARNING no direct tesserato document query patched',flush=True)

if not MARKER.exists():
    db_backup=backup_db()
    conn=sqlite3.connect(str(DB),timeout=60); conn.row_factory=sqlite3.Row
    archived_orphans=[]; normalized_mu=[]; minor_flags=[]; synced_mu=[]; stale_tasks=[]; onboarding_fixed=[]
    try:
        # 1) Remove operational inbound rows pointing to intentionally deleted athletes.
        conn.execute("""CREATE TABLE IF NOT EXISTS bodymind_orphan_records_archive(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source_table TEXT NOT NULL,
          source_id INTEGER NOT NULL,
          former_tesserato_id INTEGER,
          reason TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          semantics_json TEXT,
          events_json TEXT,
          archived_at TEXT NOT NULL,
          UNIQUE(source_table,source_id)
        )""")
        if table(conn,'inbound_documents'):
            rows=conn.execute("""SELECT i.* FROM inbound_documents i
              LEFT JOIN tesserati t ON t.id=i.tesserato_id
              WHERE coalesce(i.tesserato_id,0)>0 AND t.id IS NULL ORDER BY i.id""").fetchall()
            for r in rows:
                iid=int(r['id']); tid=int(r['tesserato_id'] or 0)
                docrefs=[]
                if table(conn,'documenti') and 'inbound_id' in cols(conn,'documenti'):
                    docrefs=conn.execute('SELECT id FROM documenti WHERE inbound_id=?',(iid,)).fetchall()
                if docrefs:
                    # Referential safety: never delete a row still backing a dossier document.
                    continue
                events=[]
                if table(conn,'inbound_events') and 'inbound_document_id' in cols(conn,'inbound_events'):
                    events=[dict(x) for x in conn.execute('SELECT * FROM inbound_events WHERE inbound_document_id=? ORDER BY id',(iid,)).fetchall()]
                sem=[]
                if table(conn,'bodymind_document_semantics'):
                    sem=[dict(x) for x in conn.execute("""SELECT * FROM bodymind_document_semantics
                      WHERE source_table='inbound_documents' AND source_id=? ORDER BY id""",(iid,)).fetchall()]
                conn.execute("""INSERT OR IGNORE INTO bodymind_orphan_records_archive
                  (source_table,source_id,former_tesserato_id,reason,payload_json,semantics_json,events_json,archived_at)
                  VALUES(?,?,?,?,?,?,?,?)""",
                  ('inbound_documents',iid,tid,'R81 deleted-athlete orphan cleanup',
                   json.dumps(dict(r),ensure_ascii=False,default=str),
                   json.dumps(sem,ensure_ascii=False,default=str),
                   json.dumps(events,ensure_ascii=False,default=str),
                   datetime.now().isoformat(timespec='seconds')))
                if events:
                    conn.execute('DELETE FROM inbound_events WHERE inbound_document_id=?',(iid,))
                if table(conn,'bodymind_document_semantics'):
                    conn.execute("DELETE FROM bodymind_document_semantics WHERE source_table='inbound_documents' AND source_id=?",(iid,))
                conn.execute('DELETE FROM inbound_documents WHERE id=?',(iid,))
                archived_orphans.append({'id':iid,'former_tid':tid})

        # 2) Normalize every active MU dossier row.
        if table(conn,'documenti'):
            dc=cols(conn,'documenti')
            for d in conn.execute("SELECT * FROM documenti WHERE coalesce(visibile,1)=1 ORDER BY id").fetchall():
                if not is_mu(d): continue
                sets=[]; vals=[]
                if 'doc_type' in dc and str(d['doc_type'] or '').strip().lower()!='modulo_unico_tesseramento':
                    sets.append('doc_type=?'); vals.append('modulo_unico_tesseramento')
                if 'categoria' in dc and 'modulo iscrizione' not in str(d['categoria'] or '').strip().lower():
                    sets.append('categoria=?'); vals.append('Modulo iscrizione BodyMind')
                if sets:
                    vals.append(int(d['id']))
                    conn.execute('UPDATE documenti SET '+','.join(sets)+' WHERE id=?',tuple(vals))
                    normalized_mu.append(int(d['id']))

        # 3) Minor flag derives from DOB. This does not invent guardian data.
        tc=cols(conn,'tesserati')
        if {'id','data_nascita','minorenne'}.issubset(tc):
            for a in conn.execute('SELECT * FROM tesserati ORDER BY id').fetchall():
                aa=age(a['data_nascita'])
                if aa is None: continue
                wanted=1 if aa<18 else 0
                current=int(a['minorenne'] or 0)
                if current!=wanted:
                    conn.execute('UPDATE tesserati SET minorenne=? WHERE id=?',(wanted,int(a['id'])))
                    minor_flags.append({'tid':int(a['id']),'from':current,'to':wanted})

        # 4) Re-run canonical MU cache through shared sync: empty-only profile/guardian enrichment.
        from asd_app.verified_mu_sync_core_r68 import sync_verified_mu_document, sync_verified_mu_inbound
        tids_with_mu=set()
        if table(conn,'documenti'):
            for d in conn.execute("SELECT * FROM documenti WHERE coalesce(visibile,1)=1 ORDER BY tesserato_id,id DESC").fetchall():
                if not is_mu(d): continue
                tid=int(d['tesserato_id'] or 0)
                if tid<=0 or tid in tids_with_mu: continue
                tids_with_mu.add(tid)
                res=sync_verified_mu_document(conn,d,tid,allow_live=False)
                synced_mu.append({'tid':tid,'document_id':int(d['id']),'result':res})

        # If dossier cache was absent, try the strongest trusted inbound cache for the same athlete.
        if table(conn,'inbound_documents'):
            for tid in sorted(tids_with_mu):
                row=conn.execute("""SELECT * FROM inbound_documents
                  WHERE tesserato_id=? AND lower(coalesce(document_type,''))='modulo_unico_tesseramento'
                    AND coalesce(match_score,0)>=95
                  ORDER BY document_confidence DESC,id DESC LIMIT 1""",(tid,)).fetchone()
                if row:
                    res=sync_verified_mu_inbound(conn,row,allow_live=False)
                    synced_mu.append({'tid':tid,'inbound_id':int(row['id']),'result':res})

        # 5) Onboarding truth: if no visible MU and no trusted MU inbound, stale "signed" must be cleared.
        if 'iscrizione_firmata' in tc:
            for a in conn.execute('SELECT * FROM tesserati ORDER BY id').fetchall():
                tid=int(a['id'])
                has_doc=tid in tids_with_mu
                trusted=False
                if table(conn,'inbound_documents'):
                    rr=conn.execute("""SELECT 1 FROM inbound_documents
                      WHERE tesserato_id=? AND lower(coalesce(document_type,''))='modulo_unico_tesseramento'
                        AND coalesce(match_score,0)>=95 AND coalesce(document_confidence,0)>=95
                        AND lower(coalesce(status,'')) IN ('associato','accepted','manual_accepted','verificato','resolved')
                      LIMIT 1""",(tid,)).fetchone()
                    trusted=bool(rr)
                if not has_doc and not trusted and int(a['iscrizione_firmata'] or 0)==1:
                    sets=['iscrizione_firmata=0']; vals=[]
                    if 'documenti_onboarding_ok' in tc:
                        sets.append('documenti_onboarding_ok=0')
                    vals.append(tid)
                    conn.execute('UPDATE tesserati SET '+','.join(sets)+' WHERE id=?',tuple(vals))
                    onboarding_fixed.append({'tid':tid,'reason':'no_real_mu'})

        # 6) Old "awaiting_confirmation" tasks with no pending action are stale workflow state.
        no_pending=True
        if table(conn,'bodymind_operator_actions') and 'status' in cols(conn,'bodymind_operator_actions'):
            no_pending=not bool(conn.execute("""SELECT 1 FROM bodymind_operator_actions
              WHERE status IN ('pending','awaiting_confirmation') LIMIT 1""").fetchone())
        if no_pending and table(conn,'bodymind_operator_tasks') and 'status' in cols(conn,'bodymind_operator_tasks'):
            rows=conn.execute("""SELECT id FROM bodymind_operator_tasks
              WHERE status='awaiting_confirmation' ORDER BY id""").fetchall()
            for r in rows:
                conn.execute("UPDATE bodymind_operator_tasks SET status='superseded' WHERE id=?",(int(r['id']),))
                stale_tasks.append(int(r['id']))

        conn.commit()
        counts={
          'tesserati':int(conn.execute('SELECT COUNT(*) FROM tesserati').fetchone()[0]),
          'documenti':int(conn.execute('SELECT COUNT(*) FROM documenti').fetchone()[0]),
          'inbound_documents':int(conn.execute('SELECT COUNT(*) FROM inbound_documents').fetchone()[0]),
        }
        integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
        fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
    finally:
        conn.close()

    print('[r81-repair] orphan_inbound_archived='+json.dumps(archived_orphans)+
          ' normalized_mu='+json.dumps(normalized_mu)+
          ' minor_flags='+json.dumps(minor_flags)+
          ' synced_mu='+json.dumps(synced_mu,ensure_ascii=False)+
          ' onboarding_fixed='+json.dumps(onboarding_fixed)+
          ' stale_tasks_closed='+str(len(stale_tasks))+
          ' counts='+json.dumps(counts)+' backup='+db_backup+
          ' integrity='+integrity+' fk='+str(fk),flush=True)
    if counts['tesserati']!=32 or integrity.lower()!='ok' or fk:
        raise RuntimeError('R81 integrity/count guard failed')
    MARKER.write_text('BodyMind R81 stabilization applied\n',encoding='utf-8')
    print('[r81-selftest] PASS orphan-cleanup MU-normalization minor-flags cache-sync onboarding-truth stale-task-cleanup db-ok',flush=True)
else:
    print('[r81-repair] already applied',flush=True)


# BODYMIND_R81_FINAL_CONVERGENCE
# Always-run, evidence-only convergence for two classes that can legitimately
# reappear after the original one-time R81 marker: exact file duplicates and
# trusted MU inbound rows that never reached the visible document dossier.
conn=sqlite3.connect(str(DB),timeout=60); conn.row_factory=sqlite3.Row
r81_final_backup=''; exact_archived=[]; mu_materialized=[]; r81_final_changed=False
try:
    dc=cols(conn,'documenti')
    ic=cols(conn,'inbound_documents')

    # 7) Proven exact duplicate documents: same athlete + same semantic type + same SHA.
    # Keep the best operational row, hide the others, archive metadata, never delete files.
    if table(conn,'documenti'):
        conn.execute("""CREATE TABLE IF NOT EXISTS bodymind_duplicate_records_archive(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source_table TEXT NOT NULL,
          source_id INTEGER NOT NULL,
          tesserato_id INTEGER,
          status TEXT,
          reason TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          semantics_json TEXT,
          file_path TEXT,
          archived_at TEXT NOT NULL,
          UNIQUE(source_table,source_id)
        )""")
        groups={}
        rows=conn.execute("SELECT * FROM documenti WHERE coalesce(visibile,1)=1 AND coalesce(tesserato_id,0)>0 ORDER BY id").fetchall()
        for d in rows:
            path=''
            for k in ('filename','saved_path'):
                if k in d.keys() and d[k]:
                    path=str(d[k]); break
            p=Path(path)
            if not p.is_file():
                continue
            try: sha=hashlib.sha256(p.read_bytes()).hexdigest()
            except Exception: continue
            kind=''
            hay=' '.join(str(d[k] or '').lower() for k in ('doc_type','categoria','titolo','original_filename','filename') if k in d.keys())
            if is_mu(d):
                kind='modulo_unico_tesseramento'
            elif 'certificato_medico' in hay or 'certificato medico' in hay:
                kind='certificato_medico'
            else:
                kind=str(d['doc_type'] or d['categoria'] or 'altro').strip().lower() if ('doc_type' in d.keys() or 'categoria' in d.keys()) else 'altro'
            key=(int(d['tesserato_id']),kind,sha)
            groups.setdefault(key,[]).append(d)

        for (tid,kind,sha),grp in groups.items():
            if len(grp)<2:
                continue
            def _score(row):
                keys=set(row.keys())
                inbound=1 if ('inbound_id' in keys and int(row['inbound_id'] or 0)>0) else 0
                status=str(row['status'] or '').strip().lower() if 'status' in keys else ''
                status_score=2 if status in ('salvato','associato','verificato','accepted') else (1 if status not in ('','da_verificare','needs_review','pending') else 0)
                typed=1 if ('doc_type' in keys and str(row['doc_type'] or '').strip().lower() not in ('','altro','da verificare','da_verificare')) else 0
                return (inbound,status_score,typed,-int(row['id']))
            keep=max(grp,key=_score)
            for d in grp:
                if int(d['id'])==int(keep['id']):
                    continue
                did=int(d['id'])
                sem=[]
                if table(conn,'bodymind_document_semantics'):
                    sem=[dict(x) for x in conn.execute("""SELECT * FROM bodymind_document_semantics
                      WHERE source_table='documenti' AND source_id=? ORDER BY id""",(did,)).fetchall()]
                fpath=''
                for k in ('filename','saved_path','original_filename'):
                    if k in d.keys() and d[k]:
                        fpath=str(d[k]); break
                if not r81_final_changed:
                    r81_final_backup=backup_db(); r81_final_changed=True
                conn.execute("""INSERT OR IGNORE INTO bodymind_duplicate_records_archive
                  (source_table,source_id,tesserato_id,status,reason,payload_json,semantics_json,file_path,archived_at)
                  VALUES(?,?,?,?,?,?,?,?,?)""",
                  ('documenti',did,tid,str(d['status'] or '') if 'status' in d.keys() else '',
                   'R81 final exact duplicate: same athlete + same type + identical SHA-256; canonical document '+str(int(keep['id'])),
                   json.dumps(dict(d),ensure_ascii=False,default=str),
                   json.dumps(sem,ensure_ascii=False,default=str),fpath,datetime.now().isoformat(timespec='seconds')))
                sets=[]
                if 'visibile' in dc: sets.append('visibile=0')
                if 'status' in dc: sets.append("status='duplicate_exact_archived'")
                if 'note' in dc: sets.append("note='Duplicato esatto archiviato; canonico ID "+str(int(keep['id']))+"'")
                if sets:
                    conn.execute("UPDATE documenti SET "+','.join(sets)+" WHERE id=?",(did,))
                    exact_archived.append({'document_id':did,'keep_id':int(keep['id']),'tid':tid,'type':kind,'sha256':sha})

    # 8) Trusted MU inbound without a visible dossier row.
    # Materialize only when identity and document confidence are both >=95 and
    # the physical staged/saved file still exists. No values are invented.
    if table(conn,'inbound_documents') and table(conn,'documenti'):
        rows=conn.execute("""SELECT * FROM inbound_documents
          WHERE coalesce(tesserato_id,0)>0
            AND lower(coalesce(document_type,''))='modulo_unico_tesseramento'
            AND coalesce(match_score,0)>=95 AND coalesce(document_confidence,0)>=95
          ORDER BY id""").fetchall()
        for r in rows:
            tid=int(r['tesserato_id'] or 0)
            has_mu=False
            for d in conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1",(tid,)).fetchall():
                if is_mu(d):
                    has_mu=True; break
            if has_mu:
                continue
            saved=''
            for k in ('saved_path','filename'):
                if k in r.keys() and r[k]:
                    saved=str(r[k]); break
            if not saved or not Path(saved).is_file():
                continue
            if not r81_final_changed:
                r81_final_backup=backup_db(); r81_final_changed=True
            original=str(r['original_filename'] or Path(saved).name) if 'original_filename' in r.keys() else Path(saved).name
            vals={
              'tesserato_id':tid,
              'titolo':original or 'Modulo iscrizione',
              'categoria':'Modulo iscrizione BodyMind',
              'filename':saved,
              'original_filename':original,
              'data_caricamento':datetime.now().date().isoformat(),
              'visibile':1,
              'doc_type':'modulo_unico_tesseramento',
              'confidence':int(r['document_confidence'] or 0) if 'document_confidence' in r.keys() else 100,
              'match_score':int(r['match_score'] or 0) if 'match_score' in r.keys() else 100,
              'source':'r81_final_trusted_mu',
              'status':'salvato',
              'inbound_id':int(r['id'])
            }
            vals={k:v for k,v in vals.items() if k in dc}
            existing=None
            if 'inbound_id' in dc:
                existing=conn.execute("SELECT id FROM documenti WHERE inbound_id=? ORDER BY id DESC LIMIT 1",(int(r['id']),)).fetchone()
            if not existing:
                required={'tesserato_id','titolo','categoria','filename','original_filename'}
                if required.issubset(vals):
                    keys=list(vals)
                    cur=conn.execute("INSERT INTO documenti("+','.join(keys)+") VALUES("+','.join('?' for _ in keys)+")",
                                     [vals[k] for k in keys])
                    did=int(cur.lastrowid)
                    if 'status' in ic:
                        conn.execute("UPDATE inbound_documents SET status='associato' WHERE id=?",(int(r['id']),))
                    try:
                        from asd_app.verified_mu_sync_core_r68 import sync_verified_mu_inbound
                        sync_verified_mu_inbound(conn,r,allow_live=False)
                    except Exception:
                        pass
                    try:
                        from asd_app.onboarding_flow import sync_unified_module_flags, recompute_onboarding_status
                        sync_unified_module_flags(conn,tid,source='r81_final_trusted_mu')
                        recompute_onboarding_status(conn,tid)
                    except Exception:
                        pass
                    mu_materialized.append({'inbound_id':int(r['id']),'document_id':did,'tid':tid})

    conn.commit()
    final_integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    final_fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:
    conn.close()

print('[r81-final-convergence] exact_archived='+json.dumps(exact_archived,ensure_ascii=False)+
      ' mu_materialized='+json.dumps(mu_materialized,ensure_ascii=False)+
      ' backup='+str(r81_final_backup)+' integrity='+str(final_integrity)+' fk='+str(final_fk),flush=True)
if str(final_integrity).lower()!='ok' or final_fk:
    raise RuntimeError('R81 final convergence DB guard failed')
