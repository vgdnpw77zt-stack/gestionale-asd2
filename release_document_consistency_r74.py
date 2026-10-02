# -*- coding: utf-8 -*-
from __future__ import annotations
import compileall, hashlib, json, re, shutil, sqlite3, sys
from datetime import datetime
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
BACK=Path('/data/release_backups/20261002_r74_consistency')
BACK.mkdir(parents=True,exist_ok=True)
MARKER=APP/'.BODYMIND_R74_CONSISTENCY'

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

def table(conn,name):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())

def cols(conn,name):
    return {str(r[1]) for r in conn.execute("PRAGMA table_info("+name+")").fetchall()} if table(conn,name) else set()

def backup_file(p:Path):
    try: rel=p.relative_to(APP)
    except Exception: rel=Path(p.name)
    dst=BACK/rel
    if p.exists() and not dst.exists():
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(p,dst)

def backup_db():
    dst=BACK/('pre_r74_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.db')
    src=sqlite3.connect(str(DB),timeout=30)
    out=sqlite3.connect(str(dst))
    try: src.backup(out)
    finally: out.close(); src.close()
    return dst

def norm(v):
    return re.sub(r"[^a-z0-9]","",str(v or "").lower().replace("à","a").replace("è","e").replace("é","e").replace("ì","i").replace("ò","o").replace("ù","u"))

# ------------------------------------------------------------------
# 1) Operator: strong MU + valid CF => create athlete autonomously.
# ------------------------------------------------------------------
OP=APP/'asd_app/routes_operator_bodymind.py'
s=OP.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R74_AUTOCREATE_STRICT_CF' not in s:
    backup_file(OP)
    old=r'''                    else:
                        fields=_enrollment_fields(candidate_conn,semantic)
                        candidate={
                            "inbound_id":inbound_id,
                            "name":name,
                            "analysis":semantic,
                            "preview_fields":fields,
                        }
                        new_athletes.append(candidate)
                        item["status"]="nuova_tesserata_pronta"
                        item["reason"]="Modulo di iscrizione leggibile: nuova anagrafica da confermare"
                        item["new_athlete_preview"]=fields
                        item["handwriting_present"]=semantic.get("handwriting_present")
                        item["handwriting_legibility"]=semantic.get("handwriting_legibility")
                        results.append(item)
                        continue
'''
    new=r'''                    else:
                        # BODYMIND_R74_AUTOCREATE_STRICT_CF
                        # A new enrolment form is created immediately only when:
                        # - production mode is active
                        # - semantic confidence is very high
                        # - Italian fiscal code is formally valid
                        # - admin is executing the flow
                        if (production_mode and current_role()=="admin"
                                and _enrollment_identity_ready(semantic,require_valid_cf=True)):
                            try:
                                _operator_db_backup("r74_auto_enrollment")
                            except Exception:
                                pass
                            cr=_enrollment_create(candidate_conn,semantic,source="operator_r74",require_valid_cf=True)
                            tid=int(cr.get("tesserato_id") or 0)
                            if tid>0:
                                ic=_cols(candidate_conn,"inbound_documents")
                                sets=[]; vals=[]
                                for col in ("tesserato_id","matched_tesserato_id","suggested_tesserato_id"):
                                    if col in ic:
                                        sets.append(col+"=?"); vals.append(tid)
                                if "match_score" in ic:
                                    sets.append("match_score=?"); vals.append(100)
                                if "document_type" in ic:
                                    sets.append("document_type=?"); vals.append("modulo_unico_tesseramento")
                                if "document_confidence" in ic:
                                    sets.append("document_confidence=?"); vals.append(int(round(sem_conf*100)))
                                if sets:
                                    vals.append(inbound_id)
                                    candidate_conn.execute("UPDATE inbound_documents SET "+",".join(sets)+" WHERE id=?",tuple(vals))
                                candidate_conn.commit()
                                item["tesserato_id"]=tid
                                item["new_athlete_created"]=True
                                item["status"]="nuova_tesserata_creata"
                                item["reason"]="Nuova tesserata creata automaticamente da Modulo Unico ad alta certezza con CF valido"
                        if tid<=0:
                            fields=_enrollment_fields(candidate_conn,semantic)
                            candidate={
                                "inbound_id":inbound_id,
                                "name":name,
                                "analysis":semantic,
                                "preview_fields":fields,
                            }
                            new_athletes.append(candidate)
                            item["status"]="nuova_tesserata_pronta"
                            item["reason"]="Modulo leggibile ma identità non abbastanza forte per auto-creazione"
                            item["new_athlete_preview"]=fields
                            item["handwriting_present"]=semantic.get("handwriting_present")
                            item["handwriting_legibility"]=semantic.get("handwriting_legibility")
                            results.append(item)
                            continue
'''
    if old not in s:
        raise RuntimeError('R74 enrollment auto-create anchor missing')
    s=s.replace(old,new,1)

    # Final iPhone composer authority. Avoid scrollIntoView jumps and track the visual viewport.
    css_anchor='''    /* BODYMIND_R73_MOBILE_COMPOSER_AUTONOMY */'''
    if css_anchor not in s:
        raise RuntimeError('R74 R73 composer marker missing')
    inject_css=r'''
    /* BODYMIND_R74_IPHONE_COMPOSER */
    @media(max-width:800px){{
      .bmo-compose-shell{{
        position:fixed!important;left:0!important;right:0!important;
        bottom:var(--bmo-r74-keyboard,0px)!important;z-index:10040!important;
        width:100%!important;padding:8px 8px calc(8px + env(safe-area-inset-bottom))!important;
        background:linear-gradient(180deg,rgba(23,23,23,0),#171717 20%)!important;
      }}
      .bmo-chat{{height:calc(100dvh - 56px)!important;min-height:0!important;overflow:hidden!important}}
      .bmo-messages{{padding-bottom:118px!important;min-height:0!important;overflow-y:auto!important}}
    }}
'''
    # append immediately before the closing style tag of the operator page
    style_end=s.find('</style>',s.find(css_anchor))
    if style_end<0:
        raise RuntimeError('R74 style end missing')
    s=s[:style_end]+inject_css+s[style_end:]

    old_helper=r'''      function bodymindKeepComposerVisible(){{
        try{{
          messages.scrollTop=messages.scrollHeight;
          if(window.matchMedia&&window.matchMedia('(max-width:800px)').matches){{
            const shell=document.querySelector('.bmo-compose-shell');
            if(shell) shell.scrollIntoView({{block:'end',behavior:'smooth'}});
          }}
        }}catch(e){{}}
      }}
'''
    new_helper=r'''      function bodymindR74Viewport(){{
        try{{
          let kb=0;
          if(window.visualViewport){{
            kb=Math.max(0,window.innerHeight-(window.visualViewport.height+window.visualViewport.offsetTop));
          }}
          document.documentElement.style.setProperty('--bmo-r74-keyboard',Math.round(kb)+'px');
        }}catch(e){{}}
      }}
      function bodymindKeepComposerVisible(){{
        try{{
          bodymindR74Viewport();
          messages.scrollTop=messages.scrollHeight;
        }}catch(e){{}}
      }}
      if(window.visualViewport){{
        window.visualViewport.addEventListener('resize',bodymindR74Viewport);
        window.visualViewport.addEventListener('scroll',bodymindR74Viewport);
      }}
      window.addEventListener('resize',bodymindR74Viewport);
      input?.addEventListener('focus',()=>setTimeout(bodymindR74Viewport,40));
      input?.addEventListener('blur',()=>setTimeout(bodymindR74Viewport,80));
      bodymindR74Viewport();
'''
    if old_helper not in s:
        raise RuntimeError('R74 composer helper anchor missing')
    s=s.replace(old_helper,new_helper,1)
    OP.write_text(s,encoding='utf-8')
    compileall.compile_file(str(OP),quiet=1)

