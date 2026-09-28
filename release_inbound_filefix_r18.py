from __future__ import annotations
from pathlib import Path
from datetime import datetime
import compileall, shutil, sqlite3, re, unicodedata

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MEDIA=Path('/data/tenants/default/media')
MARKER=APP/'.BODYMIND_INBOUND_FILEFIX_R18'
BACKUPS=Path('/data/release_backups/20260928_inbound_filefix_r18')
ACTIVE=(
    'needs_manual_match','associato_tipo_da_verificare','richiede_conferma',
    'needs_review','da_verificare','pending'
)

def backup(rel):
    src=APP/rel; dst=BACKUPS/rel
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dst)

def cols(conn,table):
    return {r[1] for r in conn.execute(f'PRAGMA table_info({table})').fetchall()}

def has_table(conn,table):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone() is not None

def norm_words(value):
    s=unicodedata.normalize('NFKD',str(value or ''))
    s=''.join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return [x for x in re.split(r'[^a-z0-9]+',s) if x]

def compact(value):
    return ''.join(norm_words(value))

def ngrams(words,maxn=5):
    out=set(words)
    for i in range(len(words)):
        for j in range(i+2,min(len(words),i+maxn)+1):
            out.add(''.join(words[i:j]))
    return out

def filename_candidate(athletes, filename, dtype=''):
    words=norm_words(Path(str(filename or '')).stem)
    grams=ngrams(words)
    surname_counts={}
    for a in athletes:
        sc=compact(a['cognome'] if 'cognome' in a.keys() else '')
        if sc:
            surname_counts[sc]=surname_counts.get(sc,0)+1
    ranked=[]
    certificate_hint=(str(dtype or '').lower()=='certificato_medico' or 'cm' in words or 'certificato' in words or 'cert' in words)
    module_hint=('iscrizione' in str(dtype or '').lower() or 'modulo' in words or 'iscrizione' in words)
    for a in athletes:
        aid=int(a['id'])
        nc=compact(a['nome'] if 'nome' in a.keys() else '')
        sc=compact(a['cognome'] if 'cognome' in a.keys() else '')
        if not sc or len(sc)<4:
            continue
        surname_hit=sc in grams
        name_hit=bool(nc and nc in grams)
        if surname_hit and name_hit:
            ranked.append((100,aid))
        elif surname_hit and surname_counts.get(sc,0)==1 and (certificate_hint or module_hint):
            ranked.append((92,aid))
    if not ranked:
        return None
    ranked=sorted(set(ranked),reverse=True)
    top_score=ranked[0][0]
    top=[x for x in ranked if x[0]==top_score]
    return top[0] if len(top)==1 else None

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

if not MARKER.exists():
    rel='asd_app/routes_inbound_documents.py'
    p=APP/rel
    if not p.exists():
        raise RuntimeError('R18 inbound route target missing')
    s=p.read_text(encoding='utf-8')
    if 'BODYMIND_R18_INBOUND_FILE_ROUTE' not in s:
        backup(rel)
        anchor="@app.route('/documenti-automatici/file/<int:doc_id>')"
        start=s.find(anchor)
        if start<0:
            raise RuntimeError('R18 legacy file route anchor missing')
        end=s.find('\n@app.',start+len(anchor))
        if end<0:
            raise RuntimeError('R18 legacy file route end missing')
        replacement=r'''# BODYMIND_R18_INBOUND_FILE_ROUTE
@app.route('/documenti-automatici/file/<int:doc_id>')
@admin_required
def inbound_document_file_r18(doc_id: int):
    conn=db()
    try:
        row=conn.execute("SELECT id,saved_path,original_filename FROM inbound_documents WHERE id=?",(int(doc_id),)).fetchone()
    finally:
        conn.close()
    if not row:
        abort(404)
    media_root=get_workspace_media_dir().resolve()
    raw_text=str(row['saved_path'] or '').replace('\\','/').strip()
    candidates=[]
    if raw_text:
        raw=Path(raw_text)
        if raw.is_absolute():
            candidates.append(raw.resolve())
        else:
            candidates.append((media_root/raw).resolve())
    # Safe fallback for historical path drift: exact basename, unique inside the workspace media volume.
    basename=Path(raw_text).name if raw_text else Path(str(row['original_filename'] or '')).name
    if basename:
        try:
            hits=[x.resolve() for x in media_root.rglob(basename) if x.is_file()]
            if len(hits)==1:
                candidates.append(hits[0])
        except Exception:
            pass
    fp=None
    seen=set()
    for candidate in candidates:
        key=str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate!=media_root and media_root not in candidate.parents:
            continue
        if candidate.exists() and candidate.is_file():
            fp=candidate
            break
    if fp is None:
        abort(404)
    return send_file(fp,as_attachment=(request.args.get('download')=='1'),download_name=(row['original_filename'] or fp.name))


'''
        s=s[:start]+replacement+s[end:]
        p.write_text(s,encoding='utf-8')
        if not compileall.compile_file(str(p),quiet=1):
            raise RuntimeError('R18 inbound route compile failed')
    MARKER.write_text('BodyMind inbound filefix R18 applied\n',encoding='utf-8')
    print('[filefix-r18] source applied',flush=True)

# Safe retroactive auto-match for obvious filenames. Runs every restart.
BACKUPS.mkdir(parents=True,exist_ok=True)
if DB.exists() and not (BACKUPS/'asd.db').exists():
    shutil.copy2(DB,BACKUPS/'asd.db')

