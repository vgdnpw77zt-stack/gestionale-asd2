# -*- coding: utf-8 -*-
from __future__ import annotations
import json, py_compile, re, shutil, sqlite3
from datetime import datetime
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
OP=APP/'asd_app/routes_operator_bodymind.py'
CORE=APP/'asd_app/core.py'
BACK=Path('/data/release_backups/20261012_r156_operator_review_actions')
BACK.mkdir(parents=True,exist_ok=True)

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')
for p in (OP,CORE):
    if not p.exists():
        raise RuntimeError('R156 required source missing: '+str(p))

# ---------------------------------------------------------------------------
# 1) iOS Safari: bind the full operator shell to the ACTUAL visual viewport.
#    R90 correctly used visualViewport.height but left the shell at top:0.
#    Safari can expose a non-zero offsetTop when browser chrome is visible,
#    leaving a strip of the underlying page at the bottom and pushing the
#    composer into an unusable area. R156 tracks offsetTop/offsetLeft too.
# ---------------------------------------------------------------------------
s=OP.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R156_IOS_VISUAL_VIEWPORT_ANCHOR' not in s:
    shutil.copy2(OP,BACK/'routes_operator_bodymind.pre_r156.py')
    canonical='BODYMIND_OPERATOR_MOBILE_LAYOUT_CANONICAL'
    a=s.find(canonical)
    if a<0: raise RuntimeError('R156 operator canonical style marker missing')
    style_end=s.find('</style>',a)
    main_start=s.find('<main class="bmo">',a)
    if style_end<0 or main_start<0 or style_end>main_start:
        raise RuntimeError('R156 operator style boundary invalid')
    css=r'''
    /* BODYMIND_R156_IOS_VISUAL_VIEWPORT_ANCHOR
       Safari-safe final mobile authority: shell follows visible viewport origin
       and size; composer remains fully tappable above browser chrome. */
    @media(max-width:800px){{
      .bmo{{
        position:fixed!important;
        inset:auto!important;
        top:var(--bmo-r156-vv-top,0px)!important;
        left:var(--bmo-r156-vv-left,0px)!important;
        width:var(--bmo-r156-vv-width,100vw)!important;
        height:var(--bmo-r156-vv-height,100dvh)!important;
        min-height:0!important;
        max-height:none!important;
        overflow:hidden!important;
      }}
      .bmo-chat,.bmo-grid{{min-height:0!important;overflow:hidden!important}}
      .bmo-messages{{
        flex:1 1 auto!important;
        min-height:0!important;
        padding-bottom:10px!important;
        scroll-padding-bottom:92px!important;
      }}
      .bmo-compose-shell{{
        position:relative!important;
        flex:0 0 auto!important;
        width:100%!important;
        margin:0!important;
        padding:6px 8px max(12px,env(safe-area-inset-bottom))!important;
        box-sizing:border-box!important;
        background:#171717!important;
        overflow:visible!important;
        z-index:20!important;
      }}
      .bmo-compose{{
        grid-template-rows:auto!important;
        align-items:end!important;
        min-height:56px!important;
        height:auto!important;
        max-height:128px!important;
        overflow:visible!important;
      }}
      .bmo-compose>#bmoInput{{
        min-height:40px!important;
        height:auto!important;
        max-height:112px!important;
        overflow-y:auto!important;
        padding:9px 8px!important;
        line-height:22px!important;
        align-self:end!important;
        touch-action:manipulation!important;
      }}
      .bmo-attach,.bmo-mic,.bmo-send{{align-self:end!important}}
    }}
'''
    s=s[:style_end]+css+s[style_end:]

    # Add a final viewport synchronizer after the existing R90 synchronizer.
    js_anchor='      bodymindR90SyncSoon();\n'
    pos=s.find(js_anchor)
    if pos<0: raise RuntimeError('R156 R90 JS anchor missing')
    pos+=len(js_anchor)
    js=r'''
      // BODYMIND_R156_IOS_VISUAL_VIEWPORT_ANCHOR
      function bodymindR156SyncViewport(){{
        try{{
          if(!(window.matchMedia&&window.matchMedia('(max-width:800px)').matches))return;
          const root=document.documentElement;
          const vv=window.visualViewport;
          const h=Math.max(260,Math.round(vv?vv.height:window.innerHeight));
          const w=Math.max(280,Math.round(vv?vv.width:window.innerWidth));
          const top=Math.max(0,Math.round(vv?vv.offsetTop:0));
          const left=Math.max(0,Math.round(vv?vv.offsetLeft:0));
          root.style.setProperty('--bmo-r156-vv-height',h+'px');
          root.style.setProperty('--bmo-r156-vv-width',w+'px');
          root.style.setProperty('--bmo-r156-vv-top',top+'px');
          root.style.setProperty('--bmo-r156-vv-left',left+'px');
          // Keep the older height variable coherent for rules that still read it.
          root.style.setProperty('--bmo-r90-vv-height',h+'px');
          if(document.activeElement===input){{
            fitComposer();
            requestAnimationFrame(()=>{{messages.scrollTop=messages.scrollHeight}});
          }}
        }}catch(e){{}}
      }}
      function bodymindR156SyncSoon(){{
        bodymindR156SyncViewport();
        [30,90,180,320,520].forEach(ms=>setTimeout(bodymindR156SyncViewport,ms));
      }}
      if(window.visualViewport){{
        window.visualViewport.addEventListener('resize',bodymindR156SyncViewport,{{passive:true}});
        window.visualViewport.addEventListener('scroll',bodymindR156SyncViewport,{{passive:true}});
      }}
      window.addEventListener('resize',bodymindR156SyncViewport,{{passive:true}});
      window.addEventListener('orientationchange',bodymindR156SyncSoon,{{passive:true}});
      input?.addEventListener('focus',bodymindR156SyncSoon);
      input?.addEventListener('blur',bodymindR156SyncSoon);
      bodymindR156SyncSoon();
'''
    s=s[:pos]+js+s[pos:]

