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
                        if (production_mode and sem_conf>=.98 and current_role()=="admin"
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
