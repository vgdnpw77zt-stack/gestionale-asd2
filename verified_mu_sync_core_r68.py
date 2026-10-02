# -*- coding: utf-8 -*-
from __future__ import annotations
import hashlib, re
from datetime import date, datetime
from pathlib import Path

def _norm(v):
    s=str(v or "").strip().lower()
    s=re.sub(r"\s+"," ",s)
    return re.sub(r"[^a-z0-9àèéìòù ]+","",s)

def _cols(conn,table):
    try:
        return {str(r[1]) for r in conn.execute("PRAGMA table_info("+table+")").fetchall()}
    except Exception:
        return set()

def _table(conn,name):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())

def _read_path(stored):
    raw=str(stored or "").strip()
    if not raw:
        return b""
    p=Path(raw)
    candidates=[p]
    if not p.is_absolute():
        candidates += [
            Path("/data/tenants/default/media")/raw.lstrip("/"),
            Path("/data")/raw.lstrip("/"),
        ]
    for q in candidates:
        try:
            if q.is_file():
                return q.read_bytes()
        except Exception:
            pass
    return b""

def _row_bytes(row):
    if not row:
        return "",b""
    keys=set(row.keys())
    name=""
    for k in ("original_filename","filename","titolo"):
        if k in keys and row[k]:
            name=str(row[k]); break
    for k in ("saved_path","stored_path","path","filename"):
        if k in keys and row[k]:
            data=_read_path(row[k])
            if data:
                return name or Path(str(row[k])).name,data
    return name,b""

def _semantic(conn,source_table,source_id,row,record_usage=None,allow_live=True):
    name,data=_row_bytes(row)
    if not data:
        return None,"no_file"
    sha=hashlib.sha256(data).hexdigest()
    try:
        from .operator_doc_semantic_core_r52 import cache_get
        cached=cache_get(conn,source_table,int(source_id),sha)
        if isinstance(cached,dict):
            return cached,"cache"
    except Exception:
        pass
    if not allow_live:
        return None,"no_cache"
    try:
        from .operator_doc_semantic_ai_r52 import analyze_bytes
        analysis=analyze_bytes(conn,name,data,"","modulo_unico_tesseramento",record_usage)
        return (analysis if isinstance(analysis,dict) else None),"live"
    except Exception as exc:
        return None,"analysis_error:"+repr(exc)[:180]

def _identity_matches(target,analysis):
    if not target or not isinstance(analysis,dict):
        return False,"missing"
    tk=set(target.keys())
    target_cf=re.sub(r"[^A-Z0-9]","",str(target["codice_fiscale"] or "").upper()) if "codice_fiscale" in tk else ""
    ai_cf=re.sub(r"[^A-Z0-9]","",str(analysis.get("codice_fiscale") or "").upper())
    if target_cf and ai_cf:
        return (target_cf==ai_cf),"cf"
    tn=_norm(target["nome"] if "nome" in tk else "")
    tc=_norm(target["cognome"] if "cognome" in tk else "")
    an=_norm(analysis.get("first_name"))
    ac=_norm(analysis.get("last_name"))
    if tn and tc and an and ac:
        return (tn==an and tc==ac),"name"
    person=_norm(analysis.get("person_name"))
    if tn and tc and person:
        ok=(tn in person and tc in person)
        return ok,"person_name"
    return False,"insufficient_identity"

def _iso(v):
    raw=str(v or "").strip()[:10]
    for fmt in ("%Y-%m-%d","%d/%m/%Y","%d-%m-%Y","%d.%m.%Y"):
        try: return datetime.strptime(raw,fmt).date().isoformat()
        except Exception: pass
    return ""

def _age(birth):
    d=_iso(birth)
    if not d: return None
    born=date.fromisoformat(d); today=date.today()
    return today.year-born.year-((today.month,today.day)<(born.month,born.day))