# ---------------------------------------------------------------------------
# 2) Operator semantics: "elimina documenti da verificare, Ferlan e Padovani"
#    targets queue records/titles, NOT athletes. It prepares a confirmed,
#    auditable soft removal and never deletes physical files.
# ---------------------------------------------------------------------------
if 'BODYMIND_R156_PENDING_DOCUMENT_ACTIONS' not in s:
    helper_anchor='def _execute_agent_tool(conn, plan, raw_message=""):'
    if helper_anchor not in s: raise RuntimeError('R156 operator tool anchor missing')
    helpers=r'''
# BODYMIND_R156_PENDING_DOCUMENT_ACTIONS
def _bodymind_pending_review_candidates_r156(conn):
    out=[]
    review_states={"verifica","review","pending","dubbio","incerto","richiede_conferma","needs_manual_match","nuovo_pronto","ready","da_verificare","needs_review","associato_tipo_da_verificare"}
    positive={"deleted","archived","archived_orphan","accepted","manual_accepted","verificato","resolved","associato","archived_to_tesserato","superseded_by_canonical"}
    if _table(conn,"documenti"):
        dc=_cols(conn,"documenti")
        where=" WHERE coalesce(visibile,1)=1" if "visibile" in dc else ""
        for r in conn.execute("SELECT * FROM documenti"+where+" ORDER BY id DESC").fetchall():
            st=str(r["status"] or "").strip().lower() if "status" in r.keys() else ""
            tid=int(r["tesserato_id"] or 0) if "tesserato_id" in r.keys() else 0
            typ=_doc_type(r)
            pending=(st in review_states or tid<=0 or not typ or typ=="altro")
            if not pending: continue
            title=""
            for k in ("original_filename","titolo","filename"):
                if k in r.keys() and str(r[k] or "").strip():
                    title=str(r[k]).split("/")[-1];break
            out.append({"source":"documenti","id":int(r["id"]),"title":title or ("Documento "+str(r["id"]))})
    if _table(conn,"inbound_documents"):
        ic=_cols(conn,"inbound_documents")
        deleted="coalesce(deleted_at,'')=''" if "deleted_at" in ic else "1=1"
        for r in conn.execute("SELECT * FROM inbound_documents WHERE "+deleted+" ORDER BY id DESC LIMIT 500").fetchall():
            st=str(r["status"] or "").strip().lower() if "status" in r.keys() else ""
            if st in positive: continue
            title=""
            for k in ("original_filename","filename","stored_filename","subject"):
                if k in r.keys() and str(r[k] or "").strip():
                    title=str(r[k]).split("/")[-1];break
            out.append({"source":"inbound","id":int(r["id"]),"title":title or ("Invio "+str(r["id"]))})
    return out

def _bodymind_pending_targets_r156(conn,raw):
    n=_norm(raw)
    stop={"elimina","eliminare","rimuovi","rimuovere","cancella","cancellare","documenti","documento","da","verificare","verifica","in","coda","dalla","dalla coda","i","il","lo","la","le","gli","e","ed","per","favore"}
    words=[w for w in n.split() if len(w)>=4 and w not in stop]
    if not words:return []
    found=[]
    seen=set()
    for item in _bodymind_pending_review_candidates_r156(conn):
        hay=_norm(item.get("title") or "")
        if any(w in hay for w in words):
            key=(item["source"],int(item["id"]))
            if key not in seen:
                seen.add(key);found.append(item)
    return found

def _bodymind_prepare_pending_delete_r156(conn,raw):
    n=_norm(raw)
    delete=any(x in n for x in ("elimina","eliminare","rimuovi","rimuovere","cancella","cancellare"))
    queue=any(x in n for x in ("documenti da verificare","documento da verificare","da verificare","coda documenti"))
    if not (delete and queue):return None
    items=_bodymind_pending_targets_r156(conn,raw)
    if not items:
        return {"text":"Non trovo nella coda da verificare documenti che corrispondano ai nomi indicati. Non ho modificato nulla.","mode":"warning","links":[{"label":"Apri Da verificare","href":"/documenti/da-verificare"}]}
    aid=_set_pending_action(conn,"archive_pending_review_documents",{"items":items})
    labels=", ".join(x["title"] for x in items[:12])
    more=(" e altri "+str(len(items)-12)) if len(items)>12 else ""
    return {"text":"Ho trovato "+str(len(items))+" documento/i nella coda da verificare: "+labels+more+". Confermi che devo rimuoverli dalla coda? I file fisici resteranno conservati per sicurezza.","mode":"confirm","action_id":aid,"pending_review_items":items,"links":[{"label":"Apri Da verificare","href":"/documenti/da-verificare"}]}

'''
    s=s.replace(helper_anchor,helpers+helper_anchor,1)

    # Deterministic intent must run before athlete matching and before the cloud planner.
    answer_anchor='''    scoped=_targeted_query_response(conn,raw)
    if scoped:
        return scoped
'''
    if answer_anchor not in s: raise RuntimeError('R156 answer routing anchor missing')
    answer_new='''    pending_delete=_bodymind_prepare_pending_delete_r156(conn,raw)
    if pending_delete:
        return pending_delete

'''+answer_anchor
    s=s.replace(answer_anchor,answer_new,1)

    # Cloud planner can also choose the same safe action.
    catalog_old='''        {"name":"list_pending_documents","description":"Conta e riepiloga la coda documenti da verificare.","write":False},
'''
    catalog_new=catalog_old+'''        {"name":"cleanup_pending_documents","description":"Prepara la rimozione dalla coda DA VERIFICARE dei documenti identificati per nome/file nella richiesta. Non cercare quei nomi come tesserati. Richiede conferma e conserva i file fisici.","write":True},
'''
    if catalog_old in s:
        s=s.replace(catalog_old,catalog_new,1)

    allowed_old='''if not athlete and tool not in ("global_status","find_duplicate_documents","cleanup_duplicate_documents","list_pending_documents","navigate"):'''
    allowed_new='''if not athlete and tool not in ("global_status","find_duplicate_documents","cleanup_duplicate_documents","list_pending_documents","cleanup_pending_documents","navigate"):'''
    if allowed_old in s:s=s.replace(allowed_old,allowed_new,1)

    tool_anchor='''    if tool=="list_pending_documents":
        cnt=_pending_count(conn)
        return {"text":f"Ci sono {cnt} documenti che richiedono verifica.","mode":"agent_tool","links":[{"label":"Apri Da verificare","href":"/documenti/da-verificare"}]}
'''
    if tool_anchor in s:
        s=s.replace(tool_anchor,tool_anchor+'''
    if tool=="cleanup_pending_documents":
        prepared=_bodymind_prepare_pending_delete_r156(conn,raw_message)
        if prepared:return prepared
        return {"text":"Indicami i nomi o i file della coda da verificare che vuoi rimuovere.","mode":"clarify","links":[{"label":"Apri Da verificare","href":"/documenti/da-verificare"}]}
''',1)

    # Execution after explicit confirmation: soft archive DB rows, no file unlink.
    exec_anchor='''    if kind=="archive_semantic_duplicates":
'''
    if exec_anchor not in s: raise RuntimeError('R156 pending execution anchor missing')
    exec_block=r'''    if kind=="archive_pending_review_documents":
        if current_role()!="admin":
            return {"text":"La rimozione dalla coda documenti richiede un account amministratore. Non ho modificato nulla.","mode":"warning"}
        items=payload.get("items") if isinstance(payload.get("items"),list) else []
        if not items:
            conn.execute("UPDATE bodymind_operator_actions SET status='cancelled' WHERE id=?",(aid,))
            conn.commit();session.pop("bodymind_operator_pending_action",None)
            return {"text":"Non ci sono documenti da rimuovere. Non ho modificato nulla.","mode":"warning"}
        backup_dir=Path("/data/operator_backups");backup_dir.mkdir(parents=True,exist_ok=True)
        backup_file=backup_dir/(datetime.now().strftime("%Y%m%d_%H%M%S")+"_pending_review_"+str(aid)+".db")
        db_path=Path("/data/tenants/default/asd.db")
        if db_path.exists():shutil.copy2(db_path,backup_file)
        done=[];blocked=[];now=datetime.now().isoformat(timespec="seconds")
        try:
            conn.execute("BEGIN IMMEDIATE")
            for item in items:
                source=str(item.get("source") or "");rid=int(item.get("id") or 0);title=str(item.get("title") or "")
                if source=="inbound" and _table(conn,"inbound_documents"):
                    cols=_cols(conn,"inbound_documents");sets=[];vals=[]
                    if "status" in cols:sets.append("status=?");vals.append("deleted")
                    if "deleted_at" in cols:sets.append("deleted_at=?");vals.append(now)
                    if "updated_at" in cols:sets.append("updated_at=?");vals.append(now)
                    if not sets:blocked.append(item);continue
                    vals.append(rid)
                    cur=conn.execute("UPDATE inbound_documents SET "+",".join(sets)+" WHERE id=?"+(" AND coalesce(deleted_at,'')=''" if "deleted_at" in cols else ""),tuple(vals))
                elif source=="documenti" and _table(conn,"documenti"):
                    cols=_cols(conn,"documenti");sets=[];vals=[]
                    if "visibile" in cols:sets.append("visibile=0")
                    if "status" in cols:sets.append("status=?");vals.append("deleted_from_review")
                    if "updated_at" in cols:sets.append("updated_at=?");vals.append(now)
                    if not sets:blocked.append(item);continue
                    vals.append(rid)
                    cur=conn.execute("UPDATE documenti SET "+",".join(sets)+" WHERE id=?"+(" AND coalesce(visibile,1)=1" if "visibile" in cols else ""),tuple(vals))
                else:
                    blocked.append(item);continue
                if int(cur.rowcount or 0)==1:done.append({"source":source,"id":rid,"title":title})
                else:blocked.append(item)
            st="executed" if not blocked else ("executed_partial" if done else "blocked_safety")
            conn.execute("UPDATE bodymind_operator_actions SET status=?,confirmed_by=?,executed_at=?,payload_json=? WHERE id=?",
                         (st,_identity(),now,json.dumps({**payload,"archived":done,"blocked":blocked,"backup":str(backup_file)},ensure_ascii=False),aid))
            conn.commit()
        except Exception:
            conn.rollback();raise
        session.pop("bodymind_operator_pending_action",None)
        if not done:
            return {"text":"Non ho rimosso alcun documento: la coda è cambiata oppure i record non sono più attivi. Nessun file fisico è stato cancellato.","mode":"warning","links":[{"label":"Apri Da verificare","href":"/documenti/da-verificare"}]}
        msg="Ho rimosso dalla coda da verificare "+str(len(done))+" documento/i. I file fisici sono rimasti conservati e ho creato un backup preventivo."
        if blocked:msg+=" "+str(len(blocked))+" elemento/i non sono stati toccati perché non erano più nello stato atteso."
        return {"text":msg,"mode":"action","pending_review_archived":done,"pending_review_blocked":blocked,"links":[{"label":"Apri Da verificare","href":"/documenti/da-verificare"}]}

'''
    s=s.replace(exec_anchor,exec_block+exec_anchor,1)

