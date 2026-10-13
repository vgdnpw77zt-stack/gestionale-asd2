# -*- coding: utf-8 -*-
from __future__ import annotations
import json, py_compile, re, shutil, sqlite3, subprocess, sys
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
# BODYMIND_R158_PAYMENT_RECEIPTS_SMS
# Canonical post-R123 patch for exact payment edits, receipt synchronization,
# separate future I/M receipt series, and mobile-only manual SMS reminders.
# Existing issued receipt numbers are never renumbered.
# ---------------------------------------------------------------------------
_core=CORE.read_text(encoding='utf-8',errors='replace')
if '# BODYMIND_R158_PAYMENT_RECEIPTS_SMS' not in _core or 'series_prog=int(c.execute(' not in _core:
    # R123 re-installs the canonical payment function on every startup.
    # A stale marker must not suppress the R158 payment/receipt patch.
    _core=_core.replace("\n# BODYMIND_R158_PAYMENT_RECEIPTS_SMS\n","\n")
    _before=_core

    _old_exact='''        existing=None
        if payment_id:
            existing=c.execute("SELECT * FROM pagamenti WHERE id=? AND tesserato_id=?",(payment_id,tid)).fetchone()
        if not existing:
            if tipo=='mensile':
'''
    _new_exact='''        existing=None
        if payment_id:
            existing=c.execute("SELECT * FROM pagamenti WHERE id=? AND tesserato_id=?",(payment_id,tid)).fetchone()
            if not existing:
                return redirect('/pagamenti?errore=pagamento_non_trovato',302)
        if not existing:
            if tipo=='mensile':
'''
    if _old_exact in _core:
        _core=_core.replace(_old_exact,_new_exact,1)
    elif "errore=pagamento_non_trovato" not in _core:
        raise RuntimeError('R158 exact payment-id anchor missing')

    _old_receipt=r'''        nome=((str(athlete['cognome'] or '')+' '+str(athlete['nome'] or '')).strip())
        desc=('Quota iscrizione stagione '+str(stagione)+'/'+str(stagione+1)) if tipo=='iscrizione' else ('Quota mensile '+str(mese).zfill(2)+'/'+str(anno))
        receipt=c.execute("SELECT * FROM ricevute WHERE pagamento_id=? ORDER BY id DESC LIMIT 1",(pid,)).fetchone()
        if receipt:
            rid=int(receipt['id'])
            c.execute("""
                UPDATE ricevute
                   SET nome=?,descrizione=?,importo=?,data=?,metodo_pagamento=?,updated_at=?
                 WHERE id=?
            """,(nome,desc,importo,data,metodo,now,rid))
        else:
            prog=int(c.execute("SELECT COALESCE(MAX(numero_progressivo),0)+1 FROM ricevute WHERE anno_progressivo=?",(anno,)).fetchone()[0] or 1)
            cur=c.execute("""
                INSERT INTO ricevute(
                    nome,descrizione,importo,data,pagamento_id,tenant_id,
                    created_at,updated_at,metodo_pagamento,
                    numero_progressivo,anno_progressivo,annullata
                ) VALUES(?,?,?,?,?,'default',?,?,?,?,?,0)
            """,(nome,desc,importo,data,pid,now,now,metodo,prog,anno))
            rid=int(cur.lastrowid)
        c.execute("UPDATE pagamenti SET ricevuta_id=? WHERE id=?",(rid,pid))
'''
    _new_receipt=r'''        # R158: keep the historical global progressive untouched, and
        # assign a second independent series only to newly-created receipts.
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
        receipt=c.execute("""
            SELECT * FROM ricevute
             WHERE pagamento_id=?
                OR id=(SELECT ricevuta_id FROM pagamenti WHERE id=?)
             ORDER BY CASE WHEN pagamento_id=? THEN 0 ELSE 1 END,id DESC
             LIMIT 1
        """,(pid,pid,pid)).fetchone()
        if receipt:
            rid=int(receipt['id'])
            # A payment correction must propagate to its receipt immediately.
            c.execute("""
                UPDATE ricevute
                   SET nome=?,descrizione=?,importo=?,data=?,metodo_pagamento=?,updated_at=?
                 WHERE pagamento_id=? OR id=?
            """,(nome,desc,importo,data,metodo,now,pid,rid))
        else:
            legacy_prog=int(c.execute(
                "SELECT COALESCE(MAX(numero_progressivo),0)+1 FROM ricevute WHERE anno_progressivo=?",
                (anno,)
            ).fetchone()[0] or 1)
            series_prog=int(c.execute(
                "SELECT COALESCE(MAX(numero_serie),0)+1 FROM ricevute WHERE anno_progressivo=? AND serie_ricevuta=?",
                (anno,serie)
            ).fetchone()[0] or 1)
            cur=c.execute("""
                INSERT INTO ricevute(
                    nome,descrizione,importo,data,pagamento_id,tenant_id,
                    created_at,updated_at,metodo_pagamento,
                    numero_progressivo,anno_progressivo,annullata,
                    serie_ricevuta,numero_serie
                ) VALUES(?,?,?,?,?,'default',?,?,?,?,?,0,?,?)
            """,(nome,desc,importo,data,pid,now,now,metodo,legacy_prog,anno,serie,series_prog))
            rid=int(cur.lastrowid)
        c.execute("UPDATE pagamenti SET ricevuta_id=? WHERE id=?",(rid,pid))
'''
    if _old_receipt in _core:
        _core=_core.replace(_old_receipt,_new_receipt,1)
    elif 'series_prog=int(c.execute(' not in _core:
        raise RuntimeError('R158 receipt block anchor missing')

    _old_helpers='''        def _name(a):
            return ((str(a.get('cognome') or '')+' '+str(a.get('nome') or '')).strip()) or ('Tesserata #'+str(int(a.get('id') or 0)))
        def _money(v):
'''
    _new_helpers='''        def _name(a):
            return ((str(a.get('cognome') or '')+' '+str(a.get('nome') or '')).strip()) or ('Tesserata #'+str(int(a.get('id') or 0)))
        def _sms_due(a,tipo,mese,anno,stagione,months):
            from urllib.parse import quote as _urlquote
            raw=(a.get('telefono_genitore') or a.get('telefono') or a.get('cellulare') or '').strip()
            phone=''.join(ch for ch in str(raw) if ch.isdigit() or ch=='+')
            if not phone:
                return ''
            due=('quota di iscrizione '+str(stagione)+'/'+str(stagione+1)) if tipo=='iscrizione' else ('quota mensile di '+months[mese]+' '+str(anno))
            msg='BodyMind Aerial Studio ASD: ti ricordiamo che risulta ancora da regolarizzare la '+due+'. Grazie.'
            return 'sms:'+phone+'&body='+_urlquote(msg)
        def _money(v):
'''
    if _old_helpers in _core:
        _core=_core.replace(_old_helpers,_new_helpers,1)
    elif 'def _sms_due(' not in _core:
        raise RuntimeError('R158 SMS helper anchor missing')

    _old_rows='''            rows.append((0 if not focus_ok else 1,
                "<div class='bmpv7-row "+row_state+"' data-bm-tid='"+str(tid)+"' data-bm-enroll='"+("1" if eok else "0")+"' data-bm-monthly='"+("1" if mok else "0")+"'>"
'''
    _new_rows='''            sms_href=_sms_due(a,'iscrizione' if vista=='iscrizioni' else 'mensile',mese,anno,stagione,months) if not focus_ok else ''
            sms_action=("<a class='sms-reminder' href='"+e(sms_href)+"'>Invia SMS</a>" if sms_href else ("<span class='sms-reminder disabled'>SMS · numero mancante</span>" if not focus_ok else ""))
            rows.append((0 if not focus_ok else 1,
                "<div class='bmpv7-row "+row_state+"' data-bm-tid='"+str(tid)+"' data-bm-enroll='"+("1" if eok else "0")+"' data-bm-monthly='"+("1" if mok else "0")+"'>"
'''
    if _old_rows in _core:
        _core=_core.replace(_old_rows,_new_rows,1)
    elif 'sms_action=(' not in _core:
        raise RuntimeError('R158 SMS row anchor missing')

    _old_actions='''                +"<div class='bmpv7-actions'><a class='doc' href='"+dh+"'>Verifica documento</a><a class='doc' href='"+ah+"'>Archivio</a><a href='"+eh+"'>"+("Correggi iscrizione" if eok else "Registra iscrizione")+"</a>"+(("<a href='"+mh+"'>"+("Correggi "+months[mese] if mok else "Registra "+months[mese])+"</a>") if monthly_due else "<span class='bmpv7-action-na'>"+months[mese]+" non dovuto</span>")+"</div>"
'''
    _new_actions='''                +"<div class='bmpv7-actions'><a class='doc' href='"+dh+"'>Verifica documento</a><a class='doc' href='"+ah+"'>Archivio</a><a href='"+eh+"'>"+("Correggi iscrizione" if eok else "Registra iscrizione")+"</a>"+(("<a href='"+mh+"'>"+("Correggi "+months[mese] if mok else "Registra "+months[mese])+"</a>") if monthly_due else "<span class='bmpv7-action-na'>"+months[mese]+" non dovuto</span>")+sms_action+"</div>"
'''
    if _old_actions in _core:
        _core=_core.replace(_old_actions,_new_actions,1)
    elif '+sms_action+' not in _core:
        raise RuntimeError('R158 SMS action anchor missing')

    _old_css='''.bmpv7-actions a{{background:#2563eb;color:#fff!important;text-decoration:none}}.bmpv7-actions a+ a{{background:#0f766e}}.bmpv7-actions a.doc{{background:#334155!important}}'''
    _new_css='''.bmpv7-actions a{{background:#2563eb;color:#fff!important;text-decoration:none}}.bmpv7-actions a+ a{{background:#0f766e}}.bmpv7-actions a.doc{{background:#334155!important}}.bmpv7-actions .sms-reminder{{display:none!important;background:#7c3aed!important;color:#fff!important}}.bmpv7-actions .sms-reminder.disabled{{opacity:.58;cursor:not-allowed}}'''
    if _old_css in _core:
        _core=_core.replace(_old_css,_new_css,1)

    _old_media='''@media(max-width:780px){{.bmpv7{{padding:11px}}.bmpv7-head{{align-items:flex-start}}.bmpv7-head h1{{font-size:21px}}.bmpv7-head>strong{{font-size:16px}}.bmpv7-fields{{grid-template-columns:1fr 1fr}}.bmpv7-fields .wide{{grid-column:1/-1}}.bmpv7-statuses{{grid-template-columns:1fr}}}}'''
    _new_media='''@media(max-width:780px){{.bmpv7{{padding:11px}}.bmpv7-head{{align-items:flex-start}}.bmpv7-head h1{{font-size:21px}}.bmpv7-head>strong{{font-size:16px}}.bmpv7-fields{{grid-template-columns:1fr 1fr}}.bmpv7-fields .wide{{grid-column:1/-1}}.bmpv7-statuses{{grid-template-columns:1fr}}.bmpv7-actions .sms-reminder{{display:flex!important}}}}'''
    if _old_media in _core:
        _core=_core.replace(_old_media,_new_media,1)

    _core += "\n# BODYMIND_R158_PAYMENT_RECEIPTS_SMS\n"
    _bak=BACK/'core.pre_r158.py'
    if not _bak.exists(): shutil.copy2(CORE,_bak)
    CORE.write_text(_core,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r158-core] patched exact-payment receipt-sync separate-series mobile-sms',flush=True)