def _fill_empty(conn,table,row_id,mapping):
    cols=_cols(conn,table)
    row=conn.execute("SELECT * FROM "+table+" WHERE id=?",(int(row_id),)).fetchone()
    if not row:
        return {}
    keys=set(row.keys()); changed={}
    sets=[]; vals=[]
    for col,val in mapping.items():
        if col not in cols or col not in keys:
            continue
        if val is None: continue
        if isinstance(val,str): val=val.strip()
        if val in ("",None): continue
        current=row[col]
        empty=(current is None or str(current).strip()=="" or (isinstance(current,(int,float)) and current==0 and col=="minorenne"))
        if not empty:
            continue
        sets.append(col+"=?"); vals.append(val); changed[col]=val
    if sets:
        vals.append(int(row_id))
        conn.execute("UPDATE "+table+" SET "+",".join(sets)+" WHERE id=?",tuple(vals))
    return changed

def _ensure_minor(conn,tid,target,analysis):
    if not _table(conn,"minori"):
        return None,{}
    mcols=_cols(conn,"minori")
    existing=conn.execute("SELECT * FROM minori WHERE tesserato_id=? LIMIT 1",(int(tid),)).fetchone() if "tesserato_id" in mcols else None
    guardian=str(analysis.get("guardian_name") or "").strip()
    if not existing:
        age=_age(analysis.get("birth_date") or (target["data_nascita"] if "data_nascita" in target.keys() else ""))
        target_minor=int(target["minorenne"] or 0)==1 if "minorenne" in target.keys() else False
        if not guardian or not (target_minor or (age is not None and age<18)):
            return None,{}
        values={}
        if "tesserato_id" in mcols: values["tesserato_id"]=int(tid)
        for col,key in (
          ("nome","first_name"),("cognome","last_name"),("genitore","guardian_name"),
          ("nome_genitore","guardian_name"),("telefono_genitore","guardian_phone"),
          ("email_genitore","guardian_email")
        ):
            v=str(analysis.get(key) or "").strip()
            if col in mcols and v: values[col]=v
        now=datetime.now().isoformat(timespec="seconds")
        if "created_at" in mcols: values["created_at"]=now
        if "updated_at" in mcols: values["updated_at"]=now
        info=conn.execute("PRAGMA table_info(minori)").fetchall()
        for r in info:
            col=str(r[1]); typ=str(r[2] or "").upper(); notnull=bool(r[3]); default=r[4]; pk=bool(r[5])
            if pk or col in values or not notnull or default is not None: continue
            values[col]=0 if any(x in typ for x in ("INT","REAL","NUM")) else ""
        if "tesserato_id" not in values:
            return None,{}
        cols=list(values)
        cur=conn.execute("INSERT INTO minori ("+",".join(cols)+") VALUES ("+",".join("?" for _ in cols)+")",tuple(values[c] for c in cols))
        existing=conn.execute("SELECT * FROM minori WHERE id=?",(int(cur.lastrowid),)).fetchone()
    if not existing:
        return None,{}
    mapping={
      "genitore":str(analysis.get("guardian_name") or "").strip(),
      "nome_genitore":str(analysis.get("guardian_name") or "").strip(),
      "telefono_genitore":str(analysis.get("guardian_phone") or "").strip(),
      "email_genitore":str(analysis.get("guardian_email") or "").strip(),
    }
    changed=_fill_empty(conn,"minori",int(existing["id"]),mapping)
    return int(existing["id"]),changed