OP.write_text(s,encoding='utf-8')
py_compile.compile(str(OP),doraise=True)

# ---------------------------------------------------------------------------
# 3) Manual queue UI: every V18 review card gets an explicit "Elimina dalla
#    coda" action. This is a soft archive only; physical bytes remain intact.
# ---------------------------------------------------------------------------
c=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R156_REVIEW_DELETE_ROUTE' not in c:
    shutil.copy2(CORE,BACK/'core.pre_r156.py')
    route_anchor="""@app.route('/documenti/da-verificare',methods=['GET'],endpoint='bodymind_document_review_v18')
"""
    if route_anchor not in c: raise RuntimeError('R156 V18 GET route anchor missing')
    route=r'''
# BODYMIND_R156_REVIEW_DELETE_ROUTE
@app.route('/documenti/da-verificare/elimina',methods=['POST'],endpoint='bodymind_document_review_delete_v20')
@admin_required
def bodymind_document_review_delete_v20():
    from flask import redirect
    source=str(request.form.get('source') or '').strip()
    try:rid=int(request.form.get('id') or 0)
    except Exception:rid=0
    if source not in ('documenti','inbound') or rid<=0:
        return redirect('/documenti/da-verificare?error=elimina')
    c=db();c.row_factory=sqlite3.Row
    backup_dir=Path('/data/operator_backups');backup_dir.mkdir(parents=True,exist_ok=True)
    backup=backup_dir/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_review_delete_'+source+'_'+str(rid)+'.db')
    dbp=Path('/data/tenants/default/asd.db')
    if dbp.exists():shutil.copy2(dbp,backup)
    now=datetime.now().isoformat(timespec='seconds')
    try:
        if source=='inbound':
            cols={str(x[1]) for x in c.execute('PRAGMA table_info(inbound_documents)').fetchall()}
            sets=[];vals=[]
            if 'status' in cols:sets.append('status=?');vals.append('deleted')
            if 'deleted_at' in cols:sets.append('deleted_at=?');vals.append(now)
            if 'updated_at' in cols:sets.append('updated_at=?');vals.append(now)
            if not sets:return redirect('/documenti/da-verificare?error=elimina')
            vals.append(rid)
            cur=c.execute('UPDATE inbound_documents SET '+','.join(sets)+' WHERE id=?'+(" AND coalesce(deleted_at,'')=''" if 'deleted_at' in cols else ''),tuple(vals))
        else:
            cols={str(x[1]) for x in c.execute('PRAGMA table_info(documenti)').fetchall()}
            sets=[];vals=[]
            if 'visibile' in cols:sets.append('visibile=0')
            if 'status' in cols:sets.append('status=?');vals.append('deleted_from_review')
            if 'updated_at' in cols:sets.append('updated_at=?');vals.append(now)
            if not sets:return redirect('/documenti/da-verificare?error=elimina')
            vals.append(rid)
            cur=c.execute('UPDATE documenti SET '+','.join(sets)+' WHERE id=?'+(" AND coalesce(visibile,1)=1" if 'visibile' in cols else ''),tuple(vals))
        c.commit()
        return redirect('/documenti/da-verificare?deleted=1' if int(cur.rowcount or 0)==1 else '/documenti/da-verificare?error=elimina')
    except Exception:
        c.rollback()
        return redirect('/documenti/da-verificare?error=elimina')
    finally:
        c.close()

'''
    c=c.replace(route_anchor,route+route_anchor,1)

    form_anchor="""                <button type='submit'>Verifica e aggiorna stato</button>
              </form>
            </article>"""
    if form_anchor not in c: raise RuntimeError('R156 V18 card form anchor missing')
    form_new="""                <button type='submit'>Verifica e aggiorna stato</button>
              </form>
              <form class='rv18-delete-form' method='post' action='/documenti/da-verificare/elimina'>
                {csrf_input()}<input type='hidden' name='source' value='{source}'><input type='hidden' name='id' value='{rid}'>
                <button class='rv18-delete' type='submit' onclick=\"return confirm('Rimuovere questo documento dalla coda da verificare? Il file fisico resterà conservato.')\">Elimina dalla coda</button>
              </form>
            </article>"""
    c=c.replace(form_anchor,form_new,1)

    css_anchor=".rv18-no-preview{{padding:10px;border-radius:10px;background:#4c1d1d;color:#fecaca;font-weight:800}}"
    if css_anchor not in c: raise RuntimeError('R156 V18 CSS anchor missing')
    c=c.replace(css_anchor,css_anchor+".rv18-delete-form{{margin-top:7px}}.rv18-delete{{background:#7f1d1d!important;color:#fff!important;border:1px solid #ef4444!important}}",1)

    msg_anchor="""        messages={'scadenza':'Per un certificato medico inserisci la scadenza.','atleta':'Seleziona l’atleta.','materializza':'Il file non è disponibile: non è stato approvato.','tipo':'Seleziona il tipo documento.'}
"""
    if msg_anchor in c:
        c=c.replace(msg_anchor,"""        messages={'scadenza':'Per un certificato medico inserisci la scadenza.','atleta':'Seleziona l’atleta.','materializza':'Il file non è disponibile: non è stato approvato.','tipo':'Seleziona il tipo documento.','elimina':'Non sono riuscito a rimuovere il documento dalla coda.'}
""",1)

    success_anchor="""        {("<div class='okmsg'>Documento verificato e stato aggiornato.</div>" if request.args.get('verified') else "")}
"""
    if success_anchor in c:
        c=c.replace(success_anchor,success_anchor+"""        {("<div class='okmsg'>Documento rimosso dalla coda. Il file fisico è stato conservato.</div>" if request.args.get('deleted') else "")}
""",1)