# ------------------------------------------------------------------
# 2) Dossier/UI: verified MU + satisfied tutela => no false orange banner.
# ------------------------------------------------------------------
COH=APP/'asd_app/routes_document_coherence_r41.py'
c=COH.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R74_TUTELA_FROM_MU' not in c:
    backup_file(COH)
    anchor='''def _replace_contextual_not_generated(html,state):
'''
    helper=r'''# BODYMIND_R74_TUTELA_FROM_MU
def _tutela_satisfied(tid):
    if tid<=0:
        return False
    conn=db()
    try:
        t=conn.execute("SELECT * FROM tesserati WHERE id=?",(tid,)).fetchone()
        if not t:
            return False
        keys=set(t.keys())
        try:
            minor=int(t['minorenne'] or 0)==1 if 'minorenne' in keys else False
        except Exception:
            minor=False
        if not minor:
            return True
        guardian=''
        for k in ('genitore','nome_genitore'):
            if k in keys and t[k]:
                guardian=str(t[k]).strip()
                if guardian: break
        if not guardian:
            return False
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='minori'").fetchone():
            m=conn.execute("SELECT * FROM minori WHERE tesserato_id=? LIMIT 1",(tid,)).fetchone()
            if m:
                mk=set(m.keys())
                if 'consenso_firmato' in mk and int(m['consenso_firmato'] or 0)!=1:
                    return False
        return True
    finally:
        conn.close()

'''
    if anchor not in c:
        raise RuntimeError('R74 tutela helper anchor missing')
    c=c.replace(anchor,helper+anchor,1)

    after_anchor='''        if state:
            html=_replace_contextual_not_generated(html,state)
'''
    after_new='''        if state:
            html=_replace_contextual_not_generated(html,state)
            if state=='verified' and _tutela_satisfied(tid):
                # A verified MU plus coherent guardian/minor data must not keep the stale orange warning.
                html=re.sub(r"(?is)<div[^>]*>\s*<[^>]*>\s*Attenzione tutela minori\..*?</div>","",html,count=1)
                html=re.sub(r"(?is)<div[^>]*>.*?Attenzione tutela minori\..*?Serve genitore.*?</div>","",html,count=1)
'''
    if after_anchor not in c:
        raise RuntimeError('R74 tutela after_request anchor missing')
    c=c.replace(after_anchor,after_new,1)
    COH.write_text(c,encoding='utf-8')
    compileall.compile_file(str(COH),quiet=1)