def sync_analysis_to_existing_athlete(conn,tid,analysis,source="verified_mu"):
    if not isinstance(analysis,dict):
        return {"ok":False,"reason":"analysis_missing"}
    if str(analysis.get("document_type") or "")!="modulo_unico_tesseramento":
        return {"ok":False,"reason":"not_mu"}
    try: conf=float(analysis.get("confidence") or 0)
    except Exception: conf=0.0
    if conf<.95:
        return {"ok":False,"reason":"low_confidence","confidence":conf}
    if str(analysis.get("handwriting_legibility") or "unknown")=="poor":
        return {"ok":False,"reason":"poor_handwriting","confidence":conf}
    target=conn.execute("SELECT * FROM tesserati WHERE id=?",(int(tid),)).fetchone()
    if not target:
        return {"ok":False,"reason":"athlete_missing"}
    match,why=_identity_matches(target,analysis)
    if not match:
        return {"ok":False,"reason":"identity_mismatch","identity_check":why,"confidence":conf}

    age=_age(analysis.get("birth_date"))
    mapping={
      "codice_fiscale":re.sub(r"[^A-Z0-9]","",str(analysis.get("codice_fiscale") or "").upper()),
      "data_nascita":_iso(analysis.get("birth_date")),
      "luogo_nascita":str(analysis.get("birth_place") or "").strip(),
      "indirizzo":str(analysis.get("address") or "").strip(),
      "citta":str(analysis.get("city") or "").strip(),
      "comune":str(analysis.get("city") or "").strip(),
      "cap":str(analysis.get("postal_code") or "").strip(),
      "provincia":str(analysis.get("province") or "").strip(),
      "telefono":str(analysis.get("phone") or "").strip(),
      "cellulare":str(analysis.get("phone") or "").strip(),
      "email":str(analysis.get("email") or "").strip(),
      "genitore":str(analysis.get("guardian_name") or "").strip(),
      "nome_genitore":str(analysis.get("guardian_name") or "").strip(),
      "telefono_genitore":str(analysis.get("guardian_phone") or "").strip(),
      "email_genitore":str(analysis.get("guardian_email") or "").strip(),
      "minorenne":1 if age is not None and age<18 else None,
    }
    changed=_fill_empty(conn,"tesserati",int(tid),mapping)
    minor_id,minor_changed=_ensure_minor(conn,int(tid),target,analysis)

    try:
        from .onboarding_flow import sync_unified_module_flags, recompute_onboarding_status
        sync_unified_module_flags(conn,int(tid),source=source)
        recompute_onboarding_status(conn,int(tid))
    except Exception:
        pass
    return {
      "ok":True,"tesserato_id":int(tid),"confidence":conf,"identity_check":why,
      "fields_filled":sorted(changed.keys()),"minor_id":minor_id,
      "minor_fields_filled":sorted(minor_changed.keys()),
    }

def sync_verified_mu_inbound(conn,row,record_usage=None,allow_live=True):
    if not row:
        return {"ok":False,"reason":"row_missing"}
    keys=set(row.keys())
    dtype=str(row["document_type"] or "") if "document_type" in keys else ""
    aliases={"modulo_unico_tesseramento","iscrizione","domanda_iscrizione","manleva","liberatoria_immagini","consenso_minore","autorizzazione_genitore","privacy","privacy_consenso","safeguarding","tutela_minore"}
    if dtype not in aliases:
        return {"ok":False,"reason":"not_mu"}
    tid=int(row["tesserato_id"] or 0) if "tesserato_id" in keys else 0
    if tid<=0:
        return {"ok":False,"reason":"no_athlete"}
    analysis,method=_semantic(conn,"inbound_documents",int(row["id"]),row,record_usage,allow_live=allow_live)
    result=sync_analysis_to_existing_athlete(conn,tid,analysis,source="verified_mu_inbound")
    result["semantic_method"]=method
    return result

def sync_verified_mu_document(conn,row,tid,record_usage=None,allow_live=True):
    if not row or int(tid or 0)<=0:
        return {"ok":False,"reason":"row_or_athlete_missing"}
    keys=set(row.keys())
    hay=" ".join(str(row[k] or "").lower() for k in ("doc_type","categoria","titolo","original_filename","filename") if k in keys)
    if not any(x in hay for x in ("modulo_unico","modulo unico","modulo iscrizione","iscrizione")):
        return {"ok":False,"reason":"not_mu"}
    analysis,method=_semantic(conn,"documenti",int(row["id"]),row,record_usage,allow_live=allow_live)
    result=sync_analysis_to_existing_athlete(conn,int(tid),analysis,source="verified_mu_document")
    result["semantic_method"]=method
    return result