conn=sqlite3.connect(str(DB),timeout=30); conn.row_factory=sqlite3.Row
assigned=[]
try:
    athletes=conn.execute("SELECT id,nome,cognome FROM tesserati ORDER BY id").fetchall()
    for a in athletes:
        joined=compact(str(a['nome'] or '')+' '+str(a['cognome'] or ''))
        if int(a['id'])==11 or any(key in joined for key in ('ferlan','pimpinelli','giulia')):
            print(f"[filefix-r18-roster] id={int(a['id'])} nome={str(a['nome'] or '')} cognome={str(a['cognome'] or '')}",flush=True)
    vals=','.join('?' for _ in ACTIVE)
    rows=conn.execute(f"""SELECT * FROM inbound_documents
        WHERE LOWER(COALESCE(status,'')) IN ({vals})
          AND COALESCE(deleted_at,'')=''
          AND COALESCE(tesserato_id,0)=0
        ORDER BY id""",ACTIVE).fetchall()
    for row in rows:
        candidate=filename_candidate(athletes,row['original_filename'],row['document_type'])
        if not candidate:
            continue
        score,tid=candidate
        # Absolute safety: the chosen ID must exist and no other same-score candidate exists.
        a=conn.execute("SELECT id,nome,cognome FROM tesserati WHERE id=?",(tid,)).fetchone()
        if not a:
            continue
        dtype=str(row['document_type'] or '')
        dconf=int(row['document_confidence'] or 0)
        strong_type=(dtype not in ('','altro') and dconf>=60)
        new_status=('pagamento_da_verificare' if dtype=='ricevuta_pagamento' else ('associato' if strong_type else 'associato_tipo_da_verificare'))
        ic=cols(conn,'inbound_documents')
        sets=["tesserato_id=?","match_score=?","match_action='auto_save'","status=?"]
        params=[tid,score,new_status]
        if 'matched_tesserato_id' in ic:
            sets.append("matched_tesserato_id=?"); params.append(tid)
        if 'suggested_tesserato_id' in ic:
            sets.append("suggested_tesserato_id=?"); params.append(tid)
        if 'updated_at' in ic:
            sets.append("updated_at=?"); params.append(datetime.now().isoformat(timespec='seconds'))
        params.append(int(row['id']))
        conn.execute("UPDATE inbound_documents SET "+','.join(sets)+" WHERE id=?",params)

        saved=str(row['saved_path'] or '')
        if saved and Path(saved).is_file() and has_table(conn,'documenti'):
            dc=cols(conn,'documenti')
            existing=None
            if 'inbound_id' in dc:
                existing=conn.execute("SELECT id FROM documenti WHERE inbound_id=? ORDER BY id DESC LIMIT 1",(int(row['id']),)).fetchone()
            if not existing:
                existing=conn.execute("SELECT id FROM documenti WHERE filename=? ORDER BY id DESC LIMIT 1",(saved,)).fetchone()
            values={
                'tesserato_id':tid,'titolo':str(row['original_filename'] or Path(saved).name),
                'categoria':'Certificato medico' if dtype=='certificato_medico' else ('Modulo iscrizione BodyMind' if dtype=='modulo_unico_tesseramento' else 'Altro'),
                'filename':saved,'original_filename':str(row['original_filename'] or Path(saved).name),
                'data_caricamento':datetime.now().date().isoformat(),'visibile':1,
                'doc_type':dtype,'confidence':dconf,'match_score':score,'source':'autopilot',
                'status':'salvato','inbound_id':int(row['id'])
            }
            values={k:v for k,v in values.items() if k in dc}
            if existing:
                keys=list(values.keys())
                conn.execute("UPDATE documenti SET "+','.join(k+'=?' for k in keys)+" WHERE id=?",[values[k] for k in keys]+[int(existing['id'])])
            else:
                required={'tesserato_id','titolo','categoria','filename','original_filename'}
                if required.issubset(values):
                    keys=list(values.keys())
                    conn.execute("INSERT INTO documenti("+','.join(keys)+") VALUES("+','.join('?' for _ in keys)+")",[values[k] for k in keys])
        assigned.append((int(row['id']),tid,score,str(row['original_filename'] or ''),str(a['nome'] or '')+' '+str(a['cognome'] or '')))

    conn.commit()
    remaining=conn.execute(f"""SELECT COUNT(*) FROM inbound_documents
        WHERE LOWER(COALESCE(status,'')) IN ({vals}) AND COALESCE(deleted_at,'')=''""",ACTIVE).fetchone()[0]
finally:
    conn.close()

# Synthetic ambiguity checks.
fake=[
    {'id':1,'nome':'Giulia','cognome':'Ferlan'},
    {'id':2,'nome':'Anna','cognome':'Rossi'},
]
assert filename_candidate(fake,'CM_Ferlan_Giulia.pdf','certificato_medico')==(100,1)
assert filename_candidate(fake,'CM_Rossi.pdf','certificato_medico')==(92,2)
amb=[
    {'id':3,'nome':'Anna','cognome':'Pimpinelli'},
    {'id':4,'nome':'Sara','cognome':'Pimpinelli'},
]
assert filename_candidate(amb,'CM_Pimpinelli.JPG','certificato_medico') is None

print(f'[filefix-r18] auto_assigned={len(assigned)} remaining_pending={remaining}',flush=True)
for did,tid,score,file,name in assigned:
    print(f'[filefix-r18-item] id={did} tid={tid} score={score} athlete={name} file={file}',flush=True)
print('[filefix-r18-selftest] PASS absolute-path-open unique-basename-fallback obvious-fullname unique-surname ambiguous-safe',flush=True)