# ------------------------------------------------------------------
# 3) Existing trusted MU reconciliation + safe semantic duplicate archive.
# ------------------------------------------------------------------
db_backup=backup_db()
sys.path.insert(0,str(APP))
from asd_app.verified_mu_sync_core_r68 import sync_verified_mu_inbound

conn=sqlite3.connect(str(DB),timeout=45)
conn.row_factory=sqlite3.Row
reconciled=[]
archived=[]
remaining_groups=[]
target_audit=[]
try:
    before={
      'tesserati':int(conn.execute('SELECT COUNT(*) FROM tesserati').fetchone()[0]),
      'documenti':int(conn.execute('SELECT COUNT(*) FROM documenti').fetchone()[0]),
      'inbound_documents':int(conn.execute('SELECT COUNT(*) FROM inbound_documents').fetchone()[0]),
    }

    # Reconcile all trusted MU from cache only. No cloud calls during startup.
    if table(conn,'inbound_documents'):
        rows=conn.execute("""SELECT * FROM inbound_documents
          WHERE coalesce(tesserato_id,0)>0
            AND lower(coalesce(document_type,'')) IN ('modulo_unico_tesseramento','iscrizione','domanda_iscrizione','manleva')
            AND lower(coalesce(status,'')) IN ('associato','accepted','manual_accepted','verificato')
            AND coalesce(document_confidence,0)>=95
          ORDER BY id DESC""").fetchall()
        seen=set()
        for row in rows:
            tid=int(row['tesserato_id'] or 0)
            if tid in seen: continue
            seen.add(tid)
            res=sync_verified_mu_inbound(conn,row,allow_live=False)
            reconciled.append({'id':int(row['id']),'tid':tid,'ok':bool(res.get('ok')),'reason':res.get('reason'),'identity':res.get('identity_check')})

    # Strong semantic duplicate groups in dossier only.
    if table(conn,'bodymind_document_semantics') and table(conn,'documenti'):
        semrows=conn.execute("""SELECT s.*,d.tesserato_id,d.status,d.visibile,d.filename,d.titolo,d.categoria,d.doc_type
            FROM bodymind_document_semantics s
            JOIN documenti d ON s.source_table='documenti' AND s.source_id=d.id
            WHERE coalesce(d.tesserato_id,0)>0 AND coalesce(d.visibile,1)=1
              AND coalesce(s.confidence,0)>=0.95
            ORDER BY s.id DESC""").fetchall()
        latest={}
        for r in semrows:
            sid=int(r['source_id'])
            if sid not in latest:
                latest[sid]=r
        groups={}
        for r in latest.values():
            dtype=str(r['document_type'] or '').strip().lower()
            sk=str(r['semantic_key'] or '').strip()
            sha=str(r['sha256'] or '').strip()
            if not dtype or dtype=='altro':
                continue
            tid=int(r['tesserato_id'])
            # Exact semantic key is strongest; exact SHA remains valid fallback.
            key=(tid,dtype,'sem',sk) if sk else ((tid,dtype,'sha',sha) if sha else None)
            if key:
                groups.setdefault(key,[]).append(r)
        for key,items in groups.items():
            if len(items)<2:
                continue
            # Keep newest active copy; archive older active copies, never delete files.
            items=sorted(items,key=lambda x:int(x['source_id']),reverse=True)
            keep=int(items[0]['source_id'])
            for r in items[1:]:
                rid=int(r['source_id'])
                dc=cols(conn,'documenti')
                sets=[]; vals=[]
                if 'visibile' in dc: sets.append('visibile=0')
                if 'status' in dc: sets.append('status=?'); vals.append('semantic_duplicate_archived_r74')
                if 'note' in dc:
                    sets.append('note=?')
                    vals.append('Duplicato semantico forte archiviato R74; copia attiva ID '+str(keep))
                if sets:
                    vals.append(rid)
                    cur=conn.execute('UPDATE documenti SET '+','.join(sets)+' WHERE id=? AND coalesce(visibile,1)=1',tuple(vals))
                    if int(cur.rowcount or 0)==1:
                        archived.append({'keep':keep,'archived':rid,'tid':int(r['tesserato_id']),'type':str(r['document_type'])})

        # Report unresolved same-person/same-type multi-doc groups without auto-deleting them.
        rows=conn.execute("""SELECT tesserato_id,coalesce(doc_type,categoria,''),COUNT(*) n
            FROM documenti WHERE coalesce(visibile,1)=1 AND coalesce(tesserato_id,0)>0
            GROUP BY tesserato_id,coalesce(doc_type,categoria,'') HAVING COUNT(*)>1
            ORDER BY n DESC""").fetchall()
        remaining_groups=[(int(x[0]),str(x[1]),int(x[2])) for x in rows[:80]]

    # Targeted read-only audit for the reported cases.
    rows=conn.execute("SELECT * FROM tesserati ORDER BY id").fetchall()
    for t in rows:
        full=(str(t['nome'] or '')+' '+str(t['cognome'] or '')).strip()
        n=norm(full)
        if 'angelucci' not in n and 'dangelo' not in n:
            continue
        tid=int(t['id'])
        tk=set(t.keys())
        docs=conn.execute("SELECT id,titolo,categoria,doc_type,status,visibile,filename FROM documenti WHERE tesserato_id=? ORDER BY id",(tid,)).fetchall()
        inbound=conn.execute("SELECT id,document_type,status,document_confidence,match_score,original_filename FROM inbound_documents WHERE coalesce(tesserato_id,0)=? ORDER BY id",(tid,)).fetchall()
        target_audit.append({
          'id':tid,'name':full,
          'guardian':str(t['genitore'] or '') if 'genitore' in tk else '',
          'guardian_phone':str(t['telefono_genitore'] or '') if 'telefono_genitore' in tk else '',
          'minor':int(t['minorenne'] or 0) if 'minorenne' in tk else None,
          'docs':[dict(x) for x in docs],
          'inbound':[dict(x) for x in inbound],
        })

    conn.commit()
    after={
      'tesserati':int(conn.execute('SELECT COUNT(*) FROM tesserati').fetchone()[0]),
      'documenti':int(conn.execute('SELECT COUNT(*) FROM documenti').fetchone()[0]),
      'inbound_documents':int(conn.execute('SELECT COUNT(*) FROM inbound_documents').fetchone()[0]),
    }
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:
    conn.close()


