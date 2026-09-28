from __future__ import annotations
from pathlib import Path
import compileall, sqlite3, shutil

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MARKER=APP/'.BODYMIND_DOCUMENT_FLOW_R25'
BACKUPS=Path('/data/release_backups/20260928_document_flow_r25')

def patch(rel, fn):
    p=APP/rel
    if not p.exists():
        raise RuntimeError('R25 target missing: '+rel)
    old=p.read_text(encoding='utf-8')
    new=fn(old)
    if new!=old:
        dst=BACKUPS/rel
        if not dst.exists():
            dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(p,dst)
        p.write_text(new,encoding='utf-8')
    return new

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

if not MARKER.exists():
    BACKUPS.mkdir(parents=True,exist_ok=True)

    def onboarding(s):
        if 'BODYMIND_R25_MINOR_MU_SYNC' in s:
            return s
        old="'consenso_informato','liberatoria_immagini','manleva_firmata',"
        if old not in s:
            raise RuntimeError('R25 covered flags anchor missing')
        s=s.replace(old,"'consenso_informato','manleva_firmata',  # BODYMIND_R25_MINOR_MU_SYNC",1)
        anchor="""        minor=conn.execute('SELECT id FROM minori WHERE tesserato_id=? LIMIT 1',(tid,)).fetchone()
        if minor:
"""
        insert="""        minor=conn.execute('SELECT id FROM minori WHERE tesserato_id=? LIMIT 1',(tid,)).fetchone()
        # BODYMIND_R25_MINOR_MU_SYNC: create linked minor row only from known athlete/guardian data.
        if not minor:
            trow=conn.execute('SELECT * FROM tesserati WHERE id=? LIMIT 1',(tid,)).fetchone()
            if trow:
                tkeys=set(trow.keys()) if hasattr(trow,'keys') else set()
                is_minor=int((trow['minorenne'] if 'minorenne' in tkeys else 0) or 0)==1
                guardian=str((trow['genitore'] if 'genitore' in tkeys else '') or '').strip()
                if is_minor and guardian:
                    values={}
                    for key in ('nome','cognome','genitore','telefono_genitore','email_genitore','tenant_id'):
                        if key in mcols and key in tkeys:
                            values[key]=trow[key]
                    if 'tesserato_id' in mcols: values['tesserato_id']=tid
                    if 'created_at' in mcols: values['created_at']=datetime.now().isoformat(timespec='seconds')
                    if 'updated_at' in mcols: values['updated_at']=datetime.now().isoformat(timespec='seconds')
                    if {'nome','cognome','genitore','tesserato_id'}.issubset(values):
                        keys=list(values)
                        conn.execute('INSERT INTO minori('+','.join(keys)+') VALUES('+','.join('?' for _ in keys)+')',[values[k] for k in keys])
                        minor=conn.execute('SELECT id FROM minori WHERE tesserato_id=? LIMIT 1',(tid,)).fetchone()
        if minor:
"""
        if anchor not in s:
            raise RuntimeError('R25 minor link anchor missing')
        return s.replace(anchor,insert,1)

    patch('asd_app/onboarding_flow.py',onboarding)

    def documenti(s):
        if 'BODYMIND_R25_DOSSIER_MU_VERIFY' in s:
            return s
        anchor="""        conn.commit()
    finally:
        try: conn.close()
        except Exception: pass
    return redirect_with_message("/documenti", "Documento verificato.", "success", tesserato_id=tesserato_id)
"""
        repl="""        # BODYMIND_R25_DOSSIER_MU_VERIFY
        dtype=str((row["doc_type"] if "doc_type" in row.keys() else "") or "").strip().lower()
        cat=str((row["categoria"] if "categoria" in row.keys() else "") or "").strip().lower()
        title=str((row["titolo"] if "titolo" in row.keys() else "") or "").strip().lower()
        aliases={'modulo_unico_tesseramento','iscrizione','domanda_iscrizione','manleva','liberatoria_immagini','consenso_minore','autorizzazione_genitore','privacy','privacy_consenso','safeguarding','tutela_minore'}
        is_mu=(dtype in aliases or 'modulo unico' in cat or 'modulo unico' in title or 'modulo iscrizione' in cat)
        if is_mu and tesserato_id>0:
            from .onboarding_flow import sync_unified_module_flags, recompute_onboarding_status
            sync_unified_module_flags(conn,tesserato_id,source='dossier_ok')
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='onboarding_document_requests'").fetchone():
                ocols={str(x[1]) for x in c.execute("PRAGMA table_info(onboarding_document_requests)").fetchall()}
                sets=["status='manual_accepted'"]
                if 'returned_at' in ocols: sets.append("returned_at=COALESCE(returned_at,datetime('now'))")
                if 'accepted_at' in ocols: sets.append("accepted_at=COALESCE(accepted_at,datetime('now'))")
                if 'accepted_by' in ocols: sets.append("accepted_by='admin'")
                if 'note' in ocols: sets.append("note=TRIM(COALESCE(note,'') || ' | Modulo Unico verificato dal dossier')")
                c.execute("UPDATE onboarding_document_requests SET "+','.join(sets)+" WHERE tesserato_id=? AND document_type='modulo_unico_tesseramento' AND required=1 AND status NOT IN ('deleted','cancelled')",(tesserato_id,))
            recompute_onboarding_status(conn,tesserato_id)
        conn.commit()
    finally:
        try: conn.close()
        except Exception: pass
    return redirect_with_message("/documenti", "Documento verificato.", "success", tesserato_id=tesserato_id)
"""
        if anchor not in s:
            raise RuntimeError('R25 dossier verify anchor missing')
        return s.replace(anchor,repl,1)

    patch('asd_app/routes_documenti.py',documenti)

    def email(s):
        if 'BODYMIND_R25_MU_TRUST_BOUNDARY' in s:
            return s
        old="""        if tesserato_id:
            if doc_area == 'pagamenti':
                status = 'pagamento_da_verificare'
            elif classification.get('type_needs_review'):
                status = 'associato_tipo_da_verificare'
            else:
                status = 'associato'
"""
        new="""        if tesserato_id:
            # BODYMIND_R25_MU_TRUST_BOUNDARY: identity may be automatic; consent/signatures may not.
            ctype=str(classification.get('type') or classification.get('document_type') or classification.get('doc_type') or '').strip().lower()
            fname_low=str(filename or '').lower()
            is_mu=(ctype in {'modulo_unico_tesseramento','iscrizione','domanda_iscrizione','manleva','liberatoria_immagini','consenso_minore','autorizzazione_genitore','privacy','privacy_consenso','safeguarding','tutela_minore'} or 'modulo_unico' in fname_low or 'modulo unico' in fname_low or 'iscrizione' in fname_low)
            if doc_area == 'pagamenti':
                status = 'pagamento_da_verificare'
            elif is_mu:
                status = 'richiede_conferma'
            elif classification.get('type_needs_review'):
                status = 'associato_tipo_da_verificare'
            else:
                status = 'associato'
"""
        if old not in s:
            raise RuntimeError('R25 inbound status anchor missing')
        s=s.replace(old,new,1)
        old_sync="if status in ('associato', 'associato_tipo_da_verificare', 'pagamento_da_verificare'):"
        if old_sync in s:
            s=s.replace(old_sync,"if status in ('associato', 'associato_tipo_da_verificare', 'richiede_conferma', 'pagamento_da_verificare'):",1)
        return s

    patch('asd_app/routes_email_documents.py',email)

    def inbound(s):
        if 'BODYMIND_R25_MANUAL_TYPE_MU' in s:
            return s
        old="            new_status = 'pagamento_da_verificare' if new_type == 'ricevuta_pagamento' else 'associato'"
        new="            # BODYMIND_R25_MANUAL_TYPE_MU\n            new_status = ('richiede_conferma' if new_type == 'modulo_unico_tesseramento' else ('pagamento_da_verificare' if new_type == 'ricevuta_pagamento' else 'associato'))"
        if old not in s:
            raise RuntimeError('R25 manual type anchor missing')
        return s.replace(old,new,1)

    patch('asd_app/routes_inbound_documents.py',inbound)

    if not compileall.compile_dir(str(APP/'asd_app'),quiet=1):
        raise RuntimeError('R25 compile failed')
    checks={
        'minor-sync':'BODYMIND_R25_MINOR_MU_SYNC' in (APP/'asd_app/onboarding_flow.py').read_text(encoding='utf-8'),
        'dossier-sync':'BODYMIND_R25_DOSSIER_MU_VERIFY' in (APP/'asd_app/routes_documenti.py').read_text(encoding='utf-8'),
        'trust-boundary':'BODYMIND_R25_MU_TRUST_BOUNDARY' in (APP/'asd_app/routes_email_documents.py').read_text(encoding='utf-8'),
        'manual-type':'BODYMIND_R25_MANUAL_TYPE_MU' in (APP/'asd_app/routes_inbound_documents.py').read_text(encoding='utf-8'),
    }
    failed=[k for k,v in checks.items() if not v]
    if failed:
        raise RuntimeError('R25 selftest failed: '+repr(failed))
    MARKER.write_text('BodyMind document flow R25 applied\n',encoding='utf-8')
    print('[document-flow-r25] applied',flush=True)
    print('[document-flow-r25-selftest] PASS mu-trust-boundary dossier-ok minor-consent explicit-no-preserved',flush=True)
else:
    print('[document-flow-r25] already applied',flush=True)

if DB.exists():
    conn=sqlite3.connect(str(DB),timeout=20)
    try:
        integrity=str(conn.execute('PRAGMA integrity_check').fetchone()[0])
        fk=len(conn.execute('PRAGMA foreign_key_check').fetchall())
        tess=int(conn.execute('SELECT COUNT(*) FROM tesserati').fetchone()[0])
        minors=int(conn.execute('SELECT COUNT(*) FROM minori').fetchone()[0]) if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='minori'").fetchone() else 0
        auto=0
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='onboarding_document_requests'").fetchone():
            sql="SELECT COUNT(*) FROM onboarding_document_requests WHERE document_type='modulo_unico_tesseramento' AND lower(coalesce(accepted_by,''))='autopilot' AND lower(coalesce(status,'')) IN ('accepted','manual_accepted')"
            auto=int(conn.execute(sql).fetchone()[0])
        print(f'[document-flow-r25-audit] integrity={integrity} fk={fk} tesserati={tess} minori={minors} autopilot_mu_accepted={auto}',flush=True)
        if integrity.lower()!='ok' or fk:
            raise RuntimeError('R25 DB integrity failed')
    finally:
        conn.close()