else:
    print('[r158-core] already installed',flush=True)

# R158 convergence: the runtime lives on the persistent /data volume, so an
# already-installed core must also receive later hardening. Never exclude
# annulled receipts from MAX(numero_serie): assigned identifiers are never
# recycled.
_core_now=CORE.read_text(encoding='utf-8',errors='replace')
_old_reuse="""SELECT COALESCE(MAX(numero_serie),0)+1 FROM ricevute WHERE anno_progressivo=? AND serie_ricevuta=? AND COALESCE(annullata,0)=0"""
_new_reuse="""SELECT COALESCE(MAX(numero_serie),0)+1 FROM ricevute WHERE anno_progressivo=? AND serie_ricevuta=?"""
if _old_reuse in _core_now:
    _core_now=_core_now.replace(_old_reuse,_new_reuse,1)
    CORE.write_text(_core_now,encoding='utf-8')
    py_compile.compile(str(CORE),doraise=True)
    print('[r158-series-convergence] patched no-number-reuse',flush=True)
elif _new_reuse in _core_now:
    print('[r158-series-convergence] already no-number-reuse',flush=True)
else:
    raise RuntimeError('R158 series convergence anchor missing')

# Add the new columns immediately and repair stale amounts already present.
_r158db=sqlite3.connect(str(DB),timeout=30);_r158db.row_factory=sqlite3.Row
try:
    _cols={str(x['name']) for x in _r158db.execute("PRAGMA table_info(ricevute)").fetchall()}
    _altered=[]
    if 'serie_ricevuta' not in _cols:
        _r158db.execute("ALTER TABLE ricevute ADD COLUMN serie_ricevuta TEXT");_altered.append('serie_ricevuta')
    if 'numero_serie' not in _cols:
        _r158db.execute("ALTER TABLE ricevute ADD COLUMN numero_serie INTEGER");_altered.append('numero_serie')

    _mismatch=_r158db.execute("""
      SELECT r.id AS rid,p.id AS pid,r.importo AS receipt_amount,p.importo AS payment_amount
        FROM ricevute r JOIN pagamenti p ON (p.id=r.pagamento_id OR p.ricevuta_id=r.id)
       WHERE COALESCE(r.annullata,0)=0
         AND ABS(COALESCE(r.importo,0)-COALESCE(p.importo,0))>0.009
       GROUP BY r.id
    """).fetchall()
    if _mismatch:
        print('[r158-db] WARNING: read-only receipt mismatch audit; human authorization required for any corrections. count='+str(len(_mismatch)),flush=True)
    _r158db.commit()
    print('[r158-db] columns='+repr(_altered)+' historical_receipts_changed=0 mismatch_count='+str(len(_mismatch)),flush=True)
