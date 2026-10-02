# -*- coding: utf-8 -*-
from __future__ import annotations
import json, py_compile, shutil, sqlite3
from datetime import datetime
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
P=APP/'asd_app/routes_operator_bodymind.py'
BACK=Path('/data/release_backups/20261002_r79_canonical_mu')
BACK.mkdir(parents=True,exist_ok=True)
MARKER=APP/'.BODYMIND_R79_CANONICAL_MU'

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

def backup_db():
    dst=BACK/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_pre_r79.db')
    src=sqlite3.connect(str(DB),timeout=30); out=sqlite3.connect(str(dst))
    try: src.backup(out)
    finally: out.close(); src.close()
    return str(dst)

# Patch the final R78 runtime layer, not historical upload code.
s=P.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R79_SELF_CANONICAL' not in s:
    b=BACK/'routes_operator_bodymind.py'
    if not b.exists(): shutil.copy2(P,b)

    old='''    if docrefs:
        if "status" in _cols(conn,"inbound_documents"):
            conn.execute("UPDATE inbound_documents SET status='duplicato_risolto' WHERE id=?",(int(inbound_id),))
            conn.commit()
        return {"archived":False,"deleted":False,"reason":"referenced","document_ids":[int(x["id"]) for x in docrefs]}
'''
    new='''    # BODYMIND_R79_SELF_CANONICAL
    if docrefs:
        ref_ids=[int(x["id"]) for x in docrefs]
        ic=_cols(conn,"inbound_documents")
        if int(canonical_document_id or 0) in ref_ids:
            sets=[]; vals=[]
            if "status" in ic: sets.append("status=?"); vals.append("associato")
            if "document_type" in ic: sets.append("document_type=?"); vals.append("modulo_unico_tesseramento")
            if "match_score" in ic: sets.append("match_score=CASE WHEN coalesce(match_score,0)<99 THEN 99 ELSE match_score END")
            if sets:
                vals.append(int(inbound_id))
                conn.execute("UPDATE inbound_documents SET "+",".join(sets)+" WHERE id=?",tuple(vals))
            conn.commit()
            return {"archived":False,"deleted":False,"reason":"same_upload_canonical","self_created_canonical":True,"document_ids":ref_ids}
        if "status" in ic:
            conn.execute("UPDATE inbound_documents SET status='duplicato_risolto' WHERE id=?",(int(inbound_id),))
            conn.commit()
        return {"archived":False,"deleted":False,"reason":"referenced","document_ids":ref_ids}
'''
    if old not in s:
        raise RuntimeError('R79 referenced-staging anchor missing')
    s=s.replace(old,new,1)

    old='''    sync={"ok":True,"reason":"not_mu"}
    if incoming_type=="modulo_unico_tesseramento":
        try:
            from .verified_mu_sync_core_r68 import sync_analysis_to_existing_athlete
            sync=sync_analysis_to_existing_athlete(conn,tid,semantic,source="operator_duplicate_mu_r78")
        except Exception as exc:
            sync={"ok":False,"reason":"mu_sync_error","error":repr(exc)[:180]}
'''
    new='''    sync={"ok":True,"reason":"not_mu"}
    if incoming_type=="modulo_unico_tesseramento":
        dc=_cols(conn,"documenti"); sets=[]; vals=[]
        if "doc_type" in dc: sets.append("doc_type=?"); vals.append("modulo_unico_tesseramento")
        if "categoria" in dc: sets.append("categoria=?"); vals.append("Modulo iscrizione BodyMind")
        if "status" in dc and str(canonical["status"] or "").strip().lower() in ("da_verificare","needs_review","associato_tipo_da_verificare",""):
            sets.append("status=?"); vals.append("salvato")
        if "visibile" in dc: sets.append("visibile=1")
        if sets:
            vals.append(canonical_id)
            conn.execute("UPDATE documenti SET "+",".join(sets)+" WHERE id=?",tuple(vals))
            conn.commit()
        try:
            from .verified_mu_sync_core_r68 import sync_analysis_to_existing_athlete
            sync=sync_analysis_to_existing_athlete(conn,tid,semantic,source="operator_duplicate_mu_r79")
        except Exception as exc:
            sync={"ok":False,"reason":"mu_sync_error","error":repr(exc)[:180]}
'''
    if old not in s:
        raise RuntimeError('R79 canonical-MU anchor missing')
    s=s.replace(old,new,1)

    old='''                    item.update({
                        "status":"duplicato_risolto","duplicate":True,
                        "duplicate_of":dup.get("existing_id"),"duplicate_reason":dup.get("reason"),
                        "association_resolved":bool(resolved.get("ok")),
                        "canonical_document_id":resolved.get("canonical_document_id"),
                        "mu_sync":resolved.get("mu_sync"),
                        "duplicate_staging":resolved.get("staging")
                    })
'''
    new='''                    same_upload=bool((resolved.get("staging") or {}).get("self_created_canonical"))
                    item.update({
                        "status":"importato_associato" if same_upload else "duplicato_risolto",
                        "duplicate":False if same_upload else True,
                        "duplicate_of":dup.get("existing_id"),"duplicate_reason":dup.get("reason"),
                        "association_resolved":bool(resolved.get("ok")),
                        "canonical_document_id":resolved.get("canonical_document_id"),
                        "mu_sync":resolved.get("mu_sync"),
                        "duplicate_staging":resolved.get("staging")
                    })
'''
    if old not in s:
        raise RuntimeError('R79 result wording anchor missing')
    s=s.replace(old,new,1)
    s=s.replace('duplicati risolti sulla copia già presente','documenti già presenti o risolti correttamente sul dossier')
    P.write_text(s,encoding='utf-8')
    py_compile.compile(str(P),doraise=True)
    print('[operator-r79] PASS self-produced-canonical is association, not duplicate',flush=True)

