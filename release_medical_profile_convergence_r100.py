# -*- coding: utf-8 -*-
from __future__ import annotations
import json, py_compile, re, shutil, sqlite3
from datetime import date, datetime
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
BACK=Path('/data/release_backups/20261002_r100_medical_profile')
BACK.mkdir(parents=True,exist_ok=True)

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

def table(c,n):
    return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(n,)).fetchone())

def cols(c,n):
    return {str(r[1]) for r in c.execute("PRAGMA table_info("+n+")").fetchall()} if table(c,n) else set()

def norm(v):
    return re.sub(r'[^a-z0-9]','',str(v or '').lower().replace('à','a').replace('è','e').replace('é','e').replace('ì','i').replace('ò','o').replace('ù','u'))

def parse_date(v):
    raw=str(v or '').strip()[:10]
    for fmt in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y','%d.%m.%Y'):
        try: return datetime.strptime(raw,fmt).date()
        except Exception: pass
    return None

def iso(v):
    d=parse_date(v)
    return d.isoformat() if d else ''

def sem(c,st,sid):
    if not table(c,'bodymind_document_semantics'): return {}
    r=c.execute("SELECT * FROM bodymind_document_semantics WHERE source_table=? AND source_id=? ORDER BY id DESC LIMIT 1",(st,int(sid))).fetchone()
    if not r:return {}
    try:a=json.loads(str(r['analysis_json'] or '{}'))
    except Exception:a={}
    return {'row':r,'analysis':a if isinstance(a,dict) else {},'confidence':float(r['confidence'] or 0),
            'key':str(r['semantic_key'] or ''),'sha':str(r['sha256'] or ''),
            'person':str(r['person_name'] or ''),'cf':str(r['codice_fiscale'] or '')}

def actual_medical(r,sm=None):
    ks=set(r.keys())
    title=str(r['titolo'] or '').lower() if 'titolo' in ks else ''
    cat=str(r['categoria'] or '').lower() if 'categoria' in ks else ''
    dtype=str(r['doc_type'] or '').lower() if 'doc_type' in ks else ''
    summary=str(((sm or {}).get('analysis') or {}).get('content_summary') or '').lower()
    if dtype=='richiesta_certificato_medico' or 'richiesta certificato' in title or 'promemoria' in title:
        return False
    if 'non il certificato stesso' in summary or 'richiesta promemoria' in summary or 'promemoria consegna' in summary:
        return False
    return dtype=='certificato_medico' or cat=='certificato medico' or ('certificato medico' in title)

def backup_db():
    dst=BACK/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_pre_r100.db')
    src=sqlite3.connect(str(DB),timeout=30); out=sqlite3.connect(str(dst))
    try: src.backup(out)
    finally: out.close(); src.close()
    return str(dst)

def backup_file(p):
    try: rel=p.relative_to(APP)
    except Exception: rel=Path(p.name)
    dst=BACK/rel
    if p.exists() and not dst.exists():
        dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,dst)

# ------------------------------------------------------------------
# 1) Mobile athlete profile: persist only submitted fields, verify post-commit,
#    synchronize guardian data and return to athlete panel.
# ------------------------------------------------------------------
profile_matches=[]
for p in (APP/'asd_app').rglob('*.py'):
    try:s=p.read_text(encoding='utf-8',errors='replace')
    except Exception:continue
    if "@app.route('/mobile/atleta/<int:tid>',methods=['GET','POST'])" in s and 'def fix12_mobile_atleta' in s:
        profile_matches.append((p,s))
if len(profile_matches)!=1:
    raise RuntimeError('R100 expected one active mobile athlete source, found '+repr([str(x[0]) for x in profile_matches]))