# ------------------------------------------------------------------
# R75 hardening: one active trusted MU per athlete/season + hide archived rows in dossier.
# ------------------------------------------------------------------
DOCS=APP/'asd_app/routes_documenti.py'
dsrc=DOCS.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R75_HIDE_ARCHIVED_DOCS' not in dsrc:
    backup_file(DOCS)
    original=dsrc
    patterns=[
      (r'FROM documenti WHERE tesserato_id=\? ORDER BY', 'FROM documenti WHERE tesserato_id=? AND COALESCE(visibile,1)=1 ORDER BY'),
      (r'FROM documenti WHERE tesserato_id = \? ORDER BY', 'FROM documenti WHERE tesserato_id = ? AND COALESCE(visibile,1)=1 ORDER BY'),
    ]
    for pat,repl in patterns:
        dsrc=re.sub(pat,repl,dsrc)
    # If the main dossier query aliases the table, cover that exact read pattern too.
    dsrc=re.sub(r'FROM documenti d WHERE d\.tesserato_id=\? ORDER BY',
                'FROM documenti d WHERE d.tesserato_id=? AND COALESCE(d.visibile,1)=1 ORDER BY',dsrc)
    dsrc=re.sub(r'FROM documenti d WHERE d\.tesserato_id = \? ORDER BY',
                'FROM documenti d WHERE d.tesserato_id = ? AND COALESCE(d.visibile,1)=1 ORDER BY',dsrc)
    if dsrc!=original:
        # Safe source marker.
        dsrc='# BODYMIND_R75_HIDE_ARCHIVED_DOCS\n'+dsrc
        DOCS.write_text(dsrc,encoding='utf-8')
        if not compileall.compile_file(str(DOCS),quiet=1):
            raise RuntimeError('R75 routes_documenti compile failed')
        print('[r75-dossier-filter] PASS archived visibile=0 excluded from tesserato dossier reads',flush=True)
    else:
        print('[r75-dossier-filter] no matching dossier SQL anchor; runtime query unchanged',flush=True)