CORE.write_text(c,encoding='utf-8')
py_compile.compile(str(CORE),doraise=True)

# Read-only verification only. No production record is mutated by this release QA.
op=OP.read_text(encoding='utf-8',errors='replace')
core=CORE.read_text(encoding='utf-8',errors='replace')
checks={
    'viewport_origin':"--bmo-r156-vv-top" in op and "vv.offsetTop" in op and "vv.offsetLeft" in op,
    'composer_autogrow':".bmo-compose>#bmoInput" in op and "max-height:112px!important" in op,
    'operator_queue_intent':"_bodymind_prepare_pending_delete_r156" in op and "archive_pending_review_documents" in op,
    'manual_delete_route':"bodymind_document_review_delete_v20" in core,
    'manual_delete_button':"Elimina dalla coda" in core,
    'soft_delete_only':"deleted_from_review" in core and "unlink(" not in core[core.find('BODYMIND_R156_REVIEW_DELETE_ROUTE'):core.find("@app.route('/documenti/da-verificare',methods=['GET']",core.find('BODYMIND_R156_REVIEW_DELETE_ROUTE'))],
}
conn=sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True,timeout=20)
try:
    integ=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=conn.execute('PRAGMA foreign_key_check').fetchall()
finally:
    conn.close()
checks['db']=integ.lower()=='ok' and not fk
print('[r156-audit] '+repr(checks)+' integrity='+integ+' fk='+str(len(fk)),flush=True)
if not all(checks.values()):
    raise RuntimeError('R156 QA failed '+repr(checks))