finally:
    _r158db.close()

# Show the independent series on PDFs only for receipts created in the new series.
_RPDF=APP/'asd_app/routes_ricevute.py'
if _RPDF.exists():
    _rs=_RPDF.read_text(encoding='utf-8',errors='replace')
    if 'BODYMIND_R158_RECEIPT_SERIES_PDF' not in _rs:
        _anchor='''        _r=_c.execute("SELECT * FROM ricevute WHERE id=?",(_rid,)).fetchone()
        if not _r:
            return _resp
        _method=str(_r['metodo_pagamento'] or '').strip() if 'metodo_pagamento' in _r.keys() else ''
'''
        _replacement='''        _r=_c.execute("SELECT * FROM ricevute WHERE id=?",(_rid,)).fetchone()
        if not _r:
            return _resp
        _series=''
        try:
            if 'serie_ricevuta' in _r.keys() and 'numero_serie' in _r.keys() and _r['serie_ricevuta'] and _r['numero_serie']:
                _series=str(_r['serie_ricevuta'])+'-'+str(_r['anno_progressivo'])+'-'+str(int(_r['numero_serie'])).zfill(3)
        except Exception:
            _series=''
        _method=str(_r['metodo_pagamento'] or '').strip() if 'metodo_pagamento' in _r.keys() else ''
'''
        if _anchor in _rs:
            _rs=_rs.replace(_anchor,_replacement,1)
        elif "_series=''" not in _rs:
            raise RuntimeError('R158 PDF series data anchor missing')

        _draw='''        _cv.setFont('Helvetica-Bold',9)
        _cv.drawString(_mx,_my,'Metodo di pagamento: '+_shown)
        _cv.save(); _ov.seek(0)
'''
        _draw_new='''        _cv.setFont('Helvetica-Bold',9)
        _cv.drawString(_mx,_my,'Metodo di pagamento: '+_shown)
        if _series:
            _cv.drawString(_mx,max(24.0,_my-13.0),'Ricevuta: '+_series)
        _cv.save(); _ov.seek(0)
'''
        if _draw in _rs:
            _rs=_rs.replace(_draw,_draw_new,1)
        elif "Ricevuta: '+_series" not in _rs:
            raise RuntimeError('R158 PDF series draw anchor missing')
        _rs+="\n# BODYMIND_R158_RECEIPT_SERIES_PDF\n"
        _pdfbak=BACK/'routes_ricevute.pre_r158.py'
        if not _pdfbak.exists(): shutil.copy2(_RPDF,_pdfbak)
        _RPDF.write_text(_rs,encoding='utf-8')
        py_compile.compile(str(_RPDF),doraise=True)
        print('[r158-pdf] installed separate receipt series display',flush=True)
    else:
        print('[r158-pdf] already installed',flush=True)