conn=sqlite3.connect(str(DB),timeout=45); conn.row_factory=sqlite3.Row
try:
    dc=cols(conn,'documenti')
    trusted_status={'salvato','verificato','accepted','manual_accepted','ok'}
    rows=conn.execute("SELECT * FROM documenti WHERE coalesce(tesserato_id,0)>0 AND coalesce(visibile,1)=1 ORDER BY tesserato_id,id DESC").fetchall()
    mu=[]
    for r in rows:
        hay=' '.join(str(r[k] or '').strip().lower() for k in ('doc_type','categoria','titolo','filename') if k in r.keys())
        is_mu=('modulo_unico_tesseramento' in hay or 'modulo iscrizione' in hay or 'modulo unico' in hay or 'domanda iscrizione' in hay or 'iscrizione manleva' in hay)
        st=str(r['status'] or '').strip().lower() if 'status' in r.keys() else ''
        if is_mu and st in trusted_status:
            mu.append(r)

    groups={}
    for r in mu:
        tid=int(r['tesserato_id'])
        groups.setdefault(tid,[]).append(r)

    r75_archived=[]
    for tid,items in groups.items():
        if len(items)<2:
            continue
        # BodyMind invariant: one active Modulo Unico per athlete.
        # Historical copies remain on disk and are only hidden/archived.
        items=sorted(items,key=lambda x:int(x['id']),reverse=True)
        keep=int(items[0]['id'])
        for old in items[1:]:
            oid=int(old['id'])
            sets=[]; vals=[]
            if 'visibile' in dc: sets.append('visibile=0')
            if 'status' in dc: sets.append('status=?'); vals.append('mu_duplicate_archived_r75')
            if 'note' in dc:
                sets.append('note=?'); vals.append('Modulo Unico precedente archiviato R75; unica copia attiva ID '+str(keep))
            vals.append(oid)
            cur=conn.execute('UPDATE documenti SET '+','.join(sets)+' WHERE id=? AND coalesce(visibile,1)=1',tuple(vals))
            if int(cur.rowcount or 0)==1:
                r75_archived.append({'tid':tid,'keep':keep,'archived':oid})

    conn.commit()
    active_mu_dupes=[]
    rows=conn.execute("""SELECT tesserato_id,COUNT(*) n FROM documenti
        WHERE coalesce(tesserato_id,0)>0 AND coalesce(visibile,1)=1
          AND (lower(coalesce(doc_type,''))='modulo_unico_tesseramento'
               OR lower(coalesce(categoria,'')) LIKE '%modulo iscrizione%'
               OR lower(coalesce(titolo,'')) LIKE '%modulo unico%')
        GROUP BY tesserato_id HAVING COUNT(*)>1 ORDER BY n DESC""").fetchall()
    active_mu_dupes=[(int(x[0]),int(x[1])) for x in rows]
    integrity75=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk75=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:
    conn.close()

print('[r75-mu-single-active] archived='+json.dumps(r75_archived,ensure_ascii=False)+' remaining='+json.dumps(active_mu_dupes),flush=True)
if integrity75.lower()!='ok' or fk75:
    raise RuntimeError('R75 DB integrity failed')
if active_mu_dupes:
    raise RuntimeError('R75 still has duplicate active MU '+repr(active_mu_dupes))

print('[r74-target-audit] '+json.dumps(target_audit,ensure_ascii=False),flush=True)
print('[r74-dedupe] archived='+json.dumps(archived,ensure_ascii=False)+' remaining_groups='+json.dumps(remaining_groups,ensure_ascii=False),flush=True)
print('[r74-mu-reconcile] '+json.dumps(reconciled,ensure_ascii=False),flush=True)
print('[r74-counts] before='+repr(before)+' after='+repr(after)+' integrity='+integrity+' fk='+str(fk)+' backup='+db_backup.name,flush=True)

if before!=after:
    # visibility/status changes are allowed; row counts must remain identical.
    raise RuntimeError('R74 business row counts changed unexpectedly')
if integrity.lower()!='ok' or fk:
    raise RuntimeError('R74 database integrity failed')
if 'BODYMIND_R74_AUTOCREATE_STRICT_CF' not in OP.read_text(encoding='utf-8',errors='replace'):
    raise RuntimeError('R74 operator marker missing')
if 'BODYMIND_R74_TUTELA_FROM_MU' not in COH.read_text(encoding='utf-8',errors='replace'):
    raise RuntimeError('R74 tutela marker missing')

MARKER.write_text('BodyMind R74 consistency active\n',encoding='utf-8')
print('[r74-selftest] PASS strict-CF-autocreate trusted-MU-tutela semantic-dedupe no-file-delete iphone-visualViewport db-ok',flush=True)


