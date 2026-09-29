# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from datetime import datetime, timedelta
from pathlib import Path

from flask import Response, jsonify, request, session

from .core import app, db, layout, login_required, current_role, current_username, e

BRIDGE_VERSION="R36.0"
PAIR_TTL_MINUTES=10
ONLINE_SECONDS=90

def _now():
    return datetime.now().replace(microsecond=0)

def _iso(dt=None):
    return (dt or _now()).isoformat(timespec='seconds')

def _hash(value):
    return hashlib.sha256(str(value or '').encode('utf-8')).hexdigest()

def _schema(conn):
    conn.execute("""
      CREATE TABLE IF NOT EXISTS bodymind_ai_pair_codes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code_hash TEXT NOT NULL,
        created_by TEXT,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        used_at TEXT
      )
    """)
    conn.execute("""
      CREATE TABLE IF NOT EXISTS bodymind_ai_bridge_devices(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT NOT NULL UNIQUE,
        device_name TEXT NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        active INTEGER NOT NULL DEFAULT 1,
        paired_at TEXT NOT NULL,
        last_seen_at TEXT,
        last_error TEXT
      )
    """)
    conn.execute("""
      CREATE TABLE IF NOT EXISTS bodymind_ai_jobs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT,
        identity_name TEXT,
        question TEXT NOT NULL,
        base_text TEXT,
        messages_json TEXT NOT NULL,
        max_tokens INTEGER NOT NULL DEFAULT 80,
        status TEXT NOT NULL DEFAULT 'pending',
        device_id TEXT,
        created_at TEXT NOT NULL,
        leased_at TEXT,
        completed_at TEXT,
        response_text TEXT,
        error_text TEXT
      )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bodymind_ai_jobs_status ON bodymind_ai_jobs(status,id)")
    conn.commit()

def _device_online(row):
    if not row or not row['last_seen_at']:
        return False
    try:
        seen=datetime.fromisoformat(str(row['last_seen_at']))
        return (_now()-seen).total_seconds() <= ONLINE_SECONDS
    except Exception:
        return False

def _latest_device(conn):
    _schema(conn)
    return conn.execute(
        "SELECT * FROM bodymind_ai_bridge_devices WHERE active=1 ORDER BY coalesce(last_seen_at,paired_at) DESC,id DESC LIMIT 1"
    ).fetchone()

def _auth_device(conn):
    _schema(conn)
    auth=str(request.headers.get('Authorization') or '')
    if not auth.lower().startswith('bearer '):
        return None
    token=auth.split(' ',1)[1].strip()
    if not token:
        return None
    row=conn.execute(
        "SELECT * FROM bodymind_ai_bridge_devices WHERE token_hash=? AND active=1 LIMIT 1",
        (_hash(token),)
    ).fetchone()
    if row:
        conn.execute("UPDATE bodymind_ai_bridge_devices SET last_seen_at=? WHERE id=?",(_iso(),int(row['id'])))
        conn.commit()
        row=conn.execute("SELECT * FROM bodymind_ai_bridge_devices WHERE id=?",(int(row['id']),)).fetchone()
    return row

def bridge_enhance_result(conn, message, result, conversation_id='', identity=''):
    """Use the paired local iMac only for responses that otherwise need AI.
    Deterministic write/confirmation paths remain authoritative.
    """
    try:
        if not isinstance(result,dict):
            return result
        mode=str(result.get('mode') or '')
        if not (result.get('allow_device_ai') or mode in ('fallback','help')):
            return result
        _schema(conn)
        device=_latest_device(conn)
        if not _device_online(device):
            return result

        base=str(result.get('text') or '')
        system=(
            "Sei Operatore BodyMind, assistente intelligente di una ASD italiana di danza aerea. "
            "Rispondi in italiano naturale, conciso e competente. "
            "I dati riportati come RISPOSTA VERIFICATA BODYMIND sono il solo riferimento per i dati interni: "
            "non modificarli, non inventare nomi, quote, documenti, consensi, pagamenti o stati. "
            "Se i dati non bastano, chiedi una precisazione. "
            "Non dichiarare di aver eseguito modifiche: le azioni sul gestionale passano solo dal motore deterministico con conferma."
        )
        user=(
            "INTERLOCUTORE: "+str(identity or 'Operatore')+"\n"
            "RICHIESTA: "+str(message or '')[:6000]+"\n"
            "RISPOSTA VERIFICATA BODYMIND: "+base[:7000]+"\n"
            "Rispondi alla richiesta in modo più naturale e utile, restando fedele ai dati verificati."
        )
        messages=[{'role':'system','content':system},{'role':'user','content':user}]
        cur=conn.execute(
            """INSERT INTO bodymind_ai_jobs
               (conversation_id,identity_name,question,base_text,messages_json,max_tokens,status,created_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (str(conversation_id or ''),str(identity or ''),str(message or '')[:8000],base[:8000],
             json.dumps(messages,ensure_ascii=False),80,'pending',_iso())
        )
        job_id=int(cur.lastrowid)
        conn.commit()

        wait_seconds=float(os.environ.get('BODYMIND_LOCAL_AI_WAIT_SECONDS','55') or 55)
        wait_seconds=max(5.0,min(wait_seconds,90.0))
        deadline=time.time()+wait_seconds
        while time.time()<deadline:
            row=conn.execute("SELECT status,response_text,error_text FROM bodymind_ai_jobs WHERE id=?",(job_id,)).fetchone()
            if row:
                status=str(row['status'] or '')
                if status=='done' and str(row['response_text'] or '').strip():
                    out=dict(result)
                    out['text']=str(row['response_text']).strip()[:7000]
                    out['mode']='local_ai'
                    out['allow_device_ai']=False
                    out['local_ai']=True
                    return out
                if status in ('error','expired'):
                    break
            time.sleep(.5)

        conn.execute(
            "UPDATE bodymind_ai_jobs SET status='expired',completed_at=? WHERE id=? AND status IN ('pending','leased')",
            (_iso(),job_id)
        )
        conn.commit()
        return result
    except Exception:
        return result

@app.get('/operatore-bodymind/bridge/status')
@login_required
def bodymind_ai_bridge_status():
    conn=db()
    try:
        device=_latest_device(conn)
        return jsonify({
            'online':bool(_device_online(device)),
            'device_name':str(device['device_name'] or '') if device else '',
            'last_seen_at':str(device['last_seen_at'] or '') if device else '',
            'version':BRIDGE_VERSION,
        })
    finally:
        conn.close()

@app.get('/operatore-bodymind/bridge/setup')
@login_required
def bodymind_ai_bridge_setup():
    if current_role() not in ('admin','manager'):
        return Response('Permessi insufficienti',status=403)
    conn=db()
    try:
        _schema(conn)
        code=secrets.token_hex(5).upper()
        expires=_now()+timedelta(minutes=PAIR_TTL_MINUTES)
        conn.execute(
            "INSERT INTO bodymind_ai_pair_codes(code_hash,created_by,created_at,expires_at) VALUES(?,?,?,?)",
            (_hash(code),str(current_username() or ''),_iso(),_iso(expires))
        )
        conn.commit()
        device=_latest_device(conn)
        online=_device_online(device)
    finally:
        conn.close()
    base=request.url_root.rstrip('/')
    command=f"curl -fsSL {base}/bodymind-ai-bridge/install.sh | bash -s -- {code}"
    html=f"""
    <main style="max-width:900px;margin:0 auto;padding:24px">
      <h1>BodyMind AI · iMac</h1>
      <p>Il motore IA locale non è una app separata: gira in background sul tuo iMac e viene avviato automaticamente da macOS.</p>
      <div style="padding:14px 16px;border:1px solid #ccc;border-radius:14px;margin:16px 0">
        <b>Stato bridge:</b> {'ONLINE' if online else 'NON COLLEGATO / OFFLINE'}
        {('<br>Dispositivo: '+e(str(device['device_name'] or ''))) if device else ''}
      </div>
      <p>Per collegare questo iMac al gestionale, copia nel Terminale del Mac il comando seguente entro {PAIR_TTL_MINUTES} minuti:</p>
      <pre style="white-space:pre-wrap;word-break:break-all;padding:16px;border-radius:12px;background:#111;color:#eee">{e(command)}</pre>
      <p>Il codice è monouso. La chiave definitiva viene salvata solo sul Mac e non compare in questa pagina.</p>
      <p><a href="/operatore-bodymind">← Torna all'Operatore</a></p>
    </main>
    """
    return layout(html)

@app.post('/bodymind-ai-bridge/pair')
def bodymind_ai_bridge_pair():
    payload=request.get_json(silent=True) or {}
    code=str(payload.get('code') or '').strip().upper()
    device_name=str(payload.get('device_name') or 'iMac BodyMind').strip()[:120]
    if not code:
        return jsonify({'ok':False,'error':'pair code missing'}),400
    conn=db()
    try:
        _schema(conn)
        now=_iso()
        row=conn.execute(
            """SELECT * FROM bodymind_ai_pair_codes
               WHERE code_hash=? AND used_at IS NULL AND expires_at>=?
               ORDER BY id DESC LIMIT 1""",
            (_hash(code),now)
        ).fetchone()
        if not row:
            return jsonify({'ok':False,'error':'pair code invalid or expired'}),403
        token=secrets.token_urlsafe(40)
        device_id=secrets.token_hex(12)
        conn.execute("UPDATE bodymind_ai_pair_codes SET used_at=? WHERE id=?",(now,int(row['id'])))
        conn.execute(
            """INSERT INTO bodymind_ai_bridge_devices
               (device_id,device_name,token_hash,active,paired_at,last_seen_at)
               VALUES(?,?,?,?,?,?)""",
            (device_id,device_name,_hash(token),1,now,now)
        )
        conn.commit()
        return jsonify({'ok':True,'device_id':device_id,'token':token,'version':BRIDGE_VERSION})
    finally:
        conn.close()

@app.post('/bodymind-ai-bridge/heartbeat')
def bodymind_ai_bridge_heartbeat():
    conn=db()
    try:
        device=_auth_device(conn)
        if not device:
            return jsonify({'ok':False}),401
        return jsonify({'ok':True,'device_id':device['device_id']})
    finally:
        conn.close()

@app.get('/bodymind-ai-bridge/poll')
def bodymind_ai_bridge_poll():
    conn=db()
    try:
        device=_auth_device(conn)
        if not device:
            return jsonify({'ok':False}),401
        cutoff=_iso(_now()-timedelta(seconds=150))
        conn.execute(
            "UPDATE bodymind_ai_jobs SET status='pending',device_id=NULL,leased_at=NULL WHERE status='leased' AND leased_at<?",
            (cutoff,)
        )
        conn.commit()
        conn.execute('BEGIN IMMEDIATE')
        row=conn.execute(
            "SELECT * FROM bodymind_ai_jobs WHERE status='pending' ORDER BY id LIMIT 1"
        ).fetchone()
        if not row:
            conn.commit()
            return jsonify({'ok':True,'job':None})
        job_id=int(row['id'])
        now=_iso()
        conn.execute(
            "UPDATE bodymind_ai_jobs SET status='leased',device_id=?,leased_at=? WHERE id=? AND status='pending'",
            (str(device['device_id']),now,job_id)
        )
        conn.commit()
        row=conn.execute("SELECT * FROM bodymind_ai_jobs WHERE id=?",(job_id,)).fetchone()
        return jsonify({
            'ok':True,
            'job':{
                'id':job_id,
                'messages':json.loads(str(row['messages_json'] or '[]')),
                'max_tokens':int(row['max_tokens'] or 80),
            }
        })
    finally:
        conn.close()

@app.post('/bodymind-ai-bridge/result')
def bodymind_ai_bridge_result():
    payload=request.get_json(silent=True) or {}
    job_id=int(payload.get('job_id') or 0)
    text=str(payload.get('text') or '').strip()
    error=str(payload.get('error') or '').strip()
    conn=db()
    try:
        device=_auth_device(conn)
        if not device:
            return jsonify({'ok':False}),401
        row=conn.execute("SELECT * FROM bodymind_ai_jobs WHERE id=?",(job_id,)).fetchone()
        if not row or str(row['device_id'] or '')!=str(device['device_id']):
            return jsonify({'ok':False,'error':'job not leased to this device'}),409
        if str(row['status'] or '')=='expired':
            return jsonify({'ok':False,'error':'job expired'}),409
        if error:
            conn.execute(
                "UPDATE bodymind_ai_jobs SET status='error',error_text=?,completed_at=? WHERE id=?",
                (error[:4000],_iso(),job_id)
            )
            conn.execute("UPDATE bodymind_ai_bridge_devices SET last_error=? WHERE id=?",(error[:1000],int(device['id'])))
        else:
            conn.execute(
                "UPDATE bodymind_ai_jobs SET status='done',response_text=?,completed_at=? WHERE id=?",
                (text[:12000],_iso(),job_id)
            )
            conn.execute("UPDATE bodymind_ai_bridge_devices SET last_error=NULL WHERE id=?",(int(device['id']),))
        conn.commit()
        return jsonify({'ok':True})
    finally:
        conn.close()

@app.get('/bodymind-ai-bridge/install.sh')
def bodymind_ai_bridge_install_script():
    base=request.url_root.rstrip('/')
    script=r'''#!/bin/bash
set -e

CODE="$1"
if [ -z "$CODE" ]; then
  echo "Uso: install.sh CODICE_ABBINAMENTO"
  exit 1
fi

BASE="$HOME/BodyMindAI"
mkdir -p "$BASE/logs" "$HOME/Library/LaunchAgents"
PY3="$(command -v python3)"
if [ -z "$PY3" ]; then
  echo "Python 3 non trovato."
  exit 1
fi

PAIR_PAYLOAD="$("$PY3" -c 'import json,sys; print(json.dumps({"code":sys.argv[1],"device_name":"iMac BodyMind"}))' "$CODE")"
PAIR_JSON="$(curl -fsS -X POST "__BASE__/bodymind-ai-bridge/pair" -H "Content-Type: application/json" -d "$PAIR_PAYLOAD")"
TOKEN="$(printf '%s' "$PAIR_JSON" | "$PY3" -c 'import json,sys; d=json.load(sys.stdin); print(d.get("token",""))')"
if [ -z "$TOKEN" ]; then
  echo "Abbinamento non riuscito: $PAIR_JSON"
  exit 1
fi
printf '%s' "$TOKEN" > "$BASE/bridge_token"
chmod 600 "$BASE/bridge_token"

cat > "$BASE/bodymind-bridge.py" <<'PY'
import json, os, time, urllib.request

BASE_URL="__BASE__"
ROOT=os.path.expanduser("~/BodyMindAI")
TOKEN=open(os.path.join(ROOT,"bridge_token"),encoding="utf-8").read().strip()
LOCAL="http://127.0.0.1:8088/v1/chat/completions"

def req(url, method="GET", payload=None, auth=True, timeout=180):
    data=None if payload is None else json.dumps(payload).encode("utf-8")
    headers={"Content-Type":"application/json"}
    if auth:
        headers["Authorization"]="Bearer "+TOKEN
    r=urllib.request.Request(url,data=data,headers=headers,method=method)
    with urllib.request.urlopen(r,timeout=timeout) as resp:
        raw=resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}

def local_chat(messages,max_tokens):
    payload={
        "model":"bodymind",
        "messages":messages,
        "temperature":0.45,
        "max_tokens":int(max_tokens or 80),
    }
    return req(LOCAL,"POST",payload,auth=False,timeout=240)

while True:
    try:
        polled=req(BASE_URL+"/bodymind-ai-bridge/poll",timeout=30)
        job=polled.get("job")
        if not job:
            time.sleep(1.2)
            continue
        jid=int(job["id"])
        try:
            ans=local_chat(job.get("messages") or [],job.get("max_tokens") or 80)
            text=((ans.get("choices") or [{}])[0].get("message") or {}).get("content","").strip()
            if not text:
                raise RuntimeError("llama-server non ha restituito testo")
            req(BASE_URL+"/bodymind-ai-bridge/result","POST",{"job_id":jid,"text":text},timeout=30)
        except Exception as exc:
            try:
                req(BASE_URL+"/bodymind-ai-bridge/result","POST",{"job_id":jid,"error":repr(exc)},timeout=30)
            except Exception:
                pass
            time.sleep(3)
    except Exception:
        time.sleep(5)
PY

cat > "$HOME/Library/LaunchAgents/com.bodymind.ai.bridge.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.bodymind.ai.bridge</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY3</string>
    <string>$BASE/bodymind-bridge.py</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$BASE/logs/bridge-out.log</string>
  <key>StandardErrorPath</key><string>$BASE/logs/bridge-error.log</string>
</dict>
</plist>
EOF

launchctl unload "$HOME/Library/LaunchAgents/com.bodymind.ai.bridge.plist" 2>/dev/null || true
launchctl load "$HOME/Library/LaunchAgents/com.bodymind.ai.bridge.plist"
sleep 3
echo "BodyMind AI Bridge installato e avviato."
'''
    script=script.replace('__BASE__',base)
    return Response(script,mimetype='text/plain; charset=utf-8')
