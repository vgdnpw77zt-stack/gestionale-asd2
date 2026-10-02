# -*- coding: utf-8 -*-
from __future__ import annotations
import hashlib, inspect, json, re, sqlite3
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')

def table(c,n): return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(n,)).fetchone())
def norm(v): return re.sub(r'[^a-z0-9]','',str(v or '').lower().replace('à','a').replace('è','e').replace('é','e').replace('ì','i').replace('ò','o').replace('ù','u'))
def is_med(r):
    ks=set(r.keys()); hay=' '.join(str(r[k] or '').lower() for k in ('doc_type','categoria','titolo','filename','original_filename') if k in ks)
    return 'certificato_medico' in hay or 'certificato medico' in hay or ('certificato' in hay and ('medic' in hay or 'agonist' in hay or 'sportiv' in hay))
def sem(c,st,sid):
    if not table(c,'bodymind_document_semantics'): return {}
    r=c.execute("SELECT * FROM bodymind_document_semantics WHERE source_table=? AND source_id=? ORDER BY id DESC LIMIT 1",(st,int(sid))).fetchone()
    if not r:return {}
    try:a=json.loads(str(r['analysis_json'] or '{}'))
    except Exception:a={}
    return {'key':str(r['semantic_key'] or ''),'sha':str(r['sha256'] or ''),'confidence':float(r['confidence'] or 0),
            'person':str(r['person_name'] or ''),'cf':str(r['codice_fiscale'] or ''),'analysis':a if isinstance(a,dict) else {}}

conn=sqlite3.connect(str(DB),timeout=45); conn.row_factory=sqlite3.Row
try:
    athletes=conn.execute("SELECT * FROM tesserati ORDER BY id").fetchall()
    by_cf={norm(a['codice_fiscale']):a for a in athletes if 'codice_fiscale' in a.keys() and norm(a['codice_fiscale'])}
    by_name={}
    for a in athletes:
        key=norm((str(a['nome'] or '')+' '+str(a['cognome'] or '')).strip())
        if key: by_name.setdefault(key,[]).append(a)

    compact=[]; groups={}
    rows=conn.execute("SELECT * FROM documenti WHERE coalesce(tesserato_id,0)>0 AND coalesce(visibile,1)=1 ORDER BY tesserato_id,id").fetchall()
    for d in rows:
        if not is_med(d): continue
        tid=int(d['tesserato_id']); a=conn.execute("SELECT * FROM tesserati WHERE id=?",(tid,)).fetchone()
        sm=sem(conn,'documenti',int(d['id'])); an=sm.get('analysis') or {}
        cf=norm(an.get('codice_fiscale') or sm.get('cf'))
        pname=str(an.get('person_name') or sm.get('person') or '').strip()
        first=str(an.get('first_name') or '').strip(); last=str(an.get('last_name') or '').strip()
        target=None
        if cf and cf in by_cf:
            target=by_cf[cf]
        else:
            for nm in (pname,(first+' '+last).strip(),(last+' '+first).strip()):
                k=norm(nm)
                if k and k in by_name and len(by_name[k])==1:
                    target=by_name[k][0]; break
        fpath=str(d['filename'] or '') if 'filename' in d.keys() else ''
        disk_sha=''
        try:
            p=Path(fpath)
            if p.is_file(): disk_sha=hashlib.sha256(p.read_bytes()).hexdigest()
        except Exception: pass
        summary=str(an.get('content_summary') or '')[:180]
        rec={
          'document_id':int(d['id']),'assigned_tid':tid,'assigned_name':((str(a['nome'] or '')+' '+str(a['cognome'] or '')).strip() if a else ''),
          'resolved_tid':int(target['id']) if target else None,'resolved_name':((str(target['nome'] or '')+' '+str(target['cognome'] or '')).strip() if target else ''),
          'title':str(d['titolo'] or '') if 'titolo' in d.keys() else '',
          'category':str(d['categoria'] or '') if 'categoria' in d.keys() else '',
          'doc_type':str(d['doc_type'] or '') if 'doc_type' in d.keys() else '',
          'status':str(d['status'] or '') if 'status' in d.keys() else '',
          'inbound_id':int(d['inbound_id'] or 0) if 'inbound_id' in d.keys() else 0,
          'filename':fpath,'disk_sha':disk_sha,
          'semantic_key':sm.get('key',''),'semantic_sha':sm.get('sha',''),'semantic_confidence':sm.get('confidence',0),
          'semantic_person':pname or (first+' '+last).strip(),'semantic_cf':cf,
          'issue_date':str(an.get('issue_date') or ''),'expiry_date':str(an.get('expiry_date') or ''),
          'summary':summary,
          'identity_mismatch':bool(target and int(target['id'])!=tid)
        }
        compact.append(rec); groups.setdefault(tid,[]).append(rec)

    multi=[{'tid':tid,'name':items[0]['assigned_name'],'profile_expiry':str(conn.execute("SELECT certificato_scadenza FROM tesserati WHERE id=?",(tid,)).fetchone()[0] or ''),'docs':items}
           for tid,items in groups.items() if len(items)>1]
    mismatch=[x for x in compact if x['identity_mismatch']]
    giulia=[x for x in compact if x['assigned_tid']==19 or x['resolved_tid']==19 or 'giuliadifrancia' in norm(x['semantic_person'])]

    print('[r98-medical-mismatch] '+json.dumps(mismatch,ensure_ascii=False),flush=True)
    print('[r98-medical-multi] '+json.dumps(multi,ensure_ascii=False),flush=True)
    print('[r98-giulia] '+json.dumps(giulia,ensure_ascii=False),flush=True)
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0]); fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:
    conn.close()

# Emit only exact function bodies relevant to mobile profile edit/save and obvious criticality POST handlers.
ath=[]
crit=[]
for p in (APP/'asd_app').rglob('*.py'):
    try: txt=p.read_text(encoding='utf-8',errors='replace')
    except Exception: continue
    if 'def fix24_mobile_atleta' in txt:
        pos=txt.find('def fix24_mobile_atleta')
        end=txt.find('\ndef ',pos+5)
        ath.append({'file':str(p.relative_to(APP)),'code':txt[pos:(end if end>pos else pos+18000)]})
    low=txt.lower()
    if ('criticità' in low or 'criticita' in low) and 'request.method' in txt:
        # keep snippets only around POST/update/redirect
        for m in re.finditer(r'def\s+\w+\s*\([^\)]*\):',txt):
            pos=m.start(); body=txt[pos:pos+7000]
            bl=body.lower()
            if ('criticità' in bl or 'criticita' in bl) and ('request.method' in body or 'request.form' in body):
                crit.append({'file':str(p.relative_to(APP)),'code':body})
                break
print('[r98-athlete-save-source] '+json.dumps(ath,ensure_ascii=False),flush=True)
print('[r98-criticality-save-source] '+json.dumps(crit[:8],ensure_ascii=False),flush=True)
print('[r98-selftest] PASS compact-medical + exact-save-source audit integrity='+integrity+' fk='+str(fk),flush=True)
if integrity.lower()!='ok' or fk: raise RuntimeError('R98 DB integrity failed')
