from __future__ import annotations

import json
import os
import re
import sqlite3
import hashlib
import ast
import inspect
import shutil
import unicodedata
import uuid
import base64
import smtplib
import ssl
import time
from email.message import EmailMessage
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

from flask import Response, jsonify, redirect, request, session, send_file

from .core import (
    app, db, layout, login_required, csrf_token, current_username, current_role, e
)
from .operator_doc_semantic_core_r52 import (
    ensure_schema as _docsem_ensure_schema,
    sha256_bytes as _docsem_sha256,
    cache_get as _docsem_cache_get,
    cache_put as _docsem_cache_put,
)
from .operator_doc_semantic_ai_r52 import (
    analyze_bytes as _docsem_analyze_bytes,
    compare_bytes as _docsem_compare_bytes,
)

OPERATOR_VERSION = "R52.0-semantic-secretary"
PENDING_STATUSES = (
    "needs_manual_match","associato_tipo_da_verificare","richiede_conferma",
    "needs_review","da_verificare","pending",
)

# BODYMIND_R46_CLOUD_NATIVE_SECRETARY
_CLOUD_LAST_ERROR=""
_CLOUD_LAST_OK_AT=""


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r"[^a-zA-Z0-9àèéìòù' -]+", " ", value).lower()
    return re.sub(r"\s+", " ", value).strip()


def _table(conn, name: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone())


def _cols(conn, name: str) -> set[str]:
    if not _table(conn, name):
        return set()
    return {str(r[1]) for r in conn.execute(f"PRAGMA table_info({name})").fetchall()}


def _schema(conn) -> None:
    conn.execute("""
      CREATE TABLE IF NOT EXISTS bodymind_operator_messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT NOT NULL,
        speaker TEXT NOT NULL,
        identity_name TEXT,
        message TEXT NOT NULL,
        payload_json TEXT,
        created_at TEXT NOT NULL
      )
    """)
    conn.execute("""
      CREATE TABLE IF NOT EXISTS bodymind_operator_actions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT NOT NULL,
        action_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'proposed',
        requested_by TEXT,
        confirmed_by TEXT,
        created_at TEXT NOT NULL,
        executed_at TEXT
      )
    """)
    conn.execute("""
      CREATE TABLE IF NOT EXISTS bodymind_operator_facts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject_type TEXT NOT NULL,
        subject_id INTEGER,
        fact_key TEXT NOT NULL,
        fact_value TEXT,
        note TEXT,
        created_by TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(subject_type,subject_id,fact_key)
      )
    """)
    conn.execute("""
      CREATE TABLE IF NOT EXISTS bodymind_ai_usage(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,
        model TEXT,
        input_tokens INTEGER NOT NULL DEFAULT 0,
        output_tokens INTEGER NOT NULL DEFAULT 0,
        seconds REAL NOT NULL DEFAULT 0,
        estimated_usd REAL NOT NULL DEFAULT 0,
        request_id TEXT,
        created_at TEXT NOT NULL
      )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bodymind_ai_usage_created ON bodymind_ai_usage(created_at)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_bodymind_ai_usage_request ON bodymind_ai_usage(request_id) WHERE request_id IS NOT NULL")
    _docsem_ensure_schema(conn)
    conn.execute("""
      CREATE TABLE IF NOT EXISTS bodymind_secure_settings(
        setting_key TEXT PRIMARY KEY,
        value_enc TEXT NOT NULL,
        meta_json TEXT,
        updated_at TEXT NOT NULL,
        updated_by TEXT
      )
    """)
    conn.execute("""
      CREATE TABLE IF NOT EXISTS bodymind_email_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipient TEXT NOT NULL,
        subject TEXT,
        status TEXT NOT NULL,
        error TEXT,
        sent_by TEXT,
        created_at TEXT NOT NULL
      )
    """)
    conn.commit()


# BODYMIND_R47_AI_BUDGET_METER
_TEXT_PRICING_PER_MTOK={
    "gpt-6-luna":(0.10,0.50),
    "gpt-6.1-sol":(2.00,10.00),
    "gpt-6-sol":(2.00,10.00),
    "gpt-6-astra":(10.00,50.00),
}
_STT_USD_PER_MIN={"gpt-transcribe":0.0045}
_TTS_EST_USD_PER_MIN={"gpt-4o-mini-tts":0.015}

def _budget_start():
    return str(os.environ.get("BODYMIND_AI_BUDGET_START") or "1970-01-01T00:00:00").strip()

def _budget_usd():
    try:
        return max(0.01,float(os.environ.get("BODYMIND_AI_BUDGET_USD") or "5"))
    except Exception:
        return 5.0

def _record_ai_usage(conn,kind,model="",input_tokens=0,output_tokens=0,seconds=0.0,estimated_usd=0.0,request_id=None):
    _schema(conn)
    rid=str(request_id or "").strip() or None
    try:
        conn.execute(
            """INSERT INTO bodymind_ai_usage(kind,model,input_tokens,output_tokens,seconds,estimated_usd,request_id,created_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (str(kind),str(model or ""),int(input_tokens or 0),int(output_tokens or 0),float(seconds or 0),float(estimated_usd or 0),rid,datetime.now().isoformat(timespec="seconds"))
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass

def _record_response_usage(conn,resp,model,kind="planner"):
    usage=getattr(resp,"usage",None)
    inp=int(getattr(usage,"input_tokens",0) or 0) if usage is not None else 0
    out=int(getattr(usage,"output_tokens",0) or 0) if usage is not None else 0
    rates=_TEXT_PRICING_PER_MTOK.get(str(model),(0.10,0.50))
    usd=(inp/1000000.0)*rates[0]+(out/1000000.0)*rates[1]
    rid=str(getattr(resp,"id","") or "") or None
    _record_ai_usage(conn,kind,model,inp,out,0.0,usd,rid)

def _usage_summary(conn):
    _schema(conn)
    start=_budget_start()
    row=conn.execute(
        """SELECT coalesce(sum(estimated_usd),0),coalesce(sum(input_tokens),0),coalesce(sum(output_tokens),0),
                  coalesce(sum(CASE WHEN kind='stt' THEN seconds ELSE 0 END),0),
                  coalesce(sum(CASE WHEN kind='tts' THEN seconds ELSE 0 END),0)
           FROM bodymind_ai_usage WHERE created_at>=?""",(start,)
    ).fetchone()
    spent=float(row[0] or 0)
    budget=_budget_usd()
    pct=(spent/budget*100.0) if budget else 0.0
    if pct>=100: level="critical"
    elif pct>=90: level="high"
    elif pct>=70: level="warning"
    else: level="ok"
    exhausted=any(x in str(_CLOUD_LAST_ERROR or "").lower() for x in ("credit_balance_exhausted","insufficient_quota","no credits remaining"))
    if exhausted:
        level="exhausted"
    return {
        "budget_usd":round(budget,4),
        "estimated_spent_usd":round(spent,4),
        "estimated_remaining_usd":round(max(0.0,budget-spent),4),
        "percent":round(pct,1),
        "level":level,
        "exhausted":exhausted,
        "input_tokens":int(row[1] or 0),
        "output_tokens":int(row[2] or 0),
        "stt_seconds":round(float(row[3] or 0),1),
        "tts_seconds":round(float(row[4] or 0),1),
        "start":start,
        "estimate":True,
    }


def _secret_box():
    from cryptography.fernet import Fernet
    direct=str(os.environ.get("BODYMIND_VAULT_KEY") or "").strip()
    if direct:
        return Fernet(direct.encode("ascii"))
    root=str(os.environ.get("ASD_SECRET_KEY") or "").strip()
    if not root:
        raise RuntimeError("BODYMIND_VAULT_KEY/ASD_SECRET_KEY non configurata")
    key=base64.urlsafe_b64encode(hashlib.sha256(root.encode("utf-8")).digest())
    return Fernet(key)

def _secure_setting_get(conn,key):
    _schema(conn)
    row=conn.execute("SELECT value_enc,meta_json,updated_at,updated_by FROM bodymind_secure_settings WHERE setting_key=?",(str(key),)).fetchone()
    if not row:
        return None,{}
    try:
        raw=_secret_box().decrypt(str(row["value_enc"]).encode("utf-8")).decode("utf-8")
        value=json.loads(raw)
    except Exception:
        return None,{}
    try:
        meta=json.loads(str(row["meta_json"] or "{}"))
    except Exception:
        meta={}
    meta["updated_at"]=str(row["updated_at"] or "")
    meta["updated_by"]=str(row["updated_by"] or "")
    return value,meta

def _secure_setting_set(conn,key,value,meta=None):
    _schema(conn)
    payload=json.dumps(value,ensure_ascii=False,separators=(",",":")).encode("utf-8")
    token=_secret_box().encrypt(payload).decode("utf-8")
    now=datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """INSERT INTO bodymind_secure_settings(setting_key,value_enc,meta_json,updated_at,updated_by)
           VALUES(?,?,?,?,?)
           ON CONFLICT(setting_key) DO UPDATE SET
             value_enc=excluded.value_enc,meta_json=excluded.meta_json,
             updated_at=excluded.updated_at,updated_by=excluded.updated_by""",
        (str(key),token,json.dumps(meta or {},ensure_ascii=False),now,_identity())
    )
    conn.commit()

def _smtp_public_status(conn):
    cfg,meta=_secure_setting_get(conn,"smtp")
    if not isinstance(cfg,dict):
        return {"configured":False,"provider":"","host":"","port":0,"username":"","security":"","last_test_ok":False,"last_test_at":""}
    username=str(cfg.get("username") or "")
    masked=username
    if "@" in username:
        local,domain=username.split("@",1)
        masked=(local[:2]+"***@"+domain) if local else ("***@"+domain)
    return {
        "configured":bool(cfg.get("host") and cfg.get("port") and cfg.get("username") and cfg.get("password")),
        "provider":str(cfg.get("provider") or ""),
        "host":str(cfg.get("host") or ""),
        "port":int(cfg.get("port") or 0),
        "username":masked,
        "security":str(cfg.get("security") or ""),
        "from_name":str(cfg.get("from_name") or ""),
        "last_test_ok":bool(meta.get("last_test_ok")),
        "last_test_at":str(meta.get("last_test_at") or ""),
        "last_test_error":str(meta.get("last_test_error") or "")[:180],
    }

def _smtp_test_connection(cfg):
    host=str(cfg.get("host") or "").strip()
    port=int(cfg.get("port") or 0)
    username=str(cfg.get("username") or "").strip()
    password=str(cfg.get("password") or "")
    security=str(cfg.get("security") or "starttls").strip().lower()
    if not host or not port or not username or not password:
        raise RuntimeError("Configurazione SMTP incompleta")
    if security=="ssl":
        client=smtplib.SMTP_SSL(host,port,timeout=12,context=ssl.create_default_context())
    else:
        client=smtplib.SMTP(host,port,timeout=12)
    try:
        client.ehlo()
        if security=="starttls":
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
        client.login(username,password)
        try: client.noop()
        except Exception: pass
    finally:
        try: client.quit()
        except Exception: 
            try: client.close()
            except Exception: pass
    return True

def _smtp_send_message(conn,recipient,subject,body):
    cfg,_meta=_secure_setting_get(conn,"smtp")
    if not isinstance(cfg,dict):
        raise RuntimeError("SMTP non configurato")
    host=str(cfg.get("host") or "").strip()
    port=int(cfg.get("port") or 0)
    username=str(cfg.get("username") or "").strip()
    password=str(cfg.get("password") or "")
    security=str(cfg.get("security") or "starttls").strip().lower()
    from_name=str(cfg.get("from_name") or "BodyMind Aerial Studio").strip()
    if not host or not port or not username or not password:
        raise RuntimeError("Configurazione SMTP incompleta")
    msg=EmailMessage()
    msg["From"]=(from_name+" <"+username+">") if from_name else username
    msg["To"]=str(recipient).strip()
    msg["Subject"]=str(subject or "").strip()
    msg.set_content(str(body or ""))
    client=None
    try:
        if security=="ssl":
            client=smtplib.SMTP_SSL(host,port,timeout=20,context=ssl.create_default_context())
        else:
            client=smtplib.SMTP(host,port,timeout=20)
        client.ehlo()
        if security=="starttls":
            client.starttls(context=ssl.create_default_context()); client.ehlo()
        client.login(username,password)
        client.send_message(msg)
        conn.execute("INSERT INTO bodymind_email_log(recipient,subject,status,error,sent_by,created_at) VALUES(?,?,?,?,?,?)",
                     (str(recipient).strip(),str(subject or "")[:240],"sent","",_identity(),datetime.now().isoformat(timespec="seconds")))
        conn.commit()
        return True
    except Exception as exc:
        try:
            conn.execute("INSERT INTO bodymind_email_log(recipient,subject,status,error,sent_by,created_at) VALUES(?,?,?,?,?,?)",
                         (str(recipient).strip(),str(subject or "")[:240],"failed",repr(exc)[:500],_identity(),datetime.now().isoformat(timespec="seconds")))
            conn.commit()
        except Exception:
            pass
        raise
    finally:
        if client is not None:
            try: client.quit()
            except Exception:
                try: client.close()
                except Exception: pass

def _conv_id() -> str:
    cid = str(session.get("bodymind_operator_conversation") or "").strip()
    if not cid:
        cid = uuid.uuid4().hex
        session["bodymind_operator_conversation"] = cid
    return cid


def _identity() -> str:
    spoken = str(session.get("bodymind_operator_identity") or "").strip()
    if spoken:
        return spoken
    display = str(session.get("display_name") or "").strip()
    if display:
        return display.split()[0]
    user = str(session.get("username") or current_username() or "Operatore").strip()
    if user.lower() == "admin":
        conn = db()
        try:
            if _table(conn, "users"):
                row = conn.execute(
                    "SELECT full_name FROM users WHERE username=? LIMIT 1", (user,)
                ).fetchone()
                if row and str(row["full_name"] or "").strip():
                    return str(row["full_name"]).strip().split()[0]
        finally:
            conn.close()
    return user.split()[0] if user else "Operatore"


def _log(conn, speaker: str, message: str, payload=None) -> None:
    _schema(conn)
    conn.execute(
        """INSERT INTO bodymind_operator_messages
           (conversation_id,speaker,identity_name,message,payload_json,created_at)
           VALUES(?,?,?,?,?,?)""",
        (
            _conv_id(), speaker, _identity(), str(message or "")[:12000],
            json.dumps(payload or {}, ensure_ascii=False),
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()


def _athletes(conn):
    if not _table(conn, "tesserati"):
        return []
    return conn.execute(
        "SELECT * FROM tesserati ORDER BY cognome,nome"
    ).fetchall()


def _match_athlete(conn, text: str):
    q = _norm(text)
    rows = _athletes(conn)
    exact = []
    surname = []
    scored = []
    for row in rows:
        nome = _norm(row["nome"] if "nome" in row.keys() else "")
        cognome = _norm(row["cognome"] if "cognome" in row.keys() else "")
        full = (nome + " " + cognome).strip()
        rev = (cognome + " " + nome).strip()
        if full and (full in q or rev in q):
            exact.append(row)
            continue
        if cognome and re.search(r"(?<!\w)"+re.escape(cognome)+r"(?!\w)", q):
            surname.append(row)
            continue
        words = q.split()
        for width in (2,1):
            for i in range(0, max(0, len(words)-width+1)):
                part = " ".join(words[i:i+width])
                ratio = max(
                    SequenceMatcher(None, part, full).ratio() if full else 0,
                    SequenceMatcher(None, part, cognome).ratio() if cognome else 0,
                )
                if ratio >= .83:
                    scored.append((ratio,row))
    if len(exact)==1:
        return exact[0], []
    if len(exact)>1:
        return None, exact
    uniq_s = {int(r["id"]):r for r in surname}
    if len(uniq_s)==1:
        return next(iter(uniq_s.values())), []
    if len(uniq_s)>1:
        return None, list(uniq_s.values())
    scored.sort(key=lambda x:x[0], reverse=True)
    if scored:
        top=scored[0][0]
        best={int(r["id"]):r for score,r in scored if score >= top-.03}
        if top>=.88 and len(best)==1:
            return next(iter(best.values())), []
        if top>=.83:
            return None, list(best.values())[:5]
    return None, []


def _context_athlete(conn, text: str):
    tid=int(session.get("bodymind_operator_last_tesserato") or 0)
    if tid<=0:
        return None
    n=_norm(text)
    follow=("lei","lui","sua","suo","quanto paga","il certificato","il modulo","la quota","i pagamenti","la ricevuta","cosa manca","e invece")
    if not any(x in n for x in follow):
        return None
    return conn.execute("SELECT * FROM tesserati WHERE id=?",(tid,)).fetchone()

def _athlete_name(row) -> str:
    return (str(row["nome"] or "")+" "+str(row["cognome"] or "")).strip()


def _visible_docs(conn, tid: int):
    if not _table(conn, "documenti"):
        return []
    dc=_cols(conn,"documenti")
    vis=" AND coalesce(visibile,1)=1" if "visibile" in dc else ""
    return conn.execute(
        "SELECT * FROM documenti WHERE tesserato_id=?"+vis+" ORDER BY id DESC",(tid,)
    ).fetchall()



def _document_file_candidates(stored: str):
    raw=str(stored or "").strip()
    if not raw:
        return []
    p=Path(raw)
    out=[p] if p.is_absolute() else []
    if not p.is_absolute():
        for root in (
            Path("/data/tenants/default/media"),
            Path("/data/top2_app/media"),
            Path("/data/top2_app/static"),
            Path("/data/user_static"),
        ):
            out.append(root/p)
    seen=[]; result=[]
    for x in out:
        sx=str(x)
        if sx not in seen:
            seen.append(sx); result.append(x)
    return result


def _document_fingerprint(row):
    filename=str(row["filename"] or "") if "filename" in row.keys() else ""
    for p in _document_file_candidates(filename):
        try:
            if p.is_file():
                h=hashlib.sha256()
                with p.open("rb") as fh:
                    while True:
                        chunk=fh.read(1024*1024)
                        if not chunk: break
                        h.update(chunk)
                return "sha256:"+h.hexdigest(), str(p)
        except Exception:
            pass
    # Exact same stored path is safe to treat as a duplicate DB reference.
    if filename:
        return "path:"+os.path.normpath(filename), filename
    return "", ""


# BODYMIND_R52_SEMANTIC_RUNTIME
def _document_bytes_from_row(row):
    stored=""
    for key in ("filename","saved_path","path"):
        if key in row.keys() and str(row[key] or "").strip():
            stored=str(row[key] or "").strip(); break
    for p in _document_file_candidates(stored):
        try:
            if p.is_file():
                data=p.read_bytes()
                if len(data)>40*1024*1024:
                    continue
                name=""
                for key in ("original_filename","filename"):
                    if key in row.keys() and str(row[key] or "").strip():
                        name=Path(str(row[key] or "")).name; break
                return name or p.name,data,str(p)
        except Exception:
            continue
    return "",b"",""

def _docsem_usage(conn,response,model,kind):
    _record_response_usage(conn,response,model,kind)

def _semantic_for_document_row(conn,row,source_table="documenti"):
    name,data,_path=_document_bytes_from_row(row)
    if not data:
        return None
    sha=_docsem_sha256(data)
    cached=_docsem_cache_get(conn,source_table,int(row["id"]),sha)
    if cached:
        return cached
    extracted=""
    try:
        from .routes_email_documents import extract_attachment_text
        extracted=str(extract_attachment_text(name,data) or "")
    except Exception:
        pass
    hint=_canonical_document_kind(row) if source_table=="documenti" else ""
    analysis=_docsem_analyze_bytes(conn,name,data,extracted,hint,_docsem_usage)
    _docsem_cache_put(conn,source_table,int(row["id"]),analysis)
    return analysis

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
            score=.94
            birth=str((analysis or {}).get("birth_date") or "")[:10]
            if birth and "data_nascita" in athlete.keys() and str(athlete["data_nascita"] or "")[:10]==birth:
                score=.99
            return athlete,score,"contenuto_documento"
    return None,0.0,""

def _semantic_for_new_bytes(conn,name,data,extracted_text="",type_hint=""):
    return _docsem_analyze_bytes(conn,name,data,extracted_text,type_hint,_docsem_usage)

def _semantic_same_pair(conn,name_a,data_a,analysis_a,name_b,data_b,analysis_b):
    return _docsem_compare_bytes(conn,name_a,data_a,analysis_a,name_b,data_b,analysis_b,_docsem_usage)

def _same_existing_document(conn,tid,name,data,analysis,max_candidates=8):
    wanted=_norm((analysis or {}).get("document_type") or "")
    for row in _visible_docs(conn,int(tid))[:80]:
        if wanted and _norm(_canonical_document_kind(row))!=wanted:
            continue
        ename,edata,_=_document_bytes_from_row(row)
        if not edata:
            continue
        if _docsem_sha256(edata)==_docsem_sha256(data):
            return {"duplicate":True,"existing_id":int(row["id"]),"confidence":1.0,"reason":"contenuto identico","method":"sha256"}
        existing=_semantic_for_document_row(conn,row,"documenti")
        if not existing:
            continue
        try:
            cmp=_semantic_same_pair(conn,name,data,analysis,ename,edata,existing)
        except Exception as exc:
            cmp={"same_document":False,"confidence":0.0,"reason":str(exc)[:120]}
        if bool(cmp.get("same_document")) and float(cmp.get("confidence") or 0)>=.95:
            return {
                "duplicate":True,"existing_id":int(row["id"]),"confidence":float(cmp.get("confidence") or 0),
                "reason":str(cmp.get("reason") or "stesso documento"),"method":str(cmp.get("method") or "multimodal")
            }
        max_candidates-=1
        if max_candidates<=0:
            break
    return {"duplicate":False,"existing_id":None,"confidence":0.0,"reason":"","method":""}

# BODYMIND_R52_SEMANTIC_DUPLICATES
def _semantic_duplicate_groups(conn, tid=None, max_comparisons=24):
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
        buckets.setdefault((athlete_id,_canonical_document_kind(row)),[]).append(row)
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
            match=None
            for keep in keepers:
                kname,kdata,_=_document_bytes_from_row(keep)
                if not kdata:
                    continue
                if _docsem_sha256(data)==_docsem_sha256(kdata):
                    cmp={"same_document":True,"confidence":1.0,"reason":"contenuto identico","method":"sha256"}
                else:
                    if comparisons>=max_comparisons:
                        break
                    left=_semantic_for_document_row(conn,row,"documenti")
                    right=_semantic_for_document_row(conn,keep,"documenti")
                    if not left or not right:
                        continue
                    comparisons+=1
                    try:
                        cmp=_semantic_same_pair(conn,name,data,left,kname,kdata,right)
                    except Exception:
                        cmp={"same_document":False,"confidence":0.0}
                if bool(cmp.get("same_document")) and float(cmp.get("confidence") or 0)>=.95:
                    match=(keep,cmp); break
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
                    "comparison_method":str(cmp.get("method") or "multimodal"),
                })
            else:
                keepers.append(row)
    return groups,comparisons


def _revalidate_semantic_duplicate_group(conn, group):
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
    left=_semantic_for_document_row(conn,keep,"documenti")
    right=_semantic_for_document_row(conn,rem,"documenti")
    if not left or not right:
        return False,"lettura semantica incompleta"
    try:
        cmp=_semantic_same_pair(conn,kname,kdata,left,rname,rdata,right)
    except Exception as exc:
        return False,"confronto semantico non disponibile: "+str(exc)[:120]
    if bool(cmp.get("same_document")) and float(cmp.get("confidence") or 0)>=.95:
        return True,str(cmp.get("reason") or "stesso documento")
    return False,str(cmp.get("reason") or "non abbastanza certo")


def _canonical_document_kind(row):
    parts=[]
    for key in ("doc_type","categoria","titolo","original_filename","filename"):
        if key in row.keys():
            parts.append(_norm(row[key]))
    hay=" ".join(parts)
    if any(x in hay for x in ("certificato_medico","certificato medico","certificato"," cm ","_cm_","cm.pdf","cm.jpg","cm.jpeg","cm.png")):
        return "certificato_medico"
    if any(x in hay for x in ("modulo_unico_tesseramento","modulo unico","modulo_unico","mu-2026","mu 2026","modulo iscrizione","domanda iscrizione","iscrizione manleva")):
        return "modulo_unico_tesseramento"
    dtype=_norm(row["doc_type"]) if "doc_type" in row.keys() else ""
    if dtype:
        return dtype
    cat=_norm(row["categoria"]) if "categoria" in row.keys() else ""
    return cat or "altro"


def _duplicate_document_groups(conn, tid=None):
    if not _table(conn,"documenti"):
        return []
    cols=_cols(conn,"documenti")
    if "id" not in cols or "tesserato_id" not in cols or "filename" not in cols:
        return []
    wanted=["id","tesserato_id","filename"]
    for col in ("original_filename","titolo","categoria","doc_type","visibile","status","confidence","source","data_caricamento"):
        if col in cols: wanted.append(col)
    where=[]
    vals=[]
    if "visibile" in cols:
        where.append("coalesce(visibile,1)=1")
    if tid:
        where.append("tesserato_id=?"); vals.append(int(tid))
    sql="SELECT "+",".join(wanted)+" FROM documenti"
    if where: sql+=" WHERE "+" AND ".join(where)
    sql+=" ORDER BY tesserato_id,id"
    rows=conn.execute(sql,tuple(vals)).fetchall()
    buckets={}
    for row in rows:
        fp,resolved=_document_fingerprint(row)
        if not fp: continue
        kind=_canonical_document_kind(row)
        key=(int(row["tesserato_id"] or 0),fp,kind)
        buckets.setdefault(key,[]).append((row,resolved))
    groups=[]
    for (athlete_id,fp,kind),items in buckets.items():
        if len(items)<2: continue
        def rank(item):
            row=item[0]
            status=_norm(row["status"]) if "status" in row.keys() else ""
            verified=1 if status in ("verified","verificato","ok","approved","completo") else 0
            confidence=int(row["confidence"] or 0) if "confidence" in row.keys() and str(row["confidence"] or "").isdigit() else 0
            return (verified,confidence,-int(row["id"]))
        keep=max(items,key=rank)[0]
        extras=[x[0] for x in items if int(x[0]["id"])!=int(keep["id"])]
        athlete=conn.execute("SELECT nome,cognome FROM tesserati WHERE id=?",(athlete_id,)).fetchone() if _table(conn,"tesserati") else None
        name=_athlete_name(athlete) if athlete else ("Tesserato "+str(athlete_id))
        groups.append({
            "tesserato_id":athlete_id,
            "athlete_name":name,
            "fingerprint":fp,
            "document_kind":kind,
            "keep_id":int(keep["id"]),
            "remove_ids":[int(x["id"]) for x in extras],
            "filename":str(keep["original_filename"] or keep["filename"] or "") if "original_filename" in keep.keys() else str(keep["filename"] or ""),
        })
    return groups


