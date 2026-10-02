# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import py_compile, shutil

APP=Path('/data/top2_app')
P=APP/'asd_app/routes_operator_bodymind.py'
BACK=Path('/data/release_backups/20261001_operator_r55/routes_operator_bodymind.py')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

s=P.read_text(encoding='utf-8',errors='replace')

# BODYMIND_R73_MOBILE_COMPOSER_AUTONOMY
# Apply before the historical R55 early-exit so persisted installations receive R73 too.
if 'BODYMIND_R73_MOBILE_COMPOSER_AUTONOMY' not in s:
    BACK73=Path('/data/release_backups/20261002_r73_operator/routes_operator_bodymind.py')
    BACK73.parent.mkdir(parents=True,exist_ok=True)
    if not BACK73.exists():
        shutil.copy2(P,BACK73)

    css='.bmo-compose textarea{{min-height:48px;max-height:150px;resize:vertical;border-radius:15px;padding:12px 14px;background:#081729;color:#fff;border:1px solid rgba(125,211,252,.19);font:inherit}}'
    if css not in s:
        raise RuntimeError('R73 composer CSS anchor missing')
    s=s.replace(css,css+'''
    /* BODYMIND_R73_MOBILE_COMPOSER_AUTONOMY */
    @media(max-width:800px){{
      .bmo-chat{{min-height:calc(100dvh - 150px)!important;height:calc(100dvh - 150px)!important;overflow:hidden!important}}
      .bmo-messages{{max-height:none!important;min-height:0!important;overflow-y:auto!important;-webkit-overflow-scrolling:touch!important;padding-bottom:18px!important}}
      .bmo-compose-shell{{position:sticky!important;bottom:0!important;z-index:80!important;background:rgba(5,12,23,.98)!important;padding-bottom:env(safe-area-inset-bottom)!important}}
      .bmo-compose textarea{{resize:none!important;max-height:118px!important}}
    }}''',1)

    add_anchor="      function addMsg(text,who='bot',data={{}}){{"
    helper="""      function bodymindKeepComposerVisible(){{
        try{{
          messages.scrollTop=messages.scrollHeight;
          if(window.matchMedia&&window.matchMedia('(max-width:800px)').matches){{
            const shell=document.querySelector('.bmo-compose-shell');
            if(shell) shell.scrollIntoView({{block:'end',behavior:'smooth'}});
          }}
        }}catch(e){{}}
      }}
"""
    if add_anchor not in s:
        raise RuntimeError('R73 addMsg anchor missing')
    s=s.replace(add_anchor,helper+add_anchor,1)

    old_scroll="        requestAnimationFrame(()=>{{messages.scrollTop=messages.scrollHeight}});"
    if old_scroll not in s:
        raise RuntimeError('R73 scroll anchor missing')
    s=s.replace(old_scroll,"        requestAnimationFrame(()=>{{bodymindKeepComposerVisible()}});",1)

    old_finally="        }}finally{{send.disabled=false;input.focus()}}"
    if old_finally not in s:
        raise RuntimeError('R73 focus anchor missing')
    s=s.replace(old_finally,"        }}finally{{send.disabled=false;input.focus();setTimeout(bodymindKeepComposerVisible,80)}}",1)

    if 'for agent_step in range(3):' not in s:
        raise RuntimeError('R73 agent loop anchor missing')
    s=s.replace('for agent_step in range(3):','for agent_step in range(5):',1)
    s=s.replace('if tool in discovery_tools and agent_step<2:','if tool in discovery_tools and agent_step<4:',1)

    old_prompt='"Scegli UNO strumento reale e preferisci direttamente lo strumento operativo corretto. Usa discover_capabilities solo se gli elementi pertinenti non bastano davvero. "'
    new_prompt=(
        '"Porta a termine la richiesta nello stesso turno quando gli strumenti disponibili lo consentono. "'
        '"Puoi concatenare più passaggi: scegli il prossimo strumento realmente utile e usa discover_capabilities solo se serve davvero. "'
        '"Non chiedere dettagli per letture, controlli, classificazioni, sincronizzazioni sicure o preparazione del lavoro quando il dato è ricavabile dal gestionale o dal contesto. "'
        '"Chiedi una precisazione solo se manca un dato indispensabile o esistono più identità plausibili. "'
        '"Mantieni conferma esplicita per cancellazioni, fusioni, denaro, invii esterni e altre operazioni irreversibili o sensibili. "'
    )
    if old_prompt not in s:
        raise RuntimeError('R73 planner prompt anchor missing')
    s=s.replace(old_prompt,new_prompt,1)
    P.write_text(s,encoding='utf-8')
    py_compile.compile(str(P),doraise=True)
    print('[operator-r73] PASS mobile composer + 5-step autonomous planner',flush=True)