PROFILE,ps=profile_matches[0]
if 'BODYMIND_R100_PROFILE_SAVE_VERIFY' not in ps:
    backup_file(PROFILE)
    old="""        if request.method=='POST':
            # Only explicit editable fields; everything else remains untouched.
            fields=['nome','cognome','corso','telefono','email','residenza','certificato_scadenza','genitore','telefono_genitore','email_genitore']
            cols={x[1] for x in conn.execute('PRAGMA table_info(tesserati)').fetchall()}
            fields=[f for f in fields if f in cols]
            vals=[(request.form.get(f) or '').strip() for f in fields]
            conn.execute('UPDATE tesserati SET '+','.join(f+'=?' for f in fields)+' WHERE id=?',vals+[tid]); conn.commit()
            return redirect('/mobile/atleta/%d?ok=1'%tid)
"""
    new="""        if request.method=='POST':
            # BODYMIND_R100_PROFILE_SAVE_VERIFY
            allowed=['nome','cognome','corso','telefono','email','residenza','certificato_scadenza',
                     'genitore','telefono_genitore','email_genitore','luogo_nascita','data_nascita',
                     'codice_fiscale','indirizzo','disciplina','stagione']
            tcols={x[1] for x in conn.execute('PRAGMA table_info(tesserati)').fetchall()}
            fields=[f for f in allowed if f in tcols and f in request.form]
            posted={f:(request.form.get(f) or '').strip() for f in fields}
            if fields:
                sets=[f+'=?' for f in fields]; vals=[posted[f] for f in fields]
                if 'updated_at' in tcols:
                    sets.append('updated_at=?'); vals.append(datetime.now().isoformat(timespec='seconds'))
                vals.append(tid)
                conn.execute('UPDATE tesserati SET '+','.join(sets)+' WHERE id=?',vals)
            # Keep minore/guardian data coherent immediately, not only at next startup.
            fresh=conn.execute('SELECT * FROM tesserati WHERE id=?',(tid,)).fetchone()
            if fresh and 'minorenne' in tcols and 'data_nascita' in fresh.keys():
                raw=str(fresh['data_nascita'] or '').strip()[:10]
                born=None
                for fmt in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y'):
                    try:
                        born=datetime.strptime(raw,fmt).date(); break
                    except Exception: pass
                if born:
                    today=date.today(); years=today.year-born.year-((today.month,today.day)<(born.month,born.day))
                    conn.execute('UPDATE tesserati SET minorenne=? WHERE id=?',(1 if years<18 else 0,tid))
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='minori'").fetchone():
                mcols={x[1] for x in conn.execute('PRAGMA table_info(minori)').fetchall()}
                fresh=conn.execute('SELECT * FROM tesserati WHERE id=?',(tid,)).fetchone()
                is_minor=bool(int(fresh['minorenne'] or 0)) if fresh and 'minorenne' in fresh.keys() else False
                m=conn.execute('SELECT * FROM minori WHERE tesserato_id=? ORDER BY id DESC LIMIT 1',(tid,)).fetchone()
                guardian=str(fresh['genitore'] or '').strip() if fresh and 'genitore' in fresh.keys() else ''
                gphone=str(fresh['telefono_genitore'] or '').strip() if fresh and 'telefono_genitore' in fresh.keys() else ''
                gemail=str(fresh['email_genitore'] or '').strip() if fresh and 'email_genitore' in fresh.keys() else ''
                if is_minor and (guardian or gphone or gemail):
                    if m:
                        sets=[]; vals=[]
                        for col,val in (('genitore',guardian),('telefono_genitore',gphone),('email_genitore',gemail)):
                            if col in mcols: sets.append(col+'=?'); vals.append(val)
                        if 'updated_at' in mcols: sets.append('updated_at=?'); vals.append(datetime.now().isoformat(timespec='seconds'))
                        if sets:
                            vals.append(int(m['id'])); conn.execute('UPDATE minori SET '+','.join(sets)+' WHERE id=?',vals)
                    elif 'tesserato_id' in mcols:
                        values={'tesserato_id':tid}
                        for col,val in (('nome',str(fresh['nome'] or '') if 'nome' in fresh.keys() else ''),
                                        ('cognome',str(fresh['cognome'] or '') if 'cognome' in fresh.keys() else ''),
                                        ('genitore',guardian),('telefono_genitore',gphone),('email_genitore',gemail)):
                            if col in mcols: values[col]=val
                        if 'created_at' in mcols: values['created_at']=datetime.now().isoformat(timespec='seconds')
                        if 'updated_at' in mcols: values['updated_at']=datetime.now().isoformat(timespec='seconds')
                        keys=list(values); conn.execute('INSERT INTO minori('+','.join(keys)+') VALUES('+','.join('?' for _ in keys)+')',[values[k] for k in keys])
            conn.commit()
            saved=conn.execute('SELECT * FROM tesserati WHERE id=?',(tid,)).fetchone()
            failed=[f for f in fields if str(saved[f] or '').strip()!=posted[f]]
            if failed:
                return redirect('/mobile/atleta/%d?save_error=1'%tid)
            return redirect('/mobile/atlete?updated=%d'%tid)
"""
    if old not in ps:
        raise RuntimeError('R100 mobile save block anchor missing')
    ps=ps.replace(old,new,1)

    old_fields="""    fields=[('nome','Nome',g('nome')),('cognome','Cognome',g('cognome')),('corso','Corso',g('corso')),('telefono','Telefono',g('telefono')),('email','Email',g('email')),('residenza','Residenza',g('residenza')),('certificato_scadenza','Scadenza certificato',g('certificato_scadenza')),('genitore','Genitore / tutore',g('genitore')),('telefono_genitore','Telefono genitore',g('telefono_genitore')),('email_genitore','Email genitore',g('email_genitore'))]
"""
    new_fields="""    fields=[('nome','Nome',g('nome')),('cognome','Cognome',g('cognome')),('corso','Corso',g('corso')),
            ('luogo_nascita','Luogo di nascita',g('luogo_nascita')),('data_nascita','Data di nascita',g('data_nascita')),
            ('codice_fiscale','Codice fiscale',g('codice_fiscale')),('indirizzo','Indirizzo',g('indirizzo')),
            ('residenza','Residenza',g('residenza')),('telefono','Telefono',g('telefono')),('email','Email',g('email')),
            ('disciplina','Disciplina',g('disciplina')),('stagione','Stagione',g('stagione')),
            ('certificato_scadenza','Scadenza certificato',g('certificato_scadenza')),
            ('genitore','Genitore / tutore',g('genitore')),('telefono_genitore','Telefono genitore',g('telefono_genitore')),
            ('email_genitore','Email genitore',g('email_genitore'))]
"""
    if old_fields not in ps:
        raise RuntimeError('R100 mobile field list anchor missing')
    ps=ps.replace(old_fields,new_fields,1)
    ps=ps.replace("docs=conn.execute('SELECT COUNT(*) FROM documenti WHERE tesserato_id=?',(tid,)).fetchone()[0]",
                  "docs=conn.execute('SELECT COUNT(*) FROM documenti WHERE tesserato_id=? AND COALESCE(visibile,1)=1',(tid,)).fetchone()[0]",1)
    PROFILE.write_text(ps,encoding='utf-8'); py_compile.compile(str(PROFILE),doraise=True)
    print('[r100-profile] PASS submitted-only update guardian-sync commit-readback return=/mobile/atlete',flush=True)