def _prepare_duplicate_cleanup(conn, tid=None):
    groups=_duplicate_document_groups(conn,tid)
    remove_ids=[i for g in groups for i in g["remove_ids"]]
    return groups,remove_ids


# BODYMIND_R48_SECRETARY_CORE
def _secretary_audit(conn):
    g=_global_check(conn)
    missing_mu=[]
    no_medical_doc=[]
    incomplete=[]
    active=[]
    for a in _athletes(conn):
        if "attivo" in a.keys() and int(a["attivo"] or 0)==0:
            continue
        active.append(a)
        try:
            snap=_athlete_snapshot(conn,a)
        except Exception:
            continue
        name=snap.get("name") or _athlete_name(a)
        issues=[]
        if not snap.get("mu"):
            missing_mu.append(name); issues.append("Modulo Unico")
        if not snap.get("medical_docs"):
            no_medical_doc.append(name); issues.append("documento medico")
        if not snap.get("cert_expiry"):
            issues.append("scadenza certificato")
        if name in set(g.get("minor_issues") or []):
            issues.append("tutela minore")
        if issues:
            incomplete.append({"id":int(a["id"]),"name":name,"issues":issues})
    return {
        "active":len(active),
        "pending_docs":int(g.get("pending_docs") or 0),
        "missing_mu":missing_mu,
        "no_medical_doc":no_medical_doc,
        "missing_cert_expiry":list(g.get("missing_cert") or []),
        "expiring_cert":list(g.get("expiring_cert") or []),
        "minor_issues":list(g.get("minor_issues") or []),
        "mu_review":list(g.get("mu_review") or []),
        "incomplete":incomplete,
        "payments":int(g.get("payments") or 0),
        "receipts":int(g.get("receipts") or 0),
    }

def _storage_audit(conn):
    root=Path("/data/tenants/default/media")
    files=[]
    if root.exists():
        for p in root.rglob("*"):
            try:
                if p.is_file() and not p.name.startswith("."):
                    files.append(p.resolve())
            except Exception:
                continue
    referenced=set()
    referenced_basenames={}
    for table in ("documenti","inbound_documents"):
        if not _table(conn,table):
            continue
        cols=_cols(conn,table)
        path_cols=[x for x in cols if "path" in x.lower() or x.lower() in ("filename","file","nome_file")]
        if not path_cols:
            continue
        rows=conn.execute("SELECT * FROM "+table).fetchall()
        for r in rows:
            for col in path_cols:
                try: raw=str(r[col] or "").strip()
                except Exception: raw=""
                if not raw: continue
                p=Path(raw)
                if not p.is_absolute():
                    p=root/p
                try: rp=p.resolve()
                except Exception: rp=p
                referenced.add(str(rp))
                referenced_basenames.setdefault(Path(raw).name,0)
                referenced_basenames[Path(raw).name]+=1
    unindexed=[]
    for p in files:
        if str(p) in referenced:
            continue
        if referenced_basenames.get(p.name,0)==1:
            continue
        unindexed.append(str(p))
    return {
        "root":str(root),
        "files_total":len(files),
        "referenced_paths":len(referenced),
        "unindexed_count":len(unindexed),
        "unindexed":unindexed[:120],
    }