if 'BODYMIND_R55_AUTONOMOUS_SECRETARY' in s:
    print('[operator-r55] already applied',flush=True)
    raise SystemExit(0)

BACK.parent.mkdir(parents=True,exist_ok=True)
if not BACK.exists():
    shutil.copy2(P,BACK)

s=s.replace('OPERATOR_VERSION = "R52.0-semantic-secretary"','OPERATOR_VERSION = "R55.0-autonomous-secretary"',1)

old='''def _semantic_match_athlete(conn,analysis):
    cf=re.sub(r"[^A-Z0-9]","",str((analysis or {}).get("codice_fiscale") or "").upper())
    tc=_cols(conn,"tesserati") if _table(conn,"tesserati") else set()
    if cf and "codice_fiscale" in tc:
        rows=conn.execute(
            "SELECT * FROM tesserati WHERE upper(replace(replace(coalesce(codice_fiscale,''),' ',''),'-',''))=?",(cf,)
        ).fetchall()
        if len(rows)==1:
            return rows[0],1.0,"codice_fiscale"
    pname=str((analysis or {}).get("person_name") or "").strip()
    if pname:
        athlete,amb=_match_athlete(conn,pname)
        if athlete and not amb:
            score=.94
            birth=str((analysis or {}).get("birth_date") or "")[:10]
            if birth and "data_nascita" in athlete.keys() and str(athlete["data_nascita"] or "")[:10]==birth:
                score=.99
            return athlete,score,"contenuto_documento"
    return None,0.0,""

def _semantic_for_new_bytes(conn,name,data,extracted_text="",type_hint=""):
    return _docsem_analyze_bytes(conn,name,data,extracted_text,type_hint,_docsem_usage)
'''
new='''# BODYMIND_R55_AUTONOMOUS_SECRETARY
def _semantic_match_athlete(conn,analysis):
    cf=re.sub(r"[^A-Z0-9]","",str((analysis or {}).get("codice_fiscale") or "").upper())
    tc=_cols(conn,"tesserati") if _table(conn,"tesserati") else set()
    if cf and "codice_fiscale" in tc:
        rows=conn.execute(
            "SELECT * FROM tesserati WHERE upper(replace(replace(coalesce(codice_fiscale,''),' ',''),'-',''))=?",(cf,)
        ).fetchall()
        if len(rows)==1:
            return rows[0],1.0,"codice_fiscale"
    pname=str((analysis or {}).get("person_name") or "").strip()
    if pname:
        athlete,amb=_match_athlete(conn,pname)
        if athlete and not amb:
            exact_name=_norm(pname)==_norm(_athlete_name(athlete))
            score=.98 if exact_name else .94
            birth=str((analysis or {}).get("birth_date") or "")[:10]
            if birth and "data_nascita" in athlete.keys() and str(athlete["data_nascita"] or "")[:10]==birth:
                score=.995
            return athlete,score,"nome_esatto_documento" if exact_name else "contenuto_documento"
    return None,0.0,""

def _semantic_for_new_bytes(conn,name,data,extracted_text="",type_hint=""):
    analysis=_docsem_analyze_bytes(conn,name,data,extracted_text,type_hint,_docsem_usage)
    txt=_norm(str(extracted_text or "")[:24000])
    dtype=_norm((analysis or {}).get("document_type") or "")
    evidence=list((analysis or {}).get("evidence") or [])
    mu_markers=("modulo unico","modulo di iscrizione","modulo iscrizione","domanda di iscrizione","domanda iscrizione","richiesta di tesseramento")
    mu_context=("privacy","consenso","manleva","tesseramento","associazione sportiva","bodymind")
    if any(x in txt for x in mu_markers) and any(x in txt for x in mu_context):
        analysis["document_type"]="modulo_unico_tesseramento"
        analysis["confidence"]=max(.97,float(analysis.get("confidence") or 0))
        evidence.append("testo esplicito del documento: modulo unico/iscrizione")
    elif "certificato medico" in txt and any(x in txt for x in ("idoneit","scaden","rilasciat","medico")):
        analysis["document_type"]="certificato_medico"
        analysis["confidence"]=max(.97,float(analysis.get("confidence") or 0))
        evidence.append("testo esplicito del documento: certificato medico")
    analysis["evidence"]=evidence[-20:]
    return analysis
'''
if old not in s:
    raise RuntimeError('R55 semantic match anchor missing')
