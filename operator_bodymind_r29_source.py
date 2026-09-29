# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from flask import Response, jsonify, request, session, send_file
from werkzeug.utils import secure_filename

from .core import (
    app, db, e, layout, csrf_token, login_required, current_username,
    current_role, current_tenant_label, get_workspace_media_dir, now_iso_dt
)
from .routes_email_documents import process_inbound_attachment
from .medical_certificate_dates import extract_attachment_text

APP_ROOT = Path("/data/top2_app")
ALLOWED_UPLOADS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".docx"}
ASD_DOC_HINTS = {
    "verbale", "assemblea", "consiglio direttivo", "consiglio", "direttivo",
    "statuto", "affiliazione", "rasd", "csen", "polizza", "assicurazione",
    "contratto", "convenzione", "siae", "tulps", "locazione", "accordo",
    "evento", "saggio", "gara", "comitato", "presidente", "vicepresidente"
}
STOPWORDS = {
    "abbiamo","caricato","caricata","caricati","il","lo","la","i","gli","le",
    "modulo","documento","documenti","certificato","medico","di","del","della",
    "per","con","senza","cosa","manca","mancano","a","ad","un","una","mi","dici",
    "dimmi","controlla","vedi","verifica","pagamento","pagamenti","quota","paga",
    "quanto","ricevuta","ricevute","tutela","consenso","genitoriale"
}

def _norm(value: str) -> str:
    raw = unicodedata.normalize("NFKD", str(value or ""))
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = re.sub(r"[^a-zA-Z0-9]+", " ", raw).lower()
    return " ".join(raw.split())

def _table_exists(conn, name: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())

def _cols(conn, name: str) -> set[str]:
    if not _table_exists(conn, name):
        return set()
    return {str(r[1]) for r in conn.execute(f"PRAGMA table_info({name})").fetchall()}

