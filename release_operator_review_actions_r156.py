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
# BODYMIND_R158_PAYMENT_RECEIPTS_SMS
# Canonical post-R123 patch for exact payment edits, receipt synchronization,
# separate future I/M receipt series, and mobile-only manual SMS reminders.
# Existing issued receipt numbers are never renumbered.
# ---------------------------------------------------------------------------
_core=CORE.read_text(encoding='utf-8',errors='replace')
if '# BODYMIND_R158_PAYMENT_RECEIPTS_SMS' not in _core:
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
                "SELECT COALESCE(MAX(numero_serie),0)+1 FROM ricevute WHERE anno_progressivo=? AND serie_ricevuta=? AND COALESCE(annullata,0)=0",
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
        _dbbak=BACK/'asd.pre_r158_receipt_sync.db'
        if not _dbbak.exists():
            _srcdb=sqlite3.connect(str(DB),timeout=30);_outdb=sqlite3.connect(str(_dbbak))
            try:_srcdb.backup(_outdb)
            finally:_outdb.close();_srcdb.close()
        for _x in _mismatch:
            _r158db.execute("UPDATE ricevute SET importo=?,updated_at=datetime('now') WHERE id=?",(float(_x['payment_amount'] or 0),int(_x['rid'])))
    _r158db.commit()
    print('[r158-db] columns='+repr(_altered)+' corrected='+str(len(_mismatch))+' '+repr([dict(x) for x in _mismatch]),flush=True)
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
checks={'page':r.status_code==200,'sms':'sms-reminder' in h and ('sms:' in h or 'numero mancante' in h),'series_cols':{'serie_ricevuta','numero_serie'}.issubset(cols),'receipt_sync':stale==0,'db':integ.lower()=='ok' and fk==0}
print('[r158-audit] '+repr(checks)+' mancinelli='+repr(man),flush=True)
if not all(checks.values()):raise RuntimeError('R158 QA failed '+repr(checks))
'''
_r158p=subprocess.run([sys.executable,'-c',_r158qa],capture_output=True,text=True,timeout=180)
print((_r158p.stdout or '').strip(),flush=True)
if _r158p.returncode!=0:
    raise RuntimeError('R158 child audit failed '+((_r158p.stderr or '')+(_r158p.stdout or ''))[-8000:])
print('[r158] PASS receipt-auto-sync separate-future-I/M-series mobile-manual-SMS historical-numbers-preserved',flush=True)
