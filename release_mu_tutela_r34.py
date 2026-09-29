# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from datetime import datetime
import shutil, sqlite3, sys

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MARKER=APP/'.BODYMIND_MU_TUTELA_R34'
BACKUPS=Path('/data/release_backups/20260929_mu_tutela_r34')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

def table(conn,name):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())

def cols(conn,name):
    return {str(r[1]) for r in conn.execute('PRAGMA table_info('+name+')').fetchall()} if table(conn,name) else set()

def norm(v):
    return str(v or '').strip().lower()

def is_mu_row(r):
    parts=[]
    for k in ('doc_type','categoria','titolo','original_filename','filename'):
        if k in r.keys():
            parts.append(norm(r[k]))
    hay=' '.join(parts)
    aliases=(
        'modulo_unico_tesseramento','modulo unico','modulo_unico','mu-2026',
        'domanda iscrizione','iscrizione manleva','modulo iscrizione'
    )
    return any(x in hay for x in aliases)

def trusted_mu_tids(conn):
    tids=set()
    trusted={'verificato','salvato','accepted','manual_accepted','ok'}
    if table(conn,'documenti'):
        dc=cols(conn,'documenti')
        if 'tesserato_id' in dc:
            rows=conn.execute("SELECT * FROM documenti WHERE coalesce(tesserato_id,0)>0").fetchall()
            for r in rows:
                if not is_mu_row(r):
                    continue
                status=norm(r['status']) if 'status' in r.keys() else ''
                visible=int((r['visibile'] if 'visibile' in r.keys() else 1) or 0)
                if visible and status in trusted:
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

if not MARKER.exists():
    if not DB.exists():
        raise RuntimeError('R34 DB missing')
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
    try:
        trusted=trusted_mu_tids(conn)
        tc=cols(conn,'tesserati')
        mc=cols(conn,'minori')
        for tid in sorted(trusted):
            athlete=conn.execute("SELECT * FROM tesserati WHERE id=?",(tid,)).fetchone()
            if not athlete:
                continue
            is_minor=int((athlete['minorenne'] if 'minorenne' in athlete.keys() else 0) or 0)==1
            if not is_minor:
                continue
            guardian=str((athlete['genitore'] if 'genitore' in athlete.keys() else '') or '').strip()
            if not guardian:
                skipped.append({'tid':tid,'name':(str(athlete['nome'])+' '+str(athlete['cognome'])).strip(),'reason':'guardian missing'})
                continue

            minor=conn.execute("SELECT * FROM minori WHERE tesserato_id=? LIMIT 1",(tid,)).fetchone() if table(conn,'minori') else None
            if not minor and table(conn,'minori'):
                values={}
                for key in ('nome','cognome','genitore','telefono_genitore','email_genitore','tenant_id'):
                    if key in mc and key in athlete.keys():
                        values[key]=athlete[key]
                if 'tesserato_id' in mc: values['tesserato_id']=tid
                if 'created_at' in mc: values['created_at']=datetime.now().isoformat(timespec='seconds')
                if 'updated_at' in mc: values['updated_at']=datetime.now().isoformat(timespec='seconds')
                if {'tesserato_id'}.issubset(values):
                    keys=list(values)
                    conn.execute(
                        'INSERT INTO minori('+','.join(keys)+') VALUES('+','.join('?' for _ in keys)+')',
                        [values[k] for k in keys]
                    )
                    minor=conn.execute("SELECT * FROM minori WHERE tesserato_id=? LIMIT 1",(tid,)).fetchone()

            if not minor:
                skipped.append({'tid':tid,'name':(str(athlete['nome'])+' '+str(athlete['cognome'])).strip(),'reason':'minor row unavailable'})
                continue

            before={k:minor[k] for k in minor.keys()}
            optional={k:before.get(k) for k in ('delega_ritiro_ok','uscita_autonoma_ok') if k in before}
            sync_unified_module_flags(conn,tid,source='r34_trusted_mu_reconcile')
            recompute_onboarding_status(conn,tid)
            after=conn.execute("SELECT * FROM minori WHERE tesserato_id=? LIMIT 1",(tid,)).fetchone()
            afterd={k:after[k] for k in after.keys()}
            for k,v in optional.items():
                if afterd.get(k)!=v:
                    raise RuntimeError(f'R34 optional choice changed tid={tid} field={k}')
            if before!=afterd:
                changed.append({
                    'tid':tid,
                    'name':(str(athlete['nome'])+' '+str(athlete['cognome'])).strip(),
                    'before':{k:before.get(k) for k in ('consenso_firmato','autorizzazioni_ok','data_consenso') if k in before},
                    'after':{k:afterd.get(k) for k in ('consenso_firmato','autorizzazioni_ok','data_consenso') if k in afterd},
                })

        conn.commit()
        integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
        fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
        if integrity.lower()!='ok' or fk:
            raise RuntimeError(f'R34 DB integrity failed integrity={integrity} fk={fk}')

        lud=conn.execute("""
            SELECT t.id,t.nome,t.cognome,t.genitore,
                   m.consenso_firmato,m.autorizzazioni_ok,m.delega_ritiro_ok,m.uscita_autonoma_ok
            FROM tesserati t
            LEFT JOIN minori m ON m.tesserato_id=t.id
            WHERE lower(t.nome)='ludovica' AND lower(t.cognome)='angelucci'
            LIMIT 1
        """).fetchone() if table(conn,'minori') else None
        lud_state=dict(lud) if lud else None

        print('[mu-tutela-r34] trusted_mu_minors='+str(len([x for x in trusted]))+' changed='+repr(changed),flush=True)
        print('[mu-tutela-r34] skipped='+repr(skipped),flush=True)
        print('[mu-tutela-r34] ludovica_angelucci='+repr(lud_state),flush=True)
        print(f'[mu-tutela-r34-audit] integrity={integrity} fk={fk}',flush=True)
    finally:
        conn.close()

    MARKER.write_text('BodyMind MU tutela R34 applied\n',encoding='utf-8')
    print('[mu-tutela-r34-selftest] PASS trusted-mu-only consent-authorizations optional-choices-preserved ludovica-audited db-ok',flush=True)
else:
    print('[mu-tutela-r34] already applied',flush=True)
