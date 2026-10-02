# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import py_compile, shutil

APP=Path('/data/top2_app')
P=APP/'asd_app/routes_operator_bodymind.py'
BACK=Path('/data/release_backups/20261001_operator_r56/routes_operator_bodymind.py')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

s=P.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R56_FAST_DEDUPE' in s:
    print('[operator-r56] already applied',flush=True)
    raise SystemExit(0)

BACK.parent.mkdir(parents=True,exist_ok=True)
if not BACK.exists():
    shutil.copy2(P,BACK)

s=s.replace('OPERATOR_VERSION = "R55.0-autonomous-secretary"','OPERATOR_VERSION = "R56.0-fast-safe-dedupe"',1)

start=s.index('# BODYMIND_R52_SEMANTIC_DUPLICATES\ndef _semantic_duplicate_groups')
end=s.index('\ndef _canonical_document_kind',start)
replacement=r'''# BODYMIND_R56_FAST_DEDUPE
def _cached_doc_analysis(conn,row,name,data):
    if not data:
        return None
    sha=_docsem_sha256(data)
    try:
        return _docsem_cache_get(conn,"documenti",int(row["id"]),sha)
    except Exception:
        return None

def _cached_same_document(left,right):
    if not isinstance(left,dict) or not isinstance(right,dict):
        return False,0.0,""
    lt=_norm(left.get("document_type") or "")
    rt=_norm(right.get("document_type") or "")
    if not lt or lt!=rt:
        return False,0.0,"tipi documentali diversi"
    try:
        lc=float(left.get("confidence") or 0); rc=float(right.get("confidence") or 0)
    except Exception:
        return False,0.0,"confidenza non valida"
    if min(lc,rc)<.95:
        return False,min(lc,rc),"analisi semantica sotto soglia"
    lcf=re.sub(r"[^A-Z0-9]","",str(left.get("codice_fiscale") or "").upper())
    rcf=re.sub(r"[^A-Z0-9]","",str(right.get("codice_fiscale") or "").upper())
    lp=_norm(left.get("person_name") or "")
    rp=_norm(right.get("person_name") or "")
    same_person=bool(lcf and rcf and lcf==rcf) or bool(lp and rp and lp==rp)
    if not same_person:
        return False,min(lc,rc),"persona non coincidente"
    lk=str(left.get("semantic_key") or "").strip()
    rk=str(right.get("semantic_key") or "").strip()
    if lk and rk and lk==rk:
        return True,min(lc,rc),"chiave semantica identica"
    return False,min(lc,rc),"chiave semantica differente"

def _semantic_duplicate_groups(conn, tid=None, max_comparisons=200):
    """Fast request-path duplicate scan.
    Never performs live multimodal/OpenAI comparisons. It uses exact SHA-256
    or already-cached semantic analyses. Expensive document understanding happens
    at ingestion time, not while the user waits for a chat reply.
    """
    if not _table(conn,"documenti"):
        return [],0
    rows=_visible_docs(conn,int(tid)) if tid else conn.execute(
        "SELECT * FROM documenti"+(" WHERE coalesce(visibile,1)=1" if "visibile" in _cols(conn,"documenti") else "")+
        " ORDER BY tesserato_id,id"
    ).fetchall()
    buckets={}
    for row in rows:
        athlete_id=int(row["tesserato_id"] or 0) if "tesserato_id" in row.keys() else 0
        if athlete_id<=0:
            continue
        kind=_canonical_document_kind(row)
        # R56 invariant: comparisons happen only inside same-person + same-type buckets.
        buckets.setdefault((athlete_id,kind),[]).append(row)
    groups=[]; comparisons=0
    for (athlete_id,kind),items in buckets.items():
        if len(items)<2:
            continue
        def _rank(row):
            st=_norm(row["status"]) if "status" in row.keys() else ""
            verified=1 if st in ("verified","verificato","ok","approved","completo","salvato") else 0
            try: conf=float(row["confidence"] or 0) if "confidence" in row.keys() else 0
            except Exception: conf=0
            return (verified,conf,-int(row["id"]))
        keepers=[]
        for row in sorted(items,key=_rank,reverse=True):
            name,data,_=_document_bytes_from_row(row)
            if not data:
                keepers.append(row); continue
            sha=_docsem_sha256(data)
            analysis=None
            match=None
            for keep in keepers:
                if comparisons>=max_comparisons:
                    break
                kname,kdata,_=_document_bytes_from_row(keep)
                if not kdata:
                    continue
                comparisons+=1
                ksha=_docsem_sha256(kdata)
                if sha==ksha:
                    match=(keep,{"confidence":1.0,"reason":"contenuto identico SHA-256","method":"sha256"})
                    break
                if analysis is None:
                    analysis=_cached_doc_analysis(conn,row,name,data)
                kanalysis=_cached_doc_analysis(conn,keep,kname,kdata)
                same,conf,reason=_cached_same_document(analysis,kanalysis)
                if same:
                    match=(keep,{"confidence":conf,"reason":reason,"method":"semantic_cache"})
                    break
            if match:
                keep,cmp=match
                athlete=conn.execute("SELECT nome,cognome FROM tesserati WHERE id=?",(athlete_id,)).fetchone()
                groups.append({
                    "tesserato_id":athlete_id,
                    "athlete_name":_athlete_name(athlete) if athlete else ("Tesserato "+str(athlete_id)),
                    "document_kind":kind,
                    "keep_id":int(keep["id"]),
                    "remove_ids":[int(row["id"])],
                    "confidence":float(cmp.get("confidence") or 0),
                    "reason":str(cmp.get("reason") or ""),
                    "comparison_method":str(cmp.get("method") or "semantic_cache"),
                })
            else:
                keepers.append(row)
    return groups,comparisons

def _revalidate_semantic_duplicate_group(conn, group):
    """Second safety gate before archive; deterministic and bounded."""
    try:
        keep_id=int(group.get("keep_id") or 0)
        remove_id=int((group.get("remove_ids") or [0])[0] or 0)
    except Exception:
        return False,"identificativi non validi"
    if keep_id<=0 or remove_id<=0 or keep_id==remove_id:
        return False,"identificativi non validi"
    keep=conn.execute("SELECT * FROM documenti WHERE id=?",(keep_id,)).fetchone()
    rem=conn.execute("SELECT * FROM documenti WHERE id=?",(remove_id,)).fetchone()
    if not keep or not rem:
        return False,"uno dei documenti non esiste più"
    if int(keep["tesserato_id"] or 0)!=int(rem["tesserato_id"] or 0):
        return False,"documenti associati a persone diverse"
    if _canonical_document_kind(keep)!=_canonical_document_kind(rem):
        return False,"tipi documentali diversi"
    kname,kdata,_=_document_bytes_from_row(keep)
    rname,rdata,_=_document_bytes_from_row(rem)
    if not kdata or not rdata:
        return False,"file fisico non leggibile"
    if _docsem_sha256(kdata)==_docsem_sha256(rdata):
        return True,"contenuto identico SHA-256"
    left=_cached_doc_analysis(conn,keep,kname,kdata)
    right=_cached_doc_analysis(conn,rem,rname,rdata)
    same,conf,reason=_cached_same_document(left,right)
    if same and conf>=.95:
        return True,reason
    return False,reason or "confronto non abbastanza certo"
'''
s=s[:start]+replacement+s[end:]

