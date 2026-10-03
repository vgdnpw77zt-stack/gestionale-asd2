# -*- coding: utf-8 -*-
from __future__ import annotations
import json, re, sqlite3, sys
from pathlib import Path

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
sys.path.insert(0,str(APP))

def table(c,n):
    return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(n,)).fetchone())

def snippet(path,patterns,radius=2200):
    p=APP/path
    if not p.exists(): return {'path':str(p),'exists':False}
    s=p.read_text(encoding='utf-8',errors='replace')
    out=[]
    for pat in patterns:
        for m in list(re.finditer(pat,s,re.I))[:4]:
            out.append({'pattern':pat,'at':m.start(),'text':s[max(0,m.start()-radius):min(len(s),m.end()+radius)]})
    return {'path':str(p),'exists':True,'matches':out[:12]}

sources=[
 snippet('asd_app/routes_inbound_documents.py',[r'needs_manual_match',r'match_score',r'documenti_da_verificare',r'r11_documento_atleta',r'conferma',r'assegna']),
 snippet('asd_app/routes_email_documents.py',[r'needs_manual_match',r'find_tesserato_for_text',r'process_inbound_attachment',r'create_athlete',r'enrollment_identity_ready']),
 snippet('asd_app/routes_operator_bodymind.py',[r'new_athletes',r'needs_manual_match',r'enrollment_identity_ready',r'create_athlete_from_analysis']),
 snippet('asd_app/enrollment_ingest_core_r65.py',[r'def enrollment_identity_ready',r'def create_athlete_from_analysis',r'def athlete_fields_from_analysis']),
 snippet('asd_app/verified_mu_sync_core_r68.py',[r'def sync_analysis_to_existing_athlete',r'guardian_',r'privacy',r'liberatoria',r'consenso',r'onboarding']),
]
conn=sqlite3.connect(str(DB),timeout=30); conn.row_factory=sqlite3.Row
try:
    latest_all=[]
    if table(conn,'inbound_documents'):
        for _r in conn.execute("SELECT * FROM inbound_documents ORDER BY id DESC LIMIT 15").fetchall():
            _d=dict(_r); _iid=int(_d.get('id') or 0); _sem=None
            if table(conn,'bodymind_document_semantics'):
                _sr=conn.execute("""SELECT analysis_json FROM bodymind_document_semantics
                    WHERE source_table='inbound_documents' AND source_id=? ORDER BY id DESC LIMIT 1""",(_iid,)).fetchone()
                if _sr:
                    try: _sem=json.loads(str(_sr['analysis_json'] or '{}'))
                    except Exception: _sem=None
            latest_all.append({
              'id':_iid,'original_filename':_d.get('original_filename'),'status':_d.get('status'),
              'document_type':_d.get('document_type'),'document_confidence':_d.get('document_confidence'),
              'match_score':_d.get('match_score'),'match_action':_d.get('match_action'),
              'tesserato_id':_d.get('tesserato_id'),'suggested_tesserato_id':_d.get('suggested_tesserato_id'),
              'semantic_type':(_sem or {}).get('document_type'),'semantic_person':(_sem or {}).get('person_name'),
              'semantic_cf':(_sem or {}).get('codice_fiscale'),'semantic_birth':(_sem or {}).get('birth_date'),
              'semantic_confidence':(_sem or {}).get('confidence')
            })
    recent=[]
    if table(conn,'inbound_documents'):
        rows=conn.execute("SELECT * FROM inbound_documents ORDER BY id DESC LIMIT 80").fetchall()
        for r in rows:
            d=dict(r)
            hay=' '.join(str(d.get(k) or '').lower() for k in ('document_type','original_filename','filename','status'))
            if not any(x in hay for x in ('modulo','iscrizion','adesion')) and str(d.get('document_type') or '')!='modulo_unico_tesseramento':
                continue
            iid=int(d.get('id') or 0)
            sem=None
            if table(conn,'bodymind_document_semantics'):
                sr=conn.execute("""SELECT analysis_json FROM bodymind_document_semantics
                    WHERE source_table='inbound_documents' AND source_id=? ORDER BY id DESC LIMIT 1""",(iid,)).fetchone()
                if sr:
                    try: sem=json.loads(str(sr['analysis_json'] or '{}'))
                    except Exception: sem=None
            recent.append({
              'id':iid,'original_filename':d.get('original_filename'),'status':d.get('status'),
              'document_type':d.get('document_type'),'document_confidence':d.get('document_confidence'),
              'match_score':d.get('match_score'),'tesserato_id':d.get('tesserato_id'),
              'matched_tesserato_id':d.get('matched_tesserato_id'),'suggested_tesserato_id':d.get('suggested_tesserato_id'),
              'semantic':{k:(sem or {}).get(k) for k in ('document_type','person_name','first_name','last_name','codice_fiscale','birth_date','guardian_name','guardian_phone','guardian_email','privacy_consent','image_consent','athlete_signature','guardian_signature','confidence')}
            })
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally: conn.close()

print('[r116-mu-no-match-audit] '+json.dumps({'latest_inbound':latest_all,'recent_mu':recent[:20],'sources':sources,'integrity':integrity,'fk':fk},ensure_ascii=False,default=str),flush=True)
if integrity.lower()!='ok' or fk:
    raise RuntimeError('R116 DB guard failed')
print('[r116-selftest] PASS read-only no-match-MU audit db-ok',flush=True)
