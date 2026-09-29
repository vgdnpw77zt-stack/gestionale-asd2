# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from datetime import datetime
import shutil, sqlite3, sys

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MARKER=APP/'.BODYMIND_MU_TUTELA_R36'
BACKUPS=Path('/data/release_backups/20260929_mu_tutela_r36')

TRUSTED_STATUSES={'verificato','salvato','accepted','manual_accepted','ok'}
MU_ALIASES=(
    'modulo_unico_tesseramento','modulo unico','modulo_unico','mu-2026','mu 2026',
    'modulo iscrizione','domanda iscrizione','iscrizione manleva'
)
COVERED_REQUEST_TYPES={
    'modulo_unico_tesseramento','consenso_minore','autorizzazione_genitore',
    'privacy_consenso','manleva','domanda_iscrizione','tutela_minore','safeguarding'
}

def table(conn,name):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())

def cols(conn,name):
    return {str(r[1]) for r in conn.execute('PRAGMA table_info('+name+')').fetchall()} if table(conn,name) else set()

def norm(v):
    return str(v or '').strip().lower()

def is_mu_row(r):
    hay=' '.join(
        norm(r[k]) for k in ('doc_type','categoria','titolo','original_filename','filename')
        if k in r.keys()
    )
    return any(alias in hay for alias in MU_ALIASES)

def trusted_mu_tids(conn):
    tids=set()
    if table(conn,'documenti'):
        dc=cols(conn,'documenti')
        if 'tesserato_id' in dc:
            for r in conn.execute("SELECT * FROM documenti WHERE coalesce(tesserato_id,0)>0").fetchall():
                if not is_mu_row(r):
                    continue
                status=norm(r['status']) if 'status' in r.keys() else ''
                visible=int((r['visibile'] if 'visibile' in r.keys() else 1) or 0)
                if visible and status in TRUSTED_STATUSES:
                    tids.add(int(r['tesserato_id']))
    if table(conn,'onboarding_document_requests'):
        oc=cols(conn,'onboarding_document_requests')
        if {'tesserato_id','document_type','status'}.issubset(oc):
            rows=conn.execute("""
                SELECT DISTINCT tesserato_id
                FROM onboarding_document_requests
                WHERE coalesce(tesserato_id,0)>0
                  AND lower(coalesce(document_type,''))='modulo_unico_tesseramento'
                  AND lower(coalesce(status,'')) IN ('accepted','manual_accepted')
            """).fetchall()
            tids.update(int(r[0]) for r in rows)
    return tids

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