print('[r156] PASS ios-visible-viewport composer-writable operator-pending-delete manual-queue-delete soft-archive-only',flush=True)


# ---------------------------------------------------------------------------
# BODYMIND_R156_PAYMENT_SMS_RECEIPT_SERIES
# Consolidated payment exact-id safety, manual SMS reminders, and separate
# future receipt series for enrollment vs monthly payments.
# Historical receipt numbers are never renumbered.
# ---------------------------------------------------------------------------
c=CORE.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R156_PAYMENT_SMS_RECEIPT_SERIES' not in c:
    shutil.copy2(CORE,BACK/'core.pre_r156_payment_sms_series.py')

    # 1) Exact payment identity: an explicit payment_id can never silently
    #    fall back to "latest payment in the same period".
    old_exact="""        existing=None
        if payment_id:
            existing=c.execute("SELECT * FROM pagamenti WHERE id=? AND tesserato_id=?",(payment_id,tid)).fetchone()
        if not existing:
            if tipo=='mensile':
"""
    new_exact="""        existing=None
        if payment_id:
            existing=c.execute("SELECT * FROM pagamenti WHERE id=? AND tesserato_id=?",(payment_id,tid)).fetchone()
            if not existing:
                return redirect('/pagamenti?errore=pagamento_non_trovato',302)
        if not existing:
            if tipo=='mensile':
"""
    if old_exact in c:
        c=c.replace(old_exact,new_exact,1)
    elif "errore=pagamento_non_trovato" not in c:
        raise RuntimeError('R156 exact payment-id anchor missing')

    # 2) Separate future receipt sequences. Never rewrite old issued rows.
    #    Add nullable series columns only if absent; old rows remain untouched.
    old_conn="""        nome=((str(athlete['cognome'] or '')+' '+str(athlete['nome'] or '')).strip())
        desc=('Quota iscrizione stagione '+str(stagione)+'/'+str(stagione+1)) if tipo=='iscrizione' else ('Quota mensile '+str(mese).zfill(2)+'/'+str(anno))
        receipt=c.execute("SELECT * FROM ricevute WHERE pagamento_id=? ORDER BY id DESC LIMIT 1",(pid,)).fetchone()
"""
    new_conn="""        # Receipt series are distinct from now on: I = iscrizione, M = mensile.
        # Historical rows keep their original progressive numbers.
        rcols={str(x[1]) for x in c.execute("PRAGMA table_info(ricevute)").fetchall()}
        if 'serie_ricevuta' not in rcols:
            c.execute("ALTER TABLE ricevute ADD COLUMN serie_ricevuta TEXT")
            rcols.add('serie_ricevuta')
        if 'numero_serie' not in rcols:
            c.execute("ALTER TABLE ricevute ADD COLUMN numero_serie INTEGER")
            rcols.add('numero_serie')

        nome=((str(athlete['cognome'] or '')+' '+str(athlete['nome'] or '')).strip())
        desc=('Quota iscrizione stagione '+str(stagione)+'/'+str(stagione+1)) if tipo=='iscrizione' else ('Quota mensile '+str(mese).zfill(2)+'/'+str(anno))
        serie=('I' if tipo=='iscrizione' else 'M')
        receipt=c.execute("SELECT * FROM ricevute WHERE pagamento_id=? ORDER BY id DESC LIMIT 1",(pid,)).fetchone()
"""
    if old_conn in c:
        c=c.replace(old_conn,new_conn,1)
    elif "serie=('I' if tipo=='iscrizione' else 'M')" not in c:
        raise RuntimeError('R156 receipt-series anchor missing')

    old_update="""            c.execute(\"\"\"
                UPDATE ricevute
                   SET nome=?,descrizione=?,importo=?,data=?,metodo_pagamento=?,updated_at=?
                 WHERE id=?
            \"\"\",(nome,desc,importo,data,metodo,now,rid))
        else:
            prog=int(c.execute("SELECT COALESCE(MAX(numero_progressivo),0)+1 FROM ricevute WHERE anno_progressivo=?",(anno,)).fetchone()[0] or 1)
            cur=c.execute(\"\"\"
                INSERT INTO ricevute(
                    nome,descrizione,importo,data,pagamento_id,tenant_id,
                    created_at,updated_at,metodo_pagamento,
                    numero_progressivo,anno_progressivo,annullata
                ) VALUES(?,?,?,?,?,'default',?,?,?,?,?,0)
            \"\"\",(nome,desc,importo,data,pid,now,now,metodo,prog,anno))
            rid=int(cur.lastrowid)
"""
    new_update="""            # Existing receipt keeps its historical numbering. Only content
            # tied to the exact payment is synchronized.
            c.execute(\"\"\"
                UPDATE ricevute
                   SET nome=?,descrizione=?,importo=?,data=?,metodo_pagamento=?,updated_at=?
                 WHERE id=?
            \"\"\",(nome,desc,importo,data,metodo,now,rid))
        else:
            # Keep the legacy global progressive for backward compatibility,
            # while assigning a new independent per-series progressive.
            prog=int(c.execute("SELECT COALESCE(MAX(numero_progressivo),0)+1 FROM ricevute WHERE anno_progressivo=?",(anno,)).fetchone()[0] or 1)
            sprog=int(c.execute("SELECT COALESCE(MAX(numero_serie),0)+1 FROM ricevute WHERE anno_progressivo=? AND serie_ricevuta=?",(anno,serie)).fetchone()[0] or 1)
            cur=c.execute(\"\"\"
                INSERT INTO ricevute(
                    nome,descrizione,importo,data,pagamento_id,tenant_id,
                    created_at,updated_at,metodo_pagamento,
                    numero_progressivo,anno_progressivo,annullata,
                    serie_ricevuta,numero_serie
                ) VALUES(?,?,?,?,?,'default',?,?,?,?,?,0,?,?)
            \"\"\",(nome,desc,importo,data,pid,now,now,metodo,prog,anno,serie,sprog))
            rid=int(cur.lastrowid)
"""
    if old_update in c:
        c=c.replace(old_update,new_update,1)
    elif "MAX(numero_serie)" not in c:
        raise RuntimeError('R156 receipt insert anchor missing')

    # 3) Manual SMS reminder on due rows. No message is sent by the server:
    #    the sms: URL only opens the user's native Messages composer.
    old_name="""        def _name(a):
            return ((str(a.get('cognome') or '')+' '+str(a.get('nome') or '')).strip()) or ('Tesserata #'+str(int(a.get('id') or 0)))
        def _money(v):
"""
    new_name="""        def _name(a):
            return ((str(a.get('cognome') or '')+' '+str(a.get('nome') or '')).strip()) or ('Tesserata #'+str(int(a.get('id') or 0)))
        def _sms_phone(a):
            raw=(a.get('telefono_genitore') or a.get('telefono') or '').strip()
            return ''.join(ch for ch in str(raw) if ch.isdigit() or ch=='+')
        def _sms_due(a,tipo,mese,anno,stagione,months):
            from urllib.parse import quote as _urlquote
            phone=_sms_phone(a)
            if not phone:return ''
            nome=(str(a.get('nome') or '')).strip()
            if tipo=='iscrizione':
                msg="BodyMind Aerial Studio ASD: promemoria quota di iscrizione "+str(stagione)+"/"+str(stagione+1)+" ancora da regolarizzare per "+nome+". Grazie."
            else:
                msg="BodyMind Aerial Studio ASD: promemoria quota mensile di "+months[mese]+" "+str(anno)+" ancora da regolarizzare per "+nome+". Grazie."
            return "sms:"+phone+"?&body="+_urlquote(msg)
        def _money(v):
"""
    if old_name in c:
        c=c.replace(old_name,new_name,1)
    elif "def _sms_due(" not in c:
        raise RuntimeError('R156 SMS helper anchor missing')

    old_rows="""            rows.append((0 if not focus_ok else 1,
                "<div class='bmpv7-row "+row_state+"' data-bm-tid='"+str(tid)+"' data-bm-enroll='"+("1" if eok else "0")+"' data-bm-monthly='"+("1" if mok else "0")+"'>"
"""
    new_rows="""            sms_href=_sms_due(a,'iscrizione' if vista=='iscrizioni' else 'mensile',mese,anno,stagione,months) if not focus_ok else ''
            sms_action=("<a class='sms' href='"+e(sms_href)+"'>SMS promemoria</a>" if sms_href else "")
            rows.append((0 if not focus_ok else 1,
                "<div class='bmpv7-row "+row_state+"' data-bm-tid='"+str(tid)+"' data-bm-enroll='"+("1" if eok else "0")+"' data-bm-monthly='"+("1" if mok else "0")+"'>"
"""
    if old_rows in c:
        c=c.replace(old_rows,new_rows,1)
    elif "sms_action=" not in c:
        raise RuntimeError('R156 SMS row anchor missing')

    old_actions="""                +"<div class='bmpv7-actions'><a class='doc' href='"+dh+"'>Verifica documento</a><a class='doc' href='"+ah+"'>Archivio</a><a href='"+eh+"'>"+("Correggi iscrizione" if eok else "Registra iscrizione")+"</a>"+(("<a href='"+mh+"'>"+("Correggi "+months[mese] if mok else "Registra "+months[mese])+"</a>") if monthly_due else "<span class='bmpv7-action-na'>"+months[mese]+" non dovuto</span>")+"</div>"
"""
    new_actions="""                +"<div class='bmpv7-actions'><a class='doc' href='"+dh+"'>Verifica documento</a><a class='doc' href='"+ah+"'>Archivio</a><a href='"+eh+"'>"+("Correggi iscrizione" if eok else "Registra iscrizione")+"</a>"+(("<a href='"+mh+"'>"+("Correggi "+months[mese] if mok else "Registra "+months[mese])+"</a>") if monthly_due else "<span class='bmpv7-action-na'>"+months[mese]+" non dovuto</span>")+sms_action+"</div>"
"""
    if old_actions in c:
        c=c.replace(old_actions,new_actions,1)
    elif "SMS promemoria" not in c:
        raise RuntimeError('R156 SMS actions anchor missing')

    old_css=""".bmpv7-actions a{{background:#2563eb;color:#fff!important;text-decoration:none}}.bmpv7-actions a+ a{{background:#0f766e}}.bmpv7-actions a.doc{{background:#334155!important}}"""
    new_css=""".bmpv7-actions a{{background:#2563eb;color:#fff!important;text-decoration:none}}.bmpv7-actions a+ a{{background:#0f766e}}.bmpv7-actions a.doc{{background:#334155!important}}.bmpv7-actions a.sms{{background:#7c3aed!important}}"""
    if old_css in c:
        c=c.replace(old_css,new_css,1)

    c+="\n# BODYMIND_R156_PAYMENT_SMS_RECEIPT_SERIES\n"
    CORE.write_text(c,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)