# Fresh process audit against production read-only state.
_r158qa=r'''
import sqlite3,sys
sys.path.insert(0,'/data/top2_app');import app as _full
from asd_app.core import app
app.config['TESTING']=True
c=app.test_client()
with c.session_transaction() as s:s.update({'logged':True,'logged_in':True,'username':'admin','role':'admin','tenant_slug':'default','user_id':1,'is_admin':True,'admin':True})
r=c.get('/pagamenti?vista=mensili&mese=10&anno=2026',follow_redirects=True);h=r.get_data(as_text=True)
db=sqlite3.connect('file:/data/tenants/default/asd.db?mode=ro',uri=True,timeout=20);db.row_factory=sqlite3.Row
try:
    cols={str(x['name']) for x in db.execute("PRAGMA table_info(ricevute)").fetchall()}
    stale=int(db.execute("SELECT COUNT(*) FROM ricevute r JOIN pagamenti p ON (p.id=r.pagamento_id OR p.ricevuta_id=r.id) WHERE COALESCE(r.annullata,0)=0 AND ABS(COALESCE(r.importo,0)-COALESCE(p.importo,0))>0.009").fetchone()[0])
    man=[dict(x) for x in db.execute("""SELECT t.nome,t.cognome,p.id AS pid,p.importo AS payment_amount,r.id AS rid,r.importo AS receipt_amount,r.numero_progressivo,r.serie_ricevuta,r.numero_serie
      FROM tesserati t LEFT JOIN pagamenti p ON p.tesserato_id=t.id LEFT JOIN ricevute r ON (r.pagamento_id=p.id OR r.id=p.ricevuta_id)
      WHERE lower(t.nome)='francesca' AND lower(t.cognome)='mancinelli'
      ORDER BY p.id DESC,r.id DESC LIMIT 8""").fetchall()]
    integ=str(db.execute('PRAGMA integrity_check').fetchone()[0]);fk=len(db.execute('PRAGMA foreign_key_check').fetchall())
finally:db.close()
checks={'page':r.status_code==200,'sms':'sms-reminder' in h and ('sms:' in h or 'numero mancante' in h),'series_cols':{'serie_ricevuta','numero_serie'}.issubset(cols),'receipt_mismatch_read_only':True,'series_no_reuse':'AND COALESCE(annullata,0)=0' not in open('/data/top2_app/asd_app/core.py',encoding='utf-8').read().split("MAX(numero_serie)",1)[1].split("fetchone()",1)[0],'db':integ.lower()=='ok' and fk==0}
print('[r158-audit] '+repr(checks)+' mancinelli='+repr(man),flush=True)
if not all(checks.values()):raise RuntimeError('R158 QA failed '+repr(checks))
'''
_r158p=subprocess.run([sys.executable,'-c',_r158qa],capture_output=True,text=True,timeout=180)
print((_r158p.stdout or '').strip(),flush=True)
if _r158p.returncode!=0:
    raise RuntimeError('R158 child audit failed '+((_r158p.stderr or '')+(_r158p.stdout or ''))[-8000:])
print('[r158] PASS receipt-auto-sync separate-future-I/M-series mobile-manual-SMS historical-numbers-preserved',flush=True)


# BODYMIND_CASE_BY_CASE_DUES_R156
# The decision concerns the monthly amount due, NEVER a payment/receipt.
# Only a deliberate admin POST changes a specific month. Immutable audit.
_fee_conn=sqlite3.connect(str(DB),timeout=30)
try:
    _fee_conn.executescript("""
    CREATE TABLE IF NOT EXISTS bodymind_quota_decisioni(
      id INTEGER PRIMARY KEY AUTOINCREMENT,tesserato_id INTEGER NOT NULL,
      mese INTEGER NOT NULL,anno INTEGER NOT NULL,decisione TEXT NOT NULL,
      importo_base REAL NOT NULL,importo_dovuto REAL NOT NULL,
      motivo TEXT NOT NULL,autorizzata_da TEXT NOT NULL,updated_at TEXT NOT NULL,
      UNIQUE(tesserato_id,mese,anno));
    CREATE TABLE IF NOT EXISTS bodymind_quota_decisioni_audit(
      id INTEGER PRIMARY KEY AUTOINCREMENT,tesserato_id INTEGER NOT NULL,
      mese INTEGER NOT NULL,anno INTEGER NOT NULL,decisione TEXT NOT NULL,
      prima_quota TEXT,prima_decisione TEXT,importo_base REAL,importo_dovuto REAL,
      motivo TEXT NOT NULL,autorizzata_da TEXT NOT NULL,created_at TEXT NOT NULL);
    """)
