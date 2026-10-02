# -*- coding: utf-8 -*-
from __future__ import annotations
import json, py_compile, re, shutil, sqlite3
from datetime import datetime
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
OP=APP/'asd_app/routes_operator_bodymind.py'
BACK=Path('/data/release_backups/20261002_r107_operator_attachment_create')
BACK.mkdir(parents=True,exist_ok=True)

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

def backup_file(p):
    dst=BACK/p.name
    if p.exists() and not dst.exists(): shutil.copy2(p,dst)

s=OP.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R107_ATTACHMENT_CREATE_CORE' not in s:
    backup_file(OP)
    anchor='@app.post("/operatore-bodymind/chat")'
    helper=r'''
# BODYMIND_R107_ATTACHMENT_CREATE_CORE
def _r107_attachment_schema(conn):
    conn.execute("""
      CREATE TABLE IF NOT EXISTS bodymind_operator_attachment_context(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT NOT NULL,
        inbound_id INTEGER NOT NULL,
        document_type TEXT,
        semantic_json TEXT,
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(conversation_id,inbound_id)
      )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_r107_attach_conv ON bodymind_operator_attachment_context(conversation_id,status,id)")
    conn.commit()

def _r107_remember_upload_results(results):
    conn=db()
    try:
        _r107_attachment_schema(conn)
        conv=_conv_id(); now=datetime.now().isoformat(timespec="seconds")
        kept=[]
        for item in (results or []):
            iid=int((item or {}).get("inbound_id") or 0)
            if iid<=0: continue
            sem=None
            if _table(conn,"bodymind_document_semantics"):
                row=conn.execute("""SELECT analysis_json FROM bodymind_document_semantics
                  WHERE source_table='inbound_documents' AND source_id=? ORDER BY id DESC LIMIT 1""",(iid,)).fetchone()
                if row:
                    try: sem=json.loads(str(row["analysis_json"] or "{}"))
                    except Exception: sem=None
            dtype=str((sem or {}).get("document_type") or (item or {}).get("type") or "")
            payload=json.dumps(sem,ensure_ascii=False,separators=(",",":")) if isinstance(sem,dict) else None
            conn.execute("""INSERT INTO bodymind_operator_attachment_context
              (conversation_id,inbound_id,document_type,semantic_json,status,created_at,updated_at)
              VALUES(?,?,?,?, 'active',?,?)
              ON CONFLICT(conversation_id,inbound_id) DO UPDATE SET
                document_type=excluded.document_type,semantic_json=COALESCE(excluded.semantic_json,bodymind_operator_attachment_context.semantic_json),
                status='active',updated_at=excluded.updated_at""",
              (conv,iid,dtype,payload,now,now))
            kept.append(iid)
        if kept:
            ph=",".join("?" for _ in kept)
            conn.execute("UPDATE bodymind_operator_attachment_context SET status='superseded',updated_at=? WHERE conversation_id=? AND status='active' AND inbound_id NOT IN ("+ph+")",
                         (now,conv,*kept))
        conn.commit()
    finally:
        conn.close()

def _r107_last_attachment(conn):
    _r107_attachment_schema(conn)
    row=conn.execute("""SELECT * FROM bodymind_operator_attachment_context
      WHERE conversation_id=? AND status='active' ORDER BY id DESC LIMIT 1""",(_conv_id(),)).fetchone()
    if not row: return None,None
    inbound=conn.execute("SELECT * FROM inbound_documents WHERE id=?",(int(row["inbound_id"]),)).fetchone() if _table(conn,"inbound_documents") else None
    sem=None
    try: sem=json.loads(str(row["semantic_json"] or "{}"))
    except Exception: sem=None
    if (not isinstance(sem,dict) or not sem) and inbound and _table(conn,"bodymind_document_semantics"):
        sr=conn.execute("""SELECT analysis_json FROM bodymind_document_semantics
          WHERE source_table='inbound_documents' AND source_id=? ORDER BY id DESC LIMIT 1""",(int(row["inbound_id"]),)).fetchone()
        if sr:
            try: sem=json.loads(str(sr["analysis_json"] or "{}"))
            except Exception: sem=None
    return inbound,(sem if isinstance(sem,dict) else None)

def _r107_requested_name(message):
    m=re.search(r"(?:crea(?:re)?\s+(?:un\s+)?tesserat[oa]|nuov[oa]\s+tesserat[oa])\s+([A-Za-zÀ-ÿ' -]{2,90}?)(?=\s+(?:e|ed|con|usando|utilizzando|aggiung\w*)\b|$)",str(message or ""),re.I)
    return re.sub(r"\s+"," ",m.group(1)).strip(" -") if m else ""

def _r107_name_conflict(requested,analysis):
    req=_norm(requested)
    if not req: return False
    first=_norm((analysis or {}).get("first_name") or "")
    last=_norm((analysis or {}).get("last_name") or "")
    person=_norm((analysis or {}).get("person_name") or ((analysis or {}).get("first_name","")+" "+(analysis or {}).get("last_name","")))
    toks=[x for x in req.split() if x]
    if len(toks)>=2:
        return bool(person and req!=person and not all(t in person for t in toks))
    if len(toks)==1:
        return bool(first or last) and toks[0] not in {first,last}
    return False

def _r107_handle_create_from_attachment(conn,message):
    n=_norm(message)
    explicit_create=bool(re.search(r"\b(crea|creare|nuov[oa])\b",n)) and ("tesserat" in n or "atlet" in n)
    refers_attachment=any(x in n for x in ("allegat","appena caricat","modulo appena","file appena","usa il modulo","aggiungi il modulo"))
    if not (explicit_create and refers_attachment):
        return None

    inbound,semantic=_r107_last_attachment(conn)
    if not inbound:
        return {"text":"Non trovo un allegato recente collegato a questa conversazione. Allega il Modulo Unico e ripeti il comando.","mode":"warning","attachment_context":False}
    if not semantic:
        return {"text":"L’allegato è presente, ma non ha ancora un’analisi semantica affidabile. L’ho lasciato in verifica senza creare anagrafiche.","mode":"warning","attachment_context":True}

    aliases={"modulo_unico_tesseramento","modulo_unico","modulo iscrizione","domanda iscrizione","domanda_iscrizione","iscrizione","modulo iscrizione manleva"}
    dtype=_norm(semantic.get("document_type") or "")
    if dtype not in {_norm(x) for x in aliases}:
        return {"text":"L’allegato recente non risulta un Modulo Unico/domanda di iscrizione con sufficiente certezza. Non creo un tesserato da un documento di altro tipo.","mode":"warning","semantic_type":semantic.get("document_type")}

    requested=_r107_requested_name(message)
    docname=(" ".join(x for x in [str(semantic.get("first_name") or "").strip(),str(semantic.get("last_name") or "").strip()] if x)).strip() or str(semantic.get("person_name") or "").strip()
    if _r107_name_conflict(requested,semantic):
        return {"text":"Il nome scritto nel comando ("+requested+") non coincide con l’identità letta dal Modulo Unico ("+(docname or "non determinata")+"). Non ho creato nulla: conferma quale identità è corretta.","mode":"identity_conflict","requested_name":requested,"document_name":docname}

    from .enrollment_ingest_core_r65 import enrollment_identity_ready,find_existing_athlete,create_athlete_from_analysis
    from .verified_mu_sync_core_r68 import sync_analysis_to_existing_athlete
    if not enrollment_identity_ready(semantic,require_valid_cf=True):
        return {"text":"Il Modulo Unico è stato letto, ma l’identità non supera ancora il gate sicuro (nome/cognome, CF valido e coerenza richiesta). Non creo duplicati o anagrafiche incerte.","mode":"review","document_name":docname}

    try: backup=_operator_db_backup("r107_create_from_attachment")
    except Exception: backup=""

    existing,reason=find_existing_athlete(conn,semantic)
    created=False
    if existing:
        tid=int(existing["id"])
    else:
        cr=create_athlete_from_analysis(conn,semantic,source="operator_r107_attachment",require_valid_cf=True)
        tid=int(cr.get("tesserato_id") or 0); created=bool(cr.get("created"))
        if tid<=0:
            conn.rollback()
            return {"text":"Il documento è leggibile ma la creazione dell’anagrafica non ha superato i controlli di integrità. Nessun dossier è stato prodotto.","mode":"error","details":cr}

    iid=int(inbound["id"])
    ic=_cols(conn,"inbound_documents"); sets=[]; vals=[]
    for col in ("tesserato_id","matched_tesserato_id","suggested_tesserato_id"):
        if col in ic: sets.append(col+"=?"); vals.append(tid)
    if "match_score" in ic: sets.append("match_score=?"); vals.append(100)
    if "document_type" in ic: sets.append("document_type=?"); vals.append("modulo_unico_tesseramento")
    if "status" in ic: sets.append("status=?"); vals.append("associato")
    if sets:
        vals.append(iid); conn.execute("UPDATE inbound_documents SET "+",".join(sets)+" WHERE id=?",tuple(vals))
    conn.commit()

    name,data,_=_inbound_file_bytes(inbound)
    dup=_semantic_key_duplicate(conn,tid,name,data,semantic) if data else {"duplicate":False}
    if dup.get("duplicate"):
        resolved=_r78_finalize_duplicate(conn,iid,tid,semantic,dup)
        prod_ok=bool(resolved.get("ok")); prod={"duplicate":True,"resolved":resolved,"canonical_document_id":resolved.get("canonical_document_id")}
    else:
        prod_ok,prod=_productionize_inbound(iid,type_hint="modulo_unico_tesseramento")

    sync=sync_analysis_to_existing_athlete(conn,tid,semantic,source="operator_r107_attachment")
    try:
        from .onboarding_flow import sync_unified_module_flags,recompute_onboarding_status
        sync_unified_module_flags(conn,tid,source="operator_r107_attachment")
        recompute_onboarding_status(conn,tid)
        conn.commit()
    except Exception:
        pass

    now=datetime.now().isoformat(timespec="seconds")
    conn.execute("UPDATE bodymind_operator_attachment_context SET status='used',updated_at=? WHERE conversation_id=? AND inbound_id=?",
                 (now,_conv_id(),iid)); conn.commit()

    athlete=conn.execute("SELECT * FROM tesserati WHERE id=?",(tid,)).fetchone()
    finalname=((str(athlete["nome"] or "")+" "+str(athlete["cognome"] or "")).strip() if athlete else docname)
    if not prod_ok:
        return {"text":"Ho "+("creato" if created else "riconosciuto")+" "+finalname+", ma il Modulo Unico non è stato prodotto correttamente nel dossier. Ho lasciato il caso tracciato per verifica, senza creare duplicati.","mode":"warning","tesserato_id":tid,"created":created,"production":prod,"sync":sync,"backup":backup}
    return {"text":("Creato" if created else "Tesserato già esistente riconosciuto")+": "+finalname+". Ho associato il Modulo Unico appena allegato, sincronizzato profilo, minore/genitore, dossier e onboarding.","mode":"action","tesserato_id":tid,"created":created,"match_reason":reason,"production":prod,"sync":sync,"backup":backup,
            "links":[{"label":"Apri scheda","href":"/tesserati/"+str(tid)+"/scheda"},{"label":"Apri dossier","href":"/mobile/atleta/"+str(tid)+"/documenti"}]}

'''
    if anchor not in s:
        raise RuntimeError('R107 chat anchor missing')
    s=s.replace(anchor,helper+anchor,1)

    # Persist the exact attachment/inbound context at the end of the upload endpoint.
    up_start=s.index('@app.post("/operatore-bodymind/upload")')
    up_end=s.index('\n@app.after_request\ndef bodymind_family_logo_override',up_start)
    block=s[up_start:up_end]
    pos=block.rfind('    return jsonify({')
    if pos<0:
        raise RuntimeError('R107 upload return anchor missing')
    remember='''    # BODYMIND_R107_PERSIST_LAST_ATTACHMENTS
    try:
        _r107_remember_upload_results(results)
    except Exception as r107_ctx_exc:
        try:
            conn_ctx=db(); _log(conn_ctx,"system","R107 attachment context warning: "+repr(r107_ctx_exc)); conn_ctx.close()
        except Exception:
            pass

'''
    block=block[:pos]+remember+block[pos:]
    s=s[:up_start]+block+s[up_end:]

    chat_start=s.index('@app.post("/operatore-bodymind/chat")')
    chat_end=s.index('\ndef _cloud_user_error',chat_start)
    chat=s[chat_start:chat_end]
    gate='''        _log(conn,"user",message)

'''
    inject='''        _log(conn,"user",message)

        # Explicit create-from-attachment is deterministic and precedes search-only planner tools.
        r107_result=_r107_handle_create_from_attachment(conn,message)
        if isinstance(r107_result,dict):
            _log(conn,"assistant",r107_result.get("text",""),r107_result)
            return jsonify(r107_result)

'''
    if gate not in chat:
        raise RuntimeError('R107 chat deterministic gate anchor missing')
    chat=chat.replace(gate,inject,1)
    s=s[:chat_start]+chat+s[chat_end:]

    OP.write_text(s,encoding='utf-8')
    py_compile.compile(str(OP),doraise=True)
    print('[r107-operator] PASS persistent-attachment-context explicit-create-before-search shared-enrollment-core',flush=True)