def _ensure_schema(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS operator_messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            persona TEXT,
            username TEXT,
            role TEXT,
            direction TEXT NOT NULL,
            text TEXT NOT NULL,
            intent TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS operator_pending_actions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_key TEXT NOT NULL UNIQUE,
            action_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            summary TEXT NOT NULL,
            requested_by TEXT,
            persona TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            decided_at TEXT,
            decided_by TEXT,
            result_text TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS operator_preferences(
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT
        )
    """)
    conn.commit()

def _log_message(conn, direction: str, text: str, intent: str = "") -> None:
    _ensure_schema(conn)
    conn.execute(
        "INSERT INTO operator_messages(persona,username,role,direction,text,intent,created_at) VALUES(?,?,?,?,?,?,?)",
        (
            str(session.get("bodymind_operator_persona") or ""),
            current_username(), current_role(), direction, str(text or "")[:12000],
            str(intent or "")[:120], now_iso_dt()
        ),
    )
    conn.commit()

def _display_name(conn=None) -> str:
    explicit = str(session.get("bodymind_operator_persona") or "").strip()
    if explicit:
        return explicit
    username = current_username()
    if conn is None:
        conn = db()
        own = True
    else:
        own = False
    try:
        if _table_exists(conn, "users"):
            row = conn.execute(
                "SELECT full_name,username FROM users WHERE lower(username)=lower(?) LIMIT 1",
                (username,),
            ).fetchone()
            if row:
                full = str(row["full_name"] or "").strip()
                if full:
                    return full.split()[0]
                usr = str(row["username"] or "").strip()
                if usr and len(usr) < 40 and "bodymind" not in usr.lower():
                    return usr
    except Exception:
        pass
    finally:
        if own:
            conn.close()
    return "Daniele" if username.lower() in {"admin", "dan2478"} else (username or "operatore")

def _find_athlete(conn, query: str):
    if not _table_exists(conn, "tesserati"):
        return None, []
    rows = conn.execute("SELECT * FROM tesserati ORDER BY cognome,nome").fetchall()
    q = _norm(query)
    q_tokens = [t for t in q.split() if t not in STOPWORDS and len(t) > 1]
    scored = []
    for row in rows:
        nome = _norm(row["nome"] if "nome" in row.keys() else "")
        cognome = _norm(row["cognome"] if "cognome" in row.keys() else "")
        full = (nome + " " + cognome).strip()
        rev = (cognome + " " + nome).strip()
        score = 0
        if full and (full in q or rev in q):
            score = 100
        elif cognome and cognome in q:
            score = 92
            if nome and nome in q:
                score = 100
        else:
            name_tokens = set((nome + " " + cognome).split())
            overlap = len(name_tokens.intersection(q_tokens))
            if overlap:
                score = 60 + 15 * overlap
        if score:
            scored.append((score, row))
    scored.sort(key=lambda x: (-x[0], str(x[1]["cognome"]), str(x[1]["nome"])))
    if not scored:
        return None, []
    best_score = scored[0][0]
    best = [r for s, r in scored if s == best_score]
    if len(best) == 1 and best_score >= 80:
        return best[0], []
    return None, best[:5]

def _resolve_document_path(raw: str) -> Path | None:
    s = str(raw or "").strip()
    if not s:
        return None
    p = Path(s)
    candidates = [p] if p.is_absolute() else [
        get_workspace_media_dir() / p,
        APP_ROOT / p,
        Path("/data") / p,
    ]
    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_file():
                return candidate
        except Exception:
            pass
    try:
        hits = [x for x in get_workspace_media_dir().rglob(p.name) if x.is_file()] if p.name else []
        if len(hits) == 1:
            return hits[0]
    except Exception:
        pass
    return None

def _document_rows(conn, tid: int):
    docs = []
    if _table_exists(conn, "documenti"):
        cols = _cols(conn, "documenti")
        visible = " AND coalesce(visibile,1)=1" if "visibile" in cols else ""
        rows = conn.execute(
            "SELECT * FROM documenti WHERE tesserato_id=?"+visible+" ORDER BY id DESC", (tid,)
        ).fetchall()
        for r in rows:
            docs.append({
                "source":"dossier",
                "id":int(r["id"]),
                "title":str((r["titolo"] if "titolo" in r.keys() else "") or ""),
                "category":str((r["categoria"] if "categoria" in r.keys() else "") or ""),
                "type":str((r["doc_type"] if "doc_type" in r.keys() else "") or ""),
                "status":str((r["status"] if "status" in r.keys() else "salvato") or ""),
                "file_ok":bool(_resolve_document_path(r["filename"] if "filename" in r.keys() else "")),
                "url":f"/documenti/visualizza/{int(r['id'])}",
            })
    if _table_exists(conn, "inbound_documents"):
        ic = _cols(conn, "inbound_documents")
        tid_expr = []
        for f in ("tesserato_id","matched_tesserato_id","suggested_tesserato_id"):
            if f in ic:
                tid_expr.append(f"coalesce({f},0)=?")
        if tid_expr:
            params = tuple(tid for _ in tid_expr)
            rows = conn.execute(
                "SELECT * FROM inbound_documents WHERE ("+" OR ".join(tid_expr)+") AND coalesce(deleted_at,'')='' ORDER BY id DESC",
                params,
            ).fetchall()
            for r in rows:
                docs.append({
                    "source":"inbound",
                    "id":int(r["id"]),
                    "title":str((r["original_filename"] if "original_filename" in r.keys() else "") or ""),
                    "category":str((r["document_label"] if "document_label" in r.keys() else "") or ""),
                    "type":str((r["document_type"] if "document_type" in r.keys() else "") or (r["doc_type"] if "doc_type" in r.keys() else "") or ""),
                    "status":str((r["status"] if "status" in r.keys() else "") or ""),
                    "file_ok":bool(_resolve_document_path((r["saved_path"] if "saved_path" in r.keys() else "") or (r["path"] if "path" in r.keys() else ""))),
                    "url":f"/documenti-automatici/file/{int(r['id'])}",
                })
    return docs

def _is_mu(doc: dict) -> bool:
    hay = _norm(" ".join([doc.get("type",""), doc.get("title",""), doc.get("category","")]))
    return any(x in hay for x in (
        "modulo unico", "modulo_unico", "modulo unico tesseramento",
        "domanda iscrizione", "iscrizione e manleva"
    ))

def _athlete_state(conn, row) -> dict:
    tid = int(row["id"])
    docs = _document_rows(conn, tid)
    minor = None
    if _table_exists(conn, "minori"):
        minor = conn.execute("SELECT * FROM minori WHERE tesserato_id=? LIMIT 1",(tid,)).fetchone()
    payments = []
    if _table_exists(conn, "pagamenti"):
        payments = conn.execute("SELECT * FROM pagamenti WHERE tesserato_id=? ORDER BY id DESC LIMIT 12",(tid,)).fetchall()
    mu_docs = [d for d in docs if _is_mu(d)]
    verified_mu = [d for d in mu_docs if _norm(d.get("status")) in {"verificato","salvato","associato","manual accepted","manual_accepted"}]
    return {
        "row": row,
        "tid": tid,
        "docs": docs,
        "mu_docs": mu_docs,
        "verified_mu": verified_mu,
        "minor": minor,
        "payments": payments,
    }

def _athlete_links(tid: int):
    return [
        {"label":"Apri scheda atleta","url":f"/tesserati/{tid}/scheda"},
        {"label":"Apri dossier documenti","url":f"/documenti?tesserato_id={tid}"},
        {"label":"Quote & Incassi","url":f"/quote-incassi/atleta/{tid}"},
    ]

def _quota_text(row) -> str:
    keys = set(row.keys())
    custom = row["quota_personalizzata"] if "quota_personalizzata" in keys else None
    discount = float(row["quota_sconto_fisso"] or 0) if "quota_sconto_fisso" in keys else 0
    qtype = str(row["quota_tipo"] or "standard") if "quota_tipo" in keys else "standard"
    note = str(row["quota_note"] or "").strip() if "quota_note" in keys else ""
    if custom not in (None, ""):
        return f"quota personalizzata €{float(custom):.2f}" + (f" ({note})" if note else "")
    if discount:
        return f"quota {qtype}, sconto fisso €{discount:.2f}" + (f" ({note})" if note else "")
    return f"quota {qtype}" + (f" ({note})" if note else "")

def _medical_text(row) -> str:
    expiry = str(row["certificato_scadenza"] or "").strip() if "certificato_scadenza" in row.keys() else ""
    if not expiry:
        return "certificato medico senza scadenza registrata"
    try:
        dt = datetime.strptime(expiry[:10], "%Y-%m-%d").date()
        delta = (dt - datetime.now().date()).days
        if delta < 0:
            return f"certificato medico scaduto il {dt.strftime('%d/%m/%Y')}"
        if delta <= 30:
            return f"certificato medico in scadenza il {dt.strftime('%d/%m/%Y')} ({delta} giorni)"
        return f"certificato medico valido fino al {dt.strftime('%d/%m/%Y')}"
    except Exception:
        return f"scadenza certificato: {expiry}"

def _minor_text(state: dict) -> str:
    row = state["row"]
    is_minor = int((row["minorenne"] if "minorenne" in row.keys() else 0) or 0) == 1
    if not is_minor:
        return "atleta maggiorenne"
    m = state["minor"]
    if not m:
        return "minorenne: scheda tutela non collegata"
    mk = set(m.keys())
    signed = int((m["consenso_firmato"] if "consenso_firmato" in mk else 0) or 0) == 1
    authz = int((m["autorizzazioni_ok"] if "autorizzazioni_ok" in mk else 0) or 0) == 1
    guardian = str((row["genitore"] if "genitore" in row.keys() else "") or "").strip()
    if signed and authz and guardian:
        return "tutela minore coperta: consenso firmato, sezione autorizzazioni verificata e genitore presente"
    missing=[]
    if not guardian: missing.append("genitore")
    if not signed: missing.append("consenso firmato")
    if not authz: missing.append("autorizzazioni")
    return "tutela minore da completare: " + ", ".join(missing)

def _create_action(conn, action_type: str, payload: dict, summary: str) -> dict:
    _ensure_schema(conn)
    key = uuid4().hex
    conn.execute(
        """INSERT INTO operator_pending_actions(action_key,action_type,payload_json,summary,requested_by,persona,status,created_at)
           VALUES(?,?,?,?,?,?,?,?)""",
        (key, action_type, json.dumps(payload, ensure_ascii=False), summary, current_username(),
         _display_name(conn), "pending", now_iso_dt())
    )
    conn.commit()
    return {"key":key, "type":action_type, "summary":summary}

def _operator_check(conn) -> tuple[str,list]:
    pending = 0
    if _table_exists(conn,"inbound_documents"):
        pending = int(conn.execute("""
            SELECT COUNT(*) FROM inbound_documents
            WHERE coalesce(deleted_at,'')=''
              AND lower(coalesce(status,'')) IN
              ('needs_manual_match','richiede_conferma','associato_tipo_da_verificare','needs_review','da_verificare','pending','pagamento_da_verificare')
        """).fetchone()[0])
    expired = due = no_cert = 0
    if _table_exists(conn,"tesserati"):
        rows = conn.execute("SELECT * FROM tesserati WHERE coalesce(attivo,1)=1").fetchall()
        today = datetime.now().date()
        for r in rows:
            raw = str((r["certificato_scadenza"] if "certificato_scadenza" in r.keys() else "") or "").strip()
            if not raw:
                no_cert += 1
                continue
            try:
                d = datetime.strptime(raw[:10],"%Y-%m-%d").date()
                delta=(d-today).days
                if delta < 0: expired += 1
                elif delta <= 30: due += 1
            except Exception:
                pass
    minor_issues = 0
    if _table_exists(conn,"tesserati") and _table_exists(conn,"minori"):
        minors=conn.execute("SELECT * FROM tesserati WHERE coalesce(minorenne,0)=1 AND coalesce(attivo,1)=1").fetchall()
        for r in minors:
            m=conn.execute("SELECT * FROM minori WHERE tesserato_id=? LIMIT 1",(int(r["id"]),)).fetchone()
            guardian=str((r["genitore"] if "genitore" in r.keys() else "") or "").strip()
            if not m or not guardian or int((m["consenso_firmato"] if m and "consenso_firmato" in m.keys() else 0) or 0)!=1 or int((m["autorizzazioni_ok"] if m and "autorizzazioni_ok" in m.keys() else 0) or 0)!=1:
                minor_issues += 1
    text = (
        f"Controllo BodyMind completato. Documenti da verificare: {pending}. "
        f"Certificati scaduti: {expired}; in scadenza entro 30 giorni: {due}; senza scadenza registrata: {no_cert}. "
        f"Minori con tutela da ricontrollare: {minor_issues}."
    )
    links=[
        {"label":"Documenti da verificare","url":"/documenti/da-verificare"},
        {"label":"Quote & Incassi","url":"/quote-incassi"},
        {"label":"Tesserati","url":"/tesserati"},
    ]
    return text, links

def _cloud_context(conn, query: str, athlete=None) -> str:
    facts=[]
    if _table_exists(conn,"tesserati"):
        facts.append(f"Tesserati totali: {int(conn.execute('SELECT COUNT(*) FROM tesserati').fetchone()[0])}.")
    if _table_exists(conn,"documenti"):
        facts.append(f"Documenti dossier: {int(conn.execute('SELECT COUNT(*) FROM documenti WHERE coalesce(visibile,1)=1').fetchone()[0])}.")
    if _table_exists(conn,"inbound_documents"):
        facts.append(f"Documenti inbound: {int(conn.execute(\"SELECT COUNT(*) FROM inbound_documents WHERE coalesce(deleted_at,'')=''\").fetchone()[0])}.")
    if athlete is not None:
        st=_athlete_state(conn, athlete)
        facts.append(
            f"Atleta: {athlete['nome']} {athlete['cognome']}; {_medical_text(athlete)}; {_quota_text(athlete)}; "
            f"documenti collegati {len(st['docs'])}; Moduli Unici riconosciuti {len(st['mu_docs'])}; {_minor_text(st)}."
        )
    return " ".join(facts)

def _cloud_answer(conn, query: str, athlete=None) -> str | None:
    key = str(os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        return None
    try:
        from openai import OpenAI
        model = str(os.environ.get("BODYMIND_AI_MODEL") or "gpt-5.6-luna").strip()
        client = OpenAI(api_key=key)
        context = _cloud_context(conn, query, athlete)
        prompt = f"""Sei Operatore BodyMind, segreteria digitale di una ASD di danza aerea.
Parla in italiano naturale, professionale e conversazionale. Usa SOLO i fatti forniti dal gestionale.
Non inventare documenti, firme, pagamenti, consensi, quote o autorizzazioni.
Se una modifica richiede conferma, dillo esplicitamente e non affermare di averla eseguita.
Distingui sempre documento presente, associato e verificato.
Gli NO espliciti a opzioni facoltative non sono documenti mancanti.
Persona che sta parlando: {_display_name(conn)}. Ruolo login: {current_role()}.
Fatti reali: {context}
Richiesta: {query}
Rispondi in modo utile e non prolisso."""
        resp = client.responses.create(model=model, input=prompt)
        out = str(getattr(resp, "output_text", "") or "").strip()
        return out[:6000] if out else None
    except Exception:
        return None

def _answer(conn, query: str) -> dict:
    raw = str(query or "").strip()
    q = _norm(raw)
    links=[]
    intent="conversation"

    # Persona conversationally declared. This does not change authenticated user/permissions.
    m = re.search(r"\b(?:sono|mi chiamo)\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ' -]{1,40})", raw, flags=re.I)
    if m and ("ciao" in q or q.startswith("sono ") or "mi chiamo" in q):
        name = re.split(r"[,.;!?]", m.group(1))[0].strip()
        name = " ".join(name.split()[:3])
        session["bodymind_operator_persona"] = name
        return {"text":f"Ciao {name}. Ti riconosco come interlocutore di questa sessione. L'accesso e i permessi restano quelli dell'utente autenticato. Dimmi pure cosa vuoi controllare o fare in BodyMind.", "intent":"identity", "links":[]}

    if q in {"ciao","buongiorno","buonasera","salve","hey"} or q.startswith("ciao "):
        name=_display_name(conn)
        return {"text":f"Ciao {name}. Sono l'Operatore BodyMind. Posso controllare tesserati, documenti, Modulo Unico, tutela minori, certificati, quote, incassi e ricevute; posso anche ricevere cartelle o documenti e sistemarli nel flusso corretto.", "intent":"greeting","links":[]}

    if any(x in q for x in ("controlla tutto","controlla bodymind","situazione generale","cosa manca oggi","fai un controllo")):
        text, links = _operator_check(conn)
        return {"text":text,"intent":"full_check","links":links}

    if "document" in q and any(x in q for x in ("da verificare","in attesa","pendenti","sospesi")):
        count=0
        if _table_exists(conn,"inbound_documents"):
            count=int(conn.execute("""SELECT COUNT(*) FROM inbound_documents WHERE coalesce(deleted_at,'')='' AND lower(coalesce(status,'')) IN ('needs_manual_match','richiede_conferma','associato_tipo_da_verificare','needs_review','da_verificare','pending','pagamento_da_verificare')""").fetchone()[0])
        return {"text":f"Ci sono {count} documenti che richiedono verifica o decisione.", "intent":"pending_documents","links":[{"label":"Apri Da verificare","url":"/documenti/da-verificare"}]}

    if "certificat" in q and any(x in q for x in ("chi non","manc","scadut","scaden")) and _table_exists(conn,"tesserati"):
        today=datetime.now().date()
        issues=[]
        rows=conn.execute("SELECT id,nome,cognome,certificato_scadenza FROM tesserati WHERE coalesce(attivo,1)=1 ORDER BY cognome,nome").fetchall()
        for r in rows:
            rawd=str(r["certificato_scadenza"] or "").strip()
            state=""
            if not rawd:
                state="senza scadenza registrata"
            else:
                try:
                    d=datetime.strptime(rawd[:10],"%Y-%m-%d").date()
                    delta=(d-today).days
                    if delta < 0: state=f"scaduto il {d.strftime('%d/%m/%Y')}"
                    elif delta <= 30: state=f"scade il {d.strftime('%d/%m/%Y')}"
                except Exception:
                    pass
            if state:
                issues.append(f"{r['nome']} {r['cognome']} — {state}")
        text="Situazioni certificati: " + ("; ".join(issues[:18]) if issues else "nessuna criticità nei prossimi 30 giorni.")
        if len(issues)>18: text += f" Altri {len(issues)-18} casi non mostrati."
        return {"text":text,"intent":"medical_audit","links":[{"label":"Apri Tesserati","url":"/tesserati"}]}

    athlete, ambiguous = _find_athlete(conn, raw)
    if ambiguous:
        names=", ".join(f"{r['nome']} {r['cognome']}" for r in ambiguous)
        return {"text":f"Ho trovato più corrispondenze possibili: {names}. Dimmi nome e cognome completi così non rischio di toccare la persona sbagliata.", "intent":"ambiguous_athlete","links":[]}

    if athlete is not None:
        state=_athlete_state(conn, athlete)
        tid=state["tid"]
        name=f"{athlete['nome']} {athlete['cognome']}"
        links=_athlete_links(tid)

        # Quota proposal: requires explicit confirmation.
        amount_match=re.search(r"(?:paga|quota(?:\s+mensile)?(?:\s+di)?|mensile(?:\s+di)?)\s*(?:€\s*)?(\d+(?:[.,]\d{1,2})?)", q)
        if amount_match:
            amount=float(amount_match.group(1).replace(",","."))
            reason=""
            rm=re.search(r"(?:sconto|perche|perché|motivo)\s+(.+)$", raw, flags=re.I)
            if rm: reason=rm.group(1).strip()
            if "sconto sorell" in q: reason="sconto sorelle"
            summary=f"Impostare per {name} una quota personalizzata di €{amount:.2f}" + (f" · {reason}" if reason else "")
            action=_create_action(conn,"set_quota",{"tesserato_id":tid,"amount":amount,"reason":reason},summary)
            return {"text":f"Ho capito: {summary}. Non modifico la scheda senza il tuo OK. Confermi?", "intent":"quota_proposal","links":links,"action":action}

        if any(x in q for x in ("modulo","tutela","consenso","genitoriale","iscrizione")):
            mu=state["mu_docs"]
            if mu:
                statuses=", ".join(sorted(set(d["status"] or "senza stato" for d in mu)))
                txt=f"Per {name} trovo {len(mu)} documento/i riconducibili al Modulo Unico o iscrizione. Stato/i: {statuses}. "
                if state["verified_mu"]:
                    txt += "Almeno uno risulta associato/salvato/verificato nel dossier. "
                else:
                    txt += "Non ne vedo uno già in stato verificato: va controllato prima di chiudere la pratica. "
            else:
                txt=f"Per {name} non trovo nel dossier o nell'inbound un documento riconosciuto come Modulo Unico."
            txt += " " + _minor_text(state) + "."
            return {"text":txt,"intent":"module_check","links":links}

        if "certificat" in q:
            cert_docs=[d for d in state["docs"] if "certificat" in _norm(d.get("type","")+" "+d.get("title","")+" "+d.get("category",""))]
            txt=f"{name}: {_medical_text(athlete)}. Documenti certificato collegati trovati: {len(cert_docs)}."
            return {"text":txt,"intent":"medical_check","links":links}

        if any(x in q for x in ("quota","paga","pagamento","pagamenti","sconto","ricevuta","ricevute")):
            pay_count=len(state["payments"])
            txt=f"{name}: {_quota_text(athlete)}. Registrazioni nella tabella pagamenti: {pay_count}."
            if pay_count==0:
                txt += " Non invento un incasso: al momento non vedo pagamenti registrati nella tabella pagamenti."
            return {"text":txt,"intent":"payment_check","links":links}

        if "document" in q or "caricat" in q:
            dossier=sum(1 for d in state["docs"] if d["source"]=="dossier")
            inbound=sum(1 for d in state["docs"] if d["source"]=="inbound")
            pending=[d for d in state["docs"] if _norm(d["status"]) in {"needs manual match","richiede conferma","associato tipo da verificare","needs review","da verificare","pending","pagamento da verificare"}]
            txt=f"{name}: {dossier} documenti nel dossier e {inbound} riferimenti inbound; {len(pending)} richiedono ancora verifica."
            return {"text":txt,"intent":"documents_check","links":links}

        txt=(
            f"{name}: {_medical_text(athlete)}; {_quota_text(athlete)}; "
            f"{_minor_text(state)}. Documenti collegati: {len(state['docs'])}; "
            f"Moduli Unici/iscrizione riconosciuti: {len(state['mu_docs'])}."
        )
        return {"text":txt,"intent":"athlete_summary","links":links}

    cloud=_cloud_answer(conn, raw, None)
    if cloud:
        return {"text":cloud,"intent":"cloud_conversation","links":[]}

    return {
        "text":(
            f"{_display_name(conn)}, posso lavorare direttamente sui dati BodyMind. "
            "Puoi chiedermi, per esempio: “abbiamo il modulo di Balbinetti?”, “cosa manca a Gaia?”, "
            "“chi ha il certificato in scadenza?”, “controlla tutto”, oppure puoi caricare documenti e cartelle. "
            "Se vuoi impostare una quota, dimmi anche l'importo e il motivo: preparerò la modifica e ti chiederò conferma."
        ),
        "intent":"local_fallback",
        "links":[]
    }

def _hash_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()

def _existing_document_by_hash(conn, payload: bytes):
    target=hashlib.sha256(payload).hexdigest()
    if not _table_exists(conn,"documenti"):
        return None
    rows=conn.execute("SELECT id,filename FROM documenti WHERE coalesce(visibile,1)=1").fetchall()
    for r in rows:
        p=_resolve_document_path(r["filename"])
        if p:
            try:
                if p.stat().st_size==len(payload) and _hash_file(p)==target:
                    return int(r["id"])
            except Exception:
                pass
    return None

def _looks_asd(filename: str, text: str) -> bool:
    hay=_norm((filename or "")+" "+(text or "")[:10000])
    return any(_norm(k) in hay for k in ASD_DOC_HINTS)

def _save_asd_document(conn, filename: str, payload: bytes, extracted: str) -> dict:
    dup=_existing_document_by_hash(conn,payload)
    if dup:
        return {"status":"duplicate","document_id":dup,"message":f"{filename}: file identico già presente nel dossier ASD."}
    safe=secure_filename(filename or "documento_asd.pdf")
    ext=Path(safe).suffix.lower()
    if ext not in ALLOWED_UPLOADS:
        raise ValueError("Tipo file non consentito")
    folder=get_workspace_media_dir()/"documenti_asd"/"operatore"/datetime.now().strftime("%Y/%m")
    folder.mkdir(parents=True,exist_ok=True)
    out=folder/(datetime.now().strftime("%Y%m%d_%H%M%S_")+uuid4().hex[:8]+"_"+safe)
    out.write_bytes(payload)
    if not _table_exists(conn,"documenti"):
        raise RuntimeError("Archivio documenti non disponibile")
    dc=_cols(conn,"documenti")
    data={
        "tesserato_id":None,
        "titolo":Path(safe).stem.replace("_"," ")[:160],
        "categoria":"Documenti ASD",
        "filename":str(out),
        "original_filename":safe,
        "data_caricamento":datetime.now().strftime("%Y-%m-%d"),
        "note":"Archiviato da Operatore BodyMind",
        "visibile":1,
        "doc_type":"documento_asd",
        "confidence":100,
        "match_score":0,
        "source":"operatore_bodymind",
        "status":"salvato",
    }
    keys=[k for k in data if k in dc]
    conn.execute(
        "INSERT INTO documenti("+",".join(keys)+") VALUES("+",".join("?" for _ in keys)+")",
        [data[k] for k in keys],
    )
    doc_id=int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.commit()
    return {"status":"archived_asd","document_id":doc_id,"message":f"{filename}: riconosciuto come documento ASD e archiviato nel dossier."}

def _logo_file() -> Path | None:
    roots=[APP_ROOT/"user_static",APP_ROOT/"static",Path("/data/tenants/default/user_static"),Path("/data/tenants/default/media")]
    scored=[]
    for root in roots:
        if not root.exists():
            continue
        try:
            for p in root.rglob("*"):
                if not p.is_file() or p.suffix.lower() not in {".png",".jpg",".jpeg",".webp",".svg"}:
                    continue
                n=p.name.lower()
                score=(20 if "bodymind" in n else 0)+(15 if "logo" in n else 0)+(5 if "brand" in n else 0)
                if score:
                    scored.append((score,p))
        except Exception:
            pass
    scored.sort(key=lambda x:(-x[0],len(str(x[1]))))
    return scored[0][1] if scored else None

@app.get("/favicon.ico")
def bodymind_favicon_r29():
    svg="""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="16" fill="#29121f"/><text x="32" y="39" text-anchor="middle" font-family="Arial" font-size="24" font-weight="700" fill="#f05b9d">BM</text></svg>"""
    return Response(svg,mimetype="image/svg+xml")

@app.get("/operatore-bodymind/logo")
@login_required
def operatore_logo():
    p=_logo_file()
    if p:
        return send_file(p)
    return bodymind_favicon_r29()

@app.get("/operatore-bodymind")
@login_required
def operatore_bodymind():
    conn=db()
    try:
        _ensure_schema(conn)
        name=_display_name(conn)
        checks, _ = _operator_check(conn)
        ai_mode="IA estesa" if os.environ.get("OPENAI_API_KEY") else "Motore ibrido"
    finally:
        conn.close()
    token=csrf_token()
    content=f"""
    <style>
    .bmop{{max-width:1180px;margin:0 auto;padding:4px 0 26px}}
    .bmop-hero{{display:grid;grid-template-columns:90px 1fr auto;gap:18px;align-items:center;padding:22px;border:1px solid rgba(148,163,184,.18);border-radius:24px;background:linear-gradient(135deg,rgba(56,189,248,.08),rgba(244,90,157,.08));box-shadow:0 18px 50px rgba(0,0,0,.12)}}
    .bmop-avatar{{width:78px;height:78px;border-radius:24px;display:grid;place-items:center;background:#130b12;border:1px solid rgba(244,90,157,.28);overflow:hidden;position:relative;box-shadow:0 12px 30px rgba(0,0,0,.24)}}
    .bmop-avatar img{{width:100%;height:100%;object-fit:contain;padding:8px}}
    .bmop-avatar.speaking:after{{content:"";position:absolute;inset:-6px;border:2px solid rgba(244,90,157,.65);border-radius:28px;animation:bmopPulse 1s ease-in-out infinite}}
    @keyframes bmopPulse{{50%{{transform:scale(1.08);opacity:.28}}}}
    .bmop-kicker{{font-size:10px;font-weight:900;letter-spacing:.14em;text-transform:uppercase;color:#f05b9d}}
    .bmop h1{{margin:4px 0 3px;font-size:clamp(25px,3vw,42px)}} .bmop-sub{{color:var(--text-dim);max-width:720px}}
    .bmop-status{{display:flex;gap:7px;flex-wrap:wrap;justify-content:flex-end}} .bmop-chip{{font-size:9px;font-weight:900;letter-spacing:.08em;text-transform:uppercase;border:1px solid rgba(148,163,184,.22);border-radius:999px;padding:7px 9px;background:rgba(255,255,255,.04)}}
    .bmop-grid{{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(270px,.75fr);gap:16px;margin-top:16px}}
    .bmop-panel{{border:1px solid rgba(148,163,184,.16);border-radius:22px;background:rgba(15,23,42,.24);overflow:hidden}}
    .bmop-chat{{height:min(60vh,620px);min-height:430px;overflow:auto;padding:18px;display:flex;flex-direction:column;gap:12px}}
    .bmop-msg{{max-width:86%;padding:12px 14px;border-radius:17px;line-height:1.5;white-space:pre-wrap}}
    .bmop-msg.me{{align-self:flex-end;background:#18324d;color:#fff;border-bottom-right-radius:5px}} .bmop-msg.ai{{align-self:flex-start;background:rgba(255,255,255,.065);border:1px solid rgba(148,163,184,.12);border-bottom-left-radius:5px}}
    .bmop-links{{display:flex;gap:7px;flex-wrap:wrap;margin-top:9px}} .bmop-link{{font-size:10px;font-weight:800;padding:7px 9px;border:1px solid rgba(56,189,248,.28);border-radius:10px;text-decoration:none}}
    .bmop-action{{margin-top:10px;padding:11px;border:1px solid rgba(251,191,36,.28);background:rgba(251,191,36,.08);border-radius:12px}} .bmop-action button{{margin-top:8px}}
    .bmop-compose{{display:grid;grid-template-columns:auto 1fr auto;gap:8px;padding:12px;border-top:1px solid rgba(148,163,184,.15);background:rgba(2,6,23,.25)}}
    .bmop-compose textarea{{min-height:48px;max-height:150px;resize:vertical}} .bmop-mic{{width:48px;border-radius:14px;font-size:20px}}
    .bmop-side{{padding:14px}} .bmop-side h3{{margin:4px 0 10px}} .bmop-quick{{display:grid;grid-template-columns:1fr 1fr;gap:8px}} .bmop-quick button{{min-height:46px;font-size:11px}}
    .bmop-drop{{margin-top:14px;border:1px dashed rgba(244,90,157,.35);border-radius:16px;padding:14px;background:rgba(244,90,157,.05)}} .bmop-drop input{{width:100%}}
    .bmop-note{{font-size:11px;color:var(--text-dim);line-height:1.5;margin-top:8px}}
    .bmop-small{{font-size:11px;color:var(--text-dim)}} .bmop-upload-result{{font-size:11px;margin-top:8px;white-space:pre-wrap}}
    @media(max-width:900px){{.bmop-hero{{grid-template-columns:68px 1fr}}.bmop-avatar{{width:62px;height:62px;border-radius:19px}}.bmop-status{{grid-column:1/-1;justify-content:flex-start}}.bmop-grid{{grid-template-columns:1fr}}.bmop-chat{{height:54vh;min-height:360px}}}}
    @media(max-width:560px){{.bmop{{padding-bottom:16px}}.bmop-hero{{padding:15px;gap:12px}}.bmop-msg{{max-width:94%}}.bmop-compose{{grid-template-columns:44px 1fr}}.bmop-compose .send{{grid-column:1/-1}}.bmop-quick{{grid-template-columns:1fr 1fr}}}}
    </style>
    <section class="bmop">
      <div class="bmop-hero">
        <div id="bmopAvatar" class="bmop-avatar"><img src="/operatore-bodymind/logo" alt="BodyMind"></div>
        <div><div class="bmop-kicker">Segreteria digitale · Operatore BodyMind</div><h1>Ciao {e(name)}.</h1><div class="bmop-sub">Parlami come parleresti a una persona della segreteria. Io controllo i dati reali del gestionale, ti dico cosa trovo e chiedo conferma prima delle modifiche delicate.</div></div>
        <div class="bmop-status"><span class="bmop-chip">DB connesso</span><span class="bmop-chip">Voce</span><span class="bmop-chip">{e(ai_mode)}</span></div>
      </div>
      <div class="bmop-grid">
        <div class="bmop-panel">
          <div id="bmopChat" class="bmop-chat"><div class="bmop-msg ai">{e("Sono pronto. "+checks)}</div></div>
          <div class="bmop-compose">
            <button id="bmopMic" class="bmop-mic" type="button" title="Parla">🎙️</button>
            <textarea id="bmopInput" placeholder="Es. Abbiamo caricato il modulo di Balbinetti?"></textarea>
            <button id="bmopSend" class="send" type="button">Invia</button>
          </div>
        </div>
        <aside class="bmop-panel bmop-side">
          <h3>Azioni rapide</h3>
          <div class="bmop-quick">
            <button data-q="Controlla tutto BodyMind">Controlla tutto</button>
            <button data-q="Quanti documenti sono da verificare?">Documenti</button>
            <button data-q="Chi ha il certificato scaduto o in scadenza?">Certificati</button>
            <button data-q="Controlla i minori e la tutela genitoriale">Minori</button>
          </div>
          <div class="bmop-drop">
            <b>Carica documenti o una cartella</b>
            <div class="bmop-note">Verbali e documenti ASD vengono archiviati; documenti atleta, certificati e ricevute entrano nell'Autopilot. I casi dubbi restano da verificare.</div>
            <input id="bmopFiles" type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.webp,.docx">
            <button id="bmopUpload" type="button" style="margin-top:8px;width:100%">Analizza e sistema</button>
            <label class="bmop-small" style="display:block;margin-top:10px">Cartella completa</label>
            <input id="bmopFolder" type="file" webkitdirectory directory multiple>
            <button id="bmopUploadFolder" type="button" style="margin-top:8px;width:100%">Analizza cartella</button>
            <div id="bmopUploadResult" class="bmop-upload-result"></div>
          </div>
          <div class="bmop-note">La voce usa le capacità disponibili del browser/dispositivo. L'identità detta a voce (“sono Katia”) personalizza la conversazione ma non cambia i permessi di accesso.</div>
        </aside>
      </div>
    </section>
    <script>
    (function(){{
      const csrf={json.dumps(token)};
      const chat=document.getElementById('bmopChat'), input=document.getElementById('bmopInput'), avatar=document.getElementById('bmopAvatar');
      let speaking=true;
      function msg(text,kind,links,action){{
        const box=document.createElement('div');box.className='bmop-msg '+kind;box.textContent=text||'';
        if(links&&links.length){{const row=document.createElement('div');row.className='bmop-links';links.forEach(x=>{{const a=document.createElement('a');a.className='bmop-link';a.href=x.url;a.textContent=x.label;row.appendChild(a);}});box.appendChild(row);}}
        if(action){{const ac=document.createElement('div');ac.className='bmop-action';const t=document.createElement('div');t.textContent=action.summary;ac.appendChild(t);const b=document.createElement('button');b.type='button';b.textContent='Conferma';b.onclick=()=>confirmAction(action.key,b,ac);ac.appendChild(b);box.appendChild(ac);}}
        chat.appendChild(box);chat.scrollTop=chat.scrollHeight;
      }}
      function speak(text){{
        if(!speaking||!('speechSynthesis' in window)||!text)return;
        speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(text);u.lang='it-IT';u.rate=.98;
        u.onstart=()=>avatar.classList.add('speaking');u.onend=()=>avatar.classList.remove('speaking');u.onerror=()=>avatar.classList.remove('speaking');
        speechSynthesis.speak(u);
      }}
      async function send(q){{
        q=(q||input.value||'').trim();if(!q)return;msg(q,'me');input.value='';
        try{{const r=await fetch('/operatore-bodymind/api/chat',{{method:'POST',headers:{{'Content-Type':'application/json','X-CSRFToken':csrf}},body:JSON.stringify({{message:q}})}});const d=await r.json();if(!r.ok)throw new Error(d.error||'Errore');msg(d.text,'ai',d.links,d.action);speak(d.text);}}
        catch(err){{msg('Errore: '+err.message,'ai');}}
      }}
      async function confirmAction(key,btn,wrap){{
        btn.disabled=true;
        try{{const r=await fetch('/operatore-bodymind/api/action',{{method:'POST',headers:{{'Content-Type':'application/json','X-CSRFToken':csrf}},body:JSON.stringify({{key}})}});const d=await r.json();if(!r.ok)throw new Error(d.error||'Errore');wrap.textContent=d.text;msg(d.text,'ai',d.links||[]);speak(d.text);}}
        catch(err){{btn.disabled=false;msg('Non ho eseguito la modifica: '+err.message,'ai');}}
      }}
      document.getElementById('bmopSend').onclick=()=>send();
      input.addEventListener('keydown',ev=>{{if(ev.key==='Enter'&&!ev.shiftKey){{ev.preventDefault();send();}}}});
      document.querySelectorAll('[data-q]').forEach(b=>b.onclick=()=>send(b.dataset.q));
      const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
      const mic=document.getElementById('bmopMic');
      if(SR){{const rec=new SR();rec.lang='it-IT';rec.interimResults=false;rec.continuous=false;rec.onstart=()=>{{mic.textContent='🔴';avatar.classList.add('speaking')}};rec.onend=()=>{{mic.textContent='🎙️';avatar.classList.remove('speaking')}};rec.onerror=()=>{{mic.textContent='🎙️';avatar.classList.remove('speaking')}};rec.onresult=ev=>{{const q=ev.results[0][0].transcript;input.value=q;send(q)}};mic.onclick=()=>rec.start();}}
      else{{mic.onclick=()=>msg('Il riconoscimento vocale diretto non è disponibile in questo browser. Puoi usare la dettatura della tastiera o scrivere il messaggio.','ai');}}
      async function upload(inputEl){{
        const files=[...(inputEl.files||[])];if(!files.length)return;
        const fd=new FormData();files.forEach(f=>fd.append('files',f,f.webkitRelativePath||f.name));fd.append('csrf_token',csrf);
        const out=document.getElementById('bmopUploadResult');out.textContent='Analisi in corso…';
        try{{const r=await fetch('/operatore-bodymind/api/upload',{{method:'POST',body:fd,headers:{{'X-CSRFToken':csrf}}}});const d=await r.json();if(!r.ok)throw new Error(d.error||'Errore');out.textContent=d.summary;msg(d.summary,'ai',d.links||[]);speak(d.summary);}}
        catch(err){{out.textContent='Errore: '+err.message;}}
      }}
      document.getElementById('bmopUpload').onclick=()=>upload(document.getElementById('bmopFiles'));
      document.getElementById('bmopUploadFolder').onclick=()=>upload(document.getElementById('bmopFolder'));
    }})();
    </script>
    """
    return layout(content)

@app.post("/operatore-bodymind/api/chat")
@login_required
def operatore_chat():
    payload=request.get_json(silent=True) or {}
    message=str(payload.get("message") or "").strip()
    if not message:
        return jsonify({"error":"Messaggio vuoto"}),400
    conn=db()
    try:
        _ensure_schema(conn)
        _log_message(conn,"user",message)
        answer=_answer(conn,message)
        _log_message(conn,"assistant",answer.get("text",""),answer.get("intent",""))
        return jsonify(answer)
    finally:
        conn.close()

@app.post("/operatore-bodymind/api/action")
@login_required
def operatore_action():
    payload=request.get_json(silent=True) or {}
    key=str(payload.get("key") or "").strip()
    conn=db()
    try:
        _ensure_schema(conn)
        row=conn.execute("SELECT * FROM operator_pending_actions WHERE action_key=? LIMIT 1",(key,)).fetchone()
        if not row:
            return jsonify({"error":"Azione non trovata"}),404
        if str(row["status"])!="pending":
            return jsonify({"error":"Azione già decisa"}),409
        if current_role() not in {"admin","manager"}:
            return jsonify({"error":"Per questa modifica serve un utente manager o admin"}),403
        data=json.loads(str(row["payload_json"] or "{}"))
        if row["action_type"]=="set_quota":
            tid=int(data.get("tesserato_id") or 0);amount=float(data.get("amount") or 0);reason=str(data.get("reason") or "").strip()
            tr=conn.execute("SELECT nome,cognome FROM tesserati WHERE id=?",(tid,)).fetchone()
            if not tr:
                raise ValueError("Tesserato non trovato")
            conn.execute("UPDATE tesserati SET quota_tipo='personalizzata', quota_personalizzata=?, quota_note=?, updated_at=? WHERE id=?",(amount,reason,now_iso_dt(),tid))
            result=f"Quota aggiornata per {tr['nome']} {tr['cognome']}: €{amount:.2f}" + (f" · {reason}" if reason else "")
            links=_athlete_links(tid)
        else:
            return jsonify({"error":"Tipo azione non supportato"}),400
        conn.execute("UPDATE operator_pending_actions SET status='approved',decided_at=?,decided_by=?,result_text=? WHERE id=?",(now_iso_dt(),current_username(),result,int(row["id"])))
        conn.commit()
        _log_message(conn,"assistant",result,"action_executed")
        return jsonify({"text":result,"links":links})
    except ValueError as exc:
        conn.rollback()
        return jsonify({"error":str(exc)}),400
    finally:
        conn.close()

@app.post("/operatore-bodymind/api/upload")
@login_required
def operatore_upload():
    files=request.files.getlist("files")
    if not files:
        return jsonify({"error":"Nessun file ricevuto"}),400
    if len(files)>80:
        return jsonify({"error":"Troppi file in un solo caricamento; massimo 80"}),400
    conn=db()
    results=[]
    try:
        _ensure_schema(conn)
        for item in files:
            filename=item.filename or "documento"
            payload=item.read()
            if not payload:
                continue
            if len(payload)>30*1024*1024:
                results.append({"message":f"{filename}: oltre 30 MB, saltato.","status":"skipped"})
                continue
            ext=Path(filename).suffix.lower()
            if ext not in ALLOWED_UPLOADS:
                results.append({"message":f"{filename}: formato non supportato.","status":"skipped"})
                continue
            extracted=""
            try:
                extracted=extract_attachment_text(filename,payload) or ""
            except Exception:
                extracted=""
            try:
                if _looks_asd(filename,extracted):
                    res=_save_asd_document(conn,filename,payload,extracted)
                else:
                    res=process_inbound_attachment(filename,payload,subject="Caricamento Operatore BodyMind",sender=_display_name(conn),body_text="",source="operatore_bodymind")
                    res={"status":str(res.get("status") or "processed"),"message":f"{filename}: {res.get('status') or 'processato'} · atleta {res.get('tesserato_id') or 'da verificare'}."}
                results.append(res)
            except Exception as exc:
                results.append({"message":f"{filename}: errore controllato ({exc}).","status":"error"})
        ok=sum(1 for r in results if r.get("status") not in {"error","skipped"})
        review=sum(1 for r in results if str(r.get("status")) in {"needs_manual_match","richiede_conferma","associato_tipo_da_verificare","pagamento_da_verificare","review","pending"})
        summary=f"Ho analizzato {len(results)} file: {ok} acquisiti/processati"
        if review: summary+=f", {review} richiedono verifica"
        errors=sum(1 for r in results if r.get("status")=="error")
        if errors: summary+=f", {errors} con errore controllato"
        summary+=". " + " ".join(str(r.get("message") or "") for r in results[:8])
        if len(results)>8: summary+=f" Altri {len(results)-8} file elaborati."
        _log_message(conn,"assistant",summary,"upload")
        return jsonify({"summary":summary,"results":results,"links":[{"label":"Apri Documenti","url":"/documenti"},{"label":"Da verificare","url":"/documenti/da-verificare"}]})
    finally:
        conn.close()