old_scope='''    if ("document" in n or "dossier" in n) and any(x in n for x in ("duplicat","doppion")):'''
new_scope='''    if any(x in n for x in ("document","dossier","certificat","modulo","mu ")) and any(x in n for x in ("duplicat","doppion")):'''
if old_scope not in s:
    raise RuntimeError('R56 duplicate scope anchor missing')
s=s.replace(old_scope,new_scope,1)

old='''        want_cleanup=any(x in n for x in ("elimina","eliminare","rimuovi","rimuovere","cancella","cancellare","pulisci","pulire"))'''
new='''        want_cleanup=any(x in n for x in (
            "elimina","eliminare","rimuovi","rimuovere","cancella","cancellare","pulisci","pulire",
            "lascia solo","lasciato solo","lasciato solamente","lasciare solo","mantieni solo",
            "uno solo per atleta","una sola per atleta","solamente uno","solamente una"
        ))'''
if old not in s:
    raise RuntimeError('R56 cleanup-intent anchor missing')
s=s.replace(old,new,1)

old='''        backup_dir=Path("/data/operator_backups")
        backup_dir.mkdir(parents=True,exist_ok=True)
        backup_file=backup_dir/(datetime.now().strftime("%Y%m%d_%H%M%S")+"_semantic_duplicates_"+str(aid)+".db")
        db_path=Path("/data/tenants/default/asd.db")
        if db_path.exists():
            shutil.copy2(db_path,backup_file)'''
new='''        backup_path=_operator_db_backup("semantic_duplicates_"+str(aid))
        backup_file=Path(backup_path) if backup_path else Path("/data/operator_backups/no_backup")'''
if old not in s:
    raise RuntimeError('R56 semantic backup anchor missing')
s=s.replace(old,new,1)

