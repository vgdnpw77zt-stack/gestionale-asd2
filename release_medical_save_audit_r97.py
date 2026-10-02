# -*- coding: utf-8 -*-
from __future__ import annotations
import inspect, json, re, sqlite3
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
    r=c.execute("""SELECT * FROM bodymind_document_semantics WHERE source_table=? AND source_id=? ORDER BY id DESC LIMIT 1""",(st,int(sid))).fetchone()
    if not r:return {}
    try:a=json.loads(str(r['analysis_json'] or '{}'))
    except Exception:a={}
    return {'semantic_key':str(r['semantic_key'] or ''),'sha256':str(r['sha256'] or ''),'confidence':float(r['confidence'] or 0),
            'person_name':str(r['person_name'] or ''),'codice_fiscale':str(r['codice_fiscale'] or ''),'analysis':a if isinstance(a,dict) else {}}

conn=sqlite3.connect(str(DB),timeout=45); conn.row_factory=sqlite3.Row
report={}
try:
    athletes=conn.execute("SELECT * FROM tesserati ORDER BY id").fetchall()
    by_cf={norm(a['codice_fiscale']):a for a in athletes if 'codice_fiscale' in a.keys() and norm(a['codice_fiscale'])}
    by_name={}
    for a in athletes:
        key=norm((str(a['nome'] or '')+' '+str(a['cognome'] or '')).strip())
        if key: by_name.setdefault(key,[]).append(a)

    active=[]
    groups={}
    rows=conn.execute("SELECT * FROM documenti WHERE coalesce(tesserato_id,0)>0 AND coalesce(visibile,1)=1 ORDER BY tesserato_id,id").fetchall()
    for d in rows:
        if not is_med(d): continue
        tid=int(d['tesserato_id']); a=conn.execute("SELECT * FROM tesserati WHERE id=?",(tid,)).fetchone()
        sm=sem(conn,'documenti',int(d['id'])); an=sm.get('analysis') or {}
        cf=norm(an.get('codice_fiscale') or sm.get('codice_fiscale'))
        pname=str(an.get('person_name') or sm.get('person_name') or '').strip()
        first=str(an.get('first_name') or '').strip(); last=str(an.get('last_name') or '').strip()
        skey=sm.get('semantic_key') or ''
        target=None; reason=''
        if cf and cf in by_cf:
            target=by_cf[cf]; reason='cf'
        else:
            candidates=[]
            for nm in [pname,(first+' '+last).strip(),(last+' '+first).strip()]:
                k=norm(nm)
                if k and k in by_name and len(by_name[k])==1:
                    candidates=by_name[k]; reason='name'; break
            if candidates: target=candidates[0]
        assigned_name=(str(a['nome'] or '')+' '+str(a['cognome'] or '')).strip() if a else ''
        resolved_tid=int(target['id']) if target else None
        rec={
          'document_id':int(d['id']),'assigned_tid':tid,'assigned_name':assigned_name,
          'title':str(d['titolo'] or '') if 'titolo' in d.keys() else '',
          'status':str(d['status'] or '') if 'status' in d.keys() else '',
          'filename':str(d['filename'] or '') if 'filename' in d.keys() else '',
          'semantic_person':pname or (first+' '+last).strip(),'semantic_cf':cf,
          'semantic_confidence':sm.get('confidence',0),'semantic_key':skey,'sha256':sm.get('sha256',''),
          'issue_date':str(an.get('issue_date') or ''),'expiry_date':str(an.get('expiry_date') or ''),
          'resolved_tid':resolved_tid,'resolved_name':((str(target['nome'] or '')+' '+str(target['cognome'] or '')).strip() if target else ''),
          'resolve_reason':reason,'identity_mismatch':bool(resolved_tid and resolved_tid!=tid)
        }
        active.append(rec); groups.setdefault(tid,[]).append(rec)
    report['active_medical']=active
    report['identity_mismatches']=[x for x in active if x['identity_mismatch']]
    report['multi_active']=[{'tid':tid,'name':items[0]['assigned_name'],'count':len(items),'docs':items} for tid,items in groups.items() if len(items)>1]
    skgroups={}
    for x in active:
        if x['semantic_key']: skgroups.setdefault((x['resolved_tid'] or x['assigned_tid'],x['semantic_key']),[]).append(x['document_id'])
    report['same_semantic_key_duplicates']=[{'tid':k[0],'key':k[1],'document_ids':v} for k,v in skgroups.items() if len(v)>1]

    # Compact exact Giulia-related docs regardless of current assignment.
    report['giulia_semantic_docs']=[x for x in active if 'giuliadifrancia' in norm(x['semantic_person']) or x['resolved_tid']==19 or x['assigned_tid']==19]

    report['integrity']=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    report['fk']=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:
    conn.close()

# Locate actual mobile athlete edit/save and criticality save code in persistent runtime.
sources={'athlete':[],'criticality':[]}
for p in (APP/'asd_app').rglob('*.py'):
    try: txt=p.read_text(encoding='utf-8',errors='replace')
    except Exception: continue
    low=txt.lower()
    if 'def fix24_mobile_atleta' in txt or '/mobile/atleta/' in txt:
        for needle in ('def fix24_mobile_atleta','/mobile/atleta/'):
            pos=txt.find(needle)
            if pos>=0:
                sources['athlete'].append({'file':str(p.relative_to(APP)),'snippet':txt[max(0,pos-2500):pos+14000]}); break
    if ('criticità' in low or 'criticita' in low) and ('request.form' in txt or 'methods=[' in txt):
        positions=[i for i in (low.find('criticità'),low.find('criticita')) if i>=0]
        if positions:
            pos=min(positions)
            sources['criticality'].append({'file':str(p.relative_to(APP)),'snippet':txt[max(0,pos-3500):pos+16000]})
report['sources']=sources

print('[r97-medical-save-audit] '+json.dumps(report,ensure_ascii=False,default=str),flush=True)
print('[r97-summary] '+json.dumps({
 'medical_active':len(report['active_medical']),
 'identity_mismatches':len(report['identity_mismatches']),
 'multi_active_athletes':len(report['multi_active']),
 'same_key_duplicates':len(report['same_semantic_key_duplicates']),
 'athlete_sources':[x['file'] for x in sources['athlete']],
 'criticality_sources':[x['file'] for x in sources['criticality']],
 'integrity':report['integrity'],'fk':report['fk']
},ensure_ascii=False),flush=True)
if report['integrity'].lower()!='ok' or report['fk']:
    raise RuntimeError('R97 DB integrity failed')
print('[r97-selftest] PASS read-only medical identity/canonical + athlete-save + criticality-source audit',flush=True)
