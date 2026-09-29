# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import runpy, sqlite3

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MARKER=APP/'.BODYMIND_MU_TUTELA_R37'
R36_MARKER=APP/'.BODYMIND_MU_TUTELA_R36'

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

if not MARKER.exists():
    # Force one clean reconciliation through the current R36 engine even if an
    # earlier R36 marker was written by a previous image.
    try:
        if R36_MARKER.exists():
            R36_MARKER.unlink()
    except Exception as exc:
        raise RuntimeError('R37 cannot refresh R36 reconciliation marker: '+repr(exc))

    runpy.run_path('/opt/bodymind/release_mu_tutela_r36.py',run_name='__main__')

    conn=sqlite3.connect(str(DB),timeout=30)
    conn.row_factory=sqlite3.Row
    try:
        def table(name):
            return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())
        def cols(name):
            return {str(r[1]) for r in conn.execute('PRAGMA table_info('+name+')').fetchall()} if table(name) else set()
        def norm(v):
            return str(v or '').strip().lower()
        def is_mu(r):
            hay=' '.join(norm(r[k]) for k in ('doc_type','categoria','titolo','original_filename','filename') if k in r.keys())
            return any(x in hay for x in ('modulo_unico_tesseramento','modulo unico','modulo_unico','mu-2026','mu 2026','modulo iscrizione','domanda iscrizione','iscrizione manleva'))
        trusted=set()
        if table('documenti') and 'tesserato_id' in cols('documenti'):
            for r in conn.execute("SELECT * FROM documenti WHERE coalesce(tesserato_id,0)>0").fetchall():
                status=norm(r['status']) if 'status' in r.keys() else ''
                visible=int((r['visibile'] if 'visibile' in r.keys() else 1) or 0)
                if visible and is_mu(r) and status in ('verificato','salvato','accepted','manual_accepted','ok'):
                    trusted.add(int(r['tesserato_id']))
        if table('onboarding_document_requests'):
            oc=cols('onboarding_document_requests')
            if {'tesserato_id','document_type','status'}.issubset(oc):
                for r in conn.execute("""SELECT DISTINCT tesserato_id FROM onboarding_document_requests
                    WHERE coalesce(tesserato_id,0)>0
                      AND lower(coalesce(document_type,''))='modulo_unico_tesseramento'
                      AND lower(coalesce(status,'')) IN ('accepted','manual_accepted')""").fetchall():
                    trusted.add(int(r[0]))

        failures=[]
        covered={'modulo_unico_tesseramento','consenso_minore','autorizzazione_genitore','privacy_consenso','manleva','domanda_iscrizione','tutela_minore','safeguarding'}
        for tid in sorted(trusted):
            t=conn.execute("SELECT * FROM tesserati WHERE id=?",(tid,)).fetchone()
            if not t:
                continue
            tk=set(t.keys())
            if int((t['minorenne'] if 'minorenne' in tk else 0) or 0)!=1:
                continue
            guardian=str((t['genitore'] if 'genitore' in tk else '') or '').strip()
            if not guardian:
                continue
            m=conn.execute("SELECT * FROM minori WHERE tesserato_id=? LIMIT 1",(tid,)).fetchone() if table('minori') else None
            if not m:
                failures.append((tid,'minor-row')); continue
            mk=set(m.keys())
            if 'consenso_firmato' in mk and int(m['consenso_firmato'] or 0)!=1:
                failures.append((tid,'consenso_firmato'))
            if 'autorizzazioni_ok' in mk and int(m['autorizzazioni_ok'] or 0)!=1:
                failures.append((tid,'autorizzazioni_ok'))
            if table('onboarding_document_requests'):
                ph=','.join('?' for _ in covered)
                pending=conn.execute(
                    "SELECT document_type,status FROM onboarding_document_requests WHERE tesserato_id=? "+
                    "AND lower(coalesce(document_type,'')) IN ("+ph+") "+
                    "AND lower(coalesce(status,'')) NOT IN ('deleted','cancelled','accepted','manual_accepted')",
                    [tid,*sorted(covered)]
                ).fetchall()
                if pending:
                    failures.append((tid,'covered-requests-pending',[(str(x[0]),str(x[1])) for x in pending]))
        integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
        fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
        print('[mu-tutela-r37-audit] trusted='+repr(sorted(trusted))+' failures='+repr(failures)+' integrity='+integrity+' fk='+str(fk),flush=True)
        if failures or integrity.lower()!='ok' or fk:
            raise RuntimeError('R37 tutela reconciliation failed '+repr(failures))
    finally:
        conn.close()

    MARKER.write_text('BodyMind trusted MU tutela R37 reconciled\n',encoding='utf-8')
    print('[mu-tutela-r37-selftest] PASS forced-reconcile trusted-MU parental-tutela no-legacy-false-positive explicit-NO-preserved db-ok',flush=True)
else:
    print('[mu-tutela-r37] already applied',flush=True)