# ------------------------------------------------------------------
# R76: physically clean proven duplicate rows from operational tables.
# Full payload + semantic cache is retained in an audit archive table.
# Physical media files are NEVER deleted here.
# ------------------------------------------------------------------
R76_MARKER=APP/'.BODYMIND_R76_DUPLICATE_DB_CLEANUP'
if not R76_MARKER.exists():
    r76_backup=backup_db()
    conn=sqlite3.connect(str(DB),timeout=60); conn.row_factory=sqlite3.Row
    deleted_docs=[]; deleted_inbound=[]; blocked76=[]
    try:
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

        doc_dup_status={
          'semantic_duplicate_archived','semantic_duplicate_archived_r74',
          'mu_duplicate_archived_r75','duplicate_exact','duplicato_confermato',
          'duplicato_non_importato','duplicate_confirmed','duplicate_archived'
        }
        inbound_dup_status={
          'duplicate_exact','duplicato_confermato','duplicato_non_importato',
          'duplicate_confirmed','semantic_duplicate_archived','duplicate_archived'
        }

        def semantics_for(source_table,source_id):
            if not table(conn,'bodymind_document_semantics'):
                return []
            rows=conn.execute("SELECT * FROM bodymind_document_semantics WHERE source_table=? AND source_id=? ORDER BY id",
                              (source_table,int(source_id))).fetchall()
            return [dict(x) for x in rows]

        def reference_hits(source_table,source_id):
            hits=[]
            tables=[str(x[0]) for x in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
            obvious={'documenti':{'document_id','doc_id','documento_id'},
                     'inbound_documents':{'inbound_id','inbound_document_id'}}[source_table]
            for tn in tables:
                if tn in {source_table,'bodymind_document_semantics','bodymind_duplicate_records_archive'}:
                    continue
                tcols={str(x[1]) for x in conn.execute("PRAGMA table_info("+tn+")").fetchall()}
                refs=set(obvious & tcols)
                try:
                    for fkrow in conn.execute("PRAGMA foreign_key_list("+tn+")").fetchall():
                        if str(fkrow[2])==source_table:
                            refs.add(str(fkrow[3]))
                except Exception:
                    pass
                for col in refs:
                    try:
                        n=int(conn.execute("SELECT COUNT(*) FROM "+tn+" WHERE "+col+"=?",(int(source_id),)).fetchone()[0])
                    except Exception:
                        n=0
                    if n:
                        hits.append((tn,col,n))
            return hits

        def archive_row(source_table,row,reason):
            keys=set(row.keys())
            sid=int(row['id'])
            tid=int(row['tesserato_id'] or 0) if 'tesserato_id' in keys else 0
            status=str(row['status'] or '') if 'status' in keys else ''
            fpath=''
            for k in ('filename','saved_path','original_filename'):
                if k in keys and row[k]:
                    fpath=str(row[k]); break
            sem=semantics_for(source_table,sid)
            conn.execute("""INSERT OR IGNORE INTO bodymind_duplicate_records_archive
              (source_table,source_id,tesserato_id,status,reason,payload_json,semantics_json,file_path,archived_at)
              VALUES(?,?,?,?,?,?,?,?,?)""",
              (source_table,sid,tid,status,reason,json.dumps(dict(row),ensure_ascii=False,default=str),
               json.dumps(sem,ensure_ascii=False,default=str),fpath,datetime.now().isoformat(timespec='seconds')))
            if table(conn,'bodymind_document_semantics'):
                conn.execute("DELETE FROM bodymind_document_semantics WHERE source_table=? AND source_id=?",(source_table,sid))

        # Documents first: this can free inbound rows that were referenced only by a duplicate dossier row.
        if table(conn,'documenti'):
            rows=conn.execute("SELECT * FROM documenti ORDER BY id").fetchall()
            for row in rows:
                st=str(row['status'] or '').strip().lower() if 'status' in row.keys() else ''
                if st not in doc_dup_status:
                    continue
                sid=int(row['id'])
                hits=reference_hits('documenti',sid)
                if hits:
                    blocked76.append({'table':'documenti','id':sid,'status':st,'references':hits})
                    continue
                archive_row('documenti',row,'R76 proven duplicate cleanup')
                conn.execute("DELETE FROM documenti WHERE id=?",(sid,))
                deleted_docs.append(sid)

        if table(conn,'inbound_documents'):
            rows=conn.execute("SELECT * FROM inbound_documents ORDER BY id").fetchall()
            for row in rows:
                st=str(row['status'] or '').strip().lower() if 'status' in row.keys() else ''
                if st not in inbound_dup_status:
                    continue
                sid=int(row['id'])
                hits=reference_hits('inbound_documents',sid)
                if hits:
                    blocked76.append({'table':'inbound_documents','id':sid,'status':st,'references':hits})
                    continue
                archive_row('inbound_documents',row,'R76 proven duplicate cleanup')
                conn.execute("DELETE FROM inbound_documents WHERE id=?",(sid,))
                deleted_inbound.append(sid)

        conn.commit()
        remaining_doc_dups=0
        remaining_inbound_dups=0
        if table(conn,'documenti'):
            qs=','.join('?' for _ in doc_dup_status)
            remaining_doc_dups=int(conn.execute("SELECT COUNT(*) FROM documenti WHERE lower(coalesce(status,'')) IN ("+qs+")",tuple(sorted(doc_dup_status))).fetchone()[0])
        if table(conn,'inbound_documents'):
            qs=','.join('?' for _ in inbound_dup_status)
            remaining_inbound_dups=int(conn.execute("SELECT COUNT(*) FROM inbound_documents WHERE lower(coalesce(status,'')) IN ("+qs+")",tuple(sorted(inbound_dup_status))).fetchone()[0])
        counts76={
          'tesserati':int(conn.execute('SELECT COUNT(*) FROM tesserati').fetchone()[0]),
          'documenti':int(conn.execute('SELECT COUNT(*) FROM documenti').fetchone()[0]),
          'inbound_documents':int(conn.execute('SELECT COUNT(*) FROM inbound_documents').fetchone()[0]),
          'duplicate_archive':int(conn.execute('SELECT COUNT(*) FROM bodymind_duplicate_records_archive').fetchone()[0]),
        }
        integrity76=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
        fk76=len(conn.execute('PRAGMA foreign_key_check').fetchall())
    finally:
        conn.close()

    print('[r76-db-cleanup] deleted_documenti='+json.dumps(deleted_docs)+
          ' deleted_inbound='+json.dumps(deleted_inbound)+
          ' blocked='+json.dumps(blocked76,ensure_ascii=False)+
          ' remaining_doc_dups='+str(remaining_doc_dups)+
          ' remaining_inbound_dups='+str(remaining_inbound_dups)+
          ' counts='+json.dumps(counts76)+
          ' backup='+r76_backup.name+
          ' integrity='+integrity76+' fk='+str(fk76),flush=True)

    if counts76['tesserati']!=32:
        raise RuntimeError('R76 refused: tesserati count changed')
    if integrity76.lower()!='ok' or fk76:
        raise RuntimeError('R76 database integrity failed')
    if remaining_doc_dups or remaining_inbound_dups:
        # Referenced duplicate rows remain operationally hidden rather than breaking links.
        if not blocked76:
            raise RuntimeError('R76 unexplained duplicate rows remain')
    R76_MARKER.write_text('BodyMind R76 duplicate DB cleanup completed\\n',encoding='utf-8')
    print('[r76-selftest] PASS backup audit-archive proven-duplicates-only no-media-delete referential-safety db-ok',flush=True)
else:
    print('[r76-db-cleanup] already applied',flush=True)


# ------------------------------------------------------------------
# R77: finish inbound duplicate cleanup with event archival and safe relinking.
# ------------------------------------------------------------------
R77_MARKER=APP/'.BODYMIND_R77_INBOUND_DUPLICATE_CLEANUP'
if not R77_MARKER.exists():
    r77_backup=backup_db()
    conn=sqlite3.connect(str(DB),timeout=60); conn.row_factory=sqlite3.Row
    deleted77=[]; relinked77=[]; blocked77=[]; event_archived77=0
    try:
        dup_status={
          'duplicate_exact','duplicato_confermato','duplicato_non_importato',
          'duplicate_confirmed','semantic_duplicate_archived','duplicate_archived'
        }

        def sem_sig(iid):
            if not table(conn,'bodymind_document_semantics'):
                return None
            rows=conn.execute("""SELECT * FROM bodymind_document_semantics
                WHERE source_table='inbound_documents' AND source_id=? ORDER BY id DESC""",(int(iid),)).fetchall()
            if not rows: return None
            r=rows[0]
            return {
              'sha':str(r['sha256'] or '').strip(),
              'key':str(r['semantic_key'] or '').strip(),
              'type':str(r['document_type'] or '').strip().lower(),
              'cf':str(r['codice_fiscale'] or '').strip().upper(),
              'confidence':float(r['confidence'] or 0),
            }

        def canonical_for(row):
            iid=int(row['id']); keys=set(row.keys())
            tid=int(row['tesserato_id'] or 0) if 'tesserato_id' in keys else 0
            dtype=str(row['document_type'] or '').strip().lower() if 'document_type' in keys else ''
            sig=sem_sig(iid)
            candidates=conn.execute("""SELECT * FROM inbound_documents
                WHERE id<>? AND coalesce(tesserato_id,0)=?
                  AND lower(coalesce(document_type,''))=?
                  AND lower(coalesce(status,'')) NOT IN ('duplicate_exact','duplicato_confermato','duplicato_non_importato','duplicate_confirmed','semantic_duplicate_archived','duplicate_archived')
                ORDER BY id DESC""",(iid,tid,dtype)).fetchall()
            strong=[]
            for c in candidates:
                cs=sem_sig(int(c['id']))
                if not sig or not cs:
                    continue
                same_sha=bool(sig['sha'] and cs['sha'] and sig['sha']==cs['sha'])
                same_key=bool(sig['key'] and cs['key'] and sig['key']==cs['key'])
                same_type=(sig['type']==cs['type']==dtype) if dtype else (sig['type']==cs['type'])
                cf_ok=(not sig['cf'] or not cs['cf'] or sig['cf']==cs['cf'])
                if same_type and cf_ok and (same_sha or same_key):
                    strong.append(c)
            return strong[0] if len(strong)==1 else None

        rows=conn.execute("SELECT * FROM inbound_documents ORDER BY id").fetchall() if table(conn,'inbound_documents') else []
        for row in rows:
            st=str(row['status'] or '').strip().lower() if 'status' in row.keys() else ''
            if st not in dup_status:
                continue
            iid=int(row['id'])

            # Any dossier document pointing at this inbound must be relinked only to a proven canonical sibling.
            docrefs=[]
            if table(conn,'documenti') and 'inbound_id' in cols(conn,'documenti'):
                docrefs=conn.execute("SELECT * FROM documenti WHERE inbound_id=?",(iid,)).fetchall()
            canonical=canonical_for(row) if docrefs else None
            if docrefs and not canonical:
                blocked77.append({'id':iid,'status':st,'reason':'document_reference_without_proven_canonical',
                                  'document_ids':[int(x['id']) for x in docrefs]})
                continue
            if docrefs and canonical:
                cid=int(canonical['id'])
                conn.execute("UPDATE documenti SET inbound_id=? WHERE inbound_id=?",(cid,iid))
                relinked77.append({'from':iid,'to':cid,'document_ids':[int(x['id']) for x in docrefs]})

            # Archive inbound row + all its events inside the audit record before deletion.
            events=[]
            if table(conn,'inbound_events') and 'inbound_document_id' in cols(conn,'inbound_events'):
                events=[dict(x) for x in conn.execute("SELECT * FROM inbound_events WHERE inbound_document_id=? ORDER BY id",(iid,)).fetchall()]
            sem=[]
            if table(conn,'bodymind_document_semantics'):
                sem=[dict(x) for x in conn.execute("SELECT * FROM bodymind_document_semantics WHERE source_table='inbound_documents' AND source_id=? ORDER BY id",(iid,)).fetchall()]
            payload={'row':dict(row),'inbound_events':events}
            tid=int(row['tesserato_id'] or 0) if 'tesserato_id' in row.keys() else 0
            fpath=''
            for k in ('saved_path','filename','original_filename'):
                if k in row.keys() and row[k]:
                    fpath=str(row[k]); break
            conn.execute("""INSERT OR IGNORE INTO bodymind_duplicate_records_archive
              (source_table,source_id,tesserato_id,status,reason,payload_json,semantics_json,file_path,archived_at)
              VALUES(?,?,?,?,?,?,?,?,?)""",
              ('inbound_documents',iid,tid,st,'R77 proven inbound duplicate cleanup',
               json.dumps(payload,ensure_ascii=False,default=str),
               json.dumps(sem,ensure_ascii=False,default=str),fpath,datetime.now().isoformat(timespec='seconds')))

            if events:
                conn.execute("DELETE FROM inbound_events WHERE inbound_document_id=?",(iid,))
                event_archived77 += len(events)
            if table(conn,'bodymind_document_semantics'):
                conn.execute("DELETE FROM bodymind_document_semantics WHERE source_table='inbound_documents' AND source_id=?",(iid,))
            conn.execute("DELETE FROM inbound_documents WHERE id=?",(iid,))
            deleted77.append(iid)

        conn.commit()
        remaining77=[]
        if table(conn,'inbound_documents'):
            qs=','.join('?' for _ in dup_status)
            remaining77=[dict(x) for x in conn.execute(
                "SELECT id,status,tesserato_id,document_type,original_filename FROM inbound_documents WHERE lower(coalesce(status,'')) IN ("+qs+") ORDER BY id",
                tuple(sorted(dup_status))).fetchall()]
        counts77={
          'tesserati':int(conn.execute('SELECT COUNT(*) FROM tesserati').fetchone()[0]),
          'documenti':int(conn.execute('SELECT COUNT(*) FROM documenti').fetchone()[0]),
          'inbound_documents':int(conn.execute('SELECT COUNT(*) FROM inbound_documents').fetchone()[0]),
          'duplicate_archive':int(conn.execute('SELECT COUNT(*) FROM bodymind_duplicate_records_archive').fetchone()[0]),
        }
        integrity77=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
        fk77=len(conn.execute('PRAGMA foreign_key_check').fetchall())
    finally:
        conn.close()

    print('[r77-inbound-cleanup] deleted='+json.dumps(deleted77)+
          ' relinked='+json.dumps(relinked77,ensure_ascii=False)+
          ' events_archived='+str(event_archived77)+
          ' blocked='+json.dumps(blocked77,ensure_ascii=False)+
          ' remaining='+json.dumps(remaining77,ensure_ascii=False)+
          ' counts='+json.dumps(counts77)+
          ' backup='+r77_backup.name+
          ' integrity='+integrity77+' fk='+str(fk77),flush=True)

    if counts77['tesserati']!=32:
        raise RuntimeError('R77 refused: tesserati count changed')
    if integrity77.lower()!='ok' or fk77:
        raise RuntimeError('R77 database integrity failed')
    if remaining77 and not blocked77:
        raise RuntimeError('R77 unexplained duplicate inbound rows remain')
    R77_MARKER.write_text('BodyMind R77 inbound duplicate cleanup completed\\n',encoding='utf-8')
    print('[r77-selftest] PASS events-archived semantic-canonical-relink proven-duplicates-only no-media-delete db-ok',flush=True)
else:
    print('[r77-inbound-cleanup] already applied',flush=True)