else:
    print('[r107-operator] already applied',flush=True)

# Read-only production invariants. No hard-coded athlete count.
conn=sqlite3.connect(str(DB),timeout=30); conn.row_factory=sqlite3.Row
try:
    before_count=int(conn.execute('SELECT COUNT(*) FROM tesserati').fetchone()[0])
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
    dup_cf=int(conn.execute("""SELECT COUNT(*) FROM (
      SELECT upper(replace(replace(trim(coalesce(codice_fiscale,'')),' ',''),'-','')) cf,COUNT(*) n
      FROM tesserati WHERE trim(coalesce(codice_fiscale,''))<>'' GROUP BY cf HAVING COUNT(*)>1)""").fetchone()[0]) if 'codice_fiscale' in {r[1] for r in conn.execute('PRAGMA table_info(tesserati)').fetchall()} else 0
    dup_identity=int(conn.execute("""SELECT COUNT(*) FROM (
      SELECT lower(trim(coalesce(nome,''))) n,lower(trim(coalesce(cognome,''))) c,lower(trim(coalesce(data_nascita,''))) d,COUNT(*) x
      FROM tesserati GROUP BY n,c,d HAVING n<>'' AND c<>'' AND COUNT(*)>1)""").fetchone()[0])
finally:
    conn.close()

text=OP.read_text(encoding='utf-8',errors='replace')
checks={
  'attachment_context':'BODYMIND_R107_PERSIST_LAST_ATTACHMENTS' in text and 'bodymind_operator_attachment_context' in text,
  'create_gate':'_r107_handle_create_from_attachment(conn,message)' in text,
  'shared_core':'from .enrollment_ingest_core_r65 import enrollment_identity_ready' in text,
  'db_ok':integrity.lower()=='ok' and fk==0,
  'duplicate_cf_zero':dup_cf==0,
  'duplicate_identity_zero':dup_identity==0,
}
print('[r107-checks] '+repr(checks)+' tesserati='+str(before_count)+' integrity='+integrity+' fk='+str(fk)+' dup_cf='+str(dup_cf)+' dup_identity='+str(dup_identity),flush=True)
failed=[k for k,v in checks.items() if not v]
if failed: raise RuntimeError('R107 QA failed '+repr(failed))
print('[r107-selftest] PASS attachment-create-core db-invariants dynamic-count',flush=True)