s=s.replace(old,new,1)

# R55C: exclude the document row linked to the same inbound while reconciling an already-stored upload.
old_sig='''def _same_existing_document(conn,tid,name,data,analysis,max_candidates=8):
    wanted=_norm((analysis or {}).get("document_type") or "")
    for row in _visible_docs(conn,int(tid))[:80]:
'''
new_sig='''def _same_existing_document(conn,tid,name,data,analysis,max_candidates=8,exclude_inbound_id=0):
    wanted=_norm((analysis or {}).get("document_type") or "")
    for row in _visible_docs(conn,int(tid))[:80]:
        if exclude_inbound_id and "inbound_id" in row.keys() and int(row["inbound_id"] or 0)==int(exclude_inbound_id):
            continue
'''
if old_sig not in s:
    raise RuntimeError('R55C duplicate signature anchor missing')
s=s.replace(old_sig,new_sig,1)

old='''        existing=_semantic_for_document_row(conn,row,"documenti")
        if not existing:
            continue
        try:
            cmp=_semantic_same_pair(conn,name,data,analysis,ename,edata,existing)'''
new='''        existing=_semantic_for_document_row(conn,row,"documenti")
        if not existing:
            continue
        # R55: documents of different semantic type are NEVER duplicate candidates.
        if wanted and _norm(existing.get("document_type") or "")!=wanted:
            continue
        try:
            cmp=_semantic_same_pair(conn,name,data,analysis,ename,edata,existing)'''
if old not in s:
    raise RuntimeError('R55 duplicate semantic anchor missing')
s=s.replace(old,new,1)