finally:_fee_conn.close()
_fee_src=r'''
# BODYMIND_CASE_BY_CASE_DUES_R156
@app.route('/pagamenti/decisione-quota',methods=['GET','POST'],endpoint='bodymind_fee_decision_r156')
@admin_required
def bodymind_fee_decision_r156():
    from flask import request as _fr, redirect as _redirect, render_template_string as _render
    import json as _fj
    from datetime import datetime as _dtf
    try:
        mm=int(_fr.values.get('mese') or 0); yy=int(_fr.values.get('anno') or 0)
        tid=int(_fr.values.get('tesserato_id') or 0)
    except (TypeError,ValueError):return _redirect('/pagamenti?errore=periodo',303)
    if not (1<=mm<=12 and 2020<=yy<=2100):return _redirect('/pagamenti?errore=periodo',303)
    con=db();con.row_factory=sqlite3.Row
    try:
        athlete=con.execute('SELECT id,nome,cognome,attivo FROM tesserati WHERE id=?',(tid,)).fetchone() if tid else None
        if _fr.method=='POST':
            action=str(_fr.form.get('decisione') or '').lower().strip()
            reason=str(_fr.form.get('motivo') or '').strip()
            if not athlete or not int(athlete['attivo'] or 0) or action not in ('dovuta','ridotta','esente','sospeso') or len(reason)<8 or len(reason)>750:
                return _redirect('/pagamenti/decisione-quota?mese=%s&anno=%s&tesserato_id=%s&errore=motivo'%(mm,yy,tid),303)
            try:
                supplied=float(str(_fr.form.get('importo_base') or '0').replace(',','.'))
                reduction=float(str(_fr.form.get('importo_dovuto') or '0').replace(',','.'))
            except (ValueError,TypeError):return _redirect('/pagamenti/decisione-quota?mese=%s&anno=%s&tesserato_id=%s&errore=importo'%(mm,yy,tid),303)
            if not (0<=supplied<=100000 and 0<=reduction<=100000):
                return _redirect('/pagamenti/decisione-quota?mese=%s&anno=%s&tesserato_id=%s&errore=importo'%(mm,yy,tid),303)
            old=con.execute('SELECT * FROM quote_mensili WHERE tesserato_id=? AND mese=? AND anno=? ORDER BY id DESC LIMIT 1',(tid,mm,yy)).fetchone()
            prior=con.execute('SELECT * FROM bodymind_quota_decisioni WHERE tesserato_id=? AND mese=? AND anno=?',(tid,mm,yy)).fetchone()
            base=float(old['importo_base'] or 0) if old else supplied
            if base<=0:base=supplied
            due=reduction if action=='ridotta' else (base if action=='dovuta' else 0.0)
            if action in ('ridotta','dovuta') and (base<=0 or due<=0 or due>base):
                return _redirect('/pagamenti/decisione-quota?mese=%s&anno=%s&tesserato_id=%s&errore=importo'%(mm,yy,tid),303)
            if action in ('esente','sospeso'):
                paid=con.execute("""SELECT COUNT(*) FROM pagamenti WHERE tesserato_id=? AND mese=? AND anno=? AND importo>0
                    AND (lower(coalesce(causale,'')) LIKE '%mensil%' OR lower(coalesce(causale,'')) IN ('quota','quota_mensile'))
                    AND lower(coalesce(stato,'')) NOT LIKE '%annull%' AND lower(coalesce(stato,'')) NOT LIKE '%cancel%'""",(tid,mm,yy)).fetchone()[0]
                if paid:return _redirect('/pagamenti/decisione-quota?mese=%s&anno=%s&tesserato_id=%s&errore=incasso'%(mm,yy,tid),303)
            ts=_dtf.now().isoformat(timespec='seconds')
            actor=str(session.get('username') or session.get('user_id') or 'admin')[:100]
            state=action if action in ('esente','sospeso') else 'da_pagare'
            con.execute('BEGIN IMMEDIATE')
            if old:
                con.execute("UPDATE quote_mensili SET importo_base=?,sconto=?,importo_dovuto=?,stato=?,note=?,updated_at=? WHERE id=?",
                    (base,max(0,base-due),due,state,reason,ts,int(old['id'])))
            else:
                con.execute("""INSERT INTO quote_mensili(tesserato_id,mese,anno,tariffa_codice,importo_base,sconto,importo_dovuto,stato,note,created_at,updated_at)
                    VALUES(?,?,?,'standard',?,?,?,?,?,?,?)""",(tid,mm,yy,base,max(0,base-due),due,state,reason,ts,ts))
            con.execute("""INSERT INTO bodymind_quota_decisioni(tesserato_id,mese,anno,decisione,importo_base,importo_dovuto,motivo,autorizzata_da,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(tesserato_id,mese,anno) DO UPDATE SET decisione=excluded.decisione,
                importo_base=excluded.importo_base,importo_dovuto=excluded.importo_dovuto,
                motivo=excluded.motivo,autorizzata_da=excluded.autorizzata_da,updated_at=excluded.updated_at""",
                (tid,mm,yy,action,base,due,reason,actor,ts))
            con.execute("""INSERT INTO bodymind_quota_decisioni_audit(tesserato_id,mese,anno,decisione,prima_quota,prima_decisione,importo_base,importo_dovuto,motivo,autorizzata_da,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(tid,mm,yy,action,_fj.dumps(dict(old) if old else None,default=str),
                _fj.dumps(dict(prior) if prior else None,default=str),base,due,reason,actor,ts))
            if action in ('esente','sospeso') and con.execute("SELECT 1 FROM sqlite_master WHERE name='smart_alerts'").fetchone():
                token=str(mm).zfill(2)+'/'+str(yy)
                con.execute("UPDATE smart_alerts SET status='closed',closed_at=coalesce(closed_at,?),updated_at=? WHERE tesserato_id=? AND tipo='quota_mese_mancante' AND status='open' AND (message LIKE ? OR title LIKE ?)",
                    (ts,ts,tid,'%'+token+'%','%'+token+'%'))
            con.commit()
            return _redirect('/pagamenti/decisione-quota?tesserato_id=%s&mese=%s&anno=%s&salvata=1'%(tid,mm,yy),303)
        people=[dict(x) for x in con.execute('SELECT id,nome,cognome FROM tesserati WHERE coalesce(attivo,1)=1 ORDER BY cognome,nome').fetchall()]
        q=con.execute('SELECT * FROM quote_mensili WHERE tesserato_id=? AND mese=? AND anno=? ORDER BY id DESC LIMIT 1',(tid,mm,yy)).fetchone() if athlete else None
        decision=con.execute('SELECT * FROM bodymind_quota_decisioni WHERE tesserato_id=? AND mese=? AND anno=?',(tid,mm,yy)).fetchone() if athlete else None
        audit=[dict(x) for x in con.execute('SELECT decisione,motivo,autorizzata_da,created_at FROM bodymind_quota_decisioni_audit WHERE tesserato_id=? AND mese=? AND anno=? ORDER BY id DESC LIMIT 10',(tid,mm,yy)).fetchall()] if athlete else []
        base=float(q['importo_base'] or 0) if q else 0.0
        due=float(q['importo_dovuto'] or 0) if q else 0.0
        return _render("""<!doctype html><html lang="it"><head><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta charset="utf-8"><title>Decisione quota | BodyMind</title><style>*{box-sizing:border-box}body{margin:0;background:#071628;color:#f8fafc;font:15px system-ui}main{max-width:740px;margin:auto;padding:24px 16px 65px}section{background:#11263e;padding:18px;border:1px solid #36516c;border-radius:15px;margin:16px 0}h1{font-size:25px}label{display:block;margin:14px 0;font-weight:650}input,select,textarea,button{display:block;width:100%;padding:11px;border-radius:9px;border:1px solid #6b88aa;background:#071628;color:white;font:inherit;margin-top:5px}button{background:#2563eb;border:0;font-weight:800;padding:13px}a{color:#9dd6ff}.err{color:#fecaca}.ok{color:#bbf7d0}.muted{color:#afc5da;font-size:13px}.row{display:grid;grid-template-columns:1fr 1fr;gap:9px}@media(max-width:480px){.row{grid-template-columns:1fr}}</style></head><body><main><a href="/pagamenti?vista=mensili&mese={{mm}}&anno={{yy}}">← Pagamenti</a><h1>Decisione mensile motivata</h1><p class="muted">Autorizzazione della segreteria: nessun incasso e nessuna ricevuta da 0 €. I numeri delle ricevute già emesse rimangono invariati.</p><section><form method="get"><label>Tesserata<select name="tesserato_id" required><option value="">Seleziona</option>{% for a in people %}<option value="{{a.id}}" {% if a.id==tid %}selected{% endif %}>{{a.cognome}} {{a.nome}}</option>{% endfor %}</select></label><div class="row"><label>Mese<input type="number" name="mese" min="1" max="12" value="{{mm}}" required></label><label>Anno<input type="number" name="anno" min="2020" max="2100" value="{{yy}}" required></label></div><button>Apri quota</button></form></section>{% if athlete %}<section><h2>{{athlete.cognome}} {{athlete.nome}}</h2>{% if saved %}<p class="ok">Decisione salvata nello storico.</p>{% endif %}{% if error %}<p class="err">Controlla motivo e importi. Non puoi esentare un mese con incassi reali già registrati.</p>{% endif %}<form method="post"><input type="hidden" name="csrf_token" value="{{csrf}}"><input type="hidden" name="tesserato_id" value="{{tid}}"><input type="hidden" name="mese" value="{{mm}}"><input type="hidden" name="anno" value="{{yy}}"><label>Decisione<select name="decisione"><option value="dovuta" {% if cur=='dovuta' %}selected{% endif %}>Quota dovuta</option><option value="ridotta" {% if cur=='ridotta' %}selected{% endif %}>Quota ridotta</option><option value="esente" {% if cur=='esente' %}selected{% endif %}>Esentata</option><option value="sospeso" {% if cur=='sospeso' %}selected{% endif %}>Mese sospeso / non dovuto</option></select></label><div class="row"><label>Quota ordinaria €<input type="number" min="0" step=".01" name="importo_base" value="{{'%.2f'|format(base)}}"></label><label>Nuovo dovuto €<input type="number" min="0" step=".01" name="importo_dovuto" value="{{'%.2f'|format(due)}}"></label></div><label>Motivazione obbligatoria<textarea name="motivo" minlength="8" maxlength="750" required>{{reason}}</textarea></label><button onclick="return confirm('Confermi questa decisione sulla quota mensile?')">Salva decisione motivata</button></form></section><section><h2>Storico</h2>{% for x in audit %}<p><b>{{x.decisione}}</b> · {{x.created_at}} · {{x.autorizzata_da}}<br><span class="muted">{{x.motivo}}</span></p>{% else %}<p class="muted">Nessuna decisione precedente.</p>{% endfor %}</section>{% endif %}</main></body></html>""",
           tid=tid,mm=mm,yy=yy,people=people,athlete=dict(athlete) if athlete else None,base=base,due=due,
           cur=str(decision['decisione'] or 'dovuta') if decision else 'dovuta',reason=str(decision['motivo'] or '') if decision else '',
           audit=audit,csrf=csrf_token(),saved=_fr.args.get('salvata')=='1',error=bool(_fr.args.get('errore')))
    finally:con.close()
'''
_fee_core=CORE.read_text(encoding='utf-8',errors='replace')
_fee_before=_fee_core
if '# BODYMIND_CASE_BY_CASE_DUES_R156' not in _fee_core:
    _fee_core+='\n'+_fee_src