old='''      async function ask(q){{
        q=String(q||'').trim();if(!q)return;
        addMsg(q,'me');input.value='';send.disabled=true;'''
old_upload='''      let uploadInFlight=false;

      async function ask(q){{
        q=String(q||'').trim();if(!q)return;
        if(uploadInFlight){{
          addMsg(q,'me');input.value='';
          const t='Il file è ancora in trasferimento o in analisi sul server BodyMind. Ti confermo l’esito appena il server termina; non considero ancora il caricamento completato.';
          addMsg(t,'bot');if(voiceStageOpen)setVoiceStage('Caricamento in corso',t);speak(t);return;
        }}
        addMsg(q,'me');input.value='';send.disabled=true;'''
new='''      let askInFlight=false;
      async function ask(q){{
        q=String(q||'').trim();if(!q)return;
        if(askInFlight){{
          if(voiceStageOpen)setVoiceStage('Sto ancora lavorando','Attendi la risposta precedente.','Evito richieste sovrapposte che rallentano il gestionale.');
          return;
        }}
        askInFlight=true;
        addMsg(q,'me');input.value='';send.disabled=true;'''
new_upload='''      let uploadInFlight=false;
      let askInFlight=false;

      async function ask(q){{
        q=String(q||'').trim();if(!q)return;
        if(uploadInFlight){{
          addMsg(q,'me');input.value='';
          const t='Il file è ancora in trasferimento o in analisi sul server BodyMind. Ti confermo l’esito appena il server termina; non considero ancora il caricamento completato.';
          addMsg(t,'bot');if(voiceStageOpen)setVoiceStage('Caricamento in corso',t);speak(t);return;
        }}
        if(askInFlight){{
          if(voiceStageOpen)setVoiceStage('Sto ancora lavorando','Attendi la risposta precedente.','Evito richieste sovrapposte che rallentano il gestionale.');
          return;
        }}
        askInFlight=true;
        addMsg(q,'me');input.value='';send.disabled=true;'''
if old_upload in s:
    s=s.replace(old_upload,new_upload,1)
elif old in s:
    s=s.replace(old,new,1)
elif 'let askInFlight=false;' not in s:
    raise RuntimeError('R56 ask anchor missing')

old='''        }}catch(err){{
          const t='Non riesco a contattare il motore dell’Operatore in questo momento. Non ho modificato nulla.';
          addMsg(t,'bot');
          if(voiceStageOpen)setVoiceStage('Connessione non disponibile',t);
        }}finally{{send.disabled=false;input.focus()}}'''
old_r73='''        }}catch(err){{
          const t='Non riesco a contattare il motore dell’Operatore in questo momento. Non ho modificato nulla.';
          addMsg(t,'bot');
          if(voiceStageOpen)setVoiceStage('Connessione non disponibile',t);
        }}finally{{send.disabled=false;input.focus();setTimeout(bodymindKeepComposerVisible,80)}}'''
new='''        }}catch(err){{
          const online=!!navigator.onLine;
          const t=online
            ? 'La richiesta non si è completata correttamente. Il gestionale è raggiungibile, ma questa operazione ha avuto un errore o ha impiegato troppo tempo. Non ho applicato modifiche non confermate.'
            : 'La connessione del dispositivo è assente. Non ho applicato modifiche non confermate.';
          addMsg(t,'bot');
          if(voiceStageOpen)setVoiceStage(online?'Richiesta interrotta':'Connessione non disponibile',t);
        }}finally{{askInFlight=false;send.disabled=false;input.focus()}}'''
new_r73='''        }}catch(err){{
          const online=!!navigator.onLine;
          const t=online
            ? 'La richiesta non si è completata correttamente. Il gestionale è raggiungibile, ma questa operazione ha avuto un errore o ha impiegato troppo tempo. Non ho applicato modifiche non confermate.'
            : 'La connessione del dispositivo è assente. Non ho applicato modifiche non confermate.';
          addMsg(t,'bot');
          if(voiceStageOpen)setVoiceStage(online?'Richiesta interrotta':'Connessione non disponibile',t);
        }}finally{{askInFlight=false;send.disabled=false;input.focus();setTimeout(bodymindKeepComposerVisible,80)}}'''
if old_r73 in s:
    s=s.replace(old_r73,new_r73,1)
elif old in s:
    s=s.replace(old,new,1)
else:
    raise RuntimeError('R56 frontend error anchor missing')

P.write_text(s,encoding='utf-8')
py_compile.compile(str(P),doraise=True)
print('[operator-r56] PASS fast-bounded-dedupe no-live-ai-in-request cleanup-intent serialized-chat sqlite-backup',flush=True)