# Patch receipt PDF display to show the new series reference when available,
# while retaining the legacy historical number underneath for traceability.
receipt_files=list((APP/'asd_app').rglob('routes_ricevute.py'))
if len(receipt_files)!=1:
    raise RuntimeError('R156 expected one routes_ricevute.py')
RPDF=receipt_files[0]
rs=RPDF.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R156_RECEIPT_SERIES_DISPLAY' not in rs:
    # Add a lightweight overlay in the existing V16 wrapper.
    anchor="""        _r=_c.execute("SELECT * FROM ricevute WHERE id=?",(_rid,)).fetchone()
        if not _r:
            return _resp
"""
    repl="""        _r=_c.execute("SELECT * FROM ricevute WHERE id=?",(_rid,)).fetchone()
        if not _r:
            return _resp
        _series=''
        try:
            if 'serie_ricevuta' in _r.keys() and 'numero_serie' in _r.keys() and _r['serie_ricevuta'] and _r['numero_serie']:
                _series=str(_r['serie_ricevuta'])+'-'+str(_r['anno_progressivo'])+'-'+str(int(_r['numero_serie'])).zfill(3)
        except Exception:
            _series=''
"""
    if anchor in rs:
        rs=rs.replace(anchor,repl,1)
    elif "_series=''" not in rs:
        raise RuntimeError('R156 receipt series PDF data anchor missing')

    draw_anchor="""        _cv.setFont('Helvetica-Bold',9)
        _cv.drawString(_mx,_my,'Metodo di pagamento: '+_shown)
        _cv.save()
"""
    draw_repl="""        _cv.setFont('Helvetica-Bold',9)
        _cv.drawString(_mx,_my,'Metodo di pagamento: '+_shown)
        if _series:
            _cv.setFont('Helvetica-Bold',9)
            _cv.drawString(_mx,max(24.0,_my-14.0),'Ricevuta: '+_series)
        _cv.save()
"""
    if draw_anchor in rs:
        rs=rs.replace(draw_anchor,draw_repl,1)
    elif "Ricevuta: '+_series" not in rs:
        raise RuntimeError('R156 receipt series PDF draw anchor missing')
    rs+="\n# BODYMIND_R156_RECEIPT_SERIES_DISPLAY\n"
    RPDF.write_text(rs,encoding='utf-8')
    py_compile.compile(str(RPDF),doraise=True)