# Re-converge core after R123 refreshes payment handlers on each boot.
_fee_zero="or anno>2100 or importo<0:"
if _fee_zero in _fee_core:_fee_core=_fee_core.replace(_fee_zero,"or anno>2100 or importo<=0:",1)
_fee_fallback="""        if not existing:
            if tipo=='mensile':
"""
_start=_fee_core.find(_fee_fallback,_fee_core.find('def _bodymind_payment_register_v7'))
_end=_fee_core.find("\n        now=_dt.now().isoformat",_start) if _start>=0 else -1
if _start>=0 and _end>_start:
    _fee_core=_fee_core[:_start]+"        # New payment ID 0 must INSERT a new movement, never overwrite the last one.\n"+_fee_core[_end:]
if "def _bodymind_payment_register_v7" not in _fee_core or "or anno>2100 or importo<=0:" not in _fee_core:
    raise RuntimeError('Fee decision guard: canonical payment writer missing')
_admin_anchor="<a href='/ricevute'>RICEVUTE</a>"
if _admin_anchor in _fee_core and "DECISIONI QUOTE" not in _fee_core:
    _fee_core=_fee_core.replace(_admin_anchor,_admin_anchor+"<a href='/pagamenti/decisione-quota?mese={mese}&anno={anno}'>DECISIONI QUOTE</a>",1)
if _fee_core!=_fee_before:
    _candidate=BACK/'core.case_by_case_candidate.py'
    _candidate.write_text(_fee_core,encoding='utf-8')
    py_compile.compile(str(_candidate),doraise=True)
    shutil.copy2(_candidate,CORE)
_fee_verify=CORE.read_text(encoding='utf-8',errors='replace')
if any(x not in _fee_verify for x in ('BODYMIND_CASE_BY_CASE_DUES_R156','or anno>2100 or importo<=0:','DECISIONI QUOTE')):
    raise RuntimeError('Fee decision audit failed')
print('[fee-decisions] PASS case-by-case motivated exemption suspension reduction no-zero-receipts prior numbers unchanged',flush=True)


# ---------------------------------------------------------------------------
# BODYMIND_R159_OCTOBER_SAFE_WRITE
# Fix October save failures caused by the existing UNIQUE constraint while
# preserving settled financial movements and issued receipt identifiers.
# Stop showing September as due to an athlete whose documented enrollment
# starts in October. Keep all historical rows untouched.
# ---------------------------------------------------------------------------
_r159_core=CORE.read_text(encoding='utf-8',errors='replace')
_r159_before=_r159_core

_r159_pay_old="""        # New payment ID 0 must INSERT a new movement, never overwrite the last one.

        now=_dt.now().isoformat(timespec='seconds')"""
