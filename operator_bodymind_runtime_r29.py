from __future__ import annotations

import json
import os
import re
import sqlite3
import unicodedata
import uuid
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

from flask import Response, jsonify, redirect, request, session, send_file

from .core import (
    app, db, layout, login_required, csrf_token, current_username, current_role, e
)

OPERATOR_VERSION = "R38.0"
PENDING_STATUSES = (
    "needs_manual_match","associato_tipo_da_verificare","richiede_conferma",
    "needs_review","da_verificare","pending",
)


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
    conn.commit()


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
        client=OpenAI(api_key=key)
        resp=client.responses.create(model=model,input=prompt)
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

    athlete, ambiguous=_match_athlete(conn,raw)
    if not athlete and not ambiguous:
        athlete=_context_athlete(conn,raw)
    if ambiguous:
        names=", ".join(_athlete_name(x) for x in ambiguous[:5])
        return {"text":"Ho trovato più possibili tesserati: "+names+". Dimmi nome e cognome completi.","mode":"clarify"}

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
            "text":"Posso parlare con te, riconoscerti per questa sessione, cercare tesserati, verificare Modulo Unico e dossier, controllare certificati e tutela minori, leggere quote e incassi, preparare modifiche di quota chiedendoti conferma, fare un controllo generale BodyMind e ricevere file/cartelle da passare all’Autopilot.",
            "mode":"help",
            "links":[{"label":"Da verificare","href":"/documenti/da-verificare"},{"label":"Quote & Incassi","href":"/quote-incassi"}]
        }

    cloud=_cloud_operator_answer(conn,raw,athlete=None)
    if cloud:
        return {"text":cloud,"mode":"cloud","allow_device_ai":False}

    return {
        "text":"Ho capito la richiesta, ma non voglio inventare una risposta. Se riguarda BodyMind posso cercare una persona, documenti, Modulo Unico, certificati, tutela, quote, pagamenti o ricevute. Puoi anche chiedermi “controlla BodyMind”.",
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
    try:
        _schema(conn)
        g=_global_check(conn)
    finally:
        conn.close()
    csrf=csrf_token()
    ident=e(_identity())
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
      .bmo-compose #bmoMobileFiles,.bmo-compose #bmoMobileFiles[hidden]{{display:none!important;position:absolute!important;width:0!important;height:0!important;overflow:hidden!important;pointer-events:none!important;}}
      .bmo-mic{{min-width:42px;width:42px;height:42px;border-radius:50%;font-size:20px;background:linear-gradient(145deg,#8d285e,#d43a7d);box-shadow:none;touch-action:manipulation;}}
      .bmo-mic.on{{box-shadow:0 0 0 4px rgba(244,90,157,.12);}}
      .bmo-attach{{display:block;min-width:36px;width:36px;height:36px;align-self:center;border-radius:11px;font-size:16px;padding:0;touch-action:manipulation;}}
      .bmo-compose textarea{{width:100%;min-width:0;max-width:100%;min-height:42px;height:42px;max-height:84px;resize:none;padding:10px 10px;align-self:center;border-radius:12px;font-size:16px;line-height:20px;box-sizing:border-box;overflow-y:auto;}}
      .bmo-send{{min-width:42px;width:42px;height:42px;padding:0;align-self:center;font-size:0;border-radius:12px;touch-action:manipulation;}}
      .bmo-send::after{{content:"➤";font-size:17px;line-height:1;}}
    }}
    </style>

    <main class="bmo">
      <section class="bmo-hero">
        <div class="bmo-avatar-wrap">
          <div class="bmo-avatar" id="bmoAvatar"><img src="/bodymind-media/logo" alt="BodyMind"></div>
          <div class="bmo-audio-bars" id="bmoAudioBars" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div>
          <div class="bmo-voice-status" id="bmoVoiceStatus">Tocca il microfono e parlami</div>
        </div>
        <div>
          <div class="bmo-kicker">BODYMIND · OPERATORE IA · {OPERATOR_VERSION}</div>
          <h1>Ciao, {ident}.</h1>
          <p>Parlami come parleresti a una persona in segreteria. Posso cercare nel gestionale, controllare documenti e tesserati, verificare cosa manca, leggere quote e incassi e preparare operazioni chiedendoti conferma quando serve.</p>
          <div class="bmo-status">
            <span class="bmo-pill">{g['athletes']} tesserati</span>
            <span class="bmo-pill">{g['pending_docs']} documenti da verificare</span>
            <span class="bmo-pill">{len(g['minor_issues'])} tutele da rivedere</span>
            <span class="bmo-pill">{len(g['expiring_cert'])} certificati urgenti</span>
            <span class="bmo-pill">{len(g['mu_review'])} MU da ricontrollare</span>
            <a class="bmo-pill" id="bmoAiPill" href="/operatore-bodymind/bridge/setup" style="text-decoration:none;color:inherit">IA iMac: verifica…</a>
            <span class="bmo-pill">IA cloud: {"pronta" if (os.environ.get("BODYMIND_AI_CLOUD") and os.environ.get("OPENAI_API_KEY")) else "non configurata"}</span>
          </div>
        </div>
      </section>

      <section class="bmo-grid">
        <div class="bmo-chat">
          <div class="bmo-messages" id="bmoMessages">
            <div class="bmo-msg bot">Sono pronto. Scrivimi o parlami: posso cercare tesserati, documenti, certificati, tutela minori, quote e incassi.</div>
          </div>
          <div class="bmo-compose">
            <button class="bmo-mic" id="bmoMic" type="button" title="Parla" aria-label="Parla con Operatore BodyMind">🎙️</button>
            <button class="bmo-attach" id="bmoAttach" type="button" title="Allega documento" aria-label="Allega documento">📎</button>
            <input id="bmoMobileFiles" type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.webp,.docx" hidden>
            <textarea id="bmoInput" placeholder="Scrivi oppure tocca il microfono e parla…" autocomplete="off"></textarea>
            <button class="bmo-send" id="bmoSend" type="button">Invia</button>
          </div>
        </div>

        <aside class="bmo-side">
          <h3>Scrivania</h3>
          <div class="bmo-quick">
            <button data-q="Controlla BodyMind">Controlla BodyMind</button>
            <button data-q="Quali documenti sono da verificare?">Documenti da verificare</button>
            <button data-q="Chi non ha il certificato medico?">Certificati</button>
            <button data-q="Ci sono tutele minori incomplete?">Tutela minori</button>
            <button data-q="Quanti pagamenti e ricevute risultano?">Pagamenti e ricevute</button>
          </div>
          <div class="bmo-upload">
            <b>Affidami documenti</b>
            <div class="small-muted" style="margin:5px 0 7px">PDF, immagini e DOCX: riconosco documenti ASD, tesserati, certificati e Moduli Unici. Su PC puoi affidarmi anche una cartella.</div>
            <form id="bmoUploadForm" enctype="multipart/form-data">
              <input type="file" name="files" id="bmoFiles" multiple accept=".pdf,.png,.jpg,.jpeg,.webp,.docx">
              <input type="file" name="folder" id="bmoFolder" multiple webkitdirectory directory>
              <button class="bmo-send" type="submit">Analizza e sistema</button>
            </form>
          </div>
          <div class="bmo-voice-row">
            <label><input type="checkbox" id="bmoVoice" checked> risposta vocale</label>
          </div>
        </aside>
      </section>
    </main>

    <script>
    (()=>{{
      const csrf={json.dumps(csrf)};
      const messages=document.getElementById('bmoMessages');
      const input=document.getElementById('bmoInput');
      const send=document.getElementById('bmoSend');
      const mic=document.getElementById('bmoMic');
      const avatar=document.getElementById('bmoAvatar');
      const voice=document.getElementById('bmoVoice');
      const voiceStatus=document.getElementById('bmoVoiceStatus');
      const attach=document.getElementById('bmoAttach');
      const mobileFiles=document.getElementById('bmoMobileFiles');
      let listening=false, recognition=null, micStream=null, audioContext=null, analyser=null, meterRAF=null;
      let ttsPrimed=false, ttsUtterance=null, ttsRetryTimer=null;
      const TTS_KEY='bodymind_tts_enabled_v2';
      function primeTTS(){{
        if(ttsPrimed || !('speechSynthesis' in window))return;
        try{{
          speechSynthesis.cancel();
          speechSynthesis.resume();
          ttsUtterance=new SpeechSynthesisUtterance('Voce attiva');
          ttsUtterance.lang='it-IT';ttsUtterance.volume=.01;ttsUtterance.rate=1.2;
          ttsUtterance.onstart=()=>{{ttsPrimed=true;try{{localStorage.setItem(TTS_KEY,'1')}}catch(e){{}}}};
          ttsUtterance.onend=()=>{{ttsPrimed=true;ttsUtterance=null;try{{localStorage.setItem(TTS_KEY,'1')}}catch(e){{}}}};
          speechSynthesis.speak(ttsUtterance);
        }}catch(e){{}}
      }}
      document.addEventListener('pointerdown',primeTTS,{{capture:true,once:true}});
      document.addEventListener('touchend',primeTTS,{{capture:true,once:true}});
      document.addEventListener('click',primeTTS,{{capture:true,once:true}});
      try{{if(localStorage.getItem(TTS_KEY)==='1')ttsPrimed=true}}catch(e){{}}
      // BODYMIND_R39_IOS_TTS_UNLOCK
      // BODYMIND_R39_IOS_TTS_PERSISTENT_FIX
      (async()=>{{
        const p=document.getElementById('bmoAiPill'); if(!p)return;
        try{{
          const r=await fetch('/operatore-bodymind/bridge/status',{{headers:{{'Cache-Control':'no-cache'}}}});
          const d=await r.json();
          p.textContent=d.online?'IA iMac: ONLINE':'IA iMac: collega/configura';
          p.title=d.last_seen_at?('Ultimo contatto: '+d.last_seen_at):'Apri la configurazione del bridge locale';
        }}catch(e){{p.textContent='IA iMac: stato non disponibile'}}
      }})();

      function esc(s){{const d=document.createElement('div');d.textContent=String(s??'');return d.innerHTML}}
      function addMsg(text,who='bot',data={{}}){{
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
        messages.appendChild(box);messages.scrollTop=messages.scrollHeight;
      }}

      function speak(text){{
        if(!voice || !voice.checked || !('speechSynthesis' in window) || !text)return;
        const doSpeak=()=>{{
          try{{
            if(ttsRetryTimer){{clearTimeout(ttsRetryTimer);ttsRetryTimer=null}}
            speechSynthesis.cancel();
            speechSynthesis.resume();
            const u=new SpeechSynthesisUtterance(String(text).replace(/\s+/g,' ').trim());
            ttsUtterance=u;
            u.lang='it-IT';u.rate=.96;u.pitch=.94;u.volume=1;
            const voices=speechSynthesis.getVoices()||[];
            const italian=voices.filter(v=>String(v.lang||'').toLowerCase().startsWith('it'));
            const preferred=['premium','enhanced','alice','federica','elsa','cosimo','luca','it-it'];
            let it=null;
            for(const key of preferred){{
              it=italian.find(v=>String(v.name||'').toLowerCase().includes(key));
              if(it)break;
            }}
            if(!it)it=italian[0]||null;
            if(it)u.voice=it;
            let started=false;
            u.onstart=()=>{{started=true;ttsPrimed=true;try{{localStorage.setItem(TTS_KEY,'1')}}catch(e){{}};avatar.classList.add('speaking');if(voiceStatus)voiceStatus.textContent='Ti sto rispondendo…'}};
            u.onend=()=>{{ttsUtterance=null;avatar.classList.remove('speaking');if(voiceStatus)voiceStatus.textContent='Tocca il microfono e parlami'}};
            u.onerror=()=>{{ttsUtterance=null;avatar.classList.remove('speaking');if(voiceStatus)voiceStatus.textContent='Voce non partita: tocca una volta lo schermo e riprova'}};
            speechSynthesis.speak(u);
            ttsRetryTimer=setTimeout(()=>{{
              if(!started && ttsUtterance===u){{
                try{{speechSynthesis.resume();speechSynthesis.speak(u)}}catch(e){{}}
              }}
            }},350);
          }}catch(e){{if(voiceStatus)voiceStatus.textContent='Voce non disponibile su questo dispositivo'}}
        }};
        if(!ttsPrimed)primeTTS();
        setTimeout(doSpeak,ttsPrimed?20:180);
      }}

      // R38: local intelligence is only the paired iMac bridge; offline uses deterministic server logic.

      async function ask(q){{
        q=String(q||'').trim();if(!q)return;
        addMsg(q,'me');input.value='';send.disabled=true;
        try{{
          const r=await fetch('/operatore-bodymind/chat',{{
            method:'POST',headers:{{'Content-Type':'application/json','X-CSRFToken':csrf}},
            body:JSON.stringify({{message:q}})
          }});
          const data=await r.json();
          let text=data.text||'Non ho ricevuto una risposta.';
          addMsg(text,'bot',data);speak(text);
        }}catch(err){{
          addMsg('Non riesco a contattare il motore dell’Operatore in questo momento. Non ho modificato nulla.','bot');
        }}finally{{send.disabled=false;input.focus()}}
      }}

      send.addEventListener('click',()=>ask(input.value));
      input.addEventListener('keydown',ev=>{{if(ev.key==='Enter'&&!ev.shiftKey){{ev.preventDefault();ask(input.value)}}}});
      document.querySelectorAll('[data-q]').forEach(b=>b.addEventListener('click',()=>ask(b.dataset.q)));


      function stopMicStream(){{
        if(meterRAF){{cancelAnimationFrame(meterRAF);meterRAF=null}}
        try{{audioContext?.close()}}catch(e){{}}
        audioContext=null;analyser=null;
        if(micStream){{micStream.getTracks().forEach(t=>t.stop());micStream=null}}
      }}
      function startMeter(stream){{
        try{{
          const AC=window.AudioContext||window.webkitAudioContext;if(!AC)return;
          audioContext=new AC();const source=audioContext.createMediaStreamSource(stream);
          analyser=audioContext.createAnalyser();analyser.fftSize=256;source.connect(analyser);
          const data=new Uint8Array(analyser.frequencyBinCount);
          const tick=()=>{{if(!analyser)return;analyser.getByteFrequencyData(data);let sum=0;for(let i=0;i<data.length;i++)sum+=data[i];const level=Math.min(1,(sum/data.length)/90);avatar.style.transform='scale('+(1+level*.045)+')';meterRAF=requestAnimationFrame(tick)}};tick();
        }}catch(e){{}}
      }}
      async function ensureMic(){{
        if(!window.isSecureContext)throw new Error('Il microfono richiede HTTPS.');
        if(!navigator.mediaDevices?.getUserMedia)throw new Error('Questo browser non espone il microfono.');
        if(micStream)return micStream;
        micStream=await navigator.mediaDevices.getUserMedia({{audio:{{echoCancellation:true,noiseSuppression:true,autoGainControl:true}}}});
        startMeter(micStream);return micStream;
      }}
      function humanMicError(code){{
        const c=String(code||'');
        if(c==='not-allowed'||c==='service-not-allowed')return 'Accesso al microfono negato. Consenti il microfono a BodyMind nelle impostazioni di Safari e riprova.';
        if(c==='audio-capture')return 'Non riesco ad accedere al microfono del dispositivo.';
        if(c==='no-speech')return 'Non ho sentito una frase. Tocca di nuovo il microfono e parla normalmente.';
        if(c==='network')return 'Il riconoscimento vocale del browser non è riuscito a collegarsi. Riprova.';
        return 'Il riconoscimento vocale non è partito correttamente ('+c+'). Riprova.';
      }}

      const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
      if(SR){{
        recognition=new SR();recognition.lang='it-IT';recognition.interimResults=true;recognition.continuous=false;recognition.maxAlternatives=1;
        recognition.onstart=()=>{{listening=true;mic.classList.add('on');avatar.classList.add('listening');if(voiceStatus)voiceStatus.textContent='Ti ascolto… parla normalmente'}};
        recognition.onend=()=>{{listening=false;mic.classList.remove('on');avatar.classList.remove('listening');avatar.style.transform='';stopMicStream();if(voiceStatus&&voiceStatus.textContent.startsWith('Ti ascolto'))voiceStatus.textContent='Tocca il microfono e parlami'}};
        recognition.onerror=ev=>{{listening=false;mic.classList.remove('on');avatar.classList.remove('listening');avatar.style.transform='';stopMicStream();const t=humanMicError(ev.error);if(voiceStatus)voiceStatus.textContent=t;addMsg(t,'bot')}};
        recognition.onresult=ev=>{{let txt='';let final=false;for(let i=ev.resultIndex;i<ev.results.length;i++){{txt+=ev.results[i][0].transcript;if(ev.results[i].isFinal)final=true}}input.value=txt.trim();if(final&&input.value){{if(voiceStatus)voiceStatus.textContent='Ho capito. Un attimo…';setTimeout(()=>ask(input.value),120)}}}};
        mic.addEventListener('click',async()=>{{
          if(listening){{try{{recognition.stop()}}catch(e){{}};return}}
          try{{speechSynthesis?.cancel();if(voiceStatus)voiceStatus.textContent='Attivo il microfono…';await ensureMic();recognition.start()}}
          catch(err){{stopMicStream();avatar.style.transform='';const t=(err?.name==='NotAllowedError'||err?.name==='SecurityError')?'Accesso al microfono negato. Consenti il microfono a BodyMind nelle impostazioni di Safari e riprova.':('Microfono non disponibile: '+(err?.message||err));if(voiceStatus)voiceStatus.textContent=t;addMsg(t,'bot')}}
        }});
      }}else{{
        mic.addEventListener('click',async()=>{{
          try{{await ensureMic();avatar.classList.add('listening');mic.classList.add('on');if(voiceStatus)voiceStatus.textContent='Microfono attivo. La trascrizione vocale web non è disponibile qui; sul Mac useremo il Bridge locale.';setTimeout(()=>{{avatar.classList.remove('listening');mic.classList.remove('on');avatar.style.transform='';stopMicStream()}},3500)}}
          catch(err){{const t='Non riesco ad aprire il microfono: '+(err?.message||err);if(voiceStatus)voiceStatus.textContent=t;addMsg(t,'bot')}}
        }});
      }}

      attach?.addEventListener('click',()=>mobileFiles?.click());
      mobileFiles?.addEventListener('change',async()=>{{
        const files=[...(mobileFiles.files||[])];if(!files.length)return;
        const fd=new FormData();files.forEach(f=>fd.append('files',f,f.name));
        addMsg('Ho ricevuto '+files.length+' file. Li passo all’Autopilot.','bot');
        try{{const r=await fetch('/operatore-bodymind/upload',{{method:'POST',headers:{{'X-CSRFToken':csrf}},body:fd}});const data=await r.json();addMsg(data.text||'Analisi completata.','bot',data);speak(data.text||'Analisi completata.')}}
        catch(e){{addMsg('Il caricamento non è riuscito. Non ho modificato file esistenti.','bot')}}
        mobileFiles.value='';
      }});

      document.getElementById('bmoUploadForm').addEventListener('submit',async ev=>{{
        ev.preventDefault();
        const fd=new FormData();
        const files=[...document.getElementById('bmoFiles').files,...document.getElementById('bmoFolder').files];
        if(!files.length){{addMsg('Seleziona almeno un file o una cartella.','bot');return}}
        files.forEach(f=>fd.append('files',f,f.webkitRelativePath||f.name));
        addMsg('Sto passando '+files.length+' file all’Autopilot. Non chiudere questa pagina.','bot');
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
        try:
            from .routes_operator_bridge import bridge_enhance_result
            result=bridge_enhance_result(conn,message,result,_conv_id(),_identity())
        except Exception as bridge_exc:
            try:
                _log(conn,"system","Local AI bridge unavailable: "+repr(bridge_exc))
            except Exception:
                pass
        if result.get("allow_device_ai"):
            cloud=_cloud_ai(message,result.get("text",""))
            if cloud:
                result["text"]=cloud
                result["mode"]="cloud"
                result["allow_device_ai"]=False
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


@app.post("/operatore-bodymind/upload")
@login_required
def bodymind_operator_upload():
    if current_role() not in ("admin","manager"):
        return jsonify({"text":"L’account connesso non può affidare documenti all’Autopilot.","mode":"warning"}),403
    files=request.files.getlist("files")
    if not files:
        return jsonify({"text":"Non ho ricevuto file.","mode":"warning"}),400
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
            if asd_kind:
                try:
                    f.stream.seek(0)
                    _,saved_name=_save_uploaded_asd_document(f,asd_kind["folder"])
                    results.append({
                        "name":name,"status":"archiviato_asd","tesserato_id":None,
                        "type":"documento_asd","confidence":asd_kind["confidence"],
                        "folder":asd_kind["folder"],"reason":asd_kind["reason"],"saved_name":saved_name,
                    })
                    continue
                except Exception as exc:
                    errors.append(name+" · archivio ASD: "+str(exc)[:160])
                    continue
            res=process_inbound_attachment(
                name,data,subject="Operatore BodyMind",
                sender=current_username(),body_text="Caricato dalla scrivania Operatore BodyMind",
                source="operatore_bodymind"
            )
            results.append({
                "name":name,
                "status":res.get("status"),
                "tesserato_id":res.get("tesserato_id"),
                "type":(res.get("classification") or {}).get("type"),
                "confidence":(res.get("classification") or {}).get("confidence"),
                "folder":"Dossier/Autopilot",
            })
        except Exception as exc:
            errors.append((f.filename or "file")+" · "+str(exc)[:180])
    auto=sum(1 for r in results if r.get("tesserato_id") and r.get("status") in ("associato","archived_to_tesserato"))
    asd=sum(1 for r in results if r.get("status")=="archiviato_asd")
    review=sum(1 for r in results if r.get("status") in PENDING_STATUSES or (not r.get("tesserato_id") and r.get("status")!="archiviato_asd"))
    text=f"Ho analizzato {len(results)} file: {auto} associati a tesserati, {asd} archiviati come documenti ASD e {review} richiedono verifica."
    if errors:
        text+=f" {len(errors)} file non sono stati elaborati."
    return jsonify({
        "text":text,"mode":"upload","results":results,"errors":errors,
        "links":[{"label":"Apri Da verificare","href":"/documenti/da-verificare"},{"label":"Apri Documenti","href":"/documenti"}]
    })


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