if not MARKER.exists():
    if not DB.exists():
        raise RuntimeError('R36 DB missing')
    BACKUPS.mkdir(parents=True,exist_ok=True)
    dbbak=BACKUPS/'asd.db'
    if not dbbak.exists():
        shutil.copy2(DB,dbbak)

    sys.path.insert(0,str(APP))
    from asd_app.onboarding_flow import sync_unified_module_flags, recompute_onboarding_status

    conn=sqlite3.connect(str(DB),timeout=30)
    conn.row_factory=sqlite3.Row
    changed=[]
    skipped=[]
    reconciled_requests=0
    try:
        trusted=trusted_mu_tids(conn)
        mc=cols(conn,'minori')
        oc=cols(conn,'onboarding_document_requests')
        for tid in sorted(trusted):
            athlete=conn.execute("SELECT * FROM tesserati WHERE id=?",(tid,)).fetchone()
            if not athlete:
                continue
            keys=set(athlete.keys())
            is_minor=int((athlete['minorenne'] if 'minorenne' in keys else 0) or 0)==1
            if not is_minor:
                continue
            name=(str(athlete['nome'] or '')+' '+str(athlete['cognome'] or '')).strip()
            guardian=str((athlete['genitore'] if 'genitore' in keys else '') or '').strip()
            if not guardian:
                skipped.append({'tid':tid,'name':name,'reason':'guardian missing'})
                continue

            before=conn.execute("SELECT * FROM minori WHERE tesserato_id=? LIMIT 1",(tid,)).fetchone() if table(conn,'minori') else None
            befored={k:before[k] for k in before.keys()} if before else {}
            optional={k:befored.get(k) for k in ('delega_ritiro_ok','uscita_autonoma_ok') if k in befored}

            sync_unified_module_flags(conn,tid,source='r36_trusted_mu_reconcile')
            recompute_onboarding_status(conn,tid)

            after=conn.execute("SELECT * FROM minori WHERE tesserato_id=? LIMIT 1",(tid,)).fetchone() if table(conn,'minori') else None
            if not after:
                raise RuntimeError(f'R36 trusted MU minor row unavailable tid={tid} name={name}')
            afterd={k:after[k] for k in after.keys()}
            for k,v in optional.items():
                if afterd.get(k)!=v:
                    raise RuntimeError(f'R36 optional choice changed tid={tid} field={k}')
            if befored!=afterd:
                changed.append({
                    'tid':tid,'name':name,
                    'before':{k:befored.get(k) for k in ('consenso_firmato','autorizzazioni_ok','data_consenso') if k in befored},
                    'after':{k:afterd.get(k) for k in ('consenso_firmato','autorizzazioni_ok','data_consenso') if k in afterd},
                })

            if table(conn,'onboarding_document_requests') and {'tesserato_id','document_type','status'}.issubset(oc):
                placeholders=','.join('?' for _ in COVERED_REQUEST_TYPES)
                sets=["status='manual_accepted'"]
                if 'returned_at' in oc: sets.append("returned_at=COALESCE(returned_at,datetime('now'))")
                if 'accepted_at' in oc: sets.append("accepted_at=COALESCE(accepted_at,datetime('now'))")
                if 'accepted_by' in oc: sets.append("accepted_by=COALESCE(NULLIF(accepted_by,''),'r36_trusted_mu')")
                if 'note' in oc: sets.append("note=CASE WHEN instr(coalesce(note,''),'R36 MU')=0 THEN trim(coalesce(note,'') || ' | R36 MU verificato: tutela genitore coperta') ELSE note END")
                params=[tid,*sorted(COVERED_REQUEST_TYPES)]
                cur=conn.execute(
                    "UPDATE onboarding_document_requests SET "+','.join(sets)+
                    " WHERE tesserato_id=? AND lower(coalesce(document_type,'')) IN ("+placeholders+")"+
                    " AND lower(coalesce(status,'')) NOT IN ('deleted','cancelled','accepted','manual_accepted')",
                    params
                )
                reconciled_requests += int(cur.rowcount or 0)
                recompute_onboarding_status(conn,tid)

        conn.commit()

        failures=[]
        trusted=trusted_mu_tids(conn)
        for tid in sorted(trusted):
            athlete=conn.execute("SELECT * FROM tesserati WHERE id=?",(tid,)).fetchone()
            if not athlete:
                continue
            keys=set(athlete.keys())
            if int((athlete['minorenne'] if 'minorenne' in keys else 0) or 0)!=1:
                continue
            guardian=str((athlete['genitore'] if 'genitore' in keys else '') or '').strip()
            if not guardian:
                continue
            m=conn.execute("SELECT * FROM minori WHERE tesserato_id=? LIMIT 1",(tid,)).fetchone() if table(conn,'minori') else None
            if not m:
                failures.append((tid,'minor row missing')); continue
            mk=set(m.keys())
            if 'consenso_firmato' in mk and int(m['consenso_firmato'] or 0)!=1:
                failures.append((tid,'consenso_firmato'))
            if 'autorizzazioni_ok' in mk and int(m['autorizzazioni_ok'] or 0)!=1:
                failures.append((tid,'autorizzazioni_ok'))

        integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
        fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
        if integrity.lower()!='ok' or fk:
            raise RuntimeError(f'R36 DB integrity failed integrity={integrity} fk={fk}')
        if failures:
            raise RuntimeError('R36 trusted MU tutela reconciliation failed '+repr(failures))

        lud=conn.execute("""
            SELECT t.id,t.nome,t.cognome,t.genitore,
                   m.consenso_firmato,m.autorizzazioni_ok,m.delega_ritiro_ok,m.uscita_autonoma_ok
            FROM tesserati t
            LEFT JOIN minori m ON m.tesserato_id=t.id
            WHERE lower(t.nome)='ludovica' AND lower(t.cognome)='angelucci'
            LIMIT 1
        """).fetchone() if table(conn,'minori') else None

        print('[mu-tutela-r36] trusted='+repr(sorted(trusted))+' changed='+repr(changed),flush=True)
        print('[mu-tutela-r36] requests_reconciled='+str(reconciled_requests)+' skipped='+repr(skipped),flush=True)
        print('[mu-tutela-r36] ludovica_angelucci='+repr(dict(lud) if lud else None),flush=True)
        print(f'[mu-tutela-r36-audit] integrity={integrity} fk={fk} failures={failures}',flush=True)
    finally:
        conn.close()

    MARKER.write_text('BodyMind MU tutela R36 reconciled\n',encoding='utf-8')
    print('[mu-tutela-r36-selftest] PASS trusted-MU minor-flags onboarding-requests explicit-NO-preserved db-ok',flush=True)
else:
    print('[mu-tutela-r36] already applied',flush=True)