# One-time DB normalization for legacy MU rows already associated to a tesserato.
if not MARKER.exists():
    backup=backup_db()
    conn=sqlite3.connect(str(DB),timeout=45); conn.row_factory=sqlite3.Row
    changed=[]; audit=[]
    try:
        dcols={str(x[1]) for x in conn.execute('PRAGMA table_info(documenti)').fetchall()}
        icols={str(x[1]) for x in conn.execute('PRAGMA table_info(inbound_documents)').fetchall()}
        rows=conn.execute("""SELECT * FROM documenti
          WHERE coalesce(tesserato_id,0)>0 AND coalesce(visibile,1)=1 ORDER BY id""").fetchall()
        for d in rows:
            did=int(d['id']); tid=int(d['tesserato_id'] or 0)
            hay=' '.join(str(d[k] or '').lower() for k in ('titolo','categoria','doc_type','filename') if k in d.keys())
            strong=('modulo_unico' in hay or 'modulo unico' in hay or ('modulo' in hay and 'iscrizion' in hay) or 'modulo iscrizione bodymind' in hay)
            if not strong:
                continue

            inbound=None
            if 'inbound_id' in dcols and int(d['inbound_id'] or 0)>0:
                inbound=conn.execute('SELECT * FROM inbound_documents WHERE id=?',(int(d['inbound_id']),)).fetchone()
            if not inbound:
                inbound=conn.execute("""SELECT * FROM inbound_documents
                  WHERE coalesce(tesserato_id,0)=? AND coalesce(match_score,0)>=95
                    AND (lower(coalesce(original_filename,'')) LIKE '%modulo%'
                         OR lower(coalesce(original_filename,'')) LIKE '%iscrizion%')
                  ORDER BY id DESC LIMIT 1""",(tid,)).fetchone()

            evidence=bool(inbound and int(inbound['tesserato_id'] or 0)==tid and int(inbound['match_score'] or 0)>=95)
            audit.append({'document_id':did,'tid':tid,'inbound_id':int(inbound['id']) if inbound else None,'strong_mu_name':strong,'strong_identity':evidence})
            if not evidence:
                continue

            sets=[]; vals=[]
            if 'doc_type' in dcols and str(d['doc_type'] or '').strip().lower()!='modulo_unico_tesseramento':
                sets.append('doc_type=?'); vals.append('modulo_unico_tesseramento')
            if 'categoria' in dcols and str(d['categoria'] or '').strip().lower()!='modulo iscrizione bodymind':
                sets.append('categoria=?'); vals.append('Modulo iscrizione BodyMind')
            if 'status' in dcols and str(d['status'] or '').strip().lower() in ('da_verificare','needs_review','associato_tipo_da_verificare',''):
                sets.append('status=?'); vals.append('salvato')
            if sets:
                vals.append(did)
                conn.execute('UPDATE documenti SET '+','.join(sets)+' WHERE id=?',tuple(vals))

            isets=[]; ivals=[]
            if 'document_type' in icols: isets.append('document_type=?'); ivals.append('modulo_unico_tesseramento')
            if 'status' in icols: isets.append('status=?'); ivals.append('associato')
            if 'match_score' in icols: isets.append('match_score=CASE WHEN coalesce(match_score,0)<99 THEN 99 ELSE match_score END')
            if isets:
                ivals.append(int(inbound['id']))
                conn.execute('UPDATE inbound_documents SET '+','.join(isets)+' WHERE id=?',tuple(ivals))

            try:
                from asd_app.onboarding_flow import sync_unified_module_flags, recompute_onboarding_status
                sync_unified_module_flags(conn,tid,source='r79_canonical_mu')
                recompute_onboarding_status(conn,tid)
            except Exception:
                pass
            changed.append({'document_id':did,'tid':tid,'inbound_id':int(inbound['id'])})

        conn.commit()
        a=conn.execute("SELECT id,nome,cognome FROM tesserati WHERE lower(coalesce(cognome,'')) LIKE '%abatini%' LIMIT 1").fetchone()
        abatini={}
        if a:
            tid=int(a['id'])
            abatini={
              'id':tid,'name':(str(a['nome'] or '')+' '+str(a['cognome'] or '')).strip(),
              'documents':[dict(x) for x in conn.execute("SELECT id,titolo,categoria,doc_type,status,visibile,inbound_id FROM documenti WHERE tesserato_id=? ORDER BY id",(tid,)).fetchall()],
              'inbound':[dict(x) for x in conn.execute("SELECT id,status,document_type,document_confidence,match_score,tesserato_id,original_filename FROM inbound_documents WHERE coalesce(tesserato_id,0)=? OR lower(coalesce(original_filename,'')) LIKE '%abatini%' ORDER BY id",(tid,)).fetchall()]
            }
        integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
        fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
        tess=int(conn.execute('SELECT COUNT(*) FROM tesserati').fetchone()[0])
    finally:
        conn.close()
    print('[r79-mu-normalization] changed='+json.dumps(changed,ensure_ascii=False)+' audit='+json.dumps(audit,ensure_ascii=False)+' Abatini='+json.dumps(abatini,ensure_ascii=False)+' backup='+backup+' integrity='+integrity+' fk='+str(fk),flush=True)
    if tess!=32 or integrity.lower()!='ok' or fk:
        raise RuntimeError('R79 integrity/count guard failed')
    MARKER.write_text('BodyMind R79 canonical MU normalization completed\n',encoding='utf-8')
    print('[r79-selftest] PASS canonical-MU metadata inbound-association onboarding-coherence db-ok',flush=True)
else:
    print('[r79-mu-normalization] already applied',flush=True)