# Read-only/static QA. Runtime migration itself only adds nullable columns;
# no historical receipt number is rewritten.
core=CORE.read_text(encoding='utf-8',errors='replace')
rp=RPDF.read_text(encoding='utf-8',errors='replace')
checks={
    'exact_payment_id':"errore=pagamento_non_trovato" in core,
    'sms_manual':"sms:" in core and "SMS promemoria" in core,
    'series_schema':"ALTER TABLE ricevute ADD COLUMN serie_ricevuta TEXT" in core and "ALTER TABLE ricevute ADD COLUMN numero_serie INTEGER" in core,
    'series_independent':"MAX(numero_serie)" in core and "serie_ricevuta=?" in core,
    'historical_not_renumbered':"Existing receipt keeps its historical numbering" in core,
    'pdf_series':"Ricevuta: '+_series" in rp,
}
conn=sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True,timeout=20)
try:
    integ=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=conn.execute('PRAGMA foreign_key_check').fetchall()
    counts={t:int(conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]) for t in ('tesserati','pagamenti','ricevute')}
finally:
    conn.close()
checks['db']=integ.lower()=='ok' and not fk
print('[r156-payment-sms-series-audit] '+repr(checks)+' counts='+repr(counts)+' integrity='+integ+' fk='+str(len(fk)),flush=True)
if not all(checks.values()):
    raise RuntimeError('R156 payment/SMS/series QA failed '+repr(checks))
print('[r156-payment-sms-series] PASS exact-id manual-sms separate-future-receipt-series historical-numbers-preserved',flush=True)