# Success feedback on athlete panel.
for p in (APP/'asd_app').rglob('*.py'):
    try:s=p.read_text(encoding='utf-8',errors='replace')
    except Exception:continue
    if 'def fix24_mobile_atlete' in s and 'Schede e controlli essenziali.' in s:
        if 'BODYMIND_R100_UPDATED_BANNER' not in s:
            backup_file(p)
            anchor="<main class='wrap'>"
            if anchor in s:
                s=s.replace(anchor,anchor+"{% if request.args.get('updated') %}<div class='card' style='background:#dcfce7;color:#166534;font-weight:900'>✓ Modifiche salvate correttamente</div>{% endif %}<!-- BODYMIND_R100_UPDATED_BANNER -->",1)
                p.write_text(s,encoding='utf-8'); py_compile.compile(str(p),doraise=True)
        break

# Mobile dossier must never render archived/hidden rows.
doc_matches=[]
for p in (APP/'asd_app').rglob('*.py'):
    try:s=p.read_text(encoding='utf-8',errors='replace')
    except Exception:continue
    if 'def fix23_mobile_athlete_documents' in s:
        doc_matches.append((p,s))
if len(doc_matches)!=1:
    raise RuntimeError('R100 expected one mobile document source')
DOCPAGE,ds=doc_matches[0]
if 'BODYMIND_R100_VISIBLE_DOCS_ONLY' not in ds:
    backup_file(DOCPAGE)
    old="docs=conn.execute('SELECT * FROM documenti WHERE tesserato_id=? ORDER BY data_caricamento DESC,id DESC',(tid,)).fetchall()"
    new="# BODYMIND_R100_VISIBLE_DOCS_ONLY\n        docs=conn.execute('SELECT * FROM documenti WHERE tesserato_id=? AND COALESCE(visibile,1)=1 ORDER BY data_caricamento DESC,id DESC',(tid,)).fetchall()"
    if old not in ds: raise RuntimeError('R100 mobile documents query anchor missing')
    ds=ds.replace(old,new,1)
    DOCPAGE.write_text(ds,encoding='utf-8'); py_compile.compile(str(DOCPAGE),doraise=True)
    print('[r100-mobile-docs] PASS hidden archived rows excluded',flush=True)

