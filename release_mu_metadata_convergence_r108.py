# -*- coding: utf-8 -*-
from __future__ import annotations
import json, sqlite3
from datetime import datetime
from pathlib import Path

DB=Path('/data/tenants/default/asd.db')
BACK=Path('/data/release_backups/20261002_r108_mu_metadata')
BACK.mkdir(parents=True,exist_ok=True)

def table(conn,name):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())

def cols(conn,name):
    return {str(r[1]) for r in conn.execute("PRAGMA table_info("+name+")").fetchall()} if table(conn,name) else set()

def is_mu_row(r):
    ks=set(r.keys())
    hay=' '.join(str(r[k] or '').lower() for k in ('doc_type','categoria','titolo','original_filename','filename') if k in ks)
    return (
      'modulo_unico_tesseramento' in hay or 'modulo unico' in hay or 'modulo_unico' in hay
      or 'modulo iscrizione' in hay or 'domanda iscrizione' in hay or 'iscrizione manleva' in hay
    )

def semantic(conn,did):
    if not table(conn,'bodymind_document_semantics'): return None
    r=conn.execute("""SELECT analysis_json,confidence,document_type FROM bodymind_document_semantics
      WHERE source_table='documenti' AND source_id=? ORDER BY id DESC LIMIT 1""",(int(did),)).fetchone()
    if not r: return None
    try: a=json.loads(str(r['analysis_json'] or '{}'))
    except Exception: a={}
    if not isinstance(a,dict): a={}
    if not a.get('document_type'): a['document_type']=r['document_type']
    if not a.get('confidence'): a['confidence']=r['confidence']
    return a

conn=sqlite3.connect(str(DB),timeout=45); conn.row_factory=sqlite3.Row
try:
    dcols=cols(conn,'documenti')
    rows=conn.execute("SELECT * FROM documenti WHERE COALESCE(visibile,1)=1 ORDER BY id").fetchall()
    targets=[]; blocked=[]
    for r in rows:
        if not is_mu_row(r): continue
        dtype=str(r['doc_type'] or '').strip().lower() if 'doc_type' in r.keys() else ''
        cat=str(r['categoria'] or '').strip().lower() if 'categoria' in r.keys() else ''
        if dtype=='modulo_unico_tesseramento' and 'modulo iscrizione' in cat: continue
        evidence=[]
        a=semantic(conn,int(r['id']))
        if isinstance(a,dict) and str(a.get('document_type') or '').strip().lower()=='modulo_unico_tesseramento':
            try: conf=float(a.get('confidence') or 0)
            except Exception: conf=0
            if conf>=.90: evidence.append('document_semantic')
        iid=int(r['inbound_id'] or 0) if 'inbound_id' in r.keys() else 0
        if iid>0 and table(conn,'inbound_documents'):
            ir=conn.execute("SELECT * FROM inbound_documents WHERE id=?",(iid,)).fetchone()
            if ir:
                itype=str(ir['document_type'] or '').strip().lower() if 'document_type' in ir.keys() else ''
                iconf=int(ir['document_confidence'] or 0) if 'document_confidence' in ir.keys() else 0
                imatch=int(ir['match_score'] or 0) if 'match_score' in ir.keys() else 0
                same_tid=int(ir['tesserato_id'] or 0)==int(r['tesserato_id'] or 0) if 'tesserato_id' in ir.keys() else False
                if itype=='modulo_unico_tesseramento' and iconf>=90 and imatch>=90 and same_tid:
                    evidence.append('trusted_inbound')
        tplt=str(r['tipo_template'] or '').lower() if 'tipo_template' in r.keys() else ''
        if 'modulo_unico_tesseramento_bodymind' in tplt:
            evidence.append('canonical_template')
        if evidence:
            targets.append((dict(r),evidence))
        else:
            blocked.append({'id':int(r['id']),'tesserato_id':int(r['tesserato_id'] or 0),'reason':'mu_signal_without_strong_evidence'})

    if targets:
        stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
        b=BACK/('pre_r108_'+stamp+'.db')
        src=sqlite3.connect(str(DB),timeout=45); dst=sqlite3.connect(str(b))
        try: src.backup(dst)
        finally: dst.close(); src.close()
        changed=[]
        for r,evidence in targets:
            sets=[]; vals=[]
            if 'doc_type' in dcols: sets.append("doc_type=?"); vals.append('modulo_unico_tesseramento')
            if 'categoria' in dcols: sets.append("categoria=?"); vals.append('Modulo iscrizione BodyMind')
            if 'status' in dcols and str(r.get('status') or '').strip().lower() in ('','da_verificare','needs_review','associato_tipo_da_verificare'):
                sets.append("status=?"); vals.append('salvato')
            if sets:
                vals.append(int(r['id']))
                conn.execute("UPDATE documenti SET "+",".join(sets)+" WHERE id=?",tuple(vals))
            tid=int(r.get('tesserato_id') or 0)
            if tid>0:
                try:
                    from asd_app.onboarding_flow import sync_unified_module_flags,recompute_onboarding_status
                    sync_unified_module_flags(conn,tid,source='r108_mu_metadata')
                    recompute_onboarding_status(conn,tid)
                except Exception:
                    pass
            changed.append({'id':int(r['id']),'tesserato_id':tid,'old_doc_type':r.get('doc_type'),'old_categoria':r.get('categoria'),'evidence':evidence})
        conn.commit()
    else:
        changed=[]; b=None

    integrity=str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    fk=len(conn.execute("PRAGMA foreign_key_check").fetchall())
    remaining=[]
    for r in conn.execute("SELECT * FROM documenti WHERE COALESCE(visibile,1)=1 ORDER BY id").fetchall():
        if not is_mu_row(r): continue
        dtype=str(r['doc_type'] or '').strip().lower() if 'doc_type' in r.keys() else ''
        cat=str(r['categoria'] or '').strip().lower() if 'categoria' in r.keys() else ''
        if dtype!='modulo_unico_tesseramento' or 'modulo iscrizione' not in cat:
            remaining.append({'id':int(r['id']),'tesserato_id':int(r['tesserato_id'] or 0),'doc_type':dtype,'categoria':cat})
finally:
    conn.close()

print('[r108-mu-metadata] '+json.dumps({
  'changed':changed,'changed_count':len(changed),'blocked':blocked,'backup':str(b) if b else '',
  'remaining_incoherent':remaining,'integrity':integrity,'fk':fk
},ensure_ascii=False,default=str),flush=True)
if remaining or integrity.lower()!='ok' or fk:
    raise RuntimeError('R108 MU metadata convergence failed')
print('[r108-selftest] PASS strong-evidence visible-MU canonical metadata integrity/fk',flush=True)

