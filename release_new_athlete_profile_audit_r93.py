# -*- coding: utf-8 -*-
import json, sqlite3
from pathlib import Path

DB=Path('/data/tenants/default/asd.db')
TARGETS=('promutico','rinaldi','sartori')

def table(conn,name):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())

def cols(conn,name):
    return {str(r[1]) for r in conn.execute("PRAGMA table_info("+name+")").fetchall()} if table(conn,name) else set()

def first(row,names):
    if not row:return ''
    ks=set(row.keys())
    for k in names:
        if k in ks and row[k] is not None and str(row[k]).strip():
            return str(row[k]).strip()
    return ''

def semantics(conn,iid):
    if not table(conn,'bodymind_document_semantics'): return {}
    r=conn.execute("""SELECT analysis_json FROM bodymind_document_semantics
      WHERE source_table='inbound_documents' AND source_id=? ORDER BY id DESC LIMIT 1""",(int(iid),)).fetchone()
    if not r:return {}
    try:
        x=json.loads(str(r['analysis_json'] or '{}'))
        return x if isinstance(x,dict) else {}
    except Exception:return {}

conn=sqlite3.connect(str(DB),timeout=30); conn.row_factory=sqlite3.Row
out=[]
try:
    tc=cols(conn,'tesserati'); mc=cols(conn,'minori'); dc=cols(conn,'documenti'); ic=cols(conn,'inbound_documents')
    for surname in TARGETS:
        a=conn.execute("SELECT * FROM tesserati WHERE lower(trim(coalesce(cognome,'')))=? ORDER BY id DESC LIMIT 1",(surname,)).fetchone()
        if not a:
            out.append({'surname':surname,'found':False}); continue
        tid=int(a['id'])
        profile={
          'id':tid,
          'nome':first(a,('nome',)),
          'cognome':first(a,('cognome',)),
          'codice_fiscale':first(a,('codice_fiscale',)),
          'data_nascita':first(a,('data_nascita',)),
          'luogo_nascita':first(a,('luogo_nascita',)),
          'indirizzo':first(a,('indirizzo',)),
          'citta':first(a,('citta','comune')),
          'cap':first(a,('cap',)),
          'provincia':first(a,('provincia',)),
          'telefono':first(a,('telefono','cellulare')),
          'email':first(a,('email',)),
          'nazionalita':first(a,('nazionalita',)),
          'sesso':first(a,('sesso',)),
          'minorenne':int(a['minorenne'] or 0) if 'minorenne' in tc else None,
          'genitore':first(a,('genitore','nome_genitore')),
          'telefono_genitore':first(a,('telefono_genitore','guardian_phone')),
          'email_genitore':first(a,('email_genitore','guardian_email')),
        }
        flags={k:int(a[k] or 0) for k in ('iscrizione_firmata','documenti_onboarding_ok','privacy_ok','liberatoria_ok','regolamento_ok') if k in tc}

        m=None
        if table(conn,'minori') and 'tesserato_id' in mc:
            mr=conn.execute("SELECT * FROM minori WHERE tesserato_id=? ORDER BY id DESC LIMIT 1",(tid,)).fetchone()
            if mr:
                m={k:mr[k] for k in mr.keys()}

        docs=[]
        if table(conn,'documenti'):
            q="SELECT * FROM documenti WHERE tesserato_id=?"
            if 'visibile' in dc:q+=" AND coalesce(visibile,1)=1"
            q+=" ORDER BY id"
            for d in conn.execute(q,(tid,)).fetchall():
                hay=' '.join(str(d[k] or '').lower() for k in ('titolo','categoria','doc_type','filename') if k in d.keys())
                if 'modulo' in hay or 'iscrizion' in hay:
                    docs.append({k:d[k] for k in d.keys() if k in ('id','titolo','categoria','doc_type','status','visibile','inbound_id','filename')})

        ins=[]
        semantic={}
        if table(conn,'inbound_documents'):
            for ir in conn.execute("SELECT * FROM inbound_documents WHERE tesserato_id=? ORDER BY id",(tid,)).fetchall():
                if str(ir['document_type'] or '').lower()=='modulo_unico_tesseramento':
                    ins.append({k:ir[k] for k in ir.keys() if k in ('id','status','document_type','document_confidence','match_score','original_filename','tesserato_id')})
                    semantic=semantics(conn,int(ir['id'])) or semantic

        semantic_fields={
          'nome':str(semantic.get('first_name') or '').strip(),
          'cognome':str(semantic.get('last_name') or '').strip(),
          'codice_fiscale':str(semantic.get('codice_fiscale') or '').strip(),
          'data_nascita':str(semantic.get('birth_date') or '').strip(),
          'luogo_nascita':str(semantic.get('birth_place') or '').strip(),
          'indirizzo':str(semantic.get('address') or '').strip(),
          'citta':str(semantic.get('city') or '').strip(),
          'cap':str(semantic.get('postal_code') or '').strip(),
          'provincia':str(semantic.get('province') or '').strip(),
          'telefono':str(semantic.get('phone') or '').strip(),
          'email':str(semantic.get('email') or '').strip(),
          'nazionalita':str(semantic.get('nationality') or '').strip(),
          'sesso':str(semantic.get('gender') or '').strip(),
          'genitore':str(semantic.get('guardian_name') or '').strip(),
          'telefono_genitore':str(semantic.get('guardian_phone') or '').strip(),
          'email_genitore':str(semantic.get('guardian_email') or '').strip(),
        }
        missed={}
        for k,v in semantic_fields.items():
            if v and not str(profile.get(k) or '').strip():
                missed[k]=v

        out.append({
          'found':True,'profile':profile,'onboarding':flags,'minor_row':m,
          'mu_documents':docs,'mu_inbound':ins,
          'semantic_confidence':semantic.get('confidence'),
          'semantic_handwriting':semantic.get('handwriting_legibility'),
          'semantic_fields':semantic_fields,
          'semantic_values_missing_from_profile':missed,
        })
    integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
    fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
finally:
    conn.close()

print('[r93-new-athlete-profile-audit] '+json.dumps(out,ensure_ascii=False,default=str),flush=True)
print('[r93-selftest] PASS read-only new-athlete profile/minor/onboarding/MU audit integrity='+integrity+' fk='+str(fk),flush=True)
if integrity.lower()!='ok' or fk:
    raise RuntimeError('R93 DB integrity failed')