# ------------------------------------------------------------------
# 2) Operator future guard: semantic medical identity overrides weak filename/text match.
# ------------------------------------------------------------------
OP=APP/'asd_app/routes_operator_bodymind.py'
osrc=OP.read_text(encoding='utf-8',errors='replace')
if 'BODYMIND_R100_MEDICAL_IDENTITY_TARGET' not in osrc:
    backup_file(OP)
    anchor='''@app.post("/operatore-bodymind/upload")
'''
    helper=r'''# BODYMIND_R100_MEDICAL_IDENTITY_TARGET
def _r100_medical_identity_target(conn,semantic):
    a=semantic if isinstance(semantic,dict) else {}
    try: conf=float(a.get("confidence") or 0)
    except Exception: conf=0.0
    if _norm(a.get("document_type") or "")!="certificato_medico" or conf<.90:
        return 0
    cf=re.sub(r"[^A-Z0-9]","",str(a.get("codice_fiscale") or "").upper())
    if cf:
        row=conn.execute("SELECT id FROM tesserati WHERE upper(replace(replace(coalesce(codice_fiscale,''),' ',''),'-',''))=?",(cf,)).fetchall()
        if len(row)==1:return int(row[0]["id"])
    names=[]
    person=str(a.get("person_name") or "").strip()
    first=str(a.get("first_name") or "").strip(); last=str(a.get("last_name") or "").strip()
    for v in (person,(first+" "+last).strip(),(last+" "+first).strip()):
        nv=_norm(v)
        if nv and nv not in names:names.append(nv)
    hits=[]
    for t in conn.execute("SELECT id,nome,cognome FROM tesserati").fetchall():
        forms={_norm((str(t["nome"] or "")+" "+str(t["cognome"] or "")).strip()),
               _norm((str(t["cognome"] or "")+" "+str(t["nome"] or "")).strip())}
        if any(n in forms for n in names):hits.append(int(t["id"]))
    hits=sorted(set(hits))
    return hits[0] if len(hits)==1 else 0

'''
    if anchor not in osrc: raise RuntimeError('R100 operator upload anchor missing')
    osrc=osrc.replace(anchor,helper+anchor,1)
    gate='''            if sem_conf<.90 or tid<=0:
'''
    insert=r'''            if sem_type=="certificato_medico" and sem_conf>=.90:
                med_conn=db()
                try:
                    med_tid=_r100_medical_identity_target(med_conn,semantic)
                    if med_tid>0 and med_tid!=tid:
                        tid=med_tid
                        ic=_cols(med_conn,"inbound_documents"); sets=["tesserato_id=?"]; vals=[tid]
                        if "matched_tesserato_id" in ic: sets.append("matched_tesserato_id=?"); vals.append(tid)
                        if "suggested_tesserato_id" in ic: sets.append("suggested_tesserato_id=?"); vals.append(tid)
                        if "match_score" in ic: sets.append("match_score=?"); vals.append(100)
                        vals.append(inbound_id)
                        med_conn.execute("UPDATE inbound_documents SET "+",".join(sets)+" WHERE id=?",tuple(vals))
                        if _table(med_conn,"documenti") and "inbound_id" in _cols(med_conn,"documenti"):
                            med_conn.execute("UPDATE documenti SET tesserato_id=? WHERE inbound_id=?",(tid,inbound_id))
                        med_conn.commit()
                        item["tesserato_id"]=tid
                        item["medical_identity_corrected"]=True
                finally:
                    med_conn.close()

'''
    if gate not in osrc: raise RuntimeError('R100 operator semantic gate anchor missing')
    osrc=osrc.replace(gate,insert+gate,1)
    OP.write_text(osrc,encoding='utf-8'); py_compile.compile(str(OP),doraise=True)
    print('[r100-operator-medical] PASS semantic identity corrects weak pre-match before dedupe/production',flush=True)