anchor='''def _verify_document_production(conn,inbound_id):'''
helpers=r'''_OPERATOR_BACKUP_CACHE={"bucket":"","path":""}

def _operator_db_backup(reason="operator"):
    src=Path("/data/tenants/default/asd.db")
    if not src.exists():
        return ""
    bucket=datetime.now().strftime("%Y%m%d_%H%M")
    if _OPERATOR_BACKUP_CACHE.get("bucket")==bucket and _OPERATOR_BACKUP_CACHE.get("path"):
        return str(_OPERATOR_BACKUP_CACHE["path"])
    root=Path("/data/release_backups/operator_runtime")
    root.mkdir(parents=True,exist_ok=True)
    dst=root/(bucket+"_"+re.sub(r"[^a-zA-Z0-9_-]+","_",str(reason))[:40]+".db")
    source=sqlite3.connect(str(src),timeout=30)
    target=sqlite3.connect(str(dst),timeout=30)
    try:
        source.backup(target)
    finally:
        target.close(); source.close()
    _OPERATOR_BACKUP_CACHE.update({"bucket":bucket,"path":str(dst)})
    return str(dst)

def _sync_mu_after_production(tid):
    tid=int(tid or 0)
    if tid<=0:
        return {"ok":False,"reason":"invalid_tesserato"}
    from .onboarding_flow import sync_unified_module_flags, recompute_onboarding_status
    conn=db()
    try:
        athlete=conn.execute("SELECT * FROM tesserati WHERE id=?",(tid,)).fetchone()
        if not athlete:
            return {"ok":False,"reason":"tesserato_missing"}
        is_minor=int((athlete["minorenne"] if "minorenne" in athlete.keys() else 0) or 0)==1
        before={}
        if is_minor and _table(conn,"minori"):
            m=conn.execute("SELECT * FROM minori WHERE tesserato_id=? LIMIT 1",(tid,)).fetchone()
            if m:
                before={k:m[k] for k in ("delega_ritiro_ok","uscita_autonoma_ok") if k in m.keys()}
        sync_unified_module_flags(conn,tid,source="operator_r55_verified_mu")
        recompute_onboarding_status(conn,tid)
        reconciled=0
        covered={
            "modulo_unico_tesseramento","consenso_minore","autorizzazione_genitore",
            "privacy_consenso","manleva","domanda_iscrizione","tutela_minore","safeguarding"
        }
        if is_minor and _table(conn,"onboarding_document_requests"):
            oc=_cols(conn,"onboarding_document_requests")
            if {"tesserato_id","document_type","status"}.issubset(oc):
                ph=",".join("?" for _ in covered)
                sets=["status='manual_accepted'"]
                if "accepted_at" in oc: sets.append("accepted_at=COALESCE(accepted_at,datetime('now'))")
                if "returned_at" in oc: sets.append("returned_at=COALESCE(returned_at,datetime('now'))")
                if "accepted_by" in oc: sets.append("accepted_by=COALESCE(NULLIF(accepted_by,''),'operator_r55')")
                if "note" in oc: sets.append("note=CASE WHEN instr(coalesce(note,''),'R55 MU')=0 THEN trim(coalesce(note,'') || ' | R55 MU verificato: tutela coperta dal Modulo Unico') ELSE note END")
                cur=conn.execute(
                    "UPDATE onboarding_document_requests SET "+",".join(sets)+
                    " WHERE tesserato_id=? AND lower(coalesce(document_type,'')) IN ("+ph+")"+
                    " AND lower(coalesce(status,'')) NOT IN ('deleted','cancelled','accepted','manual_accepted')",
                    [tid,*sorted(covered)]
                )
                reconciled=int(cur.rowcount or 0)
                recompute_onboarding_status(conn,tid)
        conn.commit()
        after={}
        if is_minor and _table(conn,"minori"):
            m=conn.execute("SELECT * FROM minori WHERE tesserato_id=? LIMIT 1",(tid,)).fetchone()
            if m:
                for k,v in before.items():
                    if k in m.keys() and m[k]!=v:
                        raise RuntimeError("R55 refused to alter optional parental choice "+k)
                after={k:m[k] for k in ("consenso_firmato","autorizzazioni_ok","delega_ritiro_ok","uscita_autonoma_ok") if k in m.keys()}
        return {"ok":True,"minor":is_minor,"requests_reconciled":reconciled,"minor_flags":after}
    finally:
        conn.close()

'''
if anchor not in s:
    raise RuntimeError('R55 production verify anchor missing')
s=s.replace(anchor,helpers+anchor,1)

old='''def _productionize_inbound(inbound_id, type_hint=""):
    hint=str(type_hint or "").strip()
    if hint:
        code=_internal_post_route(f"/documenti/da-verificare/{int(inbound_id)}/tipo",{"document_type":hint})'''
new='''def _productionize_inbound(inbound_id, type_hint=""):
    hint=str(type_hint or "").strip()
    backup_path=_operator_db_backup("document_production")
    if hint:
        code=_internal_post_route(f"/documenti/da-verificare/{int(inbound_id)}/tipo",{"document_type":hint})'''
if old not in s:
    raise RuntimeError('R55 production start anchor missing')
s=s.replace(old,new,1)

