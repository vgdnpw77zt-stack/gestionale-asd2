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

from flask import jsonify, redirect, request, session

from .core import (
    app, db, layout, login_required, csrf_token, current_username, current_role, e
)

OPERATOR_VERSION = "R29.1"
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


def _is_mu(row) -> bool:
    t=_doc_type(row)
    return any(x in t for x in (
        "modulo unico","modulo_unico","mu-2026","mu 2026",
        "iscrizione manleva","domanda iscrizione"
    ))


def _is_medical(row) -> bool:
    t=_doc_type(row)
    return "certificato medico" in t or "certificato_medico" in t or re.search(r"\bcm\b",t) is not None


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
    m=re.search(r"\b(?:sono|mi chiamo)\s+([A-Za-zÀ-ÖØ-öø-ÿ'’-]{2,40})",text,re.I)
    return (m.group(1).strip().title() if m else "")


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
        pieces.append(f"Pagamenti registrati: {g['payments']}. Ricevute: {g['receipts']}.")
        return {
            "text":" ".join(pieces),
            "mode":"audit",
            "cards":[
                {"title":"Documenti da verificare","value":g["pending_docs"],"href":"/documenti/da-verificare"},
                {"title":"Certificati senza scadenza","value":len(g["missing_cert"]),"href":"/tesserati"},
                {"title":"Tutela minori da rivedere","value":len(g["minor_issues"]),"href":"/tesserati"},
            ],
            "links":[{"label":"Apri coda documenti","href":"/documenti/da-verificare"},{"label":"Quote & Incassi","href":"/quote-incassi"}]
        }

    if any(x in n for x in ("documenti da verificare","coda documenti","documenti in attesa","documenti pendenti")):
        cnt=_pending_count(conn)
        return {"text":f"Ci sono {cnt} documenti che richiedono una decisione umana.","mode":"local","links":[{"label":"Apri Da verificare","href":"/documenti/da-verificare"}]}

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
        snap=_athlete_snapshot(conn,athlete)
        name=snap["name"]
        tid=snap["tid"]

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

    return {
        "text":"Ho capito la richiesta, ma non voglio inventare una risposta. Se riguarda BodyMind posso cercare una persona, documenti, Modulo Unico, certificati, tutela, quote, pagamenti o ricevute. Puoi anche chiedermi “controlla BodyMind”.",
        "mode":"fallback",
        "allow_device_ai":True
    }


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
    @media(max-width:800px){{.bmo-hero{{grid-template-columns:1fr;text-align:center;padding:20px}}.bmo-avatar{{width:124px;height:124px}}.bmo-avatar img{{width:90px;height:90px}}.bmo-grid{{grid-template-columns:1fr}}.bmo-side{{position:static;order:-1}}.bmo-chat{{min-height:560px}}.bmo-msg{{max-width:94%}}}}
    </style>

    <main class="bmo">
      <section class="bmo-hero">
        <div class="bmo-avatar" id="bmoAvatar"><img src="/bodymind-media/logo" alt="BodyMind"></div>
        <div>
          <div class="bmo-kicker">BODYMIND · OPERATORE INTELLIGENTE · {OPERATOR_VERSION}</div>
          <h1>Ciao, {ident}.</h1>
          <p>Parlami come parleresti a una persona in segreteria. Posso cercare nel gestionale, controllare documenti e tesserati, verificare cosa manca, leggere quote e incassi e preparare operazioni chiedendoti conferma quando servono.</p>
          <div class="bmo-status">
            <span class="bmo-pill">{g['athletes']} tesserati</span>
            <span class="bmo-pill">{g['pending_docs']} documenti da verificare</span>
            <span class="bmo-pill">{len(g['minor_issues'])} tutele da rivedere</span>
            <span class="bmo-pill">{len(g['expiring_cert'])} certificati urgenti</span>
          </div>
        </div>
      </section>

      <section class="bmo-grid">
        <div class="bmo-chat">
          <div class="bmo-messages" id="bmoMessages">
            <div class="bmo-msg bot">Sono pronto. Puoi chiedermi, per esempio: “Abbiamo caricato il modulo di Balbinetti?”, “Cosa manca a Sofia Fabiani?”, “Chi non ha il certificato?”, “Quanto paga Gaia?”, oppure “Controlla BodyMind”.</div>
          </div>
          <div class="bmo-compose">
            <button class="bmo-mic" id="bmoMic" type="button" title="Parla">🎙️</button>
            <textarea id="bmoInput" placeholder="Scrivi o parla con l’Operatore BodyMind…" autocomplete="off"></textarea>
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
            <div class="small-muted" style="margin:5px 0 7px">PDF, immagini e DOCX passano all’Autopilot. Su PC puoi selezionare anche una cartella.</div>
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
      let listening=false, recognition=null;

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
        if(!voice.checked || !('speechSynthesis' in window) || !text)return;
        speechSynthesis.cancel();
        const u=new SpeechSynthesisUtterance(text);
        u.lang='it-IT';u.rate=.98;u.pitch=1;
        const voices=speechSynthesis.getVoices();
        const it=voices.find(v=>String(v.lang||'').toLowerCase().startsWith('it'));
        if(it)u.voice=it;
        u.onstart=()=>avatar.classList.add('speaking');
        u.onend=u.onerror=()=>avatar.classList.remove('speaking');
        speechSynthesis.speak(u);
      }}

      async function deviceAI(question,serverText){{
        try{{
          let lm=null;
          if(window.LanguageModel && typeof LanguageModel.create==='function'){{
            const availability=await LanguageModel.availability();
            if(availability==='available' || availability==='readily') lm=await LanguageModel.create();
          }} else if(window.ai?.languageModel?.create){{
            lm=await window.ai.languageModel.create();
          }}
          if(!lm)return null;
          const prompt='Sei Operatore BodyMind, assistente di segreteria di una ASD italiana. Rispondi in italiano con tono professionale e naturale. Non inventare dati del gestionale. Domanda: '+question+'\\nRisposta del motore BodyMind: '+serverText+'\\nSe la domanda è generale puoi ampliarla; se riguarda dati interni resta fedele alla risposta BodyMind.';
          return await lm.prompt(prompt);
        }}catch(e){{return null}}
      }}

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
          if(data.allow_device_ai){{
            const enhanced=await deviceAI(q,text);
            if(enhanced)text=enhanced;
          }}
          addMsg(text,'bot',data);speak(text);
        }}catch(err){{
          addMsg('Non riesco a contattare il motore dell’Operatore in questo momento. Non ho modificato nulla.','bot');
        }}finally{{send.disabled=false;input.focus()}}
      }}

      send.addEventListener('click',()=>ask(input.value));
      input.addEventListener('keydown',ev=>{{if(ev.key==='Enter'&&!ev.shiftKey){{ev.preventDefault();ask(input.value)}}}});
      document.querySelectorAll('[data-q]').forEach(b=>b.addEventListener('click',()=>ask(b.dataset.q)));

      const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
      if(SR){{
        recognition=new SR();recognition.lang='it-IT';recognition.interimResults=true;recognition.continuous=false;
        recognition.onstart=()=>{{listening=true;mic.classList.add('on');avatar.classList.add('listening')}};
        recognition.onend=()=>{{listening=false;mic.classList.remove('on');avatar.classList.remove('listening')}};
        recognition.onerror=()=>{{listening=false;mic.classList.remove('on');avatar.classList.remove('listening')}};
        recognition.onresult=ev=>{{
          let txt='';let final=false;
          for(let i=ev.resultIndex;i<ev.results.length;i++){{txt+=ev.results[i][0].transcript;if(ev.results[i].isFinal)final=true}}
          input.value=txt.trim();
          if(final&&input.value){{setTimeout(()=>ask(input.value),150)}}
        }};
        mic.addEventListener('click',()=>{{if(listening)recognition.stop();else{{speechSynthesis?.cancel();recognition.start()}}}});
      }}else{{
        mic.addEventListener('click',()=>{{input.focus();addMsg('Su questo browser il riconoscimento vocale diretto non è disponibile. Puoi usare la dettatura del dispositivo nel campo di testo.','bot')}});
      }}

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
    from .routes_email_documents import process_inbound_attachment, ALLOWED_INBOUND_DOCS
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
            })
        except Exception as exc:
            errors.append((f.filename or "file")+" · "+str(exc)[:180])
    auto=sum(1 for r in results if r.get("tesserato_id") and r.get("status") in ("associato","archived_to_tesserato"))
    review=sum(1 for r in results if r.get("status") in PENDING_STATUSES or not r.get("tesserato_id"))
    text=f"Ho analizzato {len(results)} file: {auto} associati automaticamente e {review} richiedono verifica."
    if errors:
        text+=f" {len(errors)} file non sono stati elaborati."
    return jsonify({
        "text":text,"mode":"upload","results":results,"errors":errors,
        "links":[{"label":"Apri Da verificare","href":"/documenti/da-verificare"},{"label":"Apri Documenti","href":"/documenti"}]
    })


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