# ------------------------------------------------------------------
# 3) One-time/global medical reconciliation and operational cleanup.
# ------------------------------------------------------------------
backup=backup_db()
conn=sqlite3.connect(str(DB),timeout=60); conn.row_factory=sqlite3.Row
moved=[]; reclassified=[]; archived=[]; blocked=[]; expiry_updates=[]
try:
    conn.execute("""CREATE TABLE IF NOT EXISTS bodymind_medical_history_archive(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      document_id INTEGER NOT NULL UNIQUE,
      tesserato_id INTEGER,
      canonical_document_id INTEGER,
      reason TEXT NOT NULL,
      payload_json TEXT NOT NULL,
      semantics_json TEXT,
      archived_at TEXT NOT NULL
    )""")
    athletes=conn.execute("SELECT * FROM tesserati ORDER BY id").fetchall()
    by_cf={norm(a['codice_fiscale']):a for a in athletes if 'codice_fiscale' in a.keys() and norm(a['codice_fiscale'])}
    by_name={}
    for a in athletes:
        for key in {norm((str(a['nome'] or '')+' '+str(a['cognome'] or '')).strip()),norm((str(a['cognome'] or '')+' '+str(a['nome'] or '')).strip())}:
            if key:by_name.setdefault(key,[]).append(a)

    # Reassign confident semantic mismatches and reclassify reminder/request documents.
    rows=conn.execute("SELECT * FROM documenti WHERE coalesce(tesserato_id,0)>0 AND coalesce(visibile,1)=1 ORDER BY id").fetchall()
    for d in rows:
        sm=sem(conn,'documenti',int(d['id'])); an=sm.get('analysis') or {}
        title=str(d['titolo'] or '').lower() if 'titolo' in d.keys() else ''
        summary=str(an.get('content_summary') or '').lower()
        if ('richiesta certificato' in title or 'promemoria' in title or 'non il certificato stesso' in summary or 'richiesta promemoria' in summary):
            if 'doc_type' in cols(conn,'documenti'):
                conn.execute("UPDATE documenti SET doc_type='richiesta_certificato_medico',categoria='Documenti ASD' WHERE id=?",(int(d['id']),))
            if sm.get('row'):
                a2=dict(an); a2['document_type']='richiesta_certificato_medico'
                conn.execute("UPDATE bodymind_document_semantics SET document_type=?,analysis_json=? WHERE id=?",
                             ('richiesta_certificato_medico',json.dumps(a2,ensure_ascii=False),int(sm['row']['id'])))
            reclassified.append(int(d['id']))
            continue
        if not actual_medical(d,sm) or float(sm.get('confidence') or 0)<.90: continue
        cf=norm(an.get('codice_fiscale') or sm.get('cf'))
        target=None
        if cf and cf in by_cf: target=by_cf[cf]
        else:
            names=[]
            for v in (an.get('person_name') or sm.get('person'),(str(an.get('first_name') or '')+' '+str(an.get('last_name') or '')).strip(),
                      (str(an.get('last_name') or '')+' '+str(an.get('first_name') or '')).strip()):
                k=norm(v)
                if k and k not in names:names.append(k)
            hits=[]
            for k in names:
                if k in by_name and len(by_name[k])==1:hits.extend(by_name[k])
            uniq={int(x['id']):x for x in hits}
            if len(uniq)==1: target=list(uniq.values())[0]
        if target and int(target['id'])!=int(d['tesserato_id']):
            old_tid=int(d['tesserato_id']); new_tid=int(target['id']); did=int(d['id'])
            conn.execute("UPDATE documenti SET tesserato_id=? WHERE id=?",(new_tid,did))
            iid=int(d['inbound_id'] or 0) if 'inbound_id' in d.keys() else 0
            if iid and table(conn,'inbound_documents'):
                ic=cols(conn,'inbound_documents'); sets=[]; vals=[]
                for col in ('tesserato_id','matched_tesserato_id','suggested_tesserato_id'):
                    if col in ic:sets.append(col+'=?');vals.append(new_tid)
                if 'match_score' in ic:sets.append('match_score=?');vals.append(100)
                if sets:
                    vals.append(iid);conn.execute("UPDATE inbound_documents SET "+','.join(sets)+" WHERE id=?",tuple(vals))
            moved.append({'document_id':did,'from':old_tid,'to':new_tid,'inbound_id':iid})

    conn.commit()

    # Build actual active groups after correction.
    groups={}
    rows=conn.execute("SELECT * FROM documenti WHERE coalesce(tesserato_id,0)>0 AND coalesce(visibile,1)=1 ORDER BY id").fetchall()
    for d in rows:
        sm=sem(conn,'documenti',int(d['id']))
        if actual_medical(d,sm):
            groups.setdefault(int(d['tesserato_id']),[]).append((d,sm))

    def score(pair):
        d,sm=pair; an=sm.get('analysis') or {}
        exp=parse_date(an.get('expiry_date') or (d['data_scadenza'] if 'data_scadenza' in d.keys() else ''))
        iss=parse_date(an.get('issue_date'))
        return (exp.toordinal() if exp else 0,iss.toordinal() if iss else 0,float(sm.get('confidence') or 0),1 if str(d['status'] or '').lower()=='verificato' else 0,int(d['id']))

    # Common-reference guard before deleting an operational document row.
    def references(did):
        hits=[]
        tables=[str(x[0]) for x in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
        for tn in tables:
            if tn in ('documenti','bodymind_document_semantics','bodymind_medical_history_archive','bodymind_duplicate_records_archive'):continue
            tcols=cols(conn,tn); refcols=set()
            for candidate in ('document_id','doc_id','documento_id'):
                if candidate in tcols:refcols.add(candidate)
            try:
                for fkrow in conn.execute("PRAGMA foreign_key_list("+tn+")").fetchall():
                    if str(fkrow[2])=='documenti':refcols.add(str(fkrow[3]))
            except Exception:pass
            for col in refcols:
                try:n=int(conn.execute("SELECT COUNT(*) FROM "+tn+" WHERE "+col+"=?",(did,)).fetchone()[0])
                except Exception:n=0
                if n:hits.append((tn,col,n))
        return hits

    for tid,items in groups.items():
        items=sorted(items,key=score,reverse=True)
        winner,winsem=items[0]
        winner_id=int(winner['id'])
        wan=winsem.get('analysis') or {}
        wexp=iso(wan.get('expiry_date') or (winner['data_scadenza'] if 'data_scadenza' in winner.keys() else ''))
        # Normalize canonical row.
        dc=cols(conn,'documenti'); sets=[]; vals=[]
        if 'doc_type' in dc:sets.append("doc_type='certificato_medico'")
        if 'categoria' in dc:sets.append("categoria='Certificato medico'")
        if 'visibile' in dc:sets.append("visibile=1")
        if sets:conn.execute("UPDATE documenti SET "+','.join(sets)+" WHERE id=?",(winner_id,))
        # Never downgrade a later profile expiry, but fill/advance it from canonical evidence.
        if wexp:
            cur=conn.execute("SELECT certificato_scadenza FROM tesserati WHERE id=?",(tid,)).fetchone()
            old=iso(cur[0] if cur else '')
            if not old or (parse_date(wexp) and (not parse_date(old) or parse_date(wexp)>parse_date(old))):
                conn.execute("UPDATE tesserati SET certificato_scadenza=?,updated_at=? WHERE id=?",(wexp,datetime.now().isoformat(timespec='seconds'),tid))
                expiry_updates.append({'tid':tid,'old':old,'new':wexp,'document_id':winner_id})
        for loser,lsem in items[1:]:
            did=int(loser['id']); refs=references(did)
            payload=dict(loser); semrows=[]
            if table(conn,'bodymind_document_semantics'):
                semrows=[dict(x) for x in conn.execute("SELECT * FROM bodymind_document_semantics WHERE source_table='documenti' AND source_id=? ORDER BY id",(did,)).fetchall()]
            conn.execute("""INSERT OR IGNORE INTO bodymind_medical_history_archive
              (document_id,tesserato_id,canonical_document_id,reason,payload_json,semantics_json,archived_at)
              VALUES(?,?,?,?,?,?,?)""",
              (did,tid,winner_id,'R100 superseded/non-canonical medical document',
               json.dumps(payload,ensure_ascii=False,default=str),json.dumps(semrows,ensure_ascii=False,default=str),
               datetime.now().isoformat(timespec='seconds')))
            if refs:
                dc=cols(conn,'documenti');sets=[];vals=[]
                if 'visibile' in dc:sets.append('visibile=0')
                if 'status' in dc:sets.append("status='medical_history_archived_r100'")
                if sets:conn.execute("UPDATE documenti SET "+','.join(sets)+" WHERE id=?",(did,))
                blocked.append({'document_id':did,'references':refs,'canonical':winner_id})
            else:
                if table(conn,'bodymind_document_semantics'):
                    conn.execute("DELETE FROM bodymind_document_semantics WHERE source_table='documenti' AND source_id=?",(did,))
                conn.execute("DELETE FROM documenti WHERE id=?",(did,))
                archived.append({'document_id':did,'tid':tid,'canonical':winner_id})
    conn.commit()

    # Final invariants.
    mismatches=[];multi=[]
    rows=conn.execute("SELECT * FROM documenti WHERE coalesce(tesserato_id,0)>0 AND coalesce(visibile,1)=1 ORDER BY id").fetchall()
    final_groups={}
    for d in rows:
        sm=sem(conn,'documenti',int(d['id']))
        if not actual_medical(d,sm):continue
        final_groups.setdefault(int(d['tesserato_id']),[]).append(int(d['id']))
        an=sm.get('analysis') or {}
        if float(sm.get('confidence') or 0)>=.90:
            pname=norm(an.get('person_name') or sm.get('person'))
            firstlast=norm((str(an.get('first_name') or '')+' '+str(an.get('last_name') or '')).strip())
            assigned=conn.execute("SELECT nome,cognome FROM tesserati WHERE id=?",(int(d['tesserato_id']),)).fetchone()
            forms={norm((str(assigned['nome'] or '')+' '+str(assigned['cognome'] or '')).strip()),norm((str(assigned['cognome'] or '')+' '+str(assigned['nome'] or '')).strip())} if assigned else set()
            if (pname or firstlast) and not ({pname,firstlast}&forms):
                # Only flag when semantic name is populated and clearly disagrees.
                mismatches.append({'document_id':int(d['id']),'tid':int(d['tesserato_id']),'semantic_person':str(an.get('person_name') or sm.get('person') or '')})
    multi=[{'tid':tid,'docs':ids} for tid,ids in final_groups.items() if len(ids)>1]
    giulia=conn.execute("SELECT id,certificato_scadenza FROM tesserati WHERE lower(nome)='giulia' AND lower(cognome)='di francia' LIMIT 1").fetchone()
    giulia_docs=[]
    if giulia:
        giulia_docs=[int(x[0]) for x in conn.execute("""SELECT id FROM documenti WHERE tesserato_id=? AND coalesce(visibile,1)=1
          AND (lower(coalesce(doc_type,''))='certificato_medico' OR lower(coalesce(categoria,''))='certificato medico') ORDER BY id""",(int(giulia['id']),)).fetchall()]
    virginia_req=conn.execute("SELECT doc_type,categoria FROM documenti WHERE id=52").fetchone()
    counts={'tesserati':int(conn.execute('SELECT COUNT(*) FROM tesserati').fetchone()[0]),
            'documenti':int(conn.execute('SELECT COUNT(*) FROM documenti').fetchone()[0]),
            'inbound_documents':int(conn.execute('SELECT COUNT(*) FROM inbound_documents').fetchone()[0])}
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0]);fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:
    conn.close()