def _alert_audit(conn):
    names=[str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
    candidates=[n for n in names if any(k in n.lower() for k in ("alert","notific","email","mail","reminder","scadenz"))]
    latest=[]
    for table in candidates[:20]:
        try:
            cols=_cols(conn,table)
            count=int(conn.execute("SELECT COUNT(*) FROM "+table).fetchone()[0])
            row=conn.execute("SELECT * FROM "+table+" ORDER BY rowid DESC LIMIT 1").fetchone() if count else None
            safe={}
            if row:
                for k in row.keys():
                    kl=k.lower()
                    if any(secret in kl for secret in ("password","secret","token","key")):
                        continue
                    v=str(row[k] or "")
                    safe[k]=v[:180]
            latest.append({"table":table,"count":count,"latest":safe})
        except Exception:
            continue
    return {"tables":latest,"candidate_count":len(candidates)}

def _agent_tool_catalog(conn):
    return [
        {"name":"global_status","description":"Controlla stato generale BodyMind: tesserati, documenti da verificare, certificati, tutele, pagamenti e ricevute.","write":False},
        {"name":"secretary_audit","description":"Audit completo da segreteria: controlla tutti i tesserati attivi, Modulo Unico, documenti medici, scadenze certificati, tutela minori, documenti da verificare, pagamenti e ricevute. Usalo per richieste tipo controlla tutto/cosa manca/sistema la segreteria.","write":False},
        {"name":"scan_document_storage","description":"Controlla fisicamente l'archivio documenti sul volume BodyMind e segnala file non indicizzati nel database. Non cancella né sposta nulla.","write":False},
        {"name":"audit_alerts","description":"Controlla tabelle e storico relativi ad alert, notifiche, email, reminder e scadenze, senza esporre segreti.","write":False},
        {"name":"smtp_status","description":"Controlla se il servizio SMTP è configurato e se l'ultimo test di connessione è riuscito. Non legge né espone password.","write":False},
        {"name":"open_smtp_setup","description":"Apre nel gestionale il pannello sicuro per configurare SMTP/Gmail. Le credenziali non vengono inviate al modello.","write":False},
        {"name":"send_email","description":"Prepara una email reale da inviare tramite SMTP BodyMind. Args: recipient, subject, body. Richiede conferma prima dell'invio.","write":True},
        {"name":"prepare_batch_upload","description":"Prepara il prossimo caricamento massivo dichiarando il tipo documento e se va portato in produzione. Args: document_type, production. Usalo solo se l'utente lo chiede esplicitamente.","write":True},
        {"name":"search_tesserato","description":"Cerca un tesserato per nome o cognome.","write":False},
        {"name":"inspect_tesserato","description":"Legge dossier, documenti, certificato, tutela, quota e pagamenti di un tesserato.","write":False},
        {"name":"list_documents","description":"Elenca i documenti visibili di un tesserato.","write":False},
        {"name":"find_duplicate_documents","description":"Legge e confronta il contenuto reale dei documenti nel dossier e trova copie semanticamente uguali. Hash identico è una scorciatoia, altrimenti confronta persona, date, scelte, firme e contenuto.","write":False},
        {"name":"cleanup_duplicate_documents","description":"Legge e confronta il contenuto reale dei documenti e prepara la rimozione dal dossier attivo delle sole copie confermate uguali con confidenza almeno 95%. Richiede conferma e una seconda verifica prima dell'esecuzione.","write":True},
        {"name":"list_pending_documents","description":"Conta e riepiloga la coda documenti da verificare.","write":False},
        {"name":"list_payments","description":"Legge pagamenti di un tesserato oppure il conteggio globale.","write":False},
        {"name":"set_quota","description":"Prepara la modifica della quota personalizzata di un tesserato; richiede conferma.","write":True},
        {"name":"register_payment","description":"Prepara un incasso mensile per un tesserato; richiede conferma.","write":True},
        {"name":"navigate","description":"Apre una sezione del gestionale: tesserati, documenti, quote-incassi, ricevute, operatore.","write":False},
    ]


def _execute_agent_tool(conn, plan, raw_message=""):
    if not isinstance(plan,dict):
        return None
    tool=str(plan.get("tool") or "").strip()
    args=plan.get("args") if isinstance(plan.get("args"),dict) else {}
    if not tool or tool in ("none","unknown"):
        return None

    athlete=None
    athlete_name=str(args.get("athlete_name") or args.get("name") or "").strip()
    if athlete_name:
        athlete,amb=_match_athlete(conn,athlete_name)
        if amb:
            names=", ".join(_athlete_name(x) for x in amb[:5])
            return {"text":"Ho trovato più possibili tesserati: "+names+". Dimmi nome e cognome completi.","mode":"clarify"}
        if not athlete and tool not in ("global_status","find_duplicate_documents","cleanup_duplicate_documents","list_pending_documents","navigate"):
            return {"text":"Non trovo un tesserato corrispondente a “"+athlete_name+"”.","mode":"clarify"}

    if tool=="global_status":
        g=_global_check(conn)
        return {"text":f"BodyMind: {g['athletes']} tesserati, {g['pending_docs']} documenti da verificare, {len(g['missing_cert'])} certificati senza scadenza, {len(g['minor_issues'])} tutele da ricontrollare, {g['payments']} pagamenti e {g['receipts']} ricevute.","mode":"agent_tool"}

    if tool=="secretary_audit":
        a=_secretary_audit(conn)
        parts=[
            f"{a['active']} tesserati attivi",
            f"{len(a['missing_mu'])} senza Modulo Unico riconosciuto",
            f"{len(a['no_medical_doc'])} senza documento medico riconosciuto",
            f"{len(a['missing_cert_expiry'])} senza scadenza certificato",
            f"{len(a['expiring_cert'])} certificati scaduti/in scadenza",
            f"{len(a['minor_issues'])} tutele minori da rivedere",
            f"{a['pending_docs']} documenti in verifica",
        ]
        sample=[]
        for item in a["incomplete"][:10]:
            sample.append(item["name"]+" ("+", ".join(item["issues"])+")")
        text_out="Audit segreteria: "+", ".join(parts)+"."
        if sample:
            text_out+=" Priorità: "+"; ".join(sample)+"."
        return {"text":text_out,"mode":"agent_tool","secretary_audit":a,"links":[{"label":"Tesserati","href":"/tesserati"},{"label":"Documenti da verificare","href":"/documenti/da-verificare"}]}

    if tool=="scan_document_storage":
        a=_storage_audit(conn)
        text_out=f"Archivio fisico: {a['files_total']} file trovati; {a['unindexed_count']} file non risultano collegati in modo certo al database."
        if a["unindexed"]:
            text_out+=" Primi file da verificare: "+"; ".join(Path(x).name for x in a["unindexed"][:12])+"."
        return {"text":text_out,"mode":"agent_tool","storage_audit":a,"links":[{"label":"Documenti","href":"/documenti"},{"label":"Autopilot","href":"/documenti/da-verificare"}]}

    if tool=="audit_alerts":
        a=_alert_audit(conn)
        if not a["tables"]:
            return {"text":"Non trovo uno storico strutturato di alert/notifiche/email nel database. Posso cercare le funzioni di invio nel gestionale e verificare come vengono tracciate.","mode":"agent_tool","alert_audit":a}
        summary="; ".join(x["table"]+": "+str(x["count"])+" record" for x in a["tables"][:10])
        return {"text":"Storico comunicazioni/alert trovato: "+summary+". Posso approfondire l'ultimo invio o una specifica categoria.","mode":"agent_tool","alert_audit":a}

    if tool=="smtp_status":
        st=_smtp_public_status(conn)
        if not st["configured"]:
            return {"text":"SMTP non è ancora configurato. Posso aprire la configurazione sicura e preimpostare Gmail oppure un altro provider.","mode":"agent_tool","smtp_status":st,"ui_action":"smtp_setup"}
        msg=f"SMTP configurato su {st['host']}:{st['port']} ({st['security']}) per {st['username']}."
        if st["last_test_ok"]:
            msg+=" L'ultimo test di accesso è riuscito."
        elif st["last_test_at"]:
            msg+=" L'ultimo test non è riuscito: "+(st["last_test_error"] or "errore non specificato")+"."
        else:
            msg+=" Non risulta ancora un test di connessione."
        return {"text":msg,"mode":"agent_tool","smtp_status":st}

    if tool=="open_smtp_setup":
        return {"text":"Apro la configurazione SMTP sicura. Le credenziali restano nel backend cifrate e non vengono inviate all’IA.","mode":"agent_tool","ui_action":"smtp_setup","smtp_status":_smtp_public_status(conn)}

    if tool=="send_email":
        recipient=str(args.get("recipient") or "").strip()
        subject=str(args.get("subject") or "").strip()
        body=str(args.get("body") or "").strip()
        if not recipient or "@" not in recipient:
            return {"text":"Mi serve un destinatario email valido.","mode":"clarify"}
        if not subject or not body:
            return {"text":"Mi servono oggetto e testo della mail.","mode":"clarify"}
        st=_smtp_public_status(conn)
        if not st.get("configured"):
            return {"text":"SMTP non è configurato. Prima apro il pannello sicuro; poi potrò inviare davvero la mail.","mode":"warning","links":[{"label":"Configura SMTP","href":"/operatore-bodymind/smtp/setup"}]}
        aid=_set_pending_action(conn,"send_email",{"recipient":recipient,"subject":subject,"body":body})
        return {"text":"Ho preparato l’email a "+recipient+" con oggetto “"+subject+"”. Confermi l’invio reale?","mode":"confirm","action_id":aid}

    if tool=="prepare_batch_upload":
        dtype=str(args.get("document_type") or "").strip().lower()
        aliases={"modulo unico":"modulo_unico_tesseramento","modulo_unico":"modulo_unico_tesseramento","iscrizione":"modulo_unico_tesseramento","modulo iscrizione":"modulo_unico_tesseramento"}
        dtype=aliases.get(dtype,dtype)
        production=bool(args.get("production"))
        explicit=any(x in _norm(raw_message) for x in ("produzione","mettili","mandali","implementali","verifica tutti","conferma tutti","carico","caricare"))
        if production and not explicit:
            return {"text":"Per il passaggio automatico in produzione dimmelo esplicitamente, per esempio: “i prossimi file sono Moduli Unici, mettili in produzione”.","mode":"clarify"}
        if dtype not in ("modulo_unico_tesseramento","certificato_medico","documento_identita","trasporto_minori","documenti_gara","documenti_saggio"):
            return {"text":"Dimmi che tipo di documenti stai per caricare.","mode":"clarify"}
        if production and current_role()!="admin":
            return {"text":"La produzione massiva richiede un account amministratore.","mode":"warning"}
        session["bodymind_operator_upload_intent"]={"document_type":dtype,"production":production,"created_at":datetime.now().isoformat(timespec="seconds")}
        return {"text":"Modalità batch pronta. I prossimi file saranno trattati come "+dtype.replace("_"," ")+(" e porterò in produzione quelli con tesserato identificato con certezza." if production else ".")+" Gli ambigui resteranno da verificare.","mode":"action"}

    if tool=="search_tesserato":
        q=athlete_name or str(args.get("query") or raw_message or "").strip()
        row,amb=_match_athlete(conn,q)
        if row:
            return {"text":"Ho trovato "+_athlete_name(row)+".","mode":"agent_tool","links":_links_for(int(row["id"]))}
        if amb:
            return {"text":"Possibili corrispondenze: "+", ".join(_athlete_name(x) for x in amb[:8])+".","mode":"clarify"}
        return {"text":"Non trovo un tesserato corrispondente.","mode":"agent_tool"}

    if tool=="inspect_tesserato" and athlete:
        snap=_athlete_snapshot(conn,athlete)
        return {"text":f"{snap['name']}: {len(snap['docs'])} documenti visibili, {len(snap['mu'])} Moduli Unici riconosciuti, {len(snap['medical_docs'])} documenti medici, {len(snap['payments'])} pagamenti. Scadenza certificato: {snap['cert_expiry'] or 'non registrata'}. Quota: "+(f"€ {float(snap['quota_personalizzata']):.2f}" if snap["quota_personalizzata"] is not None else snap["quota_tipo"])+".","mode":"agent_tool","links":_links_for(snap["tid"])}

    if tool=="list_documents":
        if not athlete:
            return {"text":"Dimmi per quale tesserato vuoi vedere i documenti.","mode":"clarify"}
        docs=_visible_docs(conn,int(athlete["id"]))
        labels=[]
        for d in docs[:30]:
            title=""
            for k in ("original_filename","titolo","filename"):
                if k in d.keys() and str(d[k] or "").strip():
                    title=str(d[k]); break
            labels.append(title or ("Documento "+str(d["id"])))
        return {"text":f"Per {_athlete_name(athlete)} trovo {len(docs)} documenti visibili."+((" "+ "; ".join(labels)) if labels else ""),"mode":"agent_tool","links":_links_for(int(athlete["id"]))}

    if tool in ("find_duplicate_documents","cleanup_duplicate_documents"):
        scope_tid=int(athlete["id"]) if athlete else 0
        groups,comparisons=_semantic_duplicate_groups(conn,scope_tid or None)
        remove_ids=[rid for g in groups for rid in (g.get("remove_ids") or [])]
        if not groups:
            scope=(" per "+_athlete_name(athlete)) if athlete else ""
            return {"text":"Non trovo copie documentali semanticamente uguali"+scope+". Ho confrontato i documenti dello stesso tipo e della stessa persona; quelli non abbastanza certi restano distinti.","mode":"agent_tool","semantic_comparisons":comparisons,"links":_links_for(scope_tid or None)}
        athlete_count=len(set(g["tesserato_id"] for g in groups))
        sample="; ".join(g["athlete_name"]+" · "+g["document_kind"]+" · "+str(int(round(float(g.get("confidence") or 0)*100)))+"%" for g in groups[:8])
        if tool=="find_duplicate_documents":
            return {"text":f"Ho trovato {len(remove_ids)} copie confermate in {len(groups)} confronti positivi su {athlete_count} tesserati. "+sample,"mode":"agent_tool","semantic_duplicates":groups,"semantic_comparisons":comparisons,"links":_links_for(scope_tid or None)}
        aid=_set_pending_action(conn,"archive_semantic_duplicates",{"groups":groups,"scope_tesserato_id":scope_tid or None})
        return {
            "text":f"Ho letto i documenti e trovato {len(remove_ids)} copie con confidenza almeno 95%. Terrò l'originale migliore e rimuoverò dal dossier attivo soltanto le copie indicate. Prima di agire le confronterò una seconda volta e creerò un backup del database. Confermi?",
            "mode":"confirm","action_id":aid,"semantic_duplicates":groups,"semantic_comparisons":comparisons,"links":_links_for(scope_tid or None)
        }

    if tool=="list_pending_documents":
        cnt=_pending_count(conn)
        return {"text":f"Ci sono {cnt} documenti che richiedono verifica.","mode":"agent_tool","links":[{"label":"Apri Da verificare","href":"/documenti/da-verificare"}]}

    if tool=="list_payments":
        if athlete:
            snap=_athlete_snapshot(conn,athlete)
            total=sum(float(p["importo"] or 0) for p in snap["payments"])
            return {"text":f"Per {snap['name']} trovo {len(snap['payments'])} pagamenti, totale € {total:.2f}.","mode":"agent_tool","links":_links_for(snap["tid"])}
        count=int(conn.execute("SELECT COUNT(*) FROM pagamenti").fetchone()[0]) if _table(conn,"pagamenti") else 0
        return {"text":f"Nel gestionale risultano {count} pagamenti.","mode":"agent_tool","links":[{"label":"Quote & Incassi","href":"/quote-incassi"}]}

    if tool=="set_quota":
        if not athlete: return {"text":"Dimmi il tesserato per cui vuoi modificare la quota.","mode":"clarify"}
        try: amount=float(args.get("amount"))
        except Exception: return {"text":"Mi serve l'importo della nuova quota.","mode":"clarify"}
        note=str(args.get("note") or "").strip()
        aid=_set_pending_action(conn,"set_quota",{"tesserato_id":int(athlete["id"]),"amount":amount,"note":note})
        return {"text":f"Ho preparato la quota di {_athlete_name(athlete)} a € {amount:.2f}. Confermi?","mode":"confirm","action_id":aid,"links":_links_for(int(athlete["id"]))}

    if tool=="register_payment":
        if not athlete: return {"text":"Dimmi il tesserato del pagamento.","mode":"clarify"}
        try:
            month=int(args.get("month")); year=int(args.get("year") or datetime.now().year); amount=float(args.get("amount"))
        except Exception:
            return {"text":"Per registrare il pagamento mi servono mese, importo e metodo.","mode":"clarify"}
        method=str(args.get("method") or "").strip()
        if not method: return {"text":"Mi serve anche il metodo di pagamento.","mode":"clarify"}
        aid=_set_pending_action(conn,"register_payment",{"tesserato_id":int(athlete["id"]),"month":month,"year":year,"amount":amount,"method":method,"reference":"","note":str(args.get("note") or "Registrato tramite Operatore BodyMind")})
        return {"text":f"Ho preparato l’incasso per {_athlete_name(athlete)}: € {amount:.2f}, {month:02d}/{year}, metodo {method}. Confermi?","mode":"confirm","action_id":aid,"links":_links_for(int(athlete["id"]))}

    if tool=="navigate":
        section=_norm(args.get("section") or "")
        nav={"tesserati":"/tesserati","documenti":"/documenti","quote incassi":"/quote-incassi","quote":"/quote-incassi","incassi":"/quote-incassi","ricevute":"/ricevute","operatore":"/operatore-bodymind"}
        href=nav.get(section)
        if href:
            return {"text":"Apro "+section+".","mode":"navigation","links":[{"label":"Apri "+section.title(),"href":href}]}
        return {"text":"Non riconosco quella sezione.","mode":"clarify"}
    return None


def _inbound_for(conn, tid: int):
    if not _table(conn,"inbound_documents"):
        return []
    ic=_cols(conn,"inbound_documents")
    refs=["tesserato_id"]
    if "matched_tesserato_id" in ic: refs.append("matched_tesserato_id")
    if "suggested_tesserato_id" in ic: refs.append("suggested_tesserato_id")
    where=" OR ".join("coalesce("+x+",0)=?" for x in refs)
    deleted=" AND coalesce(deleted_at,'')=''" if "deleted_at" in ic else ""
    return conn.execute(
        "SELECT * FROM inbound_documents WHERE ("+where+")"+deleted+" ORDER BY id DESC",
        tuple([tid]*len(refs))
    ).fetchall()


def _doc_type(row) -> str:
    values=[]
    for key in ("doc_type","document_type","categoria","titolo","original_filename","filename"):
        if key in row.keys():
            values.append(str(row[key] or ""))
    return _norm(" ".join(values))


MONTHS = {
    "gennaio":1,"febbraio":2,"marzo":3,"aprile":4,"maggio":5,"giugno":6,
    "luglio":7,"agosto":8,"settembre":9,"ottobre":10,"novembre":11,"dicembre":12,
}

def _parse_month_year(text: str):
    n=_norm(text)
    month=None
    for name,num in MONTHS.items():
        if name in n:
            month=num
            break
    if month is None:
        m=re.search(r"\b(?:mese\s*)?(1[0-2]|0?[1-9])(?:[/-](20\d{2}))?\b",n)
        if m and any(x in n for x in ("pag","incass","quota","mensil")):
            month=int(m.group(1))
            year=int(m.group(2)) if m.group(2) else None
        else:
            year=None
    else:
        year=None
    y=re.search(r"\b(20\d{2})\b",n)
    if y: year=int(y.group(1))
    if month is not None and year is None:
        now=datetime.now()
        year=now.year
        # If a named month far in the future is mentioned late in the calendar year,
        # keep current year; the operator will state the interpreted period before confirmation.
    return month,year

def _payment_method(text: str) -> str:
    n=_norm(text)
    if "bonific" in n: return "bonifico"
    if "sumup" in n or "carta" in n or "pos" in n: return "sumup"
    if "contant" in n or "cash" in n: return "contanti"
    if "altro" in n: return "altro"
    return ""

def _classify_asd_document(filename: str, extracted_text: str=""):
    """Return a strong ASD-level archive category only when evidence is explicit."""
    n=_norm((filename or "")+" "+(extracted_text or "")[:12000])
    rules=[
        ("Verbali",("verbale consiglio","verbale direttivo","verbale assemblea","verbale riunione","consiglio direttivo","assemblea soci","assemblea dei soci")),
        ("Statuto e atti",("statuto","atto costitutivo","atto di costituzione")),
        ("Affiliazione",("affiliazione","rasd","registro nazionale attivita sportive","csen")),
        ("Assicurazioni",("polizza assicur","assicurazione rc","responsabilita civile","wakam")),
        ("Contratti",("contratto","accordo uso spazi","locazione","comodato","convenzione")),
        ("Amministrazione",("rendiconto","bilancio","registro volontari","libro soci","consiglio direttivo")),
    ]
    for folder,phrases in rules:
        hits=[p for p in phrases if p in n]
        if hits:
            return {"folder":folder,"reason":hits[0],"confidence":96 if len(hits)>1 else 91}
    return None

def _mu_review_items(conn):
    if not (_table(conn,"documenti") and _table(conn,"tesserati")):
        return []
    dc=_cols(conn,"documenti"); tc=_cols(conn,"tesserati")
    parts=[]
    if "doc_type" in dc: parts.append("lower(coalesce(d.doc_type,''))='modulo_unico_tesseramento'")
    if "categoria" in dc: parts.append("lower(coalesce(d.categoria,'')) like '%modulo unico%'")
    if "titolo" in dc: parts.append("lower(coalesce(d.titolo,'')) like '%modulo unico%'")
    if not parts: return []
    coverage=[x for x in ("consenso_informato","manleva_firmata","iscrizione_firmata","documenti_onboarding_ok","privacy_ok","liberatoria_ok","regolamento_ok") if x in tc]
    if not coverage: return []
    selects=["d.*","t.nome","t.cognome"]+[f"t.{f} AS t_{f}" for f in coverage]
    rows=conn.execute(
        "SELECT "+",".join(selects)+" FROM documenti d JOIN tesserati t ON t.id=d.tesserato_id "
        "WHERE ("+" OR ".join(parts)+") AND coalesce(d.tesserato_id,0)>0 "
        +("AND coalesce(d.visibile,1)=1 " if "visibile" in dc else "")
        +"ORDER BY d.id DESC"
    ).fetchall()
    out=[]
    for r in rows:
        miss=[f for f in coverage if int(r["t_"+f] or 0)!=1]
        if miss:
            out.append({"doc_id":int(r["id"]),"tid":int(r["tesserato_id"]),"name":(str(r["nome"] or "")+" "+str(r["cognome"] or "")).strip(),"flags":miss})
    return out

def _is_mu(row) -> bool:
    t=_doc_type(row)
    return any(x in t for x in (
        "modulo unico","modulo_unico","mu-2026","mu 2026",
        "iscrizione manleva","domanda iscrizione","modulo iscrizione"
    ))


def _is_medical(row) -> bool:
    t=_doc_type(row)
    return "certificato medico" in t or "certificato_medico" in t or re.search(r"\bcm\b",t) is not None



def _has_trusted_mu(conn, tid: int) -> bool:
    """True only when the MU passed a human/trusted completion boundary.
    Automatic recognition states such as richiede_conferma never qualify.
    """
    tid=int(tid or 0)
    if tid<=0:
        return False
    trusted={"verificato","salvato","accepted","manual_accepted","ok"}
    if _table(conn,"documenti"):
        dc=_cols(conn,"documenti")
        if "tesserato_id" in dc:
            rows=conn.execute("SELECT * FROM documenti WHERE tesserato_id=?",(tid,)).fetchall()
            for r in rows:
                if not _is_mu(r):
                    continue
                status=_norm(r["status"] if "status" in r.keys() else "")
                visible=int((r["visibile"] if "visibile" in r.keys() else 1) or 0)
                if visible and status in trusted:
                    return True
    if _table(conn,"onboarding_document_requests"):
        oc=_cols(conn,"onboarding_document_requests")
        if {"tesserato_id","document_type","status"}.issubset(oc):
            row=conn.execute(
                """SELECT 1 FROM onboarding_document_requests
                   WHERE tesserato_id=? AND lower(coalesce(document_type,''))='modulo_unico_tesseramento'
                     AND lower(coalesce(status,'')) IN ('accepted','manual_accepted')
                   LIMIT 1""",(tid,)
            ).fetchone()
            if row:
                return True
    return False


def _minor_state(conn, athlete):
    if not int(athlete["minorenne"] or 0) if "minorenne" in athlete.keys() else True:
        return {"minor":False}
    tid=int(athlete["id"])
    out={
        "minor":True,
        "guardian":str(athlete["genitore"] or "").strip() if "genitore" in athlete.keys() else "",
        "guardian_phone":str(athlete["telefono_genitore"] or "").strip() if "telefono_genitore" in athlete.keys() else "",
        "consent":False,"authorizations":False,"delegation":None,"autonomous_exit":None,
    }
    if _table(conn,"minori"):
        row=conn.execute("SELECT * FROM minori WHERE tesserato_id=? LIMIT 1",(tid,)).fetchone()
        if row:
            keys=set(row.keys())
            out["consent"]=int(row["consenso_firmato"] or 0)==1 if "consenso_firmato" in keys else False
            out["authorizations"]=int(row["autorizzazioni_ok"] or 0)==1 if "autorizzazioni_ok" in keys else False
            out["delegation"]=int(row["delega_ritiro_ok"] or 0)==1 if "delega_ritiro_ok" in keys else None
            out["autonomous_exit"]=int(row["uscita_autonoma_ok"] or 0)==1 if "uscita_autonoma_ok" in keys else None
            out["consent_date"]=str(row["data_consenso"] or "") if "data_consenso" in keys else ""
    if _has_trusted_mu(conn,tid):
        out["consent"]=True
        out["authorizations"]=True
        out["trusted_mu"]=True
    else:
        out["trusted_mu"]=False
    return out


def _athlete_snapshot(conn, athlete):
    tid=int(athlete["id"])
    docs=_visible_docs(conn,tid)
    inbound=_inbound_for(conn,tid)
    all_docs=list(docs)+list(inbound)
    mu=[r for r in all_docs if _is_mu(r)]
    medical=[r for r in all_docs if _is_medical(r)]
    minor=_minor_state(conn,athlete)
    expiry=str(athlete["certificato_scadenza"] or "").strip() if "certificato_scadenza" in athlete.keys() else ""
    quota_personalizzata=athlete["quota_personalizzata"] if "quota_personalizzata" in athlete.keys() else None
    quota_sconto=float(athlete["quota_sconto_fisso"] or 0) if "quota_sconto_fisso" in athlete.keys() else 0
    quota_tipo=str(athlete["quota_tipo"] or "standard") if "quota_tipo" in athlete.keys() else "standard"
    quota_note=str(athlete["quota_note"] or "") if "quota_note" in athlete.keys() else ""
    payments=[]
    if _table(conn,"pagamenti"):
        payments=conn.execute(
            "SELECT * FROM pagamenti WHERE tesserato_id=? ORDER BY coalesce(data,paid_at,created_at) DESC,id DESC LIMIT 12",
            (tid,)
        ).fetchall()
    return {
        "tid":tid,"name":_athlete_name(athlete),"docs":docs,"inbound":inbound,
        "mu":mu,"medical_docs":medical,"cert_expiry":expiry,"minor":minor,
        "quota_personalizzata":quota_personalizzata,"quota_sconto":quota_sconto,
        "quota_tipo":quota_tipo,"quota_note":quota_note,"payments":payments,
    }


def _pending_count(conn) -> int:
    if not _table(conn,"inbound_documents"): return 0
    ph=",".join("?" for _ in PENDING_STATUSES)
    extra=" AND coalesce(deleted_at,'')=''" if "deleted_at" in _cols(conn,"inbound_documents") else ""
    return int(conn.execute(
        "SELECT COUNT(*) FROM inbound_documents WHERE lower(coalesce(status,'')) IN ("+ph+")"+extra,
        PENDING_STATUSES
    ).fetchone()[0])


def _global_check(conn):
    athletes=_athletes(conn)
    today=date.today()
    missing_cert=[]; expiring=[]; minor_issues=[]
    for a in athletes:
        if int(a["attivo"] or 0)==0 if "attivo" in a.keys() else False:
            continue
        expiry=str(a["certificato_scadenza"] or "").strip() if "certificato_scadenza" in a.keys() else ""
        name=_athlete_name(a)
        if not expiry:
            missing_cert.append(name)
        else:
            try:
                d=date.fromisoformat(expiry[:10])
                if d < today:
                    expiring.append((name,"scaduto "+d.strftime("%d/%m/%Y")))
                elif d <= today+timedelta(days=30):
                    expiring.append((name,"scade "+d.strftime("%d/%m/%Y")))
            except Exception:
                pass
        if "minorenne" in a.keys() and int(a["minorenne"] or 0)==1:
            ms=_minor_state(conn,a)
            if not ms.get("guardian") or not ms.get("consent") or not ms.get("authorizations"):
                minor_issues.append(name)
    return {
        "athletes":len(athletes),
        "pending_docs":_pending_count(conn),
        "missing_cert":missing_cert,
        "expiring_cert":expiring,
        "minor_issues":minor_issues,
        "payments":int(conn.execute("SELECT COUNT(*) FROM pagamenti").fetchone()[0]) if _table(conn,"pagamenti") else 0,
        "receipts":int(conn.execute("SELECT COUNT(*) FROM ricevute").fetchone()[0]) if _table(conn,"ricevute") else 0,
        "mu_review":_mu_review_items(conn),
    }


def _links_for(tid: int|None=None):
    links=[
        {"label":"Tesserati","href":"/tesserati"},
        {"label":"Documenti","href":"/documenti"},
        {"label":"Quote & Incassi","href":"/quote-incassi"},
    ]
    if tid:
        links.insert(0,{"label":"Scheda atleta","href":f"/tesserati/{tid}/scheda"})
        links.insert(1,{"label":"Dossier","href":f"/documenti?tesserato_id={tid}"})
        links.insert(2,{"label":"Quote atleta","href":f"/quote-incassi/atleta/{tid}"})
    return links


def _set_pending_action(conn, action_type: str, payload: dict) -> int:
    _schema(conn)
    now=datetime.now().isoformat(timespec="seconds")
    cur=conn.execute(
        """INSERT INTO bodymind_operator_actions
           (conversation_id,action_type,payload_json,status,requested_by,created_at)
           VALUES(?,?,?,?,?,?)""",
        (_conv_id(),action_type,json.dumps(payload,ensure_ascii=False),"proposed",_identity(),now)
    )
    conn.commit()
    aid=int(cur.lastrowid)
    session["bodymind_operator_pending_action"]=aid
    return aid


def _execute_pending(conn):
    aid=int(session.get("bodymind_operator_pending_action") or 0)
    if not aid:
        return None
    row=conn.execute("SELECT * FROM bodymind_operator_actions WHERE id=?",(aid,)).fetchone()
    if not row or str(row["status"])!="proposed":
        session.pop("bodymind_operator_pending_action",None)
        return None
    payload=json.loads(str(row["payload_json"] or "{}"))
    kind=str(row["action_type"] or "")
    role=current_role()
    if role not in ("admin","manager"):
        return {"text":"Posso preparare l’operazione, ma l’account connesso non ha i permessi per confermarla.","mode":"warning"}
    if kind=="send_email":
        recipient=str(payload.get("recipient") or "").strip()
        subject=str(payload.get("subject") or "").strip()
        body=str(payload.get("body") or "")
        try:
            _smtp_send_message(conn,recipient,subject,body)
        except Exception as exc:
            conn.execute("UPDATE bodymind_operator_actions SET status='failed',confirmed_by=?,executed_at=? WHERE id=?",(_identity(),datetime.now().isoformat(timespec="seconds"),aid))
            conn.commit(); session.pop("bodymind_operator_pending_action",None)
            return {"text":"Invio non riuscito. Non considero la mail inviata. Errore SMTP: "+str(exc)[:220],"mode":"error","links":[{"label":"Controlla SMTP","href":"/operatore-bodymind/smtp/setup"}]}
        conn.execute("UPDATE bodymind_operator_actions SET status='executed',confirmed_by=?,executed_at=? WHERE id=?",(_identity(),datetime.now().isoformat(timespec="seconds"),aid))
        conn.commit(); session.pop("bodymind_operator_pending_action",None)
        return {"text":"Email inviata realmente a "+recipient+" e registrata nello storico BodyMind.","mode":"action"}

    if kind=="register_payment":
        if current_role()!="admin":
            return {"text":"Ho preparato l’incasso, ma per registrarlo serve un account amministratore. Non ho modificato nulla.","mode":"warning"}
        from .routes_quote_incassi import _register_monthly_payment
        tid=int(payload["tesserato_id"]); month=int(payload["month"]); year=int(payload["year"])
        amount=float(payload["amount"]); method=str(payload.get("method") or "altro")
        reference=str(payload.get("reference") or ""); note=str(payload.get("note") or "")
        pid=_register_monthly_payment(conn,tid,month,year,amount,method,reference,note)
        receipt=conn.execute("SELECT id,numero_progressivo,anno_progressivo FROM ricevute WHERE pagamento_id=? ORDER BY id DESC LIMIT 1",(pid,)).fetchone() if _table(conn,"ricevute") else None
        conn.execute(
            "UPDATE bodymind_operator_actions SET status='executed',confirmed_by=?,executed_at=? WHERE id=?",
            (_identity(),datetime.now().isoformat(timespec="seconds"),aid)
        )
        conn.commit(); session.pop("bodymind_operator_pending_action",None)
        athlete=conn.execute("SELECT nome,cognome FROM tesserati WHERE id=?",(tid,)).fetchone()
        name=(str(athlete["nome"])+" "+str(athlete["cognome"])).strip()
        links=_links_for(tid)
        if receipt:
            links.insert(0,{"label":"Apri ricevuta","href":f"/ricevute/pdf/{int(receipt['id'])}"})
        return {
            "text":f"Incasso registrato per {name}: € {amount:.2f}, {month:02d}/{year}, metodo {method}. "+("La ricevuta progressiva è stata creata." if receipt else "Il pagamento è stato registrato; controlla Quote & Incassi per la ricevuta."),
            "mode":"action","links":links
        }

    if kind=="archive_semantic_duplicates":
        if current_role()!="admin":
            return {"text":"La rimozione di copie documentali richiede un account amministratore. Non ho modificato nulla.","mode":"warning"}
        groups=payload.get("groups") if isinstance(payload.get("groups"),list) else []
        if not groups:
            conn.execute("UPDATE bodymind_operator_actions SET status='cancelled' WHERE id=?",(aid,))
            conn.commit(); session.pop("bodymind_operator_pending_action",None)
            return {"text":"Non ci sono copie da rimuovere. Non ho modificato nulla.","mode":"warning"}
        backup_dir=Path("/data/operator_backups")
        backup_dir.mkdir(parents=True,exist_ok=True)
        backup_file=backup_dir/(datetime.now().strftime("%Y%m%d_%H%M%S")+"_semantic_duplicates_"+str(aid)+".db")
        db_path=Path("/data/tenants/default/asd.db")
        if db_path.exists():
            shutil.copy2(db_path,backup_file)
        dc=_cols(conn,"documenti")
        archived=[]; blocked=[]
        try:
            conn.execute("BEGIN IMMEDIATE")
            for group in groups:
                ok,reason=_revalidate_semantic_duplicate_group(conn,group)
                rid=int((group.get("remove_ids") or [0])[0] or 0)
                keep_id=int(group.get("keep_id") or 0)
                if not ok:
                    blocked.append({"remove_id":rid,"keep_id":keep_id,"reason":reason})
                    continue
                sets=[]; vals=[]
                if "visibile" in dc:
                    sets.append("visibile=0")
                if "status" in dc:
                    sets.append("status=?"); vals.append("semantic_duplicate_archived")
                if "note" in dc:
                    sets.append("note=?"); vals.append("Copia semantica rimossa dal dossier attivo tramite Segreteria BodyMind; originale mantenuto ID "+str(keep_id))
                if not sets:
                    blocked.append({"remove_id":rid,"keep_id":keep_id,"reason":"schema documenti non archiviabile"})
                    continue
                vals.extend([rid,int(group.get("tesserato_id") or 0)])
                cur=conn.execute(
                    "UPDATE documenti SET "+",".join(sets)+" WHERE id=? AND tesserato_id=?"+(" AND coalesce(visibile,1)=1" if "visibile" in dc else ""),
                    tuple(vals)
                )
                if int(cur.rowcount or 0)==1:
                    archived.append({"remove_id":rid,"keep_id":keep_id,"reason":reason})
                else:
                    blocked.append({"remove_id":rid,"keep_id":keep_id,"reason":"record cambiato o già non attivo"})
            action_status="executed" if not blocked else ("executed_partial" if archived else "blocked_safety")
            conn.execute(
                "UPDATE bodymind_operator_actions SET status=?,confirmed_by=?,executed_at=?,payload_json=? WHERE id=?",
                (action_status,_identity(),datetime.now().isoformat(timespec="seconds"),
                 json.dumps({**payload,"archived":archived,"blocked":blocked,"backup":str(backup_file)},ensure_ascii=False),aid)
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        session.pop("bodymind_operator_pending_action",None)
        if not archived:
            return {"text":"Non ho rimosso alcun documento: la seconda verifica non ha confermato con sufficiente certezza le copie proposte. Il dossier è rimasto invariato.","mode":"warning","semantic_blocked":blocked}
        text_out=f"Ho rimosso dal dossier attivo {len(archived)} copia/e semantiche confermate, mantenendo sempre l'originale migliore. Backup creato: {backup_file.name}."
        if blocked:
            text_out+=f" {len(blocked)} confronto/i sono stati bloccati perché non più abbastanza certi."
        return {"text":text_out,"mode":"action","semantic_archived":archived,"semantic_blocked":blocked,"links":[{"label":"Apri Documenti","href":"/documenti"}]}

    if kind=="archive_duplicate_documents":
        conn.execute("UPDATE bodymind_operator_actions SET status='blocked_safety' WHERE id=? AND status='proposed'",(aid,))
        conn.commit(); session.pop("bodymind_operator_pending_action",None)
        return {"text":"Operazione bloccata per sicurezza: l’Operatore non può più eliminare o nascondere automaticamente documenti ritenuti duplicati. Posso solo segnalarli per revisione.","mode":"warning","links":[{"label":"Apri Documenti","href":"/documenti"}]}

    if kind=="generic_route_action":
        path=str(payload.get("path") or "")
        method=str(payload.get("method") or "POST").upper()
        params=payload.get("params") if isinstance(payload.get("params"),dict) else {}
        target,values,error=_resolve_route_action(path,method)
        if error:
            conn.execute("UPDATE bodymind_operator_actions SET status='blocked_safety' WHERE id=?",(aid,))
            conn.commit(); session.pop("bodymind_operator_pending_action",None)
            return {"text":"Operazione bloccata al secondo controllo di sicurezza: "+error+" Nessuna modifica eseguita.","mode":"warning"}
        backup_dir=Path("/data/operator_backups")
        backup_dir.mkdir(parents=True,exist_ok=True)
        backup_file=backup_dir/(datetime.now().strftime("%Y%m%d_%H%M%S")+"_action_"+str(aid)+".db")
        db_path=Path("/data/tenants/default/asd.db")
        if db_path.exists():
            shutil.copy2(db_path,backup_file)
        token=str(session.get("_csrf_token") or csrf_token() or "")
        send=dict(params)
        send.setdefault("csrf_token",token)
        sess_snapshot={k:session.get(k) for k in session.keys()}
        try:
            with app.test_client() as client:
                with client.session_transaction() as s2:
                    for k,v in sess_snapshot.items():
                        s2[k]=v
                resp=client.open(path,method=method,data=send,headers={"X-CSRFToken":token},follow_redirects=False)
            status=int(resp.status_code or 0)
        except Exception as exc:
            conn.execute("UPDATE bodymind_operator_actions SET status='failed',confirmed_by=?,executed_at=? WHERE id=?",(_identity(),datetime.now().isoformat(timespec="seconds"),aid))
            conn.commit(); session.pop("bodymind_operator_pending_action",None)
            return {"text":"La route reale ha generato un errore prima di completare l'operazione. Backup conservato in "+str(backup_file)+". Errore: "+str(exc)[:220],"mode":"error"}
        if status<200 or status>=400:
            conn.execute("UPDATE bodymind_operator_actions SET status='failed',confirmed_by=?,executed_at=? WHERE id=?",(_identity(),datetime.now().isoformat(timespec="seconds"),aid))
            conn.commit(); session.pop("bodymind_operator_pending_action",None)
            return {"text":f"La route {method} {path} ha risposto HTTP {status}. Non considero l'azione completata. Backup: {backup_file}.","mode":"warning"}
        conn.execute("UPDATE bodymind_operator_actions SET status='executed',confirmed_by=?,executed_at=? WHERE id=?",(_identity(),datetime.now().isoformat(timespec="seconds"),aid))
        conn.commit(); session.pop("bodymind_operator_pending_action",None)
        return {"text":f"Operazione eseguita tramite la route reale {method} {path} ({target['function']}). Backup preventivo creato: {backup_file.name}.","mode":"action"}

    if kind=="set_quota":
        tid=int(payload["tesserato_id"])
        amount=float(payload["amount"])
        note=str(payload.get("note") or "").strip()
        conn.execute(
            """UPDATE tesserati
               SET quota_personalizzata=?, quota_tipo='personalizzata',
                   quota_note=?, updated_at=?
               WHERE id=?""",
            (amount,note,datetime.now().isoformat(timespec="seconds"),tid)
        )
        conn.execute(
            """INSERT INTO bodymind_operator_facts
               (subject_type,subject_id,fact_key,fact_value,note,created_by,created_at,updated_at)
               VALUES('tesserato',?,'quota_personalizzata',?,?,?,?,?)
               ON CONFLICT(subject_type,subject_id,fact_key) DO UPDATE SET
                 fact_value=excluded.fact_value,note=excluded.note,created_by=excluded.created_by,updated_at=excluded.updated_at""",
            (tid,f"{amount:.2f}",note,_identity(),datetime.now().isoformat(timespec="seconds"),datetime.now().isoformat(timespec="seconds"))
        )
        conn.execute(
            "UPDATE bodymind_operator_actions SET status='executed',confirmed_by=?,executed_at=? WHERE id=?",
            (_identity(),datetime.now().isoformat(timespec="seconds"),aid)
        )
        conn.commit()
        session.pop("bodymind_operator_pending_action",None)
        athlete=conn.execute("SELECT nome,cognome FROM tesserati WHERE id=?",(tid,)).fetchone()
        name=(str(athlete["nome"])+" "+str(athlete["cognome"])).strip()
        return {"text":f"Fatto. Ho impostato per {name} una quota personalizzata di € {amount:.2f}"+(f", con nota “{note}”." if note else "."),"mode":"action","links":_links_for(tid)}
    return {"text":"Quell’azione non è ancora automatizzabile in sicurezza. Non ho modificato nulla.","mode":"warning"}


def _cancel_pending(conn):
    aid=int(session.get("bodymind_operator_pending_action") or 0)
    if aid:
        conn.execute("UPDATE bodymind_operator_actions SET status='cancelled' WHERE id=? AND status='proposed'",(aid,))
        conn.commit()
    session.pop("bodymind_operator_pending_action",None)


def _yes(text: str) -> bool:
    n=_norm(text)
    return n in {"si","sì","ok","okay","confermo","vai","procedi","fallo","esegui","certo"}


def _no(text: str) -> bool:
    n=_norm(text)
    return n in {"no","annulla","lascia stare","non farlo","stop"}


def _first_name_from_intro(text: str):
    raw=str(text or "").strip()
    # Only explicit self-introductions at the start (optionally after a greeting).
    # This deliberately avoids false positives such as "i documenti sono da verificare".
    m=re.match(
        r"^(?:(?:ciao|salve|buongiorno|buonasera)[,;:!]?\s*)?(?:io\s+)?(?:sono|mi chiamo)\s+([A-Za-zÀ-ÖØ-öø-ÿ'’-]{2,40})(?=$|[,;.!?\s])",
        raw,re.I
    )
    if not m:
        return ""
    name=m.group(1).strip().title()
    blocked={"Da","Di","Del","Della","Dei","Delle","Un","Una","Il","Lo","La","Qui","Ora","Già","Gia"}
    return "" if name in blocked else name


def _cloud_ai(question: str, grounded_text: str):
    """Optional conversational expansion. Disabled unless explicitly configured."""
    if str(os.environ.get("BODYMIND_AI_CLOUD","")).strip().lower() not in ("1","true","yes","on"):
        return None
    if not str(os.environ.get("OPENAI_API_KEY","")).strip():
        return None
    try:
        from openai import OpenAI
        client=OpenAI()
        model=str(os.environ.get("BODYMIND_AI_MODEL") or "gpt-6-astra").strip()
        prompt=(
            "Sei Operatore BodyMind, un assistente professionale di segreteria per una ASD italiana. "
            "Parla in italiano in modo naturale, competente e conciso. "
            "Non inventare mai dati del gestionale e non dichiarare eseguite azioni che il motore non ha eseguito. "
            "Se il testo BodyMind contiene un dato fattuale interno, quello è la fonte di verità. "
            "Domanda dell'utente: "+str(question)[:5000]+"\n"
            "Risposta/fatto già verificato dal motore BodyMind: "+str(grounded_text)[:8000]
        )
        response=client.responses.create(model=model,input=prompt)
        out=str(getattr(response,"output_text","") or "").strip()
        return out[:12000] if out else None
    except Exception:
        return None


def _recent_operator_context(conn, limit: int = 8):
    if not _table(conn,"bodymind_operator_messages"):
        return []
    try:
        rows=conn.execute(
            """SELECT speaker,identity_name,message,created_at
               FROM bodymind_operator_messages
               WHERE conversation_id=?
               ORDER BY id DESC LIMIT ?""",
            (_conv_id(),int(limit))
        ).fetchall()
        return [
            {"speaker":str(r["speaker"] or ""),"identity":str(r["identity_name"] or ""),
             "message":str(r["message"] or "")[:1200],"created_at":str(r["created_at"] or "")}
            for r in reversed(rows)
        ]
    except Exception:
        return []

# BODYMIND_R45_CLOUD_FULL_AGENT
# BODYMIND_R50_SEMANTIC_GLOSSARY
_BODYMIND_GLOSSARY={
    "tesserato":["iscritto","iscritta","atleta","allievo","allieva","socio","socia","persona","ragazza","ragazzo"],
    "certificato_medico":["cm","certificato","certificato medico","certificato sportivo","agonistico","non agonistico","scadenza certificato","certificato scaduto"],
    "modulo_unico_tesseramento":["mu","modulo unico","modulo iscrizione","domanda iscrizione","tesseramento","modulo tesseramento"],
    "documenti":["dossier","archivio atleta","archivio documentale","documentazione","allegati","file"],
    "pagamenti":["incassi","quote pagate","mensilita","mensilità","quota","mensile","saldo","pagato","pagamento"],
    "ricevute":["quietanze","ricevuta","ricevute associative","ricevuta quota"],
    "collaboratori":["collaboratore","collaboratrice","coach","istruttore","istruttrice","insegnante","trainer","collaboratore sportivo","co.co.co","cococo","lavoratore sportivo"],
    "corsi_lezioni":["corso","corsi","lezione","lezioni","classe","classi","orario","orari","calendario","turno","sala","planning"],
    "presenze":["presenza","presenze","assenza","assenze","partecipazione","frequenza"],
    "lista_attesa":["lista d'attesa","lista attesa","waiting list","attesa","nuova iscrizione"],
    "attrezzi":["attrezzo","attrezzatura","cerchio","cerchio aereo","tessuti","tessuto","trapezio","aerial hoop"],
    "tutela_minori":["tutela","minore","minori","genitore","consenso genitoriale","liberatoria","privacy","autorizzazione"],
    "comunicazioni":["email","mail","messaggio","messaggi","notifica","notifiche","promemoria","avviso","avvisi","chat","bacheca"],
    "eventi":["evento","eventi","esibizione","spettacolo","manifestazione","saggio","festa"],
    "registro_sportivo":["rasd","registro attività sportive dilettantistiche","csen","affiliazione","tesseramento ente","registro nazionale"],
    "collaborazione_sportiva":["compenso","compensi","ore collaboratore","liquidazione","ricevuta collaboratore","lul","lavoro sportivo","contratto collaboratore"],
}

def _bodymind_route_manifest():
    """Runtime inventory of the real Flask application. No hard-coded route count."""
    out=[]
    try:
        for rule in sorted(app.url_map.iter_rules(),key=lambda r:(str(r.rule),str(r.endpoint))):
            methods=sorted(m for m in (rule.methods or set()) if m not in ("HEAD","OPTIONS"))
            endpoint=str(rule.endpoint or "")
            fn=app.view_functions.get(endpoint)
            module=str(getattr(fn,"__module__","") or "") if fn else ""
            name=str(getattr(fn,"__name__","") or "") if fn else ""
            doc=(str(getattr(fn,"__doc__","") or "").strip().replace("\n"," "))[:400] if fn else ""
            out.append({"route":str(rule.rule),"methods":methods,"endpoint":endpoint,"module":module,"function":name,"doc":doc})
    except Exception:
        pass
    return out

def _bodymind_function_manifest():
    """Index every Python function in asd_app so the agent can retrieve implementation context."""
    out=[]
    root=Path(__file__).resolve().parent
    try:
        for p in sorted(root.glob("*.py")):
            try:
                src=p.read_text(encoding="utf-8",errors="replace")
                tree=ast.parse(src)
            except Exception:
                continue
            for node in ast.walk(tree):
                if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                    continue
                doc=(ast.get_docstring(node) or "").replace("\n"," ").strip()[:500]
                out.append({
                    "module":"asd_app."+p.stem,
                    "function":str(node.name),
                    "line":int(getattr(node,"lineno",0) or 0),
                    "doc":doc,
                })
    except Exception:
        pass
    return out

def _route_source_details(target):
    matches=[]
    q=_norm(target)
    for row in _bodymind_route_manifest():
        if q and q not in _norm(" ".join([row["route"],row["endpoint"],row["function"],row["module"]])):
            continue
        fn=app.view_functions.get(row["endpoint"])
        src=""
        try: src=inspect.getsource(fn) if fn else ""
        except Exception: src=""
        form_fields=sorted(set(re.findall(r"request\.form\.get\([\"']([^\"']+)",src)))
        arg_fields=sorted(set(re.findall(r"request\.args\.get\([\"']([^\"']+)",src)))
        json_mode=("get_json" in src)
        matches.append({
            **row,
            "form_fields":form_fields,
            "query_fields":arg_fields,
            "json":json_mode,
            "source_excerpt":src[:6000],
        })
        if len(matches)>=12:
            break
    return matches

def _bodymind_db_manifest(conn):
    """Detailed SQLite schema inventory, read-only."""
    out=[]
    try:
        tables=[str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
        for table in tables:
            columns=[]
            for r in conn.execute("PRAGMA table_info("+table+")").fetchall():
                columns.append({"name":str(r[1]),"type":str(r[2] or ""),"notnull":bool(r[3]),"pk":bool(r[5])})
            try: count=int(conn.execute("SELECT COUNT(*) FROM "+table).fetchone()[0])
            except Exception: count=None
            out.append({"table":table,"count":count,"columns":columns})
    except Exception:
        pass
    return out

def _capability_search(conn, query):
    q=_norm(query)
    tokens=[x for x in re.split(r"[^a-z0-9à-ÿ_]+",q) if len(x)>=2]
    expanded=set(tokens)
    for canonical,aliases in _BODYMIND_GLOSSARY.items():
        values=[canonical]+aliases
        if any(_norm(v) in q for v in values):
            expanded.add(canonical)
            for v in aliases:
                expanded.update(x for x in re.split(r"[^a-z0-9à-ÿ_]+",_norm(v)) if len(x)>=2)
    scored=[]
    for row in _bodymind_route_manifest():
        hay=_norm(" ".join([row["route"],row["endpoint"],row["module"],row["function"],row["doc"]]))
        score=sum(3 if t in hay else 0 for t in expanded)
        if score:
            scored.append((score,row))
    scored.sort(key=lambda x:(-x[0],x[1]["route"]))
    tables=[]
    for row in _bodymind_db_manifest(conn):
        hay=_norm(row["table"]+" "+" ".join(c["name"] for c in row["columns"]))
        score=sum(2 if t in hay else 0 for t in expanded)
        if score:
            tables.append((score,row))
    tables.sort(key=lambda x:(-x[0],x[1]["table"]))
    funcs=[]
    for row in _bodymind_function_manifest():
        hay=_norm(" ".join([row["module"],row["function"],row["doc"]]))
        score=sum(2 if t in hay else 0 for t in expanded)
        if score:
            funcs.append((score,row))
    funcs.sort(key=lambda x:(-x[0],x[1]["module"],x[1]["function"]))
    return {
        "routes":[x[1] for x in scored[:30]],
        "functions":[x[1] for x in funcs[:40]],
        "tables":[x[1] for x in tables[:15]],
        "terms":sorted(expanded)
    }

_GENERIC_ROUTE_BLOCK_PREFIXES=(
    "/health","/static","/favicon","/login","/logout",
)
_GENERIC_DESTRUCTIVE_HINTS=(
    "delete from","drop table","truncate ",".unlink(","os.remove(","shutil.rmtree",
    "visibile=0","status='deleted'","status=\"deleted\"","rimuovi","elimina","cancella",
    "delete","purge","reset","wipe","truncate",
    "send_mail","send_email","smtp","webhook","requests.post","httpx.post",
    "stripe","sumup","paypal","charge","refund","bonifico","pagamento esterno",
    "request.files","save_uploaded","upload","send_file",
)

def _resolve_route_action(path, method):
    path=str(path or "").strip()
    method=str(method or "POST").upper().strip()
    if not path.startswith("/"):
        return None,{},"Percorso route non valido."
    if method in ("GET","HEAD","OPTIONS"):
        return None,{},"Per una lettura usa gli strumenti di consultazione, non il gateway write."
    if any(path.startswith(x) for x in _GENERIC_ROUTE_BLOCK_PREFIXES):
        return None,{},"Route di sistema/autenticazione non utilizzabile dall'agente."
    try:
        adapter=app.url_map.bind("localhost")
        endpoint,values=adapter.match(path,method=method)
    except Exception:
        return None,{},"La route/metodo indicati non esistono nel gestionale."
    fn=app.view_functions.get(endpoint)
    if not fn:
        return None,{},"Endpoint non risolto."
    try: src=inspect.getsource(fn)
    except Exception: src=""
    low=src.lower()+" "+path.lower()+" "+str(endpoint).lower()
    if "request.files" in low:
        return None,{},"Le route con upload file richiedono uno strumento dedicato."
    if any(x in low for x in _GENERIC_DESTRUCTIVE_HINTS):
        return None,{},"La route è potenzialmente distruttiva: serve un adapter dedicato con verifica semantica, non il gateway generico."
    form_fields=sorted(set(re.findall(r"request\.form\.get\([\"']([^\"']+)",src)))
    json_fields=[]
    return {
        "path":path,"method":method,"endpoint":str(endpoint),"function":str(getattr(fn,"__name__","") or ""),
        "module":str(getattr(fn,"__module__","") or ""),"form_fields":form_fields,
        "json":("get_json" in src),"source_excerpt":src[:5000]
    },values,""

def _propose_generic_route_action(conn,args,raw_message=""):
    path=str(args.get("path") or "").strip()
    method=str(args.get("method") or "POST").upper().strip()
    params=args.get("params") if isinstance(args.get("params"),dict) else {}
    target,values,error=_resolve_route_action(path,method)
    if error:
        return {"text":"Non preparo l'azione: "+error+" Ho lasciato tutto invariato.","mode":"warning"}
    declared=set(target.get("form_fields") or [])
    if declared:
        extras=[k for k in params if k not in declared and k not in ("csrf_token","_csrf_token")]
        if extras:
            return {"text":"Non preparo l'azione: i parametri "+", ".join(extras)+" non risultano letti dalla route reale. Nessuna modifica eseguita.","mode":"warning"}
    aid=_set_pending_action(conn,"generic_route_action",{
        "path":path,"method":method,"params":params,"endpoint":target["endpoint"],
        "function":target["function"],"module":target["module"],"url_values":values,
    })
    fields=", ".join(sorted(params.keys())) or "nessun campo"
    return {
        "text":f"Ho preparato {method} {path} ({target['function']}) con campi: {fields}. Prima dell'esecuzione farò un backup del database e userò la route reale del gestionale. Confermi?",
        "mode":"confirm","action_id":aid,"cloud_ai":True,"agent_plan":"propose_route_action"
    }

def _full_agent_tool_catalog(conn):
    base=list(_agent_tool_catalog(conn))
    base.extend([
        {"name":"discover_capabilities","description":"Cerca in tutte le route, funzioni Flask e tabelle del gestionale per capire dove vive una funzione o concetto. Conosce sinonimi BodyMind.","write":False},
        {"name":"inspect_system_map","description":"Legge la mappa completa del gestionale: numero route, moduli, tabelle e aree funzionali.","write":False},
        {"name":"inspect_db_schema","description":"Legge schema, colonne e conteggi delle tabelle del database BodyMind.","write":False},
        {"name":"inspect_route","description":"Legge una route/funzione reale del gestionale, inclusi campi form/query e sorgente rilevante.","write":False},
        {"name":"propose_route_action","description":"Prepara una modifica tramite una route reale non distruttiva del gestionale. Args: path, method, params. Richiede sempre conferma e backup prima dell'esecuzione.","write":True},
    ])
    return base

def _parse_cloud_plan(text):
    raw=str(text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw=re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$","",raw,flags=re.I|re.S).strip()
    try:
        obj=json.loads(raw)
        return obj if isinstance(obj,dict) else None
    except Exception:
        m=re.search(r"\{.*\}",raw,re.S)
        if not m:
            return None
        try:
            obj=json.loads(m.group(0))
            return obj if isinstance(obj,dict) else None
        except Exception:
            return None

def _compact_agent_observation(tool, result):
    if not isinstance(result,dict):
        return {"tool":str(tool),"text":str(result)[:3000]}
    out={"tool":str(tool),"text":str(result.get("text") or "")[:4000],"mode":str(result.get("mode") or "")}
    caps=result.get("capabilities")
    if isinstance(caps,dict):
        out["routes"]=(caps.get("routes") or [])[:12]
        out["functions"]=(caps.get("functions") or [])[:16]
        out["tables"]=(caps.get("tables") or [])[:10]
    details=result.get("route_details")
    if isinstance(details,list):
        safe=[]
        for x in details[:5]:
            if isinstance(x,dict):
                safe.append({
                    "route":x.get("route"),"methods":x.get("methods"),"endpoint":x.get("endpoint"),
                    "module":x.get("module"),"function":x.get("function"),
                    "form_fields":x.get("form_fields"),"query_fields":x.get("query_fields"),
                    "json":x.get("json"),"source_excerpt":str(x.get("source_excerpt") or "")[:3500],
                })
        out["route_details"]=safe
    return out


def _cloud_plan_tool(conn, question: str, tool_trace=None):
    """Cloud-first planner with full BodyMind knowledge and server-enforced action safety."""
    key=str(os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        return None
    if str(os.environ.get("BODYMIND_AI_CLOUD","1")).strip().lower() not in ("1","true","yes","on"):
        return None
    try:
        from openai import OpenAI
        model=str(os.environ.get("BODYMIND_AI_MODEL") or "gpt-6-luna").strip()
        catalog=_full_agent_tool_catalog(conn)
        compact=[{"name":x["name"],"description":x["description"],"write":bool(x.get("write"))} for x in catalog]
        manifest=_bodymind_route_manifest()
        funcs=_bodymind_function_manifest()
        dbm=_bodymind_db_manifest(conn)
        overview={
            "routes":len(manifest),
            "functions":len(funcs),
            "tables":len(dbm),
            "areas":sorted(_BODYMIND_GLOSSARY.keys()),
        }
        recent=_recent_operator_context(conn,4)
        trace=tool_trace if isinstance(tool_trace,list) else []
        relevant=_capability_search(conn,question)
        relevant_context={
            "routes":relevant.get("routes",[])[:12],
            "functions":relevant.get("functions",[])[:16],
            "tables":relevant.get("tables",[])[:8],
            "terms":relevant.get("terms",[])[:24],
        }
        prompt=(
            "Sei la Segreteria BodyMind: un assistente operativo cloud con qualità conversazionale paragonabile a un ottimo assistente generale, ma specializzato completamente nel gestionale BodyMind. "
            "Parla in italiano naturale, chiaro e sintetico; non mostrare route, nomi tecnici o ragionamenti interni se non richiesti. Devi capire italiano naturale, sinonimi, abbreviazioni e contesto. "
            "Tesserato/iscritto/atleta/allievo/socio possono riferirsi alla stessa anagrafica; CM=certificato medico; "
            "MU=Modulo Unico; dossier=archivio documentale del tesserato. "
            "Conosci l'intero gestionale tramite l'indice runtime, ma per questa richiesta ricevi già gli elementi più pertinenti. "
            "Scegli UNO strumento reale e preferisci direttamente lo strumento operativo corretto. Usa discover_capabilities solo se gli elementi pertinenti non bastano davvero. "
            "Puoi scegliere strumenti write quando la richiesta lo richiede, ma NON dichiarare mai eseguita una modifica: "
            "il server presenterà anteprima/conferma e applicherà permessi, validazioni e audit. "
            "Per cancellazioni, fusioni, duplicati o operazioni distruttive devi essere conservativo: documenti di tipo diverso "
            "(es. certificato medico e Modulo Unico) non sono duplicati; se c'è ambiguità scegli analisi/revisione, non cancellazione. "
            "Restituisci SOLO JSON valido: {\"tool\":\"nome_o_none\",\"args\":{},\"answer\":\"\"}. "
            "Tool=none solo se è pura conversazione o se nessuno strumento disponibile copre ancora l'azione. "
            "Catalogo strumenti: "+json.dumps(compact,ensure_ascii=False)+
            "\nIndice sistema: "+json.dumps(overview,ensure_ascii=False)[:5000]+
            "\nElementi rilevanti per questa richiesta: "+json.dumps(relevant_context,ensure_ascii=False)[:12000]+
            "\nContesto recente: "+json.dumps(recent,ensure_ascii=False)[:6000]+
            "\nRisultati strumenti già usati in questa richiesta: "+json.dumps(trace,ensure_ascii=False)[:8000]+
            "\nSe i risultati degli strumenti bastano per rispondere, usa tool=none e formula la risposta finale in answer. "
            "Se serve un altro passaggio, scegli il prossimo strumento. "
            "\nRichiesta utente: "+str(question or "")[:7000]
        )
        client=OpenAI(api_key=key,timeout=18.0,max_retries=0)
        reasoning_effort=str(os.environ.get("BODYMIND_AI_REASONING") or "none").strip().lower()
        started=time.perf_counter()
        resp=client.responses.create(
            model=model,
            input=prompt,
            reasoning={"effort":reasoning_effort},
            max_output_tokens=350,
            store=False,
            prompt_cache_key="bodymind-r51-planner-"+model,
        )
        elapsed_ms=int((time.perf_counter()-started)*1000)
        _record_response_usage(conn,resp,model,"planner")
        try:
            usage=getattr(resp,"usage",None)
            print("[cloud-agent-r51] model="+model+" ms="+str(elapsed_ms)+" input_tokens="+str(int(getattr(usage,"input_tokens",0) or 0))+" output_tokens="+str(int(getattr(usage,"output_tokens",0) or 0)),flush=True)
        except Exception:
            pass
        global _CLOUD_LAST_ERROR,_CLOUD_LAST_OK_AT
        _CLOUD_LAST_ERROR=""
        _CLOUD_LAST_OK_AT=datetime.now().isoformat(timespec="seconds")
        plan=_parse_cloud_plan(getattr(resp,"output_text",""))
        if not plan:
            _CLOUD_LAST_ERROR="empty_plan"
            return None
        tool=str(plan.get("tool") or "").strip()
        allowed={x["name"] for x in catalog}
        if tool not in allowed and tool not in ("none","unknown",""):
            return {"tool":"discover_capabilities","args":{"query":str(question or "")},"answer":""}
        if not isinstance(plan.get("args"),dict):
            plan["args"]={}
        return plan
    except Exception as exc:
        _CLOUD_LAST_ERROR=repr(exc)[:1200]
        try:
            _log(conn,"system","R46 cloud planner unavailable: "+_CLOUD_LAST_ERROR)
        except Exception:
            pass
        try:
            print("[cloud-agent-r46] planner_error="+_CLOUD_LAST_ERROR,flush=True)
        except Exception:
            pass
        return None

def _execute_full_agent_plan(conn, plan, raw_message=""):
    if not isinstance(plan,dict):
        return None
    tool=str(plan.get("tool") or "").strip()
    args=plan.get("args") if isinstance(plan.get("args"),dict) else {}
    if tool in ("","none","unknown"):
        return None
    if tool=="discover_capabilities":
        q=str(args.get("query") or raw_message or "")
        found=_capability_search(conn,q)
        routes=found["routes"]
        tables=found["tables"]
        funcs=found.get("functions") or []
        rtxt="; ".join((x["methods"][0] if x["methods"] else "GET")+" "+x["route"]+" → "+x["function"] for x in routes[:10])
        ttxt=", ".join(x["table"] for x in tables[:10])
        ftxt=", ".join(x["module"]+"."+x["function"] for x in funcs[:10])
        return {"text":"Ho cercato nel gestionale reale. Route pertinenti: "+(rtxt or "nessuna corrispondenza forte")+". Funzioni pertinenti: "+(ftxt or "nessuna")+". Tabelle pertinenti: "+(ttxt or "nessuna")+".","mode":"cloud_tool","cloud_ai":True,"agent_plan":tool,"capabilities":found}
    if tool=="inspect_system_map":
        routes=_bodymind_route_manifest(); dbm=_bodymind_db_manifest(conn)
        mods=sorted(set(x["module"] for x in routes if x["module"]))
        funcs=_bodymind_function_manifest()
        return {"text":f"Mappa BodyMind: {len(routes)} route runtime, {len(funcs)} funzioni Python indicizzate, {len(mods)} moduli Flask e {len(dbm)} tabelle dati. Posso cercare una funzione specifica e collegarla agli strumenti operativi.","mode":"cloud_tool","cloud_ai":True,"agent_plan":tool}
    if tool=="inspect_db_schema":
        dbm=_bodymind_db_manifest(conn)
        return {"text":f"Schema BodyMind letto: {len(dbm)} tabelle. Posso cercare campi e relazioni per nome o funzione.","mode":"cloud_tool","cloud_ai":True,"agent_plan":tool,"schema":dbm[:40]}
    if tool=="inspect_route":
        target=str(args.get("target") or args.get("route") or args.get("endpoint") or raw_message or "")
        details=_route_source_details(target)
        if not details:
            return {"text":"Non trovo una route/funzione corrispondente a quella descrizione.","mode":"cloud_tool","cloud_ai":True,"agent_plan":tool}
        shown="; ".join((x["methods"][0] if x["methods"] else "GET")+" "+x["route"]+" → "+x["function"] for x in details[:8])
        return {"text":"Ho letto le route reali: "+shown+".","mode":"cloud_tool","cloud_ai":True,"agent_plan":tool,"route_details":details}
    if tool=="propose_route_action":
        return _propose_generic_route_action(conn,args,raw_message)
    result=_execute_agent_tool(conn,plan,raw_message)
    if result:
        result["cloud_ai"]=True
        result["agent_plan"]=tool
        # _execute_agent_tool only prepares writes; actual execution remains in the existing confirmed-action path.
    return result


def _cloud_operator_answer(conn, question: str, athlete=None):
    """Optional high-capability conversational layer.
    It is read-only: deterministic BodyMind functions remain the only path for writes.
    """
    key=str(os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        return None
    try:
        from openai import OpenAI
        model=str(os.environ.get("BODYMIND_AI_MODEL") or "gpt-5.6-sol").strip()
        g=_global_check(conn)
        facts={
            "identity":_identity(),
            "role":current_role(),
            "athletes":g.get("athletes"),
            "pending_docs":g.get("pending_docs"),
            "minor_issues_count":len(g.get("minor_issues") or []),
            "missing_cert_count":len(g.get("missing_cert") or []),
            "expiring_cert_count":len(g.get("expiring_cert") or []),
            "mu_review_count":len(g.get("mu_review") or []),
            "payments":g.get("payments"),
            "receipts":g.get("receipts"),
        }
        if athlete is not None:
            snap=_athlete_snapshot(conn,athlete)
            facts["athlete"]={
                "id":snap["tid"],"name":snap["name"],"documents":len(snap["docs"]),
                "inbound":len(snap["inbound"]),"mu_count":len(snap["mu"]),
                "medical_docs":len(snap["medical_docs"]),"cert_expiry":snap["cert_expiry"],
                "minor":snap["minor"],"quota_personalizzata":snap["quota_personalizzata"],
                "quota_sconto":snap["quota_sconto"],"quota_tipo":snap["quota_tipo"],
                "quota_note":snap["quota_note"],"payments_count":len(snap["payments"]),
            }
        recent=_recent_operator_context(conn,8)
        prompt=(
            "Sei Operatore BodyMind, una segreteria IA esperta di ASD italiane e danza aerea. "
            "Devi parlare in italiano naturale, professionale, amichevole e molto competente. "
            "Usa soltanto i fatti interni forniti. Non inventare documenti, firme, consensi, pagamenti, quote, date o autorizzazioni. "
            "Distingui sempre PRESENTE, ASSOCIATO e VERIFICATO. Un NO esplicito a delega, uscita autonoma o immagini non è un documento mancante. "
            "Non eseguire mai modifiche: le modifiche passano solo dagli strumenti deterministici BodyMind con conferma. "
            "Se mancano dati, fai una domanda precisa. Se la richiesta è generale, puoi ragionare come un operatore ASD senior. "
            "Fatti correnti: "+json.dumps(facts,ensure_ascii=False)+
            "\nContesto conversazione: "+json.dumps(recent,ensure_ascii=False)+
            "\nRichiesta: "+str(question or "")[:6000]
        )
        client=OpenAI(api_key=key,timeout=18.0,max_retries=0)
        resp=client.responses.create(
            model=model,
            input=prompt,
            reasoning={"effort":"none"},
            max_output_tokens=900,
            store=False,
            prompt_cache_key="bodymind-r51-answer-"+model,
        )
        _record_response_usage(conn,resp,model,"answer")
        out=str(getattr(resp,"output_text","") or "").strip()
        return out[:7000] if out else None
    except Exception as exc:
        try:
            _log(conn,"system","Cloud AI unavailable: "+repr(exc))
        except Exception:
            pass
        return None

def _answer(conn, text: str):
    raw=str(text or "").strip()
    n=_norm(raw)
    if not raw:
        return {"text":"Dimmi pure. Posso controllare tesserati, documenti, Modulo Unico, certificati, tutela minori, quote, incassi e ricevute.","mode":"local"}

    if session.get("bodymind_operator_pending_action"):
        if _yes(raw):
            done=_execute_pending(conn)
            if done: return done
        if _no(raw):
            _cancel_pending(conn)
            return {"text":"Va bene, ho annullato la proposta. Non ho modificato nulla.","mode":"action"}

    intro=_first_name_from_intro(raw)
    if intro:
        session["bodymind_operator_identity"]=intro
        return {
            "text":f"Ciao {intro}. Ti riconosco come interlocutore di questa conversazione. I permessi operativi restano quelli dell’account attualmente collegato.",
            "mode":"identity"
        }

    if any(x in n for x in ("chi sono","come mi chiamo","mi riconosci")):
        return {"text":f"Per questa conversazione sei {_identity()}.","mode":"identity"}

    if re.match(r"^(ciao|buongiorno|buonasera|salve)\b",n):
        return {
            "text":f"Ciao {_identity()}. Sono l’Operatore BodyMind. Posso controllare il gestionale e lavorare con te come una segreteria: dimmi cosa vuoi verificare.",
            "mode":"local"
        }

    # BODYMIND_R51_FAST_FACTS
    # Fatti semplici e inequivocabili arrivano direttamente dal DB: più veloci, più economici, zero allucinazioni.
    if (
        re.search(r"\b(quanti|numero|totale)\b",n)
        and any(x in n for x in ("tesserat","iscritt","atlet","alliev","soci"))
        and not any(x in n for x in ("manca","document","certificat","pagament","ricevut","quota"))
    ):
        cnt=len(_athletes(conn))
        return {
            "text":f"Nel gestionale risultano {cnt} tesserati.",
            "mode":"fast_fact",
            "cloud_ai":False,
            "links":[{"label":"Apri Tesserati","href":"/tesserati"}]
        }

    athlete, ambiguous=_match_athlete(conn,raw)
    if not athlete and not ambiguous:
        athlete=_context_athlete(conn,raw)
    if ambiguous:
        names=", ".join(_athlete_name(x) for x in ambiguous[:5])
        return {"text":"Ho trovato più possibili tesserati: "+names+". Dimmi nome e cognome completi.","mode":"clarify"}

    # BODYMIND_R40_AGENT_TOOLS
    # BODYMIND_R43_NO_AUTODELETE_DOCUMENTS
    if ("document" in n or "dossier" in n) and any(x in n for x in ("duplicat","doppion")):
        want_cleanup=any(x in n for x in ("elimina","eliminare","rimuovi","rimuovere","cancella","cancellare","pulisci","pulire"))
        plan={"tool":"cleanup_duplicate_documents" if want_cleanup else "find_duplicate_documents","args":{}}
        if athlete: plan["args"]["athlete_name"]=_athlete_name(athlete)
        out=_execute_agent_tool(conn,plan,raw)
        if out: return out

    if any(x in n for x in ("controlla bodymind","controlla tutto","situazione generale","come siamo messi","stato gestionale","cosa c e da fare","cosa c'è da fare")):
        g=_global_check(conn)
        pieces=[f"Ho controllato BodyMind: {g['athletes']} tesserati e {g['pending_docs']} documenti richiedono verifica."]
        if g["minor_issues"]: pieces.append(f"{len(g['minor_issues'])} minori hanno dati o consensi da ricontrollare.")
        else: pieces.append("Non vedo minori con tutela incompleta secondo i flag correnti.")
        if g["missing_cert"]: pieces.append(f"{len(g['missing_cert'])} tesserati non hanno una scadenza certificato registrata.")
        if g["expiring_cert"]: pieces.append(f"{len(g['expiring_cert'])} certificati sono scaduti o scadono entro 30 giorni.")
        if g["mu_review"]: pieces.append(f"{len(g['mu_review'])} Moduli Unici storici sono associati ma hanno flag di copertura non allineati: li considero da ricontrollare, non li correggo automaticamente.")
        pieces.append(f"Pagamenti registrati: {g['payments']}. Ricevute: {g['receipts']}.")
        return {
            "text":" ".join(pieces),
            "mode":"audit",
            "cards":[
                {"title":"Documenti da verificare","value":g["pending_docs"],"href":"/documenti/da-verificare"},
                {"title":"Certificati senza scadenza","value":len(g["missing_cert"]),"href":"/tesserati"},
                {"title":"Tutela minori da rivedere","value":len(g["minor_issues"]),"href":"/tesserati"},
                {"title":"Moduli Unici da ricontrollare","value":len(g["mu_review"]),"href":"/documenti"},
            ],
            "links":[{"label":"Apri coda documenti","href":"/documenti/da-verificare"},{"label":"Quote & Incassi","href":"/quote-incassi"}]
        }

    if (
        any(x in n for x in ("documenti da verificare","coda documenti","documenti in attesa","documenti pendenti"))
        or (("document" in n or "modul" in n) and any(x in n for x in ("verifica","verificare","controlla","controllare","da vedere","da controllare")))
    ) and not athlete:
        cnt=_pending_count(conn)
        g=_global_check(conn)
        extra=f" Inoltre {len(g['mu_review'])} Moduli Unici storici risultano da ricontrollare." if g["mu_review"] else ""
        return {
            "text":f"Ho controllato la coda: ci sono {cnt} documenti che richiedono una decisione umana.{extra}",
            "mode":"local",
            "links":[{"label":"Apri Da verificare","href":"/documenti/da-verificare"},{"label":"Apri Documenti","href":"/documenti"}]
        }

    if any(x in n for x in ("tutela minori","tutele minori","tutela genitori","tutela genitoriale","consenso minori","consensi minori","minori incompleti")) and not athlete:
        g=_global_check(conn)
        names=g["minor_issues"]
        if names:
            shown=", ".join(names[:12])
            more=f" e altri {len(names)-12}" if len(names)>12 else ""
            txt=f"Ho controllato le tutele: {len(names)} minori richiedono ancora un controllo secondo i dati correnti: {shown}{more}."
        else:
            txt="Ho controllato le tutele: non risultano minori con tutela incompleta secondo Modulo Unico verificato e flag correnti."
        return {"text":txt,"mode":"local","links":[{"label":"Apri Tesserati","href":"/tesserati"},{"label":"Apri Documenti","href":"/documenti"}]}

    if ("certificat" in n) and any(x in n for x in ("chi non","manc","senza","scad")) and not athlete:
        g=_global_check(conn)
        names=g["missing_cert"][:10]
        exp=g["expiring_cert"][:10]
        bits=[]
        if names: bits.append("Senza scadenza registrata: "+", ".join(names)+("." if len(names)<=10 else "…"))
        if exp: bits.append("Scaduti/in scadenza: "+", ".join(a+" ("+b+")" for a,b in exp)+".")
        if not bits: bits.append("Non vedo criticità immediate sui certificati.")
        return {"text":" ".join(bits),"mode":"local","links":[{"label":"Apri Tesserati","href":"/tesserati"}]}

    if athlete:
        session["bodymind_operator_last_tesserato"]=int(athlete["id"])
        snap=_athlete_snapshot(conn,athlete)
        name=snap["name"]
        tid=snap["tid"]

        if re.search(r"\b(registra|segna|incassa|incasso|pagamento|pagato|ricevuto)\b",n) and re.search(r"\b\d{1,4}(?:[.,]\d{1,2})?\b",n):
            month,year=_parse_month_year(raw)
            if month is None:
                return {"text":f"Ho capito che vuoi registrare un pagamento per {name}, ma mi serve il mese. Dimmi per esempio “settembre 45 euro bonifico”.","mode":"clarify","links":_links_for(tid)}
            nums=re.findall(r"\b\d{1,4}(?:[.,]\d{1,2})?\b",n)
            # Ignore month/year tokens when extracting the amount.
            candidates=[]
            for token in nums:
                val=float(token.replace(",","."))
                if int(val)==month or (year and int(val)==year):
                    continue
                candidates.append(val)
            if not candidates:
                return {"text":"Mi manca l’importo dell’incasso.","mode":"clarify","links":_links_for(tid)}
            amount=candidates[0]
            method=_payment_method(raw)
            if not method:
                return {"text":f"Ho atleta, mese e importo per {name}. Mi serve anche il metodo: contanti, bonifico, SumUp/carta oppure altro.","mode":"clarify","links":_links_for(tid)}
            note="Registrato tramite Operatore BodyMind"
            aid=_set_pending_action(conn,"register_payment",{"tesserato_id":tid,"month":month,"year":year,"amount":amount,"method":method,"reference":"","note":note})
            return {
                "text":f"Ho preparato l’incasso per {name}: € {amount:.2f}, mese {month:02d}/{year}, metodo {method}. Se confermi lo registro nel motore Quote & Incassi e genero la ricevuta progressiva. Confermi?",
                "mode":"confirm","action_id":aid,"links":_links_for(tid)
            }

        if re.search(r"\b(paga|pagare|quota|mensile|sconto)\b",n) and re.search(r"\b\d{1,4}(?:[.,]\d{1,2})?\b",n):
            nums=re.findall(r"\b\d{1,4}(?:[.,]\d{1,2})?\b",n)
            amount=float(nums[-1].replace(",","."))
            note=""
            m=re.search(r"(sconto[^,.!?]*|sorell[ae][^,.!?]*|promozion[^,.!?]*)",raw,re.I)
            if m: note=m.group(1).strip()
            aid=_set_pending_action(conn,"set_quota",{"tesserato_id":tid,"amount":amount,"note":note})
            return {
                "text":f"Ho preparato questa modifica: {name}, quota personalizzata € {amount:.2f}"+(f", nota “{note}”." if note else ".")+" Confermi?",
                "mode":"confirm","action_id":aid,"links":_links_for(tid)
            }

        if any(x in n for x in ("quanto paga","quota","mensile","sconto")):
            qp=snap["quota_personalizzata"]
            if qp is not None:
                text_out=f"{name} ha una quota personalizzata di € {float(qp):.2f}."
            else:
                text_out=f"Per {name} non trovo una quota personalizzata: il profilo è “{snap['quota_tipo']}”."
            if snap["quota_sconto"]:
                text_out+=f" Sconto fisso registrato: € {snap['quota_sconto']:.2f}."
            if snap["quota_note"]:
                text_out+=f" Nota: {snap['quota_note']}."
            text_out+=" Se vuoi, puoi dirmi ad esempio “"+name.split()[0]+" paga 45, sconto sorelle” e ti chiederò conferma prima di salvarlo."
            return {"text":text_out,"mode":"local","links":_links_for(tid)}

        if any(x in n for x in ("modulo","iscrizione","manleva","caricato","documento")):
            if snap["mu"]:
                statuses=[]
                for r in snap["mu"][:4]:
                    st=str(r["status"] or "") if "status" in r.keys() else ""
                    statuses.append(st or "presente")
                text_out=f"Sì. Per {name} trovo {len(snap['mu'])} documento/i compatibili con Modulo Unico/iscrizione. Stati: "+", ".join(statuses)+"."
            else:
                text_out=f"Per {name} non trovo un Modulo Unico chiaramente riconosciuto nel dossier o nell’Autopilot."
            return {"text":text_out,"mode":"local","links":_links_for(tid)}

        if "certificat" in n:
            expiry=snap["cert_expiry"]
            if expiry:
                try: shown=date.fromisoformat(expiry[:10]).strftime("%d/%m/%Y")
                except Exception: shown=expiry
                text_out=f"Per {name} la scadenza del certificato medico registrata è {shown}. Trovo {len(snap['medical_docs'])} documento/i medici collegati."
            else:
                text_out=f"Per {name} non risulta una scadenza del certificato medico in scheda. Trovo {len(snap['medical_docs'])} documento/i medici collegati."
            return {"text":text_out,"mode":"local","links":_links_for(tid)}

        if any(x in n for x in ("tutela","minore","genitore","consenso","autorizz")):
            ms=snap["minor"]
            if not ms.get("minor"):
                return {"text":f"{name} non risulta minorenne nella scheda.","mode":"local","links":_links_for(tid)}
            missing=[]
            if not ms.get("guardian"): missing.append("dati del genitore")
            if not ms.get("consent"): missing.append("consenso firmato")
            if not ms.get("authorizations"): missing.append("sezione autorizzazioni")
            if missing:
                text_out=f"Per {name} la tutela non è completa secondo i dati attuali: manca o va verificato "+", ".join(missing)+"."
            else:
                text_out=f"Per {name} la tutela minore risulta coperta: genitore presente, consenso firmato e sezione autorizzazioni verificata. Gli eventuali NO a delega o uscita autonoma restano scelte valide e non li considero documenti mancanti."
            return {"text":text_out,"mode":"local","links":_links_for(tid)}

        if any(x in n for x in ("pagament","incass","ricevut")):
            total=sum(float(p["importo"] or 0) for p in snap["payments"])
            return {"text":f"Per {name} trovo {len(snap['payments'])} pagamento/i registrati negli ultimi record disponibili, per un totale di € {total:.2f}.","mode":"local","links":_links_for(tid)}

        if any(x in n for x in ("cosa manca","completa","situazione","scheda")):
            ms=snap["minor"]; missing=[]
            if not snap["cert_expiry"]: missing.append("scadenza certificato medico")
            if not snap["mu"]: missing.append("Modulo Unico riconosciuto")
            if ms.get("minor"):
                if not ms.get("guardian"): missing.append("genitore")
                if not ms.get("consent"): missing.append("consenso minore")
                if not ms.get("authorizations"): missing.append("autorizzazioni minore")
            if missing:
                out=f"Per {name} controllerei: "+", ".join(missing)+"."
            else:
                out=f"Per {name} non vedo mancanze principali su Modulo Unico, certificato e tutela minore secondo i dati correnti."
            return {"text":out,"mode":"local","links":_links_for(tid)}

        return {
            "text":f"Ho trovato {name}. Posso controllare dossier, Modulo Unico, certificato medico, tutela minori, quota, pagamenti e ricevute. Dimmi cosa vuoi sapere.",
            "mode":"local","links":_links_for(tid)
        }

    if "ricevut" in n:
        count=int(conn.execute("SELECT COUNT(*) FROM ricevute").fetchone()[0]) if _table(conn,"ricevute") else 0
        return {"text":f"Al momento risultano {count} ricevute nel registro.","mode":"local","links":[{"label":"Apri Ricevute","href":"/ricevute"}]}

    if "pagament" in n or "incass" in n or "quota" in n:
        count=int(conn.execute("SELECT COUNT(*) FROM pagamenti").fetchone()[0]) if _table(conn,"pagamenti") else 0
        return {"text":f"Al momento risultano {count} pagamenti nella tabella pagamenti. Per una persona specifica dimmi nome e cognome.","mode":"local","links":[{"label":"Quote & Incassi","href":"/quote-incassi"}]}

    if any(x in n for x in ("apri tesserati","vai ai tesserati")):
        return {"text":"Ti porto ai Tesserati.","mode":"navigation","links":[{"label":"Apri Tesserati","href":"/tesserati"}]}
    if any(x in n for x in ("apri documenti","vai ai documenti")):
        return {"text":"Ti porto ai Documenti.","mode":"navigation","links":[{"label":"Apri Documenti","href":"/documenti"}]}

    if any(x in n for x in ("cosa sai fare","aiutami","help","comandi")):
        return {
            "text":"Posso leggere la mappa completa di route, funzioni e database BodyMind, capire sinonimi e abbreviazioni, cercare e controllare tesserati, dossier, documenti, Modulo Unico, certificati, tutela minori, quote, incassi e ricevute. Posso anche preparare azioni sulle route reali del gestionale: ogni modifica richiede conferma e backup; le operazioni distruttive o ambigue vengono bloccate dal gateway generico e richiedono un adapter dedicato.",
            "mode":"help",
            "links":[{"label":"Da verificare","href":"/documenti/da-verificare"},{"label":"Quote & Incassi","href":"/quote-incassi"}]
        }

    return {
        "text":"Ho capito la richiesta e la passo al planner intelligente BodyMind.",
        "mode":"fallback",
        "allow_device_ai":True
    }



def _bodymind_logo_file():
    roots=[
        Path("/data/user_static"),
        Path("/data/tenants/default/user_static"),
        Path("/data/tenants/default/media"),
        Path("/data/top2_app/user_static"),
        Path("/data/top2_app/static"),
    ]
    candidates=[]
    for root in roots:
        if not root.exists():
            continue
        try:
            for p in root.rglob("*"):
                if not p.is_file() or p.suffix.lower() not in {".png",".jpg",".jpeg",".webp",".svg"}:
                    continue
                n=p.name.lower()
                score=(40 if "bodymind" in n else 0)+(30 if "logo" in n else 0)+(10 if "brand" in n else 0)
                if score:
                    candidates.append((score,-len(str(p)),p))
        except Exception:
            pass
    candidates.sort(reverse=True)
    return candidates[0][2] if candidates else None


@app.after_request
def bodymind_operator_voice_headers(resp):
    try:
        if request.path.startswith("/operatore-bodymind"):
            resp.headers["Permissions-Policy"] = "microphone=(self)"
            resp.headers.setdefault("Cache-Control","no-store")
    except Exception:
        pass
    return resp


@app.get("/bodymind-media/logo")
@login_required
def bodymind_operator_logo():
    p=_bodymind_logo_file()
    if p:
        return send_file(p,conditional=True,max_age=3600)
    svg="""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 240">
    <defs><radialGradient id="g"><stop stop-color="#f05b9d"/><stop offset="1" stop-color="#24101f"/></radialGradient></defs>
    <circle cx="120" cy="120" r="114" fill="url(#g)"/>
    <circle cx="120" cy="120" r="103" fill="#140b13" stroke="#f05b9d" stroke-opacity=".45"/>
    <text x="120" y="112" text-anchor="middle" font-family="Arial,sans-serif" font-size="31" font-weight="800" fill="#fff">BODY</text>
    <text x="120" y="147" text-anchor="middle" font-family="Arial,sans-serif" font-size="31" font-weight="300" fill="#f6b5d1">MIND</text>
    </svg>"""
    return Response(svg,mimetype="image/svg+xml",headers={"Cache-Control":"public,max-age=3600"})


@app.get("/operatore-bodymind")
@login_required
def bodymind_operator_home():
    conn=db()
    history=[]
    try:
        _schema(conn)
        g=_global_check(conn)
        rows=conn.execute(
            """SELECT speaker,message,payload_json,created_at
               FROM bodymind_operator_messages
               WHERE conversation_id=? AND speaker IN ('user','assistant')
               ORDER BY id DESC LIMIT 60""",
            (_conv_id(),)
        ).fetchall()
        for r in reversed(rows):
            payload={}
            try:
                payload=json.loads(str(r["payload_json"] or "{}"))
                if not isinstance(payload,dict): payload={}
            except Exception:
                payload={}
            history.append({
                "speaker":str(r["speaker"] or ""),
                "message":str(r["message"] or ""),
                "payload":payload,
                "created_at":str(r["created_at"] or ""),
            })
    finally:
        conn.close()
    csrf=csrf_token()
    ident=e(_identity())
    history_json=json.dumps(history,ensure_ascii=False).replace("</","<\\/")
    html=f"""
    <style id="bodymind-operator-r29">
    .bmo{{max-width:1180px;margin:0 auto;padding:10px 0 42px}}
    .bmo-hero{{display:grid;grid-template-columns:180px 1fr;gap:28px;align-items:center;padding:28px;border:1px solid rgba(125,211,252,.16);border-radius:28px;background:radial-gradient(circle at 15% 20%,rgba(236,72,153,.18),transparent 38%),linear-gradient(135deg,rgba(8,18,34,.98),rgba(22,9,24,.96));box-shadow:0 26px 70px rgba(0,0,0,.25)}}
    .bmo-avatar{{position:relative;width:150px;height:150px;margin:auto;border-radius:50%;display:grid;place-items:center;background:radial-gradient(circle,rgba(244,90,157,.28),rgba(9,18,34,.92) 68%);box-shadow:0 0 0 1px rgba(255,255,255,.08),0 0 52px rgba(244,90,157,.18)}}
    .bmo-avatar img{{width:108px;height:108px;object-fit:contain;filter:drop-shadow(0 10px 22px rgba(0,0,0,.4))}}
    .bmo-avatar:after{{content:"";position:absolute;inset:-9px;border-radius:50%;border:2px solid rgba(244,90,157,.0);transition:.2s}}
    .bmo-avatar.speaking:after,.bmo-avatar.listening:after{{border-color:rgba(244,90,157,.72);animation:bmoPulse 1.05s infinite}}
    .bmo-avatar.listening{{box-shadow:0 0 0 1px rgba(255,255,255,.08),0 0 70px rgba(56,189,248,.30)}}
    @keyframes bmoPulse{{50%{{transform:scale(1.08);opacity:.34}}}}
    .bmo-kicker{{font-size:10px;font-weight:900;letter-spacing:.14em;color:#f3a6c8;text-transform:uppercase}}
    .bmo-hero h1{{font-size:clamp(34px,5vw,62px);margin:5px 0 8px;line-height:.98}}
    .bmo-hero p{{color:#b9c7d8;max-width:780px;margin:0;line-height:1.55}}
    .bmo-status{{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}}
    .bmo-pill{{padding:7px 10px;border:1px solid rgba(255,255,255,.10);border-radius:999px;background:rgba(255,255,255,.045);font-size:11px;color:#dce8f5}}
    .bmo-grid{{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:14px;margin-top:14px}}
    .bmo-chat,.bmo-side{{border:1px solid rgba(148,163,184,.14);border-radius:24px;background:rgba(7,16,31,.86)}}
    .bmo-chat{{min-height:600px;display:flex;flex-direction:column;overflow:hidden}}
    .bmo-messages{{padding:18px;display:flex;flex-direction:column;gap:12px;flex:1;overflow:auto;max-height:650px}}
    .bmo-msg{{max-width:min(86%,760px);padding:13px 15px;border-radius:18px;line-height:1.5;font-size:14px;white-space:pre-wrap}}
    .bmo-msg.bot{{align-self:flex-start;background:#10243a;border:1px solid rgba(125,211,252,.15)}}
    .bmo-msg.me{{align-self:flex-end;background:linear-gradient(135deg,#8d285e,#c73577);color:#fff}}
    .bmo-cards,.bmo-links{{display:flex;flex-wrap:wrap;gap:8px;margin-top:9px}}
    .bmo-card{{min-width:150px;padding:10px 12px;border-radius:14px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);text-decoration:none;color:#fff!important}}
    .bmo-card strong{{display:block;font-size:23px}}
    .bmo-link{{padding:8px 10px;border-radius:11px;border:1px solid rgba(125,211,252,.24);background:#142d46;color:#fff!important;text-decoration:none;font-size:11px;font-weight:900}}
    .bmo-compose{{border-top:1px solid rgba(148,163,184,.12);padding:12px;display:grid;grid-template-columns:auto 1fr auto;gap:8px;align-items:end;background:rgba(5,12,23,.96)}}
    .bmo-compose textarea{{min-height:48px;max-height:150px;resize:vertical;border-radius:15px;padding:12px 14px;background:#081729;color:#fff;border:1px solid rgba(125,211,252,.19);font:inherit}}
    .bmo-mic,.bmo-send{{min-width:48px;height:48px;border-radius:15px;border:1px solid rgba(255,255,255,.12);color:#fff;font-weight:900;cursor:pointer}}
    .bmo-mic{{background:#172b40;font-size:21px}}.bmo-mic.on{{background:#8d285e}}.bmo-send{{background:#2563eb;padding:0 15px}}
    .bmo-side{{padding:16px;height:max-content;position:sticky;top:12px}}
    .bmo-side h3{{margin:0 0 10px}}.bmo-quick{{display:grid;gap:8px}}
    .bmo-quick button,.bmo-upload-label{{width:100%;text-align:left;padding:11px 12px;border-radius:13px;border:1px solid rgba(148,163,184,.13);background:#0c1c30;color:#fff;cursor:pointer;font-weight:800;font-size:12px}}
    .bmo-upload{{margin-top:16px;padding-top:14px;border-top:1px solid rgba(148,163,184,.12)}}
    .bmo-upload input[type=file]{{width:100%;font-size:11px;color:#b9c7d8;margin:6px 0}}
    .bmo-upload button{{width:100%;margin-top:7px}}
    .bmo-voice-row{{display:flex;gap:8px;align-items:center;margin-top:10px;color:#9fb1c8;font-size:11px}}

    .bmo-avatar-wrap{{display:flex;flex-direction:column;align-items:center;justify-content:center}}
    .bmo-audio-bars{{height:24px;display:flex;align-items:center;gap:4px;margin-top:9px;opacity:.28;transition:.2s}}
    .bmo-audio-bars i{{display:block;width:4px;height:7px;border-radius:5px;background:linear-gradient(#f5b1cf,#f05b9d);transform-origin:center}}
    .bmo-avatar.listening + .bmo-audio-bars,.bmo-avatar.speaking + .bmo-audio-bars{{opacity:1}}
    .bmo-avatar.listening + .bmo-audio-bars i,.bmo-avatar.speaking + .bmo-audio-bars i{{animation:bmoTalk .62s ease-in-out infinite alternate}}
    .bmo-avatar.listening + .bmo-audio-bars i:nth-child(2),.bmo-avatar.speaking + .bmo-audio-bars i:nth-child(2){{animation-delay:.12s}}
    .bmo-avatar.listening + .bmo-audio-bars i:nth-child(3),.bmo-avatar.speaking + .bmo-audio-bars i:nth-child(3){{animation-delay:.24s}}
    .bmo-avatar.listening + .bmo-audio-bars i:nth-child(4),.bmo-avatar.speaking + .bmo-audio-bars i:nth-child(4){{animation-delay:.08s}}
    .bmo-avatar.listening + .bmo-audio-bars i:nth-child(5),.bmo-avatar.speaking + .bmo-audio-bars i:nth-child(5){{animation-delay:.19s}}
    @keyframes bmoTalk{{to{{height:23px;transform:scaleY(.96)}}}}
    .bmo-voice-status{{min-height:18px;margin-top:2px;font-size:11px;color:#a8bbcf;text-align:center}}
    .bmo-attach{{display:none;min-width:48px;height:48px;border-radius:15px;border:1px solid rgba(255,255,255,.12);background:#172b40;color:#fff;font-size:18px;cursor:pointer}}
    /* BODYMIND_R48_SECRETARY_VOICE_STAGE */
    .bmo-avatar{{cursor:pointer}}
    .bmo-voice-stage{{position:fixed;inset:0;z-index:5000;background:radial-gradient(circle at 50% 38%,rgba(175,42,105,.28),transparent 30%),linear-gradient(180deg,#07111f 0%,#100b16 100%);display:grid;place-items:center;padding:24px;box-sizing:border-box}}
    .bmo-voice-stage[hidden]{{display:none!important}}
    .bmo-voice-stage-inner{{width:min(760px,96vw);min-height:min(760px,88dvh);display:flex;flex-direction:column;align-items:center;justify-content:center;position:relative;text-align:center}}
    .bmo-voice-close{{position:absolute;right:0;top:0;width:44px;height:44px;border-radius:50%;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:#fff;font-size:22px;cursor:pointer}}
    .bmo-voice-orb{{width:clamp(190px,38vw,330px);height:clamp(190px,38vw,330px);border-radius:50%;display:grid;place-items:center;position:relative;background:radial-gradient(circle at 45% 40%,rgba(244,90,157,.34),rgba(15,24,40,.92) 58%,#07111f 76%);box-shadow:0 0 0 1px rgba(255,255,255,.08),0 0 95px rgba(244,90,157,.22);cursor:pointer;transition:.2s}}
    .bmo-voice-orb:before,.bmo-voice-orb:after{{content:"";position:absolute;border-radius:50%;inset:-18px;border:1px solid rgba(244,90,157,.22);opacity:.55}}
    .bmo-voice-orb:after{{inset:-38px;border-color:rgba(56,189,248,.16)}}
    .bmo-voice-orb.listening:before,.bmo-voice-orb.speaking:before{{animation:bmoVoiceRing 1.15s infinite}}
    .bmo-voice-orb.listening:after,.bmo-voice-orb.speaking:after{{animation:bmoVoiceRing 1.15s .35s infinite}}
    .bmo-voice-orb img{{width:58%;height:58%;object-fit:contain;filter:drop-shadow(0 18px 28px rgba(0,0,0,.42))}}
    @keyframes bmoVoiceRing{{50%{{transform:scale(1.055);opacity:.18}}}}
    .bmo-voice-stage-state{{margin-top:52px;font-size:14px;text-transform:uppercase;letter-spacing:.13em;font-weight:900;color:#f4a9ca}}
    .bmo-voice-stage-text{{margin-top:15px;max-width:680px;min-height:74px;font-size:clamp(22px,4vw,38px);line-height:1.18;font-weight:750;color:#fff}}
    .bmo-voice-stage-hint{{margin-top:18px;color:#9db0c5;font-size:13px}}
    .bmo-voice-bars{{display:flex;gap:6px;height:36px;align-items:center;margin-top:18px;opacity:.45}}
    .bmo-voice-bars i{{display:block;width:5px;height:8px;border-radius:10px;background:#f05b9d}}
    .bmo-voice-orb.listening~.bmo-voice-bars,.bmo-voice-orb.speaking~.bmo-voice-bars{{opacity:1}}
    .bmo-voice-orb.listening~.bmo-voice-bars i,.bmo-voice-orb.speaking~.bmo-voice-bars i{{animation:bmoTalk .55s ease-in-out infinite alternate}}
    .bmo-voice-bars i:nth-child(2){{animation-delay:.08s}}.bmo-voice-bars i:nth-child(3){{animation-delay:.16s}}.bmo-voice-bars i:nth-child(4){{animation-delay:.24s}}.bmo-voice-bars i:nth-child(5){{animation-delay:.12s}}
    .bmo-secure-modal{{position:fixed;inset:0;z-index:5100;background:rgba(2,8,18,.82);display:grid;place-items:center;padding:18px}}
    .bmo-secure-modal[hidden]{{display:none!important}}
    .bmo-secure-card{{width:min(560px,96vw);background:#081729;border:1px solid rgba(125,211,252,.20);border-radius:24px;padding:22px;box-shadow:0 28px 90px rgba(0,0,0,.55)}}
    .bmo-secure-card h2{{margin:0 0 7px}}.bmo-secure-card p{{color:#9fb1c8;font-size:12px;line-height:1.5}}
    .bmo-secure-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}.bmo-secure-grid label{{font-size:11px;color:#b8c7d9;display:grid;gap:5px}}
    .bmo-secure-grid input,.bmo-secure-grid select{{width:100%;box-sizing:border-box;border-radius:12px;border:1px solid rgba(125,211,252,.18);background:#06111f;color:#fff;padding:11px}}
    .bmo-secure-wide{{grid-column:1/-1}}.bmo-secure-actions{{display:flex;justify-content:flex-end;gap:8px;margin-top:14px}}
    @media(max-width:640px){{.bmo-secure-grid{{grid-template-columns:1fr}}.bmo-secure-wide{{grid-column:auto}}.bmo-voice-stage{{padding:12px}}.bmo-voice-stage-inner{{min-height:88dvh}}}}

    /* BODYMIND_R38_MOBILE: compact, chat-first, no dashboard-card clutter on iPhone */
    /* BODYMIND_R39_IPHONE_LAYOUT_V2 */
    @media(max-width:800px){{
      .bmo{{max-width:none;width:100%;margin:0;padding:0 8px calc(158px + env(safe-area-inset-bottom));box-sizing:border-box;overflow-x:hidden;}}
      .bmo-hero{{position:sticky;top:0;z-index:18;display:grid;grid-template-columns:46px minmax(0,1fr);gap:9px;align-items:center;text-align:left;padding:8px 9px;margin:0 -2px;border-radius:14px;box-shadow:none;background:rgba(7,16,31,.96);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);}}
      .bmo-avatar-wrap{{display:block;min-width:0;}}
      .bmo-avatar{{width:44px;height:44px;margin:0;}}
      .bmo-avatar img{{width:32px;height:32px;}}
      .bmo-audio-bars,.bmo-voice-status,.bmo-kicker,.bmo-hero p{{display:none!important;}}
      .bmo-hero>div:last-child{{display:block;min-width:0;}}
      .bmo-hero h1{{font-size:17px;line-height:1.1;margin:0 0 4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
      .bmo-status{{display:flex;gap:0;margin:0;min-width:0;}}
      .bmo-status .bmo-pill{{display:none;}}
      .bmo-status #bmoAiPill{{display:inline-flex;align-items:center;max-width:100%;font-size:10px;padding:4px 7px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;border-color:rgba(244,90,157,.25);background:rgba(244,90,157,.09);}}
      .bmo-status #bmoVoiceRecover:not([hidden]){{display:inline-flex!important;align-items:center;margin-left:5px;font-size:10px;padding:4px 7px;border-color:rgba(56,189,248,.30);background:rgba(56,189,248,.10);}}
      .bmo-grid{{display:block;margin-top:6px;}}
      .bmo-side{{display:none!important;}}
      .bmo-chat{{min-height:calc(100vh - 145px);min-height:calc(100dvh - 145px);border-radius:15px;border:1px solid rgba(148,163,184,.12);overflow:visible;background:rgba(7,16,31,.88);}}
      .bmo-messages{{height:calc(100vh - 292px);height:calc(100dvh - 292px);min-height:260px;max-height:none;padding:11px 7px 16px;gap:9px;overflow-y:auto;overscroll-behavior:contain;-webkit-overflow-scrolling:touch;}}
      .bmo-msg{{max-width:94%;padding:10px 11px;border-radius:15px;font-size:14px;line-height:1.4;overflow-wrap:anywhere;}}
      .bmo-cards{{display:grid;grid-template-columns:1fr 1fr;gap:6px;}}
      .bmo-card{{min-width:0;padding:8px 9px;border-radius:11px;overflow:hidden;}}
      .bmo-card strong{{font-size:18px;}}
      .bmo-links{{gap:6px;}}
      .bmo-link{{padding:7px 8px;border-radius:10px;font-size:10px;}}
      .bmo-compose{{position:fixed;left:max(8px,env(safe-area-inset-left));right:max(8px,env(safe-area-inset-right));bottom:calc(76px + env(safe-area-inset-bottom));z-index:999;display:grid;grid-template-columns:42px 36px minmax(0,1fr) 42px;gap:5px;align-items:center;width:auto;max-width:none;box-sizing:border-box;overflow:hidden;padding:7px;border:1px solid rgba(148,163,184,.16);border-radius:18px;background:rgba(5,12,23,.985);box-shadow:0 12px 32px rgba(0,0,0,.34);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);}}
      .bmo-compose>*{{min-width:0;box-sizing:border-box;}}
      .bmo-compose>button,.bmo-compose>textarea{{margin:0!important;}}
      /* BODYMIND_R39_IPHONE_FILE_PICKER_DYNAMIC */
      .bmo-mic{{min-width:42px;width:42px;height:42px;border-radius:50%;font-size:20px;background:linear-gradient(145deg,#8d285e,#d43a7d);box-shadow:none;touch-action:manipulation;}}
      .bmo-mic.on{{box-shadow:0 0 0 4px rgba(244,90,157,.12);}}
      .bmo-attach{{display:block;min-width:36px;width:36px;height:36px;align-self:center;border-radius:11px;font-size:16px;padding:0;touch-action:manipulation;}}
      .bmo-compose textarea{{width:100%;min-width:0;max-width:100%;min-height:42px;height:42px;max-height:84px;resize:none;padding:10px 10px;align-self:center;border-radius:12px;font-size:16px;line-height:20px;box-sizing:border-box;overflow-y:auto;}}
      .bmo-send{{min-width:42px!important;width:42px!important;max-width:42px!important;height:42px!important;padding:0!important;align-self:center;font-size:17px!important;line-height:1!important;border-radius:12px;touch-action:manipulation;white-space:nowrap!important;overflow:hidden!important;}}
      .bmo-send::before,.bmo-send::after{{content:none!important;display:none!important;}}
    }}
    /* BODYMIND_R49_CHATGPT_STYLE_SECRETARY */
    .bmo{{max-width:100%;width:100%;min-height:calc(100dvh - 82px);padding:0!important;margin:0!important;display:flex;flex-direction:column;background:#0b0f14}}
    .bmo-hero{{position:sticky!important;top:0;z-index:100!important;display:flex!important;align-items:center!important;justify-content:space-between!important;gap:12px!important;padding:10px 16px!important;margin:0!important;border:0!important;border-bottom:1px solid rgba(255,255,255,.08)!important;border-radius:0!important;background:rgba(11,15,20,.94)!important;box-shadow:none!important;backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px)}}
    .bmo-brand{{display:flex;align-items:center;gap:10px;min-width:0}}
    .bmo-avatar-wrap{{display:block!important}}
    .bmo-avatar{{width:38px!important;height:38px!important;margin:0!important;background:transparent!important;box-shadow:none!important;border:0!important;border-radius:12px!important}}
    .bmo-avatar:after{{display:none!important}}
    .bmo-avatar img{{width:36px!important;height:36px!important;object-fit:contain!important;filter:none!important}}
    .bmo-brand-copy{{display:grid;gap:1px;min-width:0}}
    .bmo-brand-title{{font-size:15px;font-weight:750;line-height:1.2;color:#f8fafc;white-space:nowrap}}
    .bmo-brand-sub{{display:flex;align-items:center;gap:6px;font-size:11px;color:#8f9bab;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
    #bmoAiPill{{padding:0!important;border:0!important;background:transparent!important;color:#8f9bab!important;font-size:11px!important}}
    .bmo-top-actions{{display:flex;align-items:center;gap:7px}}
    .bmo-top-btn{{height:34px;border:1px solid rgba(255,255,255,.10);border-radius:10px;background:#151b23;color:#e5e7eb;padding:0 10px;font-size:12px;font-weight:700;cursor:pointer}}
    .bmo-top-btn.icon{{width:34px;padding:0;font-size:16px}}
    #bmoVoiceRecover{{height:34px!important;padding:0 9px!important;border-radius:10px!important}}
    .bmo-kicker,.bmo-hero h1,.bmo-hero p,.bmo-status>.bmo-pill:not(#bmoAiPill):not(#bmoVoiceRecover),.bmo-audio-bars,.bmo-voice-status{{display:none!important}}
    .bmo-grid{{display:block!important;flex:1!important;margin:0!important}}
    .bmo-chat{{width:100%!important;min-height:calc(100dvh - 136px)!important;border:0!important;border-radius:0!important;background:#0b0f14!important;display:flex!important;flex-direction:column!important;overflow:visible!important}}
    .bmo-side{{display:none!important}}
    .bmo-messages{{width:min(820px,100%)!important;margin:0 auto!important;padding:26px 18px 190px!important;box-sizing:border-box!important;display:flex!important;flex-direction:column!important;gap:24px!important;flex:1!important;max-height:none!important;height:auto!important;overflow:visible!important}}
    .bmo-empty{{min-height:52dvh;display:grid;place-items:center;text-align:center;padding:40px 18px;color:#e5e7eb}}
    .bmo-empty[hidden]{{display:none!important}}
    .bmo-empty-inner{{max-width:560px}}
    .bmo-empty-logo{{width:76px;height:76px;object-fit:contain;margin-bottom:18px}}
    .bmo-empty h1{{font-size:clamp(25px,4vw,34px);margin:0 0 10px;letter-spacing:-.025em}}
    .bmo-empty p{{margin:0;color:#9ca3af;line-height:1.55;font-size:14px}}
    .bmo-starters{{display:flex;flex-wrap:wrap;justify-content:center;gap:8px;margin-top:20px}}
    .bmo-starters button{{border:1px solid rgba(255,255,255,.10);background:#151b23;color:#dbe3ee;border-radius:999px;padding:9px 12px;font-size:12px;cursor:pointer}}
    .bmo-msg-row{{display:flex;align-items:flex-start;gap:11px;width:100%;box-sizing:border-box}}
    .bmo-msg-row.me{{justify-content:flex-end}}
    .bmo-msg-avatar{{width:28px;height:28px;border-radius:8px;object-fit:contain;flex:0 0 28px;margin-top:2px}}
    .bmo-msg{{max-width:min(78%,690px)!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;color:#e8edf3!important;line-height:1.65!important;font-size:14.5px!important;white-space:pre-wrap;overflow-wrap:anywhere}}
    .bmo-msg.me{{padding:10px 14px!important;border-radius:18px!important;background:#262d36!important;color:#fff!important}}
    .bmo-msg.bot{{padding-top:2px!important}}
    .bmo-cards,.bmo-links{{margin-top:11px!important}}
    .bmo-card{{background:#151b23!important;border-color:rgba(255,255,255,.09)!important}}
    .bmo-compose-shell{{position:fixed;left:0;right:0;bottom:0;z-index:999;padding:16px 14px calc(18px + env(safe-area-inset-bottom));background:linear-gradient(180deg,rgba(11,15,20,0),#0b0f14 24%,#0b0f14)}}
    .bmo-compose{{width:min(820px,calc(100% - 12px))!important;margin:0 auto!important;position:relative!important;left:auto!important;right:auto!important;bottom:auto!important;display:grid!important;grid-template-columns:38px minmax(0,1fr) 38px 38px!important;gap:6px!important;align-items:end!important;padding:8px!important;border:1px solid rgba(255,255,255,.12)!important;border-radius:24px!important;background:#171c23!important;box-shadow:0 12px 36px rgba(0,0,0,.30)!important}}
    .bmo-compose textarea{{width:100%!important;min-height:40px!important;height:40px!important;max-height:150px!important;resize:none!important;padding:9px 8px!important;background:transparent!important;border:0!important;outline:0!important;color:#f8fafc!important;font-size:15px!important;line-height:22px!important}}
    .bmo-compose textarea::placeholder{{color:#7f8996}}
    .bmo-mic,.bmo-send,.bmo-attach{{display:grid!important;place-items:center;min-width:38px!important;width:38px!important;height:38px!important;padding:0!important;border-radius:50%!important;border:0!important;background:transparent!important;color:#d6dde6!important;font-size:18px!important;box-shadow:none!important}}
    .bmo-attach:hover,.bmo-mic:hover{{background:#242b34!important}}
    .bmo-mic.on{{background:#7f1d4e!important;color:#fff!important}}
    .bmo-send{{background:#f3f4f6!important;color:#111827!important;font-size:16px!important}}
    .bmo-send:disabled{{opacity:.45}}
    .bmo-compose-note{{width:min(820px,calc(100% - 24px));margin:7px auto 0;text-align:center;color:#6f7a87;font-size:10px}}
    .bmo-hidden-tools{{display:none!important}}
    @media(max-width:800px){{
      .bmo{{padding:0!important;min-height:calc(100dvh - 70px)!important}}
      .bmo-hero{{padding:8px 10px!important}}
      .bmo-brand-title{{font-size:14px}}
      .bmo-top-btn span{{display:none}}
      .bmo-top-btn{{width:34px;padding:0;font-size:16px}}
      .bmo-chat{{min-height:calc(100dvh - 118px)!important}}
      .bmo-messages{{padding:20px 12px 172px!important;gap:20px!important}}
      .bmo-msg{{max-width:88%!important;font-size:14px!important}}
      .bmo-msg-row.bot .bmo-msg{{max-width:calc(100% - 40px)!important}}
      .bmo-compose-shell{{padding:10px 7px calc(10px + env(safe-area-inset-bottom))!important}}
      .bmo-compose{{width:100%!important;grid-template-columns:38px minmax(0,1fr) 38px 38px!important;border-radius:22px!important}}
      .bmo-empty{{min-height:48dvh;padding:24px 10px}}
      .bmo-starters{{display:grid;grid-template-columns:1fr 1fr}}
      .bmo-starters button{{text-align:left;border-radius:14px}}
    }}
    /* BODYMIND_R52_CHAT_NATIVE_UI
       Final layout authority: conversational shell, not dashboard. */
    :root{{--bmo-bg:#171717;--bmo-panel:#212121;--bmo-soft:#2f2f2f;--bmo-line:rgba(255,255,255,.09);--bmo-text:#ececec;--bmo-muted:#a7a7a7}}
    .bmo{{position:fixed!important;inset:0!important;z-index:9000!important;width:100vw!important;height:100dvh!important;min-height:0!important;margin:0!important;padding:0!important;overflow:hidden!important;background:var(--bmo-bg)!important;color:var(--bmo-text)!important}}
    .bmo-hero{{position:relative!important;top:auto!important;z-index:2!important;flex:0 0 56px!important;height:56px!important;box-sizing:border-box!important;padding:8px 14px!important;background:rgba(23,23,23,.96)!important;border:0!important;border-bottom:1px solid var(--bmo-line)!important}}
    .bmo-brand{{gap:9px!important}} .bmo-avatar{{width:34px!important;height:34px!important;border-radius:10px!important}} .bmo-avatar img{{width:32px!important;height:32px!important}}
    .bmo-brand-title{{font-size:14px!important;font-weight:700!important}} .bmo-brand-sub{{font-size:10.5px!important;color:var(--bmo-muted)!important}}
    .bmo-top-actions{{gap:6px!important}} .bmo-top-btn{{height:34px!important;background:transparent!important;border:1px solid var(--bmo-line)!important;border-radius:9px!important;color:#ddd!important}}
    .bmo-grid{{display:flex!important;flex:1!important;min-height:0!important;margin:0!important;overflow:hidden!important}}
    .bmo-chat{{display:flex!important;flex-direction:column!important;flex:1!important;min-height:0!important;height:100%!important;background:var(--bmo-bg)!important;border:0!important;overflow:hidden!important}}
    .bmo-side{{display:none!important}}
    .bmo-messages{{flex:1 1 auto!important;min-height:0!important;height:auto!important;max-height:none!important;overflow-y:auto!important;overscroll-behavior:contain!important;-webkit-overflow-scrolling:touch!important;width:100%!important;max-width:none!important;margin:0!important;padding:28px max(16px,calc((100vw - 820px)/2)) 24px!important;box-sizing:border-box!important;gap:22px!important;scrollbar-gutter:stable}}
    .bmo-msg-row{{width:100%!important;max-width:820px!important;margin:0 auto!important;gap:12px!important}}
    .bmo-msg-row.me{{justify-content:flex-end!important}}
    .bmo-msg-avatar{{width:28px!important;height:28px!important;flex:0 0 28px!important;border-radius:8px!important}}
    .bmo-msg{{font-size:15px!important;line-height:1.62!important;color:var(--bmo-text)!important;max-width:calc(100% - 46px)!important;white-space:pre-wrap!important}}
    .bmo-msg.bot{{background:transparent!important;padding:2px 0!important;border:0!important}}
    .bmo-msg.me{{background:var(--bmo-soft)!important;padding:10px 15px!important;border-radius:18px!important;max-width:min(72%,620px)!important}}
    .bmo-card{{background:#252525!important;border:1px solid var(--bmo-line)!important;color:var(--bmo-text)!important}}
    .bmo-link{{background:#292929!important;border:1px solid var(--bmo-line)!important;color:#eee!important;border-radius:10px!important}}
    .bmo-empty{{flex:1!important;min-height:0!important;height:100%!important;padding:36px 18px!important;box-sizing:border-box!important}}
    .bmo-empty-logo{{width:64px!important;height:64px!important;margin-bottom:16px!important}} .bmo-empty h1{{font-size:30px!important}} .bmo-empty p{{color:var(--bmo-muted)!important}}
    .bmo-starters{{gap:8px!important}} .bmo-starters button{{background:#242424!important;border:1px solid var(--bmo-line)!important;color:#ddd!important}}
    .bmo-compose-shell{{position:relative!important;left:auto!important;right:auto!important;bottom:auto!important;z-index:3!important;flex:0 0 auto!important;width:100%!important;padding:8px 12px calc(10px + env(safe-area-inset-bottom))!important;box-sizing:border-box!important;background:linear-gradient(180deg,rgba(23,23,23,0),var(--bmo-bg) 18%)!important}}
    .bmo-compose{{position:relative!important;left:auto!important;right:auto!important;bottom:auto!important;width:min(800px,100%)!important;max-width:800px!important;margin:0 auto!important;display:grid!important;grid-template-columns:38px minmax(0,1fr) 38px 38px!important;gap:6px!important;align-items:end!important;padding:8px!important;background:#2f2f2f!important;border:1px solid rgba(255,255,255,.08)!important;border-radius:24px!important;box-shadow:0 5px 20px rgba(0,0,0,.18)!important}}
    .bmo-compose textarea{{width:100%!important;min-height:40px!important;height:40px!important;max-height:132px!important;padding:9px 7px!important;background:transparent!important;border:0!important;outline:0!important;resize:none!important;color:#f1f1f1!important;font-size:16px!important;line-height:22px!important;overflow-y:auto!important}}
    .bmo-compose textarea::placeholder{{color:#999!important}}
    .bmo-mic,.bmo-send,.bmo-attach{{display:grid!important;place-items:center!important;width:38px!important;height:38px!important;min-width:38px!important;padding:0!important;border:0!important;border-radius:50%!important;box-shadow:none!important}}
    .bmo-attach,.bmo-mic{{background:transparent!important;color:#ddd!important}} .bmo-attach:hover,.bmo-mic:hover{{background:#3b3b3b!important}}
    .bmo-mic.on{{background:#6f2448!important;color:#fff!important}} .bmo-send{{background:#f4f4f4!important;color:#181818!important}}
    .bmo-compose-note{{margin:5px auto 0!important;color:#777!important;font-size:10px!important}}
    .bmo-voice-stage{{z-index:10020!important;background:#171717!important;padding:18px!important}}
    .bmo-voice-stage-inner{{width:min(680px,100%)!important;min-height:100%!important}}
    .bmo-voice-orb{{width:170px!important;height:170px!important;background:#242424!important;box-shadow:0 0 0 1px var(--bmo-line)!important}}
    .bmo-voice-orb:before,.bmo-voice-orb:after{{display:none!important}}
    .bmo-voice-stage-state{{margin-top:36px!important;color:#bbb!important;font-size:12px!important}}
    .bmo-voice-stage-text{{font-size:clamp(22px,4vw,34px)!important;max-width:620px!important}}
    .bmo-voice-stage-hint{{color:#888!important}}
    .bmo-secure-modal{{z-index:10030!important;background:rgba(0,0,0,.72)!important}} .bmo-secure-card{{background:#242424!important;border-color:var(--bmo-line)!important}}
    @media(max-width:800px){{
      .bmo-hero{{height:52px!important;flex-basis:52px!important;padding:7px 10px!important}}
      .bmo-top-btn span{{display:none!important}} .bmo-top-btn{{width:34px!important;padding:0!important}}
      .bmo-messages{{padding:20px 12px 16px!important;gap:18px!important}}
      .bmo-msg{{font-size:14.5px!important;max-width:calc(100% - 40px)!important}}
      .bmo-msg.me{{max-width:86%!important}}
      .bmo-compose-shell{{padding:7px 7px calc(8px + env(safe-area-inset-bottom))!important}}
      .bmo-compose{{width:100%!important;border-radius:22px!important}}
      .bmo-compose-note{{display:none!important}}
      .bmo-starters{{display:grid!important;grid-template-columns:1fr!important;width:min(430px,100%)!important}}
      .bmo-starters button{{text-align:left!important;border-radius:13px!important}}
    }}
    </style>

    <main class="bmo">
      <header class="bmo-hero">
        <div class="bmo-brand">
          <div class="bmo-avatar-wrap">
            <div class="bmo-avatar" id="bmoAvatar" title="Parla con Segreteria BodyMind"><img src="/bodymind-media/logo" alt="BodyMind"></div>
          </div>
          <div class="bmo-brand-copy">
            <div class="bmo-brand-title">Segreteria BodyMind</div>
            <div class="bmo-brand-sub">
              <span id="bmoAiPill">IA Cloud · {"configurata" if (os.environ.get("BODYMIND_AI_CLOUD") and os.environ.get("OPENAI_API_KEY")) else "non configurata"}</span>
              <button class="bmo-pill" id="bmoVoiceRecover" type="button" hidden>🔊 Ascolta</button>
            </div>
          </div>
        </div>
        <div class="bmo-top-actions">
          <a class="bmo-top-btn icon" href="/" title="Torna al gestionale" aria-label="Torna al gestionale" style="display:grid;place-items:center;text-decoration:none">←</a>
          <button class="bmo-top-btn" id="bmoNewChat" type="button" title="Nuova conversazione">＋ <span>Nuova chat</span></button>
          <button class="bmo-top-btn icon" id="bmoSettings" type="button" title="Impostazioni segreteria" aria-label="Impostazioni">⚙</button>
        </div>
      </header>

      <section class="bmo-grid">
        <div class="bmo-chat">
          <div class="bmo-messages" id="bmoMessages">
            <div class="bmo-empty" id="bmoEmpty">
              <div class="bmo-empty-inner">
                <img class="bmo-empty-logo" src="/bodymind-media/logo" alt="BodyMind">
                <h1>Ciao, {ident}. Come posso aiutarti?</h1>
                <p>Sono la Segreteria BodyMind. Conosco il gestionale e posso cercare, controllare, preparare documenti e operazioni, lavorare con tesserati e collaboratori e usare gli strumenti reali quando serve.</p>
                <div class="bmo-starters">
                  <button data-q="Controlla BodyMind e dimmi cosa richiede attenzione">Controlla BodyMind</button>
                  <button data-q="Quali documenti sono da verificare?">Documenti da verificare</button>
                  <button data-q="Chi non ha il certificato medico valido?">Certificati medici</button>
                  <button data-q="Fammi un riepilogo operativo della segreteria">Riepilogo segreteria</button>
                </div>
              </div>
            </div>
          </div>
          <div class="bmo-compose-shell">
            <div class="bmo-compose">
              <button class="bmo-attach" id="bmoAttach" type="button" title="Allega file" aria-label="Allega file">＋</button>
              <textarea id="bmoInput" placeholder="Messaggio a Segreteria BodyMind" autocomplete="off"></textarea>
              <button class="bmo-mic" id="bmoMic" type="button" title="Parla" aria-label="Parla con Segreteria BodyMind">🎙</button>
              <button class="bmo-send" id="bmoSend" type="button" aria-label="Invia" title="Invia">↑</button>
            </div>
            <div class="bmo-compose-note">Le operazioni che modificano dati richiedono conferma quando necessario.</div>
          </div>
        </div>

        <aside class="bmo-side bmo-hidden-tools" aria-hidden="true">
          <form id="bmoUploadForm" enctype="multipart/form-data">
            <input type="file" name="files" id="bmoFiles" multiple accept=".pdf,.png,.jpg,.jpeg,.webp,.docx">
            <input type="file" name="folder" id="bmoFolder" multiple webkitdirectory directory>
            <select id="bmoUploadType">
              <option value="">Riconosci automaticamente</option>
              <option value="modulo_unico_tesseramento">Modulo Unico / iscrizione</option>
              <option value="certificato_medico">Certificato medico</option>
              <option value="documento_identita">Documento identità</option>
            </select>
            <input type="checkbox" id="bmoProductionMode" checked>
            <button type="submit">Analizza</button>
          </form>
          <input type="checkbox" id="bmoVoice" checked>
          <div id="bmoVoiceStatus">Pronto</div>
        </aside>
      </section>
    </main>

    <div class="bmo-voice-stage" id="bmoVoiceStage" hidden>
      <div class="bmo-voice-stage-inner">
        <button class="bmo-voice-close" id="bmoVoiceStageClose" type="button" aria-label="Chiudi">×</button>
        <div class="bmo-voice-orb" id="bmoVoiceOrb" role="button" tabindex="0" aria-label="Parla con il segretario BodyMind">
          <img src="/bodymind-media/logo" alt="BodyMind">
        </div>
        <div class="bmo-voice-bars" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div>
        <div class="bmo-voice-stage-state" id="bmoVoiceStageState">Segretario BodyMind</div>
        <div class="bmo-voice-stage-text" id="bmoVoiceStageText">Tocca e parlami.</div>
        <div class="bmo-voice-stage-hint" id="bmoVoiceStageHint">La conversazione viene trascritta anche nella chat.</div>
      </div>
    </div>

    <div class="bmo-secure-modal" id="bmoSmtpModal" hidden>
      <div class="bmo-secure-card">
        <h2>Configura SMTP</h2>
        <p>Le credenziali vengono cifrate nel backend e non vengono inviate al modello IA. Per Gmail usa normalmente una password per app o le credenziali previste dal tuo account.</p>
        <div class="bmo-secure-grid">
          <label>Provider
            <select id="bmoSmtpProvider"><option value="gmail">Gmail</option><option value="custom">Altro SMTP</option></select>
          </label>
          <label>Sicurezza
            <select id="bmoSmtpSecurity"><option value="starttls">STARTTLS</option><option value="ssl">SSL/TLS</option><option value="plain">Nessuna</option></select>
          </label>
          <label class="bmo-secure-wide">Host
            <input id="bmoSmtpHost" value="smtp.gmail.com" autocomplete="off">
          </label>
          <label>Porta
            <input id="bmoSmtpPort" type="number" value="587" min="1" max="65535">
          </label>
          <label>Nome mittente
            <input id="bmoSmtpFromName" value="BodyMind Aerial Studio" autocomplete="off">
          </label>
          <label class="bmo-secure-wide">Utente / email
            <input id="bmoSmtpUser" type="email" autocomplete="username">
          </label>
          <label class="bmo-secure-wide">Password / app-password
            <input id="bmoSmtpPassword" type="password" autocomplete="new-password" placeholder="Non viene inviata all’IA">
          </label>
        </div>
        <div id="bmoSmtpStatus" class="small-muted" style="margin-top:10px"></div>
        <div class="bmo-secure-actions">
          <button class="bmo-pill" id="bmoSmtpCancel" type="button">Annulla</button>
          <button class="bmo-send" id="bmoSmtpSave" type="button">Salva e testa</button>
        </div>
      </div>
    </div>

    <script>
    (()=>{{
      const csrf={json.dumps(csrf)};
      const initialHistory={history_json};
      const messages=document.getElementById('bmoMessages');
      const emptyState=document.getElementById('bmoEmpty');
      const newChat=document.getElementById('bmoNewChat');
      const settings=document.getElementById('bmoSettings');
      const input=document.getElementById('bmoInput');
      const send=document.getElementById('bmoSend');
      const mic=document.getElementById('bmoMic');
      const avatar=document.getElementById('bmoAvatar');
      const voice=document.getElementById('bmoVoice');
      const voiceStatus=document.getElementById('bmoVoiceStatus');
      const voiceRecover=document.getElementById('bmoVoiceRecover');
      const attach=document.getElementById('bmoAttach');
      const voiceStage=document.getElementById('bmoVoiceStage');
      const voiceStageClose=document.getElementById('bmoVoiceStageClose');
      const voiceOrb=document.getElementById('bmoVoiceOrb');
      const voiceStageState=document.getElementById('bmoVoiceStageState');
      const voiceStageText=document.getElementById('bmoVoiceStageText');
      const voiceStageHint=document.getElementById('bmoVoiceStageHint');
      const smtpModal=document.getElementById('bmoSmtpModal');
      const smtpStatus=document.getElementById('bmoSmtpStatus');
      let voiceStageOpen=false;
      let lastSpeechText='';
      function setVoiceStage(state,text,hint=''){{
        if(voiceStageState)voiceStageState.textContent=String(state||'Segretario BodyMind');
        if(voiceStageText && text!==undefined)voiceStageText.textContent=String(text||'');
        if(voiceStageHint && hint)voiceStageHint.textContent=String(hint);
      }}
      function openVoiceStage(){{
        voiceStageOpen=true;
        if(voiceStage)voiceStage.hidden=false;
        document.documentElement.style.overflow='hidden';
        setVoiceStage('Segretario BodyMind','Tocca e parlami.','La conversazione viene trascritta anche nella chat.');
      }}
      function closeVoiceStage(){{
        voiceStageOpen=false;
        if(voiceStage)voiceStage.hidden=true;
        document.documentElement.style.overflow='';
      }}
      async function openSmtpSetup(){{
        if(!smtpModal)return;
        smtpModal.hidden=false;
        if(smtpStatus)smtpStatus.textContent='Carico configurazione…';
        try{{
          const r=await fetch('/operatore-bodymind/secure/smtp',{{headers:{{'Cache-Control':'no-cache'}}}});
          const d=await r.json();
          const s=d.smtp||{{}};
          document.getElementById('bmoSmtpProvider').value=s.provider||'gmail';
          document.getElementById('bmoSmtpHost').value=s.host||'smtp.gmail.com';
          document.getElementById('bmoSmtpPort').value=String(s.port||587);
          document.getElementById('bmoSmtpSecurity').value=s.security||'starttls';
          document.getElementById('bmoSmtpFromName').value=s.from_name||'BodyMind Aerial Studio';
          if(smtpStatus)smtpStatus.textContent=s.configured
            ?('Configurato per '+(s.username||'utente')+(s.last_test_ok?' · test riuscito':' · da ritestare'))
            :'Non ancora configurato.';
        }}catch(e){{if(smtpStatus)smtpStatus.textContent='Non riesco a leggere lo stato SMTP.'}}
      }}
      function closeSmtpSetup(){{if(smtpModal)smtpModal.hidden=true}}
      voiceStageClose?.addEventListener('click',closeVoiceStage);
      document.getElementById('bmoSmtpCancel')?.addEventListener('click',closeSmtpSetup);
      settings?.addEventListener('click',openSmtpSetup);
      newChat?.addEventListener('click',async()=>{{
        try{{
          const r=await fetch('/operatore-bodymind/new-chat',{{method:'POST',headers:{{'X-CSRFToken':csrf}}}});
          const d=await r.json();
          if(!r.ok||!d.ok)throw new Error(d.text||'Errore');
          messages.querySelectorAll('.bmo-msg-row').forEach(n=>n.remove());
          if(emptyState)emptyState.hidden=false;
          input.value='';input.focus();
        }}catch(e){{addMsg('Non riesco ad aprire una nuova conversazione in questo momento.','bot')}}
      }});
      try{{
        const qs=new URLSearchParams(window.location.search);
        if(qs.get('smtp_setup')==='1')setTimeout(openSmtpSetup,120);
      }}catch(e){{}}
      document.getElementById('bmoSmtpProvider')?.addEventListener('change',ev=>{{
        if(ev.target.value==='gmail'){{
          document.getElementById('bmoSmtpHost').value='smtp.gmail.com';
          document.getElementById('bmoSmtpPort').value='587';
          document.getElementById('bmoSmtpSecurity').value='starttls';
        }}
      }});
      document.getElementById('bmoSmtpSave')?.addEventListener('click',async()=>{{
        const btn=document.getElementById('bmoSmtpSave');if(btn)btn.disabled=true;
        if(smtpStatus)smtpStatus.textContent='Salvo cifrato e provo la connessione…';
        try{{
          const payload={{
            provider:document.getElementById('bmoSmtpProvider').value,
            host:document.getElementById('bmoSmtpHost').value,
            port:Number(document.getElementById('bmoSmtpPort').value||0),
            security:document.getElementById('bmoSmtpSecurity').value,
            from_name:document.getElementById('bmoSmtpFromName').value,
            username:document.getElementById('bmoSmtpUser').value,
            password:document.getElementById('bmoSmtpPassword').value
          }};
          const r=await fetch('/operatore-bodymind/secure/smtp',{{
            method:'POST',headers:{{'Content-Type':'application/json','X-CSRFToken':csrf}},body:JSON.stringify(payload)
          }});
          const d=await r.json();
          if(smtpStatus)smtpStatus.textContent=d.text||'Operazione completata.';
          if(r.ok){{
            document.getElementById('bmoSmtpPassword').value='';
            addMsg('SMTP configurato e verificato.','bot',d);
            setTimeout(closeSmtpSetup,900);
          }}
        }}catch(e){{if(smtpStatus)smtpStatus.textContent='Errore durante la configurazione SMTP.'}}
        finally{{if(btn)btn.disabled=false}}
      }});

      function voiceDiag(stage,extra={{}}){{
        try{{
          fetch('/operatore-bodymind/voice-diag',{{
            method:'POST',
            headers:{{'Content-Type':'application/json','X-CSRFToken':csrf}},
            body:JSON.stringify(Object.assign({{
              stage:String(stage||''),
              cloud:true,
              ua:String(navigator.userAgent||'').slice(0,220)
            }},extra)),
            keepalive:true
          }}).catch(()=>{{}});
        }}catch(e){{}}
      }}
      async function refreshCloudStatus(showAlert=false){{
        const p=document.getElementById('bmoAiPill'); if(!p)return null;
        try{{
          const r=await fetch('/operatore-bodymind/cloud/status',{{headers:{{'Cache-Control':'no-cache'}}}});
          const d=await r.json();
          const b=d.budget||{{}};
          if(b.exhausted){{
            p.textContent='IA Cloud · CREDITO ESAURITO';
          }}else if(b.level==='critical'||b.level==='high'||b.level==='warning'){{
            p.textContent='IA Cloud · budget '+Math.round(b.percent||0)+'%';
          }}else{{
            p.textContent=d.ready?'IA Cloud · pronta':'IA Cloud · credito/configurazione';
          }}
          p.title='Modello: '+(d.model||'')+' · spesa stimata USD '+Number(b.estimated_spent_usd||0).toFixed(3)+' / USD '+Number(b.budget_usd||0).toFixed(2)+(d.last_ok_at?(' · ultimo successo '+d.last_ok_at):'');
          if(showAlert && b.level && b.level!=='ok'){{
            const key='bodymind-budget-'+b.level+'-'+Math.floor(Number(b.percent||0)/10);
            let seen='';try{{seen=localStorage.getItem('bodymind_budget_alert')||''}}catch(e){{}}
            if(seen!==key){{
              const msg=b.exhausted
                ?'⚠️ Credito API OpenAI esaurito. Ricarica il credito per continuare a usare l’Operatore cloud.'
                :'⚠️ Budget IA: uso stimato '+Math.round(b.percent||0)+'% (USD '+Number(b.estimated_spent_usd||0).toFixed(2)+' su USD '+Number(b.budget_usd||0).toFixed(2)+').';
              addMsg(msg,'bot');
              try{{localStorage.setItem('bodymind_budget_alert',key)}}catch(e){{}}
            }}
          }}
          return d;
        }}catch(e){{p.textContent='IA Cloud · stato non disponibile';return null}}
      }}
      refreshCloudStatus(true);

      function esc(s){{const d=document.createElement('div');d.textContent=String(s??'');return d.innerHTML}}
      function addMsg(text,who='bot',data={{}}){{
        if(emptyState)emptyState.hidden=true;
        const row=document.createElement('div');row.className='bmo-msg-row '+(who==='me'?'me':'bot');
        if(who!=='me'){{
          const av=document.createElement('img');av.className='bmo-msg-avatar';av.src='/bodymind-media/logo';av.alt='BodyMind';row.appendChild(av);
        }}
        const box=document.createElement('div');box.className='bmo-msg '+(who==='me'?'me':'bot');
        box.innerHTML=esc(text);
        if(data.cards?.length){{
          const w=document.createElement('div');w.className='bmo-cards';
          data.cards.forEach(c=>{{const a=document.createElement('a');a.className='bmo-card';a.href=c.href||'#';a.innerHTML='<span>'+esc(c.title)+'</span><strong>'+esc(c.value)+'</strong>';w.appendChild(a)}});
          box.appendChild(w);
        }}
        if(data.links?.length){{
          const w=document.createElement('div');w.className='bmo-links';
          data.links.forEach(l=>{{const a=document.createElement('a');a.className='bmo-link';a.href=l.href;a.textContent=l.label;w.appendChild(a)}});
          box.appendChild(w);
        }}
        row.appendChild(box);messages.appendChild(row);
        requestAnimationFrame(()=>{{messages.scrollTop=messages.scrollHeight}});
      }}
      if(Array.isArray(initialHistory)&&initialHistory.length){{
        initialHistory.forEach(m=>addMsg(m.message,m.speaker==='user'?'me':'bot',m.payload||{{}}));
      }}else if(emptyState){{
        emptyState.hidden=false;
      }}

      // R49: cloud-native intelligence and voice only.

      async function ask(q){{
        q=String(q||'').trim();if(!q)return;
        addMsg(q,'me');input.value='';send.disabled=true;
        if(voiceStageOpen)setVoiceStage('Sto lavorando',q,'Controllo il gestionale e gli strumenti necessari.');
        try{{
          const r=await fetch('/operatore-bodymind/chat',{{
            method:'POST',headers:{{'Content-Type':'application/json','X-CSRFToken':csrf}},
            body:JSON.stringify({{message:q}})
          }});
          const data=await r.json();
          let text=data.text||'Non ho ricevuto una risposta.';
          addMsg(text,'bot',data);
          if(voiceStageOpen)setVoiceStage('Ti rispondo',text,'Puoi continuare a parlarmi senza uscire dalla conversazione.');
          if(data.ui_action==='smtp_setup')openSmtpSetup();
          speak(text);refreshCloudStatus(true);
        }}catch(err){{
          const t='Non riesco a contattare il motore dell’Operatore in questo momento. Non ho modificato nulla.';
          addMsg(t,'bot');
          if(voiceStageOpen)setVoiceStage('Connessione non disponibile',t);
        }}finally{{send.disabled=false;input.focus()}}
      }}

      // BODYMIND_R52_COMPOSER_AUTOGROW
      function fitComposer(){{
        input.style.height='40px';
        input.style.height=Math.min(132,Math.max(40,input.scrollHeight))+'px';
      }}
      send.addEventListener('click',()=>ask(input.value));
      input.addEventListener('input',fitComposer);
      input.addEventListener('keydown',ev=>{{if(ev.key==='Enter'&&!ev.shiftKey){{ev.preventDefault();ask(input.value);fitComposer()}}}});
      fitComposer();
      document.querySelectorAll('[data-q]').forEach(b=>b.addEventListener('click',()=>ask(b.dataset.q)));


      // BODYMIND_R49_CLOUD_NATIVE_VOICE_ONLY
      // Browser captures audio only; transcription and speech synthesis are cloud services.
      // BODYMIND_R52_AUDIO_SIGNAL
      let cloudRecorder=null,cloudChunks=[],cloudRecording=false,cloudAudio=null,cloudMaxTimer=null,cloudRecordingStartedAt=0;
      let voiceAudioCtx=null,voicePlaybackSource=null,lastTtsBytes=null;
      let micAnalyser=null,micSourceNode=null,micLevelTimer=null,cloudSpeechSeen=false,cloudLastSpeechAt=0;

      async function unlockVoiceAudio(){{
        const Ctx=window.AudioContext||window.webkitAudioContext;
        if(!Ctx)return null;
        if(!voiceAudioCtx)voiceAudioCtx=new Ctx();
        if(voiceAudioCtx.state==='suspended'){{try{{await voiceAudioCtx.resume()}}catch(e){{}}}}
        return voiceAudioCtx;
      }}
      function stopMicMeter(){{
        if(micLevelTimer){{clearInterval(micLevelTimer);micLevelTimer=null}}
        try{{micSourceNode?.disconnect()}}catch(e){{}}
        micSourceNode=null;micAnalyser=null;
        if(voiceOrb)voiceOrb.style.transform='';
      }}
      async function startMicMeter(stream){{
        const ctx=await unlockVoiceAudio();if(!ctx)return;
        try{{
          micSourceNode=ctx.createMediaStreamSource(stream);
          micAnalyser=ctx.createAnalyser();micAnalyser.fftSize=512;micAnalyser.smoothingTimeConstant=.55;
          micSourceNode.connect(micAnalyser);
          const buf=new Uint8Array(micAnalyser.fftSize);
          micLevelTimer=setInterval(()=>{{
            if(!cloudRecording||!micAnalyser)return;
            micAnalyser.getByteTimeDomainData(buf);
            let sum=0;for(const v of buf){{const x=(v-128)/128;sum+=x*x}}
            const rms=Math.sqrt(sum/buf.length);
            const scale=1+Math.min(.07,rms*1.7);
            if(voiceOrb)voiceOrb.style.transform='scale('+scale.toFixed(3)+')';
            if(rms>.025){{cloudSpeechSeen=true;cloudLastSpeechAt=performance.now();}}
            const elapsed=performance.now()-cloudRecordingStartedAt;
            if(cloudSpeechSeen&&elapsed>1100&&performance.now()-cloudLastSpeechAt>1150)cloudStopAndTranscribe();
          }},90);
        }}catch(e){{voiceDiag('mic_meter_error',{{error:String(e?.message||e)}})}}
      }}

      async function speak(text,fromUserGesture=false){{
        if(!voice || !voice.checked || !text)return;
        lastSpeechText=String(text);
        try{{
          if(voiceStatus)voiceStatus.textContent='Genero la voce…';
          const r=await fetch('/operatore-bodymind/voice/speak',{{
            method:'POST',
            headers:{{'Content-Type':'application/json','X-CSRFToken':csrf}},
            body:JSON.stringify({{text:String(text)}})
          }});
          if(!r.ok){{
            let d={{}};try{{d=await r.json()}}catch(e){{}}
            throw new Error(d.text||('TTS HTTP '+r.status));
          }}
          const usageId=r.headers.get('X-BodyMind-Usage-Id')||'';
          const blob=await r.blob();
          const url=URL.createObjectURL(blob);
          try{{if(cloudAudio){{cloudAudio.pause();if(cloudAudio.src)URL.revokeObjectURL(cloudAudio.src)}}}}catch(e){{}}
          cloudAudio=new Audio(url);
          cloudAudio.preload='auto';
          cloudAudio.onloadedmetadata=()=>{{
            const secs=Number(cloudAudio?.duration||0);
            if(usageId&&isFinite(secs)&&secs>0){{
              fetch('/operatore-bodymind/cloud/usage/tts',{{
                method:'POST',headers:{{'Content-Type':'application/json','X-CSRFToken':csrf}},
                body:JSON.stringify({{usage_id:usageId,seconds:secs}})
              }}).then(()=>refreshCloudStatus(true)).catch(()=>{{}});
            }}
          }};
          cloudAudio.onplay=()=>{{avatar?.classList.add('speaking');voiceOrb?.classList.add('speaking');voiceOrb?.classList.remove('listening');if(voiceStatus)voiceStatus.textContent='Ti sto rispondendo…';if(voiceStageOpen)setVoiceStage('Ti rispondo',lastSpeechText,'Quando ho finito puoi continuare a parlarmi.');if(voiceRecover)voiceRecover.hidden=true;}};
          cloudAudio.onended=()=>{{avatar?.classList.remove('speaking');voiceOrb?.classList.remove('speaking');if(voiceStatus)voiceStatus.textContent='Tocca il microfono e parlami';if(voiceStageOpen)setVoiceStage('Segretario BodyMind','Tocca e continua.','La conversazione resta trascritta nella chat.');try{{URL.revokeObjectURL(url)}}catch(e){{}}}};
          try{{
            await cloudAudio.play();
          }}catch(e){{
            if(voiceRecover){{voiceRecover.hidden=false;voiceRecover.textContent='🔊 Ascolta risposta'}}
            if(voiceStatus)voiceStatus.textContent='Risposta pronta: tocca 🔊 per ascoltarla';
          }}
        }}catch(e){{
          if(voiceStatus)voiceStatus.textContent='Voce cloud non disponibile';
          voiceDiag('cloud_tts_error',{{error:String(e?.message||e)}});
        }}
      }}

      if(voiceRecover){{
        voiceRecover.onclick=async(ev)=>{{
          ev.preventDefault();ev.stopImmediatePropagation();
          if(cloudAudio){{try{{await cloudAudio.play();voiceRecover.hidden=true}}catch(e){{}}}}
          else if(lastSpeechText){{speak(lastSpeechText,true)}}
        }};
      }}

      async function cloudStopAndTranscribe(){{
        if(!cloudRecording||!cloudRecorder)return;
        const elapsed=performance.now()-cloudRecordingStartedAt;
        if(elapsed<650){{if(voiceStatus)voiceStatus.textContent='Ti ascolto…';return}}
        cloudRecording=false;
        if(cloudMaxTimer){{clearTimeout(cloudMaxTimer);cloudMaxTimer=null}}
        stopMicMeter();
        if(voiceStatus)voiceStatus.textContent='Trascrivo…';
        voiceOrb?.classList.remove('listening');
        if(voiceStageOpen)setVoiceStage('Trascrivo','Un attimo…','Sto trasformando la tua voce in testo.');
        try{{cloudRecorder.stop()}}catch(e){{}}
      }}

      async function cloudStartMic(ev){{
        if(ev){{ev.preventDefault();ev.stopImmediatePropagation()}}
        if(!voiceStageOpen)openVoiceStage();
        if(cloudRecording){{await cloudStopAndTranscribe();return}}
        if(!window.MediaRecorder || !navigator.mediaDevices?.getUserMedia){{
          const t='Questo browser non supporta la registrazione cloud. Usa un browser aggiornato oppure scrivi la richiesta.';
          if(voiceStatus)voiceStatus.textContent=t;addMsg(t,'bot');return;
        }}
        try{{
          const stream=await navigator.mediaDevices.getUserMedia({{audio:{{echoCancellation:true,noiseSuppression:true,autoGainControl:true}},video:false}});
          let mime='';
          for(const m of ['audio/mp4','audio/webm;codecs=opus','audio/webm']){{if(MediaRecorder.isTypeSupported?.(m)){{mime=m;break}}}}
          cloudChunks=[];
          cloudRecorder=new MediaRecorder(stream,mime?{{mimeType:mime}}:undefined);
          cloudRecorder.ondataavailable=e=>{{if(e.data&&e.data.size)cloudChunks.push(e.data)}};
          cloudRecorder.onerror=e=>{{voiceDiag('cloud_recorder_error',{{error:String(e?.error?.message||e?.message||e)}})}};
          cloudRecorder.onstop=async()=>{{
            mic.classList.remove('on');avatar.classList.remove('listening');
            try{{stream.getTracks().forEach(t=>t.stop())}}catch(e){{}}
            const blob=new Blob(cloudChunks,{{type:cloudRecorder?.mimeType||mime||'audio/webm'}});
            if(blob.size<1000){{if(voiceStatus)voiceStatus.textContent='Non ho rilevato audio. Riprova.';return}}
            if(!cloudSpeechSeen){{
              const t='Il microfono è aperto, ma non rilevo la tua voce. Controlla il microfono e riprova.';
              if(voiceStatus)voiceStatus.textContent=t;
              if(voiceStageOpen)setVoiceStage('Non sento voce',t,'Parla più vicino al microfono o controlla il permesso audio.');
              voiceDiag('no_voice_signal',{{len:blob.size}});
              return;
            }}
            const ext=(blob.type||'').includes('mp4')?'m4a':'webm';
            const fd=new FormData();fd.append('audio',blob,'voce.'+ext);
            fd.append('duration_ms',String(Math.max(0,performance.now()-cloudRecordingStartedAt)));
            try{{
              const r=await fetch('/operatore-bodymind/voice/transcribe',{{method:'POST',headers:{{'X-CSRFToken':csrf}},body:fd}});
              const d=await r.json();
              if(!r.ok)throw new Error(d.text||('STT HTTP '+r.status));
              input.value=String(d.text||'').trim();
              if(!input.value)throw new Error('Trascrizione vuota');
              if(voiceStatus)voiceStatus.textContent='Ho capito. Elaboro…';
              if(voiceStageOpen)setVoiceStage('Ho capito',input.value,'Ora controllo BodyMind.');
              await ask(input.value);
            }}catch(e){{
              const t=String(e?.message||e||'Trascrizione cloud non disponibile');
              if(voiceStatus)voiceStatus.textContent=t;addMsg(t,'bot');
            }}
          }};
          cloudRecorder.start(250);
          cloudRecordingStartedAt=performance.now();
          cloudRecording=true;
          mic.classList.add('on');avatar.classList.add('listening');voiceOrb?.classList.add('listening');
          if(voiceStatus)voiceStatus.textContent='Ti ascolto… tocca di nuovo per inviare';
          if(voiceStageOpen)setVoiceStage('Ti ascolto','Parla normalmente.','Tocca di nuovo l’orb per inviare subito.');
          cloudMaxTimer=setTimeout(()=>{{if(cloudRecording)cloudStopAndTranscribe()}},18000);
        }}catch(e){{
          cloudRecording=false;mic.classList.remove('on');avatar.classList.remove('listening');voiceOrb?.classList.remove('listening');
          const t=(e?.name==='NotAllowedError'||e?.name==='SecurityError')
            ?'Microfono non autorizzato. Consenti il microfono a BodyMind e riprova.'
            :'Non riesco ad aprire il microfono.';
          if(voiceStatus)voiceStatus.textContent=t;addMsg(t,'bot');
        }}
      }}
      mic.addEventListener('click',cloudStartMic,true);
      avatar?.addEventListener('click',cloudStartMic,true);
      voiceOrb?.addEventListener('click',cloudStartMic,true);
      voiceOrb?.addEventListener('keydown',ev=>{{if(ev.key==='Enter'||ev.key===' ')cloudStartMic(ev)}});

      attach?.addEventListener('click',()=>{{
        const picker=document.createElement('input');
        picker.type='file';
        picker.multiple=true;
        picker.accept='.pdf,.png,.jpg,.jpeg,.webp,.docx';
        picker.setAttribute('aria-hidden','true');
        picker.tabIndex=-1;
        picker.style.setProperty('display','none','important');
        document.body.appendChild(picker);
        picker.addEventListener('change',async()=>{{
          const files=[...(picker.files||[])];
          try{{
            if(!files.length)return;
            const fd=new FormData();files.forEach(f=>fd.append('files',f,f.name));
            fd.append('production_mode','1');
            const hint=document.getElementById('bmoUploadType')?.value||'';
            if(hint)fd.append('document_type_hint',hint);
            addMsg('Ho ricevuto '+files.length+' file. Li analizzo e porto in produzione quelli certi.','bot');
            const r=await fetch('/operatore-bodymind/upload',{{method:'POST',headers:{{'X-CSRFToken':csrf}},body:fd}});
            const data=await r.json();addMsg(data.text||'Analisi completata.','bot',data);speak(data.text||'Analisi completata.');
          }}catch(e){{
            addMsg('Il caricamento non è riuscito. Non ho modificato file esistenti.','bot');
          }}finally{{
            try{{picker.remove()}}catch(e){{}}
          }}
        }},{{once:true}});
        picker.click();
      }});

      document.getElementById('bmoUploadForm')?.addEventListener('submit',async ev=>{{
        ev.preventDefault();
        const fd=new FormData();
        const files=[...document.getElementById('bmoFiles').files,...document.getElementById('bmoFolder').files];
        if(!files.length){{addMsg('Seleziona almeno un file o una cartella.','bot');return}}
        files.forEach(f=>fd.append('files',f,f.webkitRelativePath||f.name));
        fd.append('production_mode',document.getElementById('bmoProductionMode')?.checked?'1':'0');
        const declaredType=document.getElementById('bmoUploadType')?.value||'';
        if(declaredType)fd.append('document_type_hint',declaredType);
        addMsg('Sto elaborando '+files.length+' file. I match certi verranno portati fino alla produzione e verificati.','bot');
        try{{
          const r=await fetch('/operatore-bodymind/upload',{{method:'POST',headers:{{'X-CSRFToken':csrf}},body:fd}});
          const data=await r.json();
          addMsg(data.text||'Analisi completata.','bot',data);
          speak(data.text||'Analisi completata.');
        }}catch(e){{addMsg('Il caricamento non è riuscito. Non ho eliminato né modificato file esistenti.','bot')}}
      }});
    }})();
    </script>
    """
    return layout(html)


@app.post("/operatore-bodymind/new-chat")
@login_required
def bodymind_operator_new_chat():
    session["bodymind_operator_conversation"]=uuid.uuid4().hex
    session.pop("bodymind_operator_last_tesserato",None)
    session.pop("bodymind_operator_pending_action",None)
    return jsonify({"ok":True,"conversation_id":session["bodymind_operator_conversation"]})


@app.post("/operatore-bodymind/voice-diag")
@login_required
def bodymind_operator_voice_diag():
    payload=request.get_json(silent=True) or {}
    safe={
        "stage":str(payload.get("stage") or "")[:80],
        "error":str(payload.get("error") or "")[:160],
        "message":str(payload.get("message") or "")[:160],
        "sr":bool(payload.get("sr")),
        "synth":bool(payload.get("synth")),
        "voices":int(payload.get("voices") or 0),
        "voice":str(payload.get("voice") or "")[:120],
        "gesture":bool(payload.get("gesture")),
        "final":bool(payload.get("final")),
        "len":int(payload.get("len") or 0),
        "level":int(payload.get("level") or 0),
        "muted":bool(payload.get("muted")),
        "enabled":payload.get("enabled"),
        "readyState":str(payload.get("readyState") or "")[:40],
        "attempt":int(payload.get("attempt") or 0),
        "ua":str(payload.get("ua") or "")[:220],
    }
    try:
        line="[voice-diag] "+json.dumps(safe,ensure_ascii=False)
        app.logger.info("%s", line)
        print(line, flush=True)
    except Exception:
        pass
    return jsonify({"ok":True}),200

@app.post("/operatore-bodymind/chat")
@login_required
def bodymind_operator_chat():
    payload=request.get_json(silent=True) or {}
    message=str(payload.get("message") or "")[:8000]
    conn=db()
    try:
        _schema(conn)
        _log(conn,"user",message)
        result=_answer(conn,message)
        planner_used=False
        # R45: cloud intelligence gets first shot. It may inspect the real system before choosing the action.
        if str(result.get("mode") or "")=="fallback":
            try:
                trace=[]
                discovery_tools={"discover_capabilities","inspect_route","inspect_system_map","inspect_db_schema"}
                for agent_step in range(3):
                    plan=_cloud_plan_tool(conn,message,trace)
                    if not plan:
                        break
                    planner_used=True
                    tool=str(plan.get("tool") or "").strip()
                    if tool in ("none","unknown",""):
                        answer=str(plan.get("answer") or "").strip()
                        if answer:
                            result={
                                "text":answer,
                                "mode":"cloud_ai",
                                "allow_device_ai":False,
                                "cloud_ai":True,
                                "agent_plan":"none",
                                "agent_steps":agent_step+1,
                            }
                        break
                    tool_result=_execute_full_agent_plan(conn,plan,message)
                    if not tool_result:
                        break
                    tool_result["agent_steps"]=agent_step+1
                    if tool in discovery_tools and agent_step<2:
                        trace.append(_compact_agent_observation(tool,tool_result))
                        result=tool_result
                        continue
                    result=tool_result
                    break
            except Exception as cloud_planner_exc:
                try:
                    _log(conn,"system","R45 cloud planner unavailable: "+repr(cloud_planner_exc))
                except Exception:
                    pass

        # R47 cloud-native: no local AI fallback in the user request path.
        if not planner_used and str(result.get("mode") or "")=="fallback":
            err=str(_CLOUD_LAST_ERROR or "")
            low=err.lower()
            if "credit_balance_exhausted" in low or "insufficient_quota" in low or "no credits remaining" in low:
                msg="L’IA cloud è configurata ma il credito API è esaurito. Ricarica il credito per continuare."
            elif err:
                msg="L’IA cloud non è disponibile in questo momento. Non ho eseguito modifiche."
            else:
                msg="Questa richiesta richiede l’IA cloud. Non ho eseguito modifiche."
            result={"text":msg,"mode":"cloud_unavailable","allow_device_ai":False,"cloud_ai":False}

        _log(conn,"assistant",result.get("text",""),result)
        return jsonify(result)
    except Exception as exc:
        try:
            _log(conn,"system","ERROR "+repr(exc))
        except Exception:
            pass
        return jsonify({"text":"Ho incontrato un errore interno mentre controllavo i dati. Non ho eseguito modifiche.","mode":"error"}),500
    finally:
        conn.close()


def _cloud_user_error(exc):
    s=repr(exc)
    low=s.lower()
    if "credit_balance_exhausted" in low or "insufficient_quota" in low or "no credits remaining" in low:
        return "Credito API OpenAI esaurito.",402
    if "rate_limit" in low or "429" in low:
        return "Limite temporaneo API raggiunto. Riprova tra poco.",429
    return "Servizio IA cloud temporaneamente non disponibile.",503

@app.get("/operatore-bodymind/cloud/status")
@login_required
def bodymind_cloud_status():
    err=str(_CLOUD_LAST_ERROR or "")
    blocked=any(x in err.lower() for x in ("credit_balance_exhausted","insufficient_quota","no credits remaining"))
    configured=bool(str(os.environ.get("OPENAI_API_KEY") or "").strip()) and str(os.environ.get("BODYMIND_AI_CLOUD","1")).lower() in ("1","true","yes","on")
    conn=db()
    try:
        budget=_usage_summary(conn)
    finally:
        conn.close()
    return jsonify({
        "configured":configured,
        "ready":configured and not blocked,
        "model":str(os.environ.get("BODYMIND_AI_MODEL") or "gpt-6-luna"),
        "voice_model":str(os.environ.get("BODYMIND_TTS_MODEL") or "gpt-4o-mini-tts"),
        "transcribe_model":str(os.environ.get("BODYMIND_STT_MODEL") or "gpt-transcribe"),
        "last_ok_at":_CLOUD_LAST_OK_AT,
        "local_ai_used":False,
        "budget":budget,
    })

@app.post("/operatore-bodymind/voice/transcribe")
@login_required
def bodymind_cloud_transcribe():
    if current_role() not in ("admin","manager"):
        return jsonify({"text":"Permessi insufficienti."}),403
    f=request.files.get("audio")
    if not f:
        return jsonify({"text":"Audio mancante."}),400
    data=f.read()
    if not data:
        return jsonify({"text":"Audio vuoto."}),400
    if len(data)>20*1024*1024:
        return jsonify({"text":"Registrazione troppo grande."}),413
    key=str(os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        return jsonify({"text":"IA cloud non configurata."}),503
    try:
        from openai import OpenAI
        client=OpenAI(api_key=key,timeout=35.0,max_retries=0)
        model=str(os.environ.get("BODYMIND_STT_MODEL") or "gpt-transcribe").strip()
        filename=str(f.filename or "voce.webm")
        mimetype=str(f.mimetype or "audio/webm")
        tr=client.audio.transcriptions.create(model=model,file=(filename,data,mimetype),language="it")
        text_out=str(getattr(tr,"text","") or "").strip()
        if not text_out:
            return jsonify({"text":"Non ho riconosciuto una frase."}),422
        try:
            seconds=max(0.0,min(120.0,float(request.form.get("duration_ms") or 0)/1000.0))
        except Exception:
            seconds=0.0
        rate=_STT_USD_PER_MIN.get(model,0.0045)
        conn=db()
        try:
            _record_ai_usage(conn,"stt",model,0,0,seconds,(seconds/60.0)*rate)
        finally:
            conn.close()
        return jsonify({"ok":True,"text":text_out,"model":model})
    except Exception as exc:
        msg,status=_cloud_user_error(exc)
        try: print("[cloud-voice-r46] stt_error="+repr(exc)[:900],flush=True)
        except Exception: pass
        return jsonify({"text":msg}),status

@app.post("/operatore-bodymind/voice/speak")
@login_required
def bodymind_cloud_speak():
    payload=request.get_json(silent=True) or {}
    text_in=str(payload.get("text") or "").strip()[:5000]
    if not text_in:
        return jsonify({"text":"Testo mancante."}),400
    key=str(os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        return jsonify({"text":"IA cloud non configurata."}),503
    try:
        from openai import OpenAI
        client=OpenAI(api_key=key,timeout=35.0,max_retries=0)
        model=str(os.environ.get("BODYMIND_TTS_MODEL") or "gpt-4o-mini-tts").strip()
        voice_name=str(os.environ.get("BODYMIND_TTS_VOICE") or "coral").strip()
        speech=client.audio.speech.create(
            model=model,voice=voice_name,input=text_in,
            instructions="Parla in italiano naturale, caldo e professionale. Sei una segretaria virtuale esperta di BodyMind. Ritmo conversazionale, niente tono robotico."
        )
        data=getattr(speech,"content",None)
        if data is None and hasattr(speech,"read"):
            data=speech.read()
        if data is None and hasattr(speech,"response"):
            data=getattr(speech.response,"content",None)
        if not data:
            raise RuntimeError("TTS returned no audio bytes")
        usage_id="tts-"+uuid.uuid4().hex
        conn=db()
        try:
            _record_ai_usage(conn,"tts",model,0,0,0.0,0.0,usage_id)
        finally:
            conn.close()
        resp=Response(data,mimetype="audio/mpeg")
        resp.headers["Cache-Control"]="no-store"
        resp.headers["X-BodyMind-Voice"]="cloud-r47"
        resp.headers["X-BodyMind-Usage-Id"]=usage_id
        return resp
    except Exception as exc:
        msg,status=_cloud_user_error(exc)
        try: print("[cloud-voice-r46] tts_error="+repr(exc)[:900],flush=True)
        except Exception: pass
        return jsonify({"text":msg}),status


@app.post("/operatore-bodymind/cloud/usage/tts")
@login_required
def bodymind_cloud_tts_usage():
    payload=request.get_json(silent=True) or {}
    usage_id=str(payload.get("usage_id") or "").strip()
    try:
        seconds=max(0.0,min(600.0,float(payload.get("seconds") or 0)))
    except Exception:
        seconds=0.0
    if not usage_id or seconds<=0:
        return jsonify({"ok":False}),400
    conn=db()
    try:
        row=conn.execute("SELECT id,model,seconds FROM bodymind_ai_usage WHERE request_id=? AND kind='tts' LIMIT 1",(usage_id,)).fetchone()
        if row and float(row["seconds"] or 0)<=0:
            rate=_TTS_EST_USD_PER_MIN.get(str(row["model"] or ""),0.015)
            conn.execute("UPDATE bodymind_ai_usage SET seconds=?,estimated_usd=? WHERE id=?",(seconds,(seconds/60.0)*rate,int(row["id"])))
            conn.commit()
        budget=_usage_summary(conn)
    finally:
        conn.close()
    return jsonify({"ok":True,"budget":budget})


def _internal_post_route(path, data=None):
    token=str(session.get("_csrf_token") or csrf_token() or "")
    snap={k:session.get(k) for k in session.keys()}
    send=dict(data or {})
    send.setdefault("csrf_token",token)
    with app.test_client() as client:
        with client.session_transaction() as s2:
            for k,v in snap.items():
                s2[k]=v
        resp=client.post(path,data=send,headers={"X-CSRFToken":token},follow_redirects=False)
    return int(resp.status_code or 0)

def _latest_inbound_after(conn,before_id,name):
    if not _table(conn,"inbound_documents"):
        return None
    cols=_cols(conn,"inbound_documents")
    filename_col="original_filename" if "original_filename" in cols else ("filename" if "filename" in cols else "")
    if filename_col:
        row=conn.execute(
            "SELECT * FROM inbound_documents WHERE id>? AND "+filename_col+"=? ORDER BY id DESC LIMIT 1",
            (int(before_id or 0),str(name))
        ).fetchone()
        if row:
            return row
    return conn.execute("SELECT * FROM inbound_documents WHERE id>? ORDER BY id DESC LIMIT 1",(int(before_id or 0),)).fetchone()

def _verify_document_production(conn,inbound_id):
    row=conn.execute("SELECT * FROM inbound_documents WHERE id=?",(int(inbound_id),)).fetchone() if _table(conn,"inbound_documents") else None
    if not row:
        return False,{"reason":"inbound_missing"}
    tid=int(row["tesserato_id"] or 0) if "tesserato_id" in row.keys() else 0
    status=str(row["status"] or "") if "status" in row.keys() else ""
    dtype=str(row["document_type"] or "") if "document_type" in row.keys() else ""
    doc=None
    if tid>0 and _table(conn,"documenti"):
        dc=_cols(conn,"documenti")
        if "inbound_id" in dc:
            doc=conn.execute("SELECT * FROM documenti WHERE inbound_id=? ORDER BY id DESC LIMIT 1",(int(inbound_id),)).fetchone()
        if not doc and "filename" in dc and "saved_path" in row.keys():
            doc=conn.execute("SELECT * FROM documenti WHERE tesserato_id=? AND filename=? ORDER BY id DESC LIMIT 1",(tid,str(row["saved_path"] or ""))).fetchone()
    verified=bool(tid>0 and status=="associato" and doc)
    details={"tesserato_id":tid,"status":status,"document_type":dtype,"document_id":int(doc["id"]) if doc else None}
    if verified and dtype=="modulo_unico_tesseramento":
        t=conn.execute("SELECT * FROM tesserati WHERE id=?",(tid,)).fetchone()
        if t:
            details["onboarding_flags"]={
                k:int(t[k] or 0) for k in (
                    "iscrizione_firmata","documenti_onboarding_ok","privacy_ok","liberatoria_ok","regolamento_ok"
                ) if k in t.keys()
            }
    return verified,details

def _productionize_inbound(inbound_id, type_hint=""):
    hint=str(type_hint or "").strip()
    if hint:
        code=_internal_post_route(f"/documenti/da-verificare/{int(inbound_id)}/tipo",{"document_type":hint})
        if code<200 or code>=400:
            return False,{"reason":"type_route_failed","http":code}
    conn=db()
    try:
        row=conn.execute("SELECT * FROM inbound_documents WHERE id=?",(int(inbound_id),)).fetchone()
        if not row:
            return False,{"reason":"inbound_missing"}
        tid=int(row["tesserato_id"] or 0)
        dtype=str(row["document_type"] or "")
        match=int(row["match_score"] or 0) if "match_score" in row.keys() else 0
        conf=int(row["document_confidence"] or 0) if "document_confidence" in row.keys() else 0
        if tid<=0:
            return False,{"reason":"athlete_not_certain","match_score":match}
        if dtype in ("","altro"):
            return False,{"reason":"document_type_uncertain","document_confidence":conf}
        if match<95:
            return False,{"reason":"athlete_match_below_95","match_score":match}
        if not hint and conf<90:
            return False,{"reason":"document_confidence_below_90","document_confidence":conf}
    finally:
        conn.close()
    code=_internal_post_route(f"/documenti/da-verificare/{int(inbound_id)}/ok",{})
    if code<200 or code>=400:
        return False,{"reason":"final_ok_route_failed","http":code}
    conn=db()
    try:
        return _verify_document_production(conn,inbound_id)
    finally:
        conn.close()


@app.get("/operatore-bodymind/smtp/setup")
@login_required
def bodymind_operator_smtp_setup():
    if current_role() not in ("admin","manager"):
        return redirect("/operatore-bodymind")
    return redirect("/operatore-bodymind?smtp_setup=1")


@app.get("/operatore-bodymind/secure/smtp")
@login_required
def bodymind_operator_smtp_status():
    if current_role() not in ("admin","manager"):
        return jsonify({"text":"Permessi insufficienti."}),403
    conn=db()
    try:
        st=_smtp_public_status(conn)
    finally:
        conn.close()
    return jsonify({"ok":True,"smtp":st})

@app.post("/operatore-bodymind/secure/smtp")
@login_required
def bodymind_operator_smtp_save():
    if current_role()!="admin":
        return jsonify({"text":"Solo un amministratore può configurare SMTP."}),403
    payload=request.get_json(silent=True) or {}
    provider=str(payload.get("provider") or "").strip().lower()
    host=str(payload.get("host") or "").strip()
    username=str(payload.get("username") or "").strip()
    password=str(payload.get("password") or "")
    from_name=str(payload.get("from_name") or "BodyMind Aerial Studio").strip()
    security=str(payload.get("security") or "starttls").strip().lower()
    try: port=int(payload.get("port") or 0)
    except Exception: port=0
    if provider=="gmail":
        host=host or "smtp.gmail.com"
        port=port or 587
        security=security if security in ("starttls","ssl") else "starttls"
    if security not in ("starttls","ssl","plain"):
        return jsonify({"text":"Tipo di sicurezza SMTP non valido."}),400
    conn=db()
    try:
        old,_meta=_secure_setting_get(conn,"smtp")
        if not password and isinstance(old,dict):
            password=str(old.get("password") or "")
        cfg={
            "provider":provider or "custom",
            "host":host,"port":port,"username":username,"password":password,
            "security":security,"from_name":from_name,
        }
        if not host or port<=0 or not username or not password:
            return jsonify({"text":"Compila host, porta, utente e password/app-password."}),400
        tested=False; err=""
        try:
            _smtp_test_connection(cfg); tested=True
        except Exception as exc:
            err=str(exc)[:300]
        meta={"last_test_ok":tested,"last_test_at":datetime.now().isoformat(timespec="seconds"),"last_test_error":err}
        _secure_setting_set(conn,"smtp",cfg,meta)
        st=_smtp_public_status(conn)
    finally:
        conn.close()
    if not tested:
        return jsonify({"ok":False,"smtp":st,"text":"Configurazione salvata cifrata, ma il test SMTP non è riuscito: "+(err or "errore non specificato")}),422
    return jsonify({"ok":True,"smtp":st,"text":"SMTP configurato e testato correttamente."})

@app.post("/operatore-bodymind/upload")
@login_required
def bodymind_operator_upload():
    if current_role() not in ("admin","manager"):
        return jsonify({"text":"L’account connesso non può affidare documenti all’Autopilot.","mode":"warning"}),403
    files=request.files.getlist("files")
    if not files:
        return jsonify({"text":"Non ho ricevuto file.","mode":"warning"}),400
    production_mode=str(request.form.get("production_mode") or "1").strip().lower() not in ("0","false","no","off")
    type_hint=str(request.form.get("document_type_hint") or "").strip()
    allowed_hints={
        "","modulo_unico_tesseramento","certificato_medico","documento_identita",
        "trasporto_minori","documenti_gara","documenti_saggio"
    }
    if type_hint not in allowed_hints:
        return jsonify({"text":"Tipo documento indicato non valido.","mode":"warning"}),400
    from .routes_email_documents import process_inbound_attachment, ALLOWED_INBOUND_DOCS, extract_attachment_text, find_tesserato_for_text
    from .routes_documenti import _save_uploaded_asd_document
    results=[]; errors=[]
    for f in files[:120]:
        try:
            name=(f.filename or "documento").replace("\\","/").split("/")[-1]
            ext=Path(name).suffix.lower()
            if ext not in ALLOWED_INBOUND_DOCS:
                errors.append(name+" · formato non supportato")
                continue
            data=f.read()
            if len(data)>40*1024*1024:
                errors.append(name+" · oltre 40 MB")
                continue
            extracted=""
            try: extracted=extract_attachment_text(name,data) or ""
            except Exception: extracted=""
            athlete_match=None
            try: athlete_match=find_tesserato_for_text((name+" "+extracted).strip(),current_username())
            except Exception: athlete_match=None
            asd_kind=_classify_asd_document(name,extracted) if not athlete_match else None
            if asd_kind and not type_hint:
                try:
                    f.stream.seek(0)
                    _,saved_name=_save_uploaded_asd_document(f,asd_kind["folder"])
                    results.append({
                        "name":name,"status":"archiviato_asd","tesserato_id":None,
                        "type":"documento_asd","confidence":asd_kind["confidence"],
                        "folder":asd_kind["folder"],"reason":asd_kind["reason"],"saved_name":saved_name,
                        "production":False,"production_reason":"documento_asd"
                    })
                    continue
                except Exception as exc:
                    errors.append(name+" · archivio ASD: "+str(exc)[:160])
                    continue
            conn0=db()
            try:
                before_id=int(conn0.execute("SELECT COALESCE(MAX(id),0) FROM inbound_documents").fetchone()[0]) if _table(conn0,"inbound_documents") else 0
            finally:
                conn0.close()
            res=process_inbound_attachment(
                name,data,subject="Operatore BodyMind",
                sender=current_username(),body_text="Caricato dalla segreteria Operatore BodyMind",
                source="operatore_bodymind"
            )
            conn1=db()
            try:
                inbound=_latest_inbound_after(conn1,before_id,name)
                inbound_id=int(inbound["id"]) if inbound else 0
            finally:
                conn1.close()
            produced=False; production_details={}
            if production_mode and inbound_id:
                produced,production_details=_productionize_inbound(inbound_id,type_hint=type_hint)
            result={
                "name":name,
                "status":res.get("status"),
                "tesserato_id":res.get("tesserato_id"),
                "type":type_hint or (res.get("classification") or {}).get("type"),
                "confidence":100 if type_hint else (res.get("classification") or {}).get("confidence"),
                "folder":"Dossier/Autopilot",
                "inbound_id":inbound_id or None,
                "production":bool(produced),
                "production_details":production_details,
            }
            if produced:
                result["status"]="produzione"
                result["tesserato_id"]=production_details.get("tesserato_id") or result.get("tesserato_id")
                result["document_id"]=production_details.get("document_id")
            results.append(result)
        except Exception as exc:
            errors.append((f.filename or "file")+" · "+str(exc)[:180])
    produced=sum(1 for r in results if r.get("production"))
    auto=sum(1 for r in results if r.get("tesserato_id") and not r.get("production") and r.get("status") in ("associato","archived_to_tesserato"))
    asd=sum(1 for r in results if r.get("status")=="archiviato_asd")
    review=sum(1 for r in results if not r.get("production") and (r.get("status") in PENDING_STATUSES or (not r.get("tesserato_id") and r.get("status")!="archiviato_asd")))
    text=f"Ho elaborato {len(results)} file: {produced} messi in produzione e verificati, {auto} associati, {asd} archiviati come documenti ASD e {review} richiedono verifica."
    if errors:
        text+=f" {len(errors)} file non sono stati elaborati."
    if produced:
        text+=" Per quelli in produzione ho ricontrollato l'esistenza del documento nel dossier dopo l'OK finale."
    return jsonify({
        "text":text,"mode":"upload","results":results,"errors":errors,
        "production_mode":production_mode,"document_type_hint":type_hint,
        "produced":produced,"review":review,
        "links":[{"label":"Apri Da verificare","href":"/documenti/da-verificare"},{"label":"Apri Documenti","href":"/documenti"}]
    })

@app.after_request
def bodymind_family_logo_override(resp):
    """Keep the public family landing branded BodyMind, never the legacy ASD Pro logo."""
    try:
        if request.path != "/area-famiglie" or request.method != "GET" or int(resp.status_code or 200) != 200:
            return resp
        if "text/html" not in str(resp.headers.get("Content-Type","")).lower():
            return resp
        html=resp.get_data(as_text=True)
        if "/bodymind-media/logo" in html:
            html=html.replace("/bodymind-media/logo","https://bodymindaerialstudio.life/seed-media/logo?v=9")
            resp.set_data(html)
            resp.headers.pop("Content-Length",None)
        resp.headers["X-BodyMind-Family-Logo"]="bodymind-public-logo-v1"
    except Exception:
        pass
    return resp

# BODYMIND_R39_FAMILY_LOGO_BODYMIND

@app.after_request
def bodymind_operator_microphone_policy(resp):
    try:
        if request.path.startswith("/operatore-bodymind"):
            resp.headers["Permissions-Policy"]="microphone=(self)"
            resp.headers["Cache-Control"]="no-store"
    except Exception:
        pass
    return resp


@app.after_request
def bodymind_operator_mobile_entry(resp):
    try:
        if request.path!="/mobile" or request.method!="GET" or int(resp.status_code or 200)!=200:
            return resp
        if "text/html" not in str(resp.headers.get("Content-Type","")).lower():
            return resp
        if request.path.startswith("/operatore-bodymind"):
            return resp
        html=resp.get_data(as_text=True)
        if "bmo-mobile-entry" in html:
            return resp
        button="""
        <style id="bmo-mobile-entry-style">
          /* BODYMIND_R39_IPHONE_ENTRY_V2 */
          @media(max-width:800px){
            #bmo-mobile-entry{
              right:12px!important;
              bottom:calc(86px + env(safe-area-inset-bottom))!important;
              width:46px!important;
              height:46px!important;
              min-width:46px!important;
              max-width:46px!important;
              padding:0!important;
              display:grid!important;
              place-items:center!important;
              border-radius:50%!important;
              font-size:20px!important;
              line-height:1!important;
              overflow:hidden!important;
            }
          }
        </style>
        <a id="bmo-mobile-entry" href="/operatore-bodymind" aria-label="Apri Operatore BodyMind" title="Operatore BodyMind"
           style="position:fixed;right:14px;bottom:calc(86px + env(safe-area-inset-bottom));z-index:9999;
           width:46px;height:46px;display:grid;place-items:center;border-radius:50%;
           background:rgba(18,10,22,.94);border:1px solid rgba(244,90,157,.42);color:#fff;
           text-decoration:none;font-weight:900;font-size:20px;box-shadow:0 10px 26px rgba(0,0,0,.30);
           backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px)">✦</a>
        """
        html=html.replace("</body>",button+"</body>") if "</body>" in html else html+button
        resp.set_data(html)
    except Exception:
        pass
    return resp


@app.get("/favicon.ico")
def bodymind_operator_favicon():
    return redirect("/bodymind-media/logo",code=302)


@app.before_request
def bodymind_operator_legacy_entrypoints():
    if request.method!="GET":
        return None
    if request.path=="/assistente-automatico":
        return redirect("/operatore-bodymind")
    return None
