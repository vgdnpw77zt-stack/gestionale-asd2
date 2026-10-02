# -*- coding: utf-8 -*-
from __future__ import annotations
import json, re, sqlite3
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')

def table(conn,name):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())

def low(v): return str(v or '').strip().lower()

def is_med(r):
    ks=set(r.keys())
    hay=' '.join(low(r[k]) for k in ('doc_type','categoria','titolo','filename','original_filename') if k in ks)
    return ('certificato_medico' in hay or 'certificato medico' in hay or
            ('certificato' in hay and ('medic' in hay or 'agonist' in hay or 'sportiv' in hay)))

def sem(conn,source_table,source_id):
    if not table(conn,'bodymind_document_semantics'): return {}
    r=conn.execute("""SELECT * FROM bodymind_document_semantics
      WHERE source_table=? AND source_id=? ORDER BY id DESC LIMIT 1""",(source_table,int(source_id))).fetchone()
    if not r:return {}
    out={k:r[k] for k in r.keys()}
    try: out['analysis']=json.loads(str(r['analysis_json'] or '{}'))
    except Exception: out['analysis']={}
    return out

conn=sqlite3.connect(str(DB),timeout=45); conn.row_factory=sqlite3.Row
report={}
try:
    g=conn.execute("""SELECT * FROM tesserati
      WHERE lower(trim(coalesce(nome,'')))='giulia' AND lower(trim(coalesce(cognome,'')))='di francia'
      ORDER BY id DESC LIMIT 1""").fetchone()
    giulia={}
    if g:
        tid=int(g['id'])
        docs=conn.execute("SELECT * FROM documenti WHERE tesserato_id=? ORDER BY id",(tid,)).fetchall()
        ins=conn.execute("SELECT * FROM inbound_documents WHERE coalesce(tesserato_id,0)=? ORDER BY id",(tid,)).fetchall() if table(conn,'inbound_documents') else []
        giulia={
          'id':tid,
          'certificato_scadenza':str(g['certificato_scadenza'] or '') if 'certificato_scadenza' in g.keys() else '',
          'documents':[{
             'id':int(d['id']),
             'title':str(d['titolo'] or '') if 'titolo' in d.keys() else '',
             'category':str(d['categoria'] or '') if 'categoria' in d.keys() else '',
             'doc_type':str(d['doc_type'] or '') if 'doc_type' in d.keys() else '',
             'status':str(d['status'] or '') if 'status' in d.keys() else '',
             'visible':int(d['visibile'] or 0) if 'visibile' in d.keys() else None,
             'filename':str(d['filename'] or '') if 'filename' in d.keys() else '',
             'inbound_id':int(d['inbound_id'] or 0) if 'inbound_id' in d.keys() else 0,
             'is_medical':is_med(d),
             'semantic':sem(conn,'documenti',int(d['id']))
          } for d in docs],
          'inbound':[{
             'id':int(r['id']),
             'status':str(r['status'] or '') if 'status' in r.keys() else '',
             'document_type':str(r['document_type'] or '') if 'document_type' in r.keys() else '',
             'confidence':int(r['document_confidence'] or 0) if 'document_confidence' in r.keys() else 0,
             'match_score':int(r['match_score'] or 0) if 'match_score' in r.keys() else 0,
             'filename':str(r['original_filename'] or '') if 'original_filename' in r.keys() else '',
             'semantic':sem(conn,'inbound_documents',int(r['id']))
          } for r in ins if is_med(r)]
        }
    report['giulia_di_francia']=giulia

    active_multi=[]
    per={}
    rows=conn.execute("SELECT * FROM documenti WHERE coalesce(tesserato_id,0)>0 AND coalesce(visibile,1)=1 ORDER BY tesserato_id,id").fetchall()
    for d in rows:
        if is_med(d):
            per.setdefault(int(d['tesserato_id']),[]).append(d)
    for tid,items in per.items():
        if len(items)>1:
            a=conn.execute("SELECT nome,cognome,certificato_scadenza FROM tesserati WHERE id=?",(tid,)).fetchone()
            active_multi.append({
              'tid':tid,
              'name':((str(a['nome'] or '')+' '+str(a['cognome'] or '')).strip() if a else ''),
              'profile_expiry':str(a['certificato_scadenza'] or '') if a else '',
              'docs':[{
                'id':int(d['id']),
                'title':str(d['titolo'] or '') if 'titolo' in d.keys() else '',
                'category':str(d['categoria'] or '') if 'categoria' in d.keys() else '',
                'doc_type':str(d['doc_type'] or '') if 'doc_type' in d.keys() else '',
                'status':str(d['status'] or '') if 'status' in d.keys() else '',
                'filename':str(d['filename'] or '') if 'filename' in d.keys() else '',
                'semantic':sem(conn,'documenti',int(d['id']))
              } for d in items]
            })
    report['active_multi_medical']=active_multi

    archived=[]
    rows=conn.execute("SELECT * FROM documenti WHERE coalesce(tesserato_id,0)>0 AND coalesce(visibile,1)=0 ORDER BY tesserato_id,id").fetchall()
    for d in rows:
        if is_med(d):
            archived.append({
              'id':int(d['id']),'tid':int(d['tesserato_id'] or 0),
              'status':str(d['status'] or '') if 'status' in d.keys() else '',
              'title':str(d['titolo'] or '') if 'titolo' in d.keys() else '',
              'filename':str(d['filename'] or '') if 'filename' in d.keys() else '',
            })
    report['archived_medical_rows_still_in_documenti']=archived

    source_hits=[]
    for p in (APP/'asd_app').rglob('*.py'):
        try: txt=p.read_text(encoding='utf-8',errors='replace')
        except Exception: continue
        lowtxt=txt.lower()
        if 'criticità' in lowtxt or 'criticita' in lowtxt:
            snippets=[]
            for m in list(re.finditer('critic',lowtxt))[:12]:
                i=m.start(); snippets.append(txt[max(0,i-900):i+2200])
            source_hits.append({'file':str(p.relative_to(APP)),'snippets':snippets})
    report['criticality_source_hits']=source_hits

    report['counts']={
      'tesserati':int(conn.execute('SELECT COUNT(*) FROM tesserati').fetchone()[0]),
      'documenti':int(conn.execute('SELECT COUNT(*) FROM documenti').fetchone()[0]),
      'inbound_documents':int(conn.execute('SELECT COUNT(*) FROM inbound_documents').fetchone()[0]),
    }
    report['integrity']=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    report['foreign_keys']=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:
    conn.close()

print('[r96-medical-criticality-audit] '+json.dumps(report,ensure_ascii=False,default=str),flush=True)
print('[r96-selftest] PASS read-only medical-global + criticality-source audit',flush=True)
if report['integrity'].lower()!='ok' or report['foreign_keys']:
    raise RuntimeError('R96 DB integrity failed')