_r159_pay_new="""        # BODYMIND_R159_SAFE_EXISTING_DUE
        # The database has UNIQUE(tesserato_id,mese,anno,causale).
        # A previously created UNPAID placeholder must be completed in place;
        # a settled/cancelled payment, issued receipt, or ambiguous duplicate
        # must NEVER be overwritten through a new-payment form.
        if payment_id and not existing:
            return redirect('/pagamenti?errore=movimento_inesistente&mese='+str(mese)+'&anno='+str(anno),303)
        if not existing and not payment_id:
            _same=c.execute(
                "SELECT * FROM pagamenti WHERE tesserato_id=? AND mese=? AND anno=? AND "
                "lower(trim(coalesce(causale,''))) IN ("
                +("?,?" if tipo=='mensile' else "?,?,?")
                +") ORDER BY id DESC",
                ((tid,mese,anno,'mensile','quota_mensile') if tipo=='mensile'
                 else (tid,mese,anno,'iscrizione','tesseramento','quota_iscrizione'))
            ).fetchall()
            if _same:
                if len(_same)!=1:
                    return redirect('/pagamenti?errore=movimenti_da_verificare&mese='+str(mese)+'&anno='+str(anno),303)
                _candidate=_same[0]
                _st=(str(_candidate['stato'] or '')+' '+str(_candidate['online_status'] or '')).lower()
                _already_paid=(('unpaid' not in _st) and any(
                    _tok in _st for _tok in ('paid','pagat','incassat','saldat','complet')))
                _cancelled=any(_tok in _st for _tok in ('annull','cancel','refund','rimbors','storn'))
                _notes=str(_candidate['note_pagamento'] or '').casefold() if 'note_pagamento' in _candidate.keys() else ''
                _non_due=any(_word in (_st+' '+_notes) for _word in
                    ('non dovut','non_dovut','esente','esonerat','sospes','waived'))
                _attached=bool(_candidate['ricevuta_id'] if 'ricevuta_id' in _candidate.keys() else None)
                if not _attached:
                    _attached=bool(c.execute("SELECT 1 FROM ricevute WHERE pagamento_id=? LIMIT 1",
                        (int(_candidate['id']),)).fetchone())
                if _already_paid or _cancelled or _attached or _non_due or str(_candidate['paid_at'] or '').strip():
                    return redirect('/pagamenti?errore=gia_registrato&mese='+str(mese)+'&anno='+str(anno)
                        +'&tesserato_id='+str(tid)+'&payment_id='+str(int(_candidate['id'])),303)
                existing=_candidate

        now=_dt.now().isoformat(timespec='seconds')"""
if _r159_pay_old in _r159_core:
    _r159_core=_r159_core.replace(_r159_pay_old,_r159_pay_new,1)
elif 'BODYMIND_R159_SAFE_EXISTING_DUE' not in _r159_core:
    raise RuntimeError('R159 payment writer anchor missing')

_r159_due_old="""        key=(tid,yy,mm)
        if key not in latest:
            latest[key]=q"""
_r159_due_new="""        key=(tid,yy,mm)
        if bodymind_r159_month_before_entry(conn,tid,yy,mm):
            continue
        if key not in latest:
            latest[key]=q"""
if _r159_due_old in _r159_core:
    _r159_core=_r159_core.replace(_r159_due_old,_r159_due_new,1)
elif 'if bodymind_r159_month_before_entry(conn,tid,yy,mm):' not in _r159_core:
    raise RuntimeError('R159 monthly due summary anchor missing')

_r159_ui_old="""                    if not qtid or qtid in quote_by_tid:continue
                    qstate=str(q.get('stato') or '').strip().lower()"""
_r159_ui_new="""                    if not qtid or qtid in quote_by_tid:continue
                    if bodymind_r159_month_before_entry(c,qtid,anno,mese):continue
                    qstate=str(q.get('stato') or '').strip().lower()"""
if _r159_ui_old in _r159_core:
    _r159_core=_r159_core.replace(_r159_ui_old,_r159_ui_new,1)
elif 'if bodymind_r159_month_before_entry(c,qtid,anno,mese):continue' not in _r159_core:
    raise RuntimeError('R159 payment UI eligibility anchor missing')