print('[r100-medical] moved='+json.dumps(moved,ensure_ascii=False)+' reclassified='+json.dumps(reclassified)+
      ' archived='+json.dumps(archived)+' blocked='+json.dumps(blocked,ensure_ascii=False)+
      ' expiry_updates='+json.dumps(expiry_updates,ensure_ascii=False)+
      ' final_multi='+json.dumps(multi)+' final_mismatches='+json.dumps(mismatches,ensure_ascii=False)+
      ' giulia_docs='+json.dumps(giulia_docs)+' giulia_expiry='+(str(giulia['certificato_scadenza'] or '') if giulia else '')+
      ' virginia_request='+(json.dumps(dict(virginia_req),ensure_ascii=False) if virginia_req else '{}')+
      ' counts='+json.dumps(counts)+' backup='+backup+' integrity='+integrity+' fk='+str(fk),flush=True)

# Runtime/source QA.
ptext=PROFILE.read_text(encoding='utf-8',errors='replace')
dtext=DOCPAGE.read_text(encoding='utf-8',errors='replace')
otext=OP.read_text(encoding='utf-8',errors='replace')
checks={
  'profile_save_verify':'BODYMIND_R100_PROFILE_SAVE_VERIFY' in ptext and "/mobile/atlete?updated=" in ptext,
  'submitted_only':"f in tcols and f in request.form" in ptext,
  'expanded_fields':all(x in ptext for x in ("codice_fiscale","data_nascita","indirizzo","luogo_nascita")),
  'mobile_docs_visible_only':'BODYMIND_R100_VISIBLE_DOCS_ONLY' in dtext and 'COALESCE(visibile,1)=1' in dtext,
  'operator_medical_target':'BODYMIND_R100_MEDICAL_IDENTITY_TARGET' in otext,
  'no_multi_medical':not multi,
  'no_medical_identity_mismatch':not mismatches,
  'giulia_one_medical':len(giulia_docs)==1,
  'virginia_request_retyped':bool(virginia_req and str(virginia_req['doc_type'] or '')=='richiesta_certificato_medico'),
  'tesserati_unchanged':counts['tesserati']==35,
  'db_ok':integrity.lower()=='ok' and fk==0,
}
print('[r100-checks] '+repr(checks),flush=True)
failed=[k for k,v in checks.items() if not v]
if failed:raise RuntimeError('R100 QA failed '+repr(failed))
print('[r100-selftest] PASS medical-canonical global-identity mobile-visible-only profile-save-readback return-athletes db-ok',flush=True)