old='''    conn=db()
    try:
        return _verify_document_production(conn,inbound_id)
    finally:
        conn.close()
'''
new='''    conn=db()
    try:
        verified,details=_verify_document_production(conn,inbound_id)
    finally:
        conn.close()
    details["backup_path"]=backup_path
    if verified and str(details.get("document_type") or "")=="modulo_unico_tesseramento":
        details["mu_sync"]=_sync_mu_after_production(details.get("tesserato_id"))
    return verified,details
'''
# only replace first occurrence after production function
prodpos=s.index('def _productionize_inbound')
tailpos=s.find(old,prodpos)
if tailpos<0:
    raise RuntimeError('R55 production tail anchor missing')
s=s[:tailpos]+new+s[tailpos+len(old):]

old='''                        if "match_score" in ic:
                            sets.append("match_score=?"); vals.append(int(round(semantic_match_score*100)))
                        if sets:'''
new='''                        if "match_score" in ic:
                            sets.append("match_score=?"); vals.append(int(round(semantic_match_score*100)))
                        if "document_type" in ic and str(semantic.get("document_type") or ""):
                            sets.append("document_type=?"); vals.append(str(semantic.get("document_type") or ""))
                        if "document_confidence" in ic:
                            sets.append("document_confidence=?"); vals.append(int(round(float(semantic.get("confidence") or 0)*100)))
                        if sets:'''
if old not in s:
    raise RuntimeError('R55 inbound semantic columns anchor missing')
s=s.replace(old,new,1)

old='''            semantic_ready=bool(semantic) and not declared_mismatch and not semantic_identity_conflict
            if production_mode and inbound_id and semantic_ready:'''
new='''            semantic_ready=(
                bool(semantic)
                and float((semantic or {}).get("confidence") or 0)>=.95
                and str((semantic or {}).get("document_type") or "") not in ("","altro")
                and float(semantic_match_score or 0)>=.98
                and not declared_mismatch
                and not semantic_identity_conflict
            )
            if production_mode and inbound_id and semantic_ready:'''
if old not in s:
    raise RuntimeError('R55 semantic ready anchor missing')
s=s.replace(old,new,1)

# BodyMind public logo, not the legacy app/ASD logo.
s=s.replace('src="/bodymind-media/logo" alt="BodyMind"','src="https://bodymindaerialstudio.life/seed-media/logo?v=9" alt="BodyMind Aerial Studio"')

css_anchor='''    @keyframes bmoVoiceRing{{50%{{transform:scale(1.055);opacity:.18}}}}'''
css_new=css_anchor+'''
    /* BODYMIND_R55_LIVING_LOGO */
    .bmo-avatar img,.bmo-voice-orb img{{transition:transform .18s ease,filter .18s ease;will-change:transform,filter}}
    .bmo-avatar:not(.speaking):not(.listening) img,.bmo-voice-orb:not(.speaking):not(.listening) img{{animation:bmoLogoBreathe 3.6s ease-in-out infinite}}
    .bmo-avatar.speaking img,.bmo-voice-orb.speaking img{{animation:bmoLogoSpeak .42s ease-in-out infinite alternate;filter:drop-shadow(0 0 22px rgba(244,90,157,.72)) drop-shadow(0 14px 26px rgba(0,0,0,.42))}}
    .bmo-avatar.listening img,.bmo-voice-orb.listening img{{animation:bmoLogoListen 1.05s ease-in-out infinite;filter:drop-shadow(0 0 24px rgba(56,189,248,.58))}}
    @keyframes bmoLogoBreathe{{0%,100%{{transform:scale(.98)}}50%{{transform:scale(1.035)}}}}
    @keyframes bmoLogoSpeak{{from{{transform:scale(.96) rotate(-1deg)}}to{{transform:scale(1.08) rotate(1deg)}}}}
    @keyframes bmoLogoListen{{0%,100%{{transform:scale(.98)}}50%{{transform:scale(1.055)}}}}
'''
if css_anchor not in s:
    raise RuntimeError('R55 voice CSS anchor missing')
s=s.replace(css_anchor,css_new,1)

P.write_text(s,encoding='utf-8')
py_compile.compile(str(P),doraise=True)
print('[operator-r55] PASS autonomous-semantic-production exact-athlete-match MU-tutela-sync typed-dedupe living-bodymind-logo backups',flush=True)