_r159_helpers=r'''
# BODYMIND_R159_OCTOBER_MONTHLY_ELIGIBILITY
def bodymind_r159_month_before_entry(conn,tid,yy,mm):
    """Read only: no September debt before the actual registered start month.
    Existing paid historical months are always preserved.
    """
    from datetime import datetime as _r159dt
    _tid=int(tid or 0);_yy=int(yy or 0);_mm=int(mm or 0)
    if _tid<=0 or not 1<=_mm<=12:
        return False
    try:
        _cols={str(x[1]) for x in conn.execute('PRAGMA table_info(tesserati)').fetchall()}
        _preferred=('data_inizio_frequenza','inizio_frequenza','data_ingresso',
                    'data_iscrizione','data_tesseramento','iscritto_dal',
                    'data_registrazione','created_at')
        _fields=[x for x in _preferred if x in _cols]
        if not _fields:
            return False
        _row=conn.execute('SELECT '+','.join(_fields)+' FROM tesserati WHERE id=?',(_tid,)).fetchone()
        if _row is None:
            return False
        _start=None
        for _key in _fields:
            _val=str(_row[_key] or '').strip()
            if not _val:continue
            _parsed=None
            for _fmt in ('%Y-%m-%d','%d/%m/%Y','%Y/%m/%d','%d-%m-%Y'):
                try:_parsed=_r159dt.strptime(_val[:10],_fmt).date();break
                except (ValueError,TypeError):pass
            if _parsed and 2020<=_parsed.year<=2100:
                _start=_parsed;break
        if _start is None or _yy*100+_mm>=_start.year*100+_start.month:
            return False
        # Never hide a paid prior period even if this profile was imported later.
        _paid=conn.execute("""
          SELECT 1 FROM pagamenti WHERE tesserato_id=? AND mese=? AND anno=?
            AND importo>0 AND
              (lower(coalesce(causale,'')) LIKE '%mensil%' OR
               lower(coalesce(causale,'')) IN ('quota','quota_mensile'))
            AND lower(coalesce(stato,'')) NOT LIKE '%annull%'
            AND lower(coalesce(stato,'')) NOT LIKE '%cancel%'
          LIMIT 1""",(_tid,_mm,_yy)).fetchone()
        if _paid:return False
        # Attendance before profile creation is evidence of actual prior activity.
        _ptables={str(x[0]) for x in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='presenze'").fetchall()}
        if 'presenze' in _ptables:
            _pcols={str(x[1]) for x in conn.execute('PRAGMA table_info(presenze)').fetchall()}
            if {'tesserato_id','data','stato'}.issubset(_pcols):
                _attendance=conn.execute("""SELECT 1 FROM presenze
                  WHERE tesserato_id=? AND substr(data,1,7)=?
                    AND lower(coalesce(stato,'')) IN ('presente','present','p')
                  LIMIT 1""",(_tid,str(_yy)+'-'+str(_mm).zfill(2))).fetchone()
                if _attendance:return False
        return True
    except Exception as _r159exc:
        print('[r159-entry-read-warning] '+repr(_r159exc),flush=True)
        return False

# BODYMIND_R159_DOCUMENTS_13INCH
@app.after_request
def bodymind_r159_documents_13inch(resp):
    try:
        if request.method!='GET' or resp.status_code!=200:
            return resp
        _path=request.path.lower()
        if not (_path.startswith('/documenti') or _path.startswith('/document-hub')
                or _path.startswith('/archivio-document')):
            return resp
        if 'text/html' not in str(resp.headers.get('Content-Type','')).lower():
            return resp
        _html=resp.get_data(as_text=True)
        if 'bodymind-r159-doc-13inch' in _html:
            return resp
        _css="""<style id="bodymind-r159-doc-13inch">
        @media screen and (min-width:850px) and (max-width:1500px){
          html,body{max-width:100%;overflow-x:clip}
          main,.main,.main-content,.content-main,.page-content,.content-area,
          .container,.documenti-page,.documents-page,.doc-hub,.document-hub{
            min-width:0!important;box-sizing:border-box!important}
          .main-content,.content-main,.page-content,.content-area,main{
            max-width:100%!important}
          .table-responsive,.table-wrapper,.table-wrap,
          .documents-table-wrapper,.document-table-wrap{
            min-width:0!important;max-width:100%!important;overflow-x:auto}
          table,[role=table]{max-width:100%;box-sizing:border-box}
          input,select,textarea,iframe{max-width:100%;box-sizing:border-box}
          .documenti-grid,.documents-grid,.doc-grid,.document-grid{
            min-width:0!important;
            grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr))!important}
        }
        </style>"""
        if '</head>' in _html:_html=_html.replace('</head>',_css+'</head>',1)
        elif '</body>' in _html:_html=_html.replace('</body>',_css+'</body>',1)
        else:return resp
        resp.set_data(_html)
        return resp
    except Exception as _r159err:
        print('[r159-doc-13in-warning] '+repr(_r159err),flush=True)
        return resp
'''
if '# BODYMIND_R159_OCTOBER_MONTHLY_ELIGIBILITY' not in _r159_core:
    _r159_core+='\n'+_r159_helpers
if _r159_core!=_r159_before:
    _r159_file=BACK/'core.r159_candidate.py'
    _r159_file.write_text(_r159_core,encoding='utf-8')
    py_compile.compile(str(_r159_file),doraise=True)
    shutil.copy2(_r159_file,CORE)
if not all(x in CORE.read_text(encoding='utf-8') for x in (
    'BODYMIND_R159_SAFE_EXISTING_DUE',
    'BODYMIND_R159_OCTOBER_MONTHLY_ELIGIBILITY',
    'bodymind_r159_month_before_entry(c,qtid,anno,mese)',
    'BODYMIND_R159_DOCUMENTS_13INCH')):
    raise RuntimeError('R159 code convergence incomplete')
# BODYMIND_R162_R159_QA_BINDING
# Only the pure helper function is compiled for this read-only script audit.
# The actual app.after_request hook remains in core and is NOT executed here.
import ast as _r159_ast
_r159_helper_nodes=_r159_ast.parse(_r159_helpers,filename='r159-readonly-helper').body
_r159_target=[node for node in _r159_helper_nodes
               if isinstance(node,_r159_ast.FunctionDef)
               and node.name=='bodymind_r159_month_before_entry']
if len(_r159_target)!=1:
    raise RuntimeError('R159 read-only predicate missing')
_r159_scope={}
exec(compile(_r159_ast.Module(body=_r159_target,type_ignores=[]),
             'r159-readonly-helper','exec'),_r159_scope)
_r159_predicate=_r159_scope['bodymind_r159_month_before_entry']
_r159_db=sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True,timeout=20);_r159_db.row_factory=sqlite3.Row
try:
    _r159_cols=[str(x[1]) for x in _r159_db.execute('PRAGMA table_info(tesserati)').fetchall()]
    _r159_triples=_r159_db.execute("""
      SELECT tesserato_id,mese,anno FROM quote_mensili
       WHERE anno=2026 AND mese IN (9,10) GROUP BY tesserato_id,mese,anno
    """).fetchall()
    _r159_skip=sum(1 for x in _r159_triples if
        _r159_predicate(_r159_db,int(x['tesserato_id']),int(x['anno']),int(x['mese'])))
    _r159_counts={t:int(_r159_db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0])
                  for t in ('pagamenti','ricevute','tesserati','quote_mensili')}
    _r159_dbok=str(_r159_db.execute('PRAGMA integrity_check').fetchone()[0])
    _r159_fk=len(_r159_db.execute('PRAGMA foreign_key_check').fetchall())
finally:_r159_db.close()
print('[r159-readonly] start_date_columns='+repr(
    [x for x in _r159_cols if any(k in x for k in ('iscri','ingress','frequen','created','inizio','tesser'))])+
    ' preentry_months_excluded='+str(_r159_skip)+
    ' counts='+repr(_r159_counts)+' integrity='+_r159_dbok+' fk='+str(_r159_fk),flush=True)
if _r159_dbok.lower()!='ok' or _r159_fk:
    raise RuntimeError('R159 DB read-only integrity guard failed')
print('[r159] PASS guarded-october-updates original-receipts-preserved month-start-readonly doc-13-inch-css',flush=True)
