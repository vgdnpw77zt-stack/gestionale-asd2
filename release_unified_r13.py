from __future__ import annotations
from pathlib import Path
import compileall, shutil

APP=Path('/data/top2_app')
MARKER=APP/'.BODYMIND_UNIFIED_DOC_R13'
BACKUPS=Path('/data/release_backups/20260927_unified_r13')

def backup(rel):
    src=APP/rel; dst=BACKUPS/rel
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dst)

def patch_file(rel, transform):
    p=APP/rel
    if not p.exists():
        raise RuntimeError('R13 target missing: '+rel)
    old=p.read_text(encoding='utf-8')
    new=transform(old)
    if new!=old:
        backup(rel)
        p.write_text(new,encoding='utf-8')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

if not MARKER.exists():
    def patch_a202(s):
        if 'BODYMIND_R13_UNIFIED_DOCUMENT' in s:
            return s

        anchor='def _r11_doc_label(value):\n'
        helper=r'''# BODYMIND_R13_UNIFIED_DOCUMENT
_R13_UNIFIED_ALIASES = {
    'modulo_unico_tesseramento','iscrizione','domanda_iscrizione','manleva',
    'liberatoria_immagini','consenso_minore','autorizzazione_genitore',
    'privacy','privacy_consenso','safeguarding','tutela_minore'
}

def _r13_canonical_type(value):
    value=str(value or '').strip()
    return 'modulo_unico_tesseramento' if value in _R13_UNIFIED_ALIASES else value

def _r13_accept_unified(conn, inbound):
    if not inbound:
        return
    dtype=_r13_canonical_type(inbound['document_type'] if 'document_type' in inbound.keys() else '')
    tid=int(inbound['tesserato_id'] or 0) if 'tesserato_id' in inbound.keys() else 0
    if dtype!='modulo_unico_tesseramento' or tid<=0:
        return
    now=datetime.now().isoformat(timespec='seconds')
    # The operator's OK means the single BodyMind registration form was actually checked.
    if _has_table(conn,'onboarding_document_requests'):
        cols=_cols(conn,'onboarding_document_requests')
        sets=["status='manual_accepted'"]
        vals=[]
        if 'returned_at' in cols: sets.append("returned_at=COALESCE(returned_at,?)"); vals.append(now)
        if 'accepted_at' in cols: sets.append("accepted_at=COALESCE(accepted_at,?)"); vals.append(now)
        if 'accepted_by' in cols: sets.append("accepted_by=COALESCE(NULLIF(accepted_by,''),'admin')")
        if 'note' in cols: sets.append("note=TRIM(COALESCE(note,'') || ' | Modulo Unico verificato dalla coda documenti')")
        vals.append(tid)
        conn.execute(
            "UPDATE onboarding_document_requests SET "+','.join(sets)+
            " WHERE tesserato_id=? AND document_type='modulo_unico_tesseramento' "
            "AND required=1 AND status NOT IN ('accepted','manual_accepted','deleted','cancelled')",
            vals
        )
    # The current MU-2026.1 contains parental consent/tutela. Do not invent guardian data:
    # only mark the consent flag on an already existing minor record.
    if _has_table(conn,'minori'):
        mcols=_cols(conn,'minori')
        if 'consenso_firmato' in mcols:
            sets=["consenso_firmato=1"]
            if 'data_consenso' in mcols:
                sets.append("data_consenso=COALESCE(NULLIF(data_consenso,''),?)")
                conn.execute("UPDATE minori SET "+','.join(sets)+" WHERE tesserato_id=?",(datetime.now().date().isoformat(),tid))
            else:
                conn.execute("UPDATE minori SET "+','.join(sets)+" WHERE tesserato_id=?",(tid,))
    try:
        from .onboarding_flow import recompute_onboarding_status
        recompute_onboarding_status(conn,tid)
    except Exception:
        pass

'''
        if anchor not in s:
            raise RuntimeError('R13 A202 label anchor missing')
        s=s.replace(anchor,helper+anchor,1)

        s=s.replace(
"""def _r11_doc_label(value):
    labels={
        'certificato_medico':'Certificato medico',
        'iscrizione':'Domanda iscrizione',
        'manleva':'Manleva',
        'liberatoria_immagini':'Liberatoria immagini',
        'documento_identita':'Documento identità',
        'consenso_minore':'Consenso minore',
        'autorizzazione_genitore':'Autorizzazione genitore',
        'trasporto_minori':'Trasporto minori',
        'documenti_gara':'Documenti gara',
        'documenti_saggio':'Documenti saggio',
        'ricevuta_pagamento':'Ricevuta / prova pagamento',
        'altro':'Altro / da classificare',
    }
    return labels.get(str(value or '').strip(), str(value or '').strip() or 'Da classificare')
""",
"""def _r11_doc_label(value):
    value=_r13_canonical_type(value)
    labels={
        'modulo_unico_tesseramento':'Modulo iscrizione / Modulo Unico MU-2026.1',
        'certificato_medico':'Certificato medico',
        'documento_identita':'Documento identità',
        'trasporto_minori':'Delega / trasporto minori',
        'documenti_gara':'Documenti gara',
        'documenti_saggio':'Documenti saggio',
        'ricevuta_pagamento':'Ricevuta / prova pagamento',
        'altro':'Altro / da classificare',
    }
    return labels.get(value, value or 'Da classificare')
""",1)

        s=s.replace(
"""def _r11_doc_category(value):
    return {
        'certificato_medico':'Certificato medico',
        'iscrizione':'Domanda iscrizione',
        'manleva':'Manleva',
        'liberatoria_immagini':'Liberatoria immagini',
        'documento_identita':'Documento identità',
        'consenso_minore':'Consenso minore',
        'autorizzazione_genitore':'Autorizzazione genitore',
        'trasporto_minori':'Trasporto minori',
        'documenti_gara':'Documenti gara',
        'documenti_saggio':'Documenti saggio',
        'ricevuta_pagamento':'Pagamenti da verificare',
        'altro':'Altro',
    }.get(str(value or '').strip(),'Altro')
""",
"""def _r11_doc_category(value):
    value=_r13_canonical_type(value)
    return {
        'modulo_unico_tesseramento':'Modulo iscrizione BodyMind',
        'certificato_medico':'Certificato medico',
        'documento_identita':'Documento identità',
        'trasporto_minori':'Delega / trasporto minori',
        'documenti_gara':'Documenti gara',
        'documenti_saggio':'Documenti saggio',
        'ricevuta_pagamento':'Pagamenti da verificare',
        'altro':'Altro',
    }.get(value,'Altro')
""",1)

        old_choices="""    choices=[
        ('certificato_medico','Certificato medico'),('iscrizione','Domanda iscrizione'),
        ('manleva','Manleva'),('liberatoria_immagini','Liberatoria immagini'),
        ('documento_identita','Documento identità'),('consenso_minore','Consenso minore'),
        ('autorizzazione_genitore','Autorizzazione genitore'),('trasporto_minori','Trasporto minori'),
        ('documenti_gara','Documenti gara'),('documenti_saggio','Documenti saggio'),
        ('ricevuta_pagamento','Ricevuta / prova pagamento'),('altro','Altro')
    ]
"""
        new_choices="""    choices=[
        ('modulo_unico_tesseramento','Modulo iscrizione / Modulo Unico MU-2026.1'),
        ('certificato_medico','Certificato medico'),
        ('documento_identita','Documento identità'),
        ('trasporto_minori','Delega / trasporto minori (solo se separata)'),
        ('documenti_gara','Documenti gara'),
        ('documenti_saggio','Documenti saggio'),
        ('ricevuta_pagamento','Ricevuta / prova pagamento'),
        ('altro','Altro')
    ]
"""
        if old_choices not in s:
            raise RuntimeError('R13 A202 choices anchor missing')
        s=s.replace(old_choices,new_choices,1)

        s=s.replace("dtype=str(r['document_type'] or 'altro')","dtype=_r13_canonical_type(r['document_type'] or 'altro')",1)

        old_allowed="""    allowed={
        'certificato_medico','iscrizione','manleva','liberatoria_immagini','documento_identita',
        'consenso_minore','autorizzazione_genitore','trasporto_minori','documenti_gara',
        'documenti_saggio','ricevuta_pagamento','altro'
    }
    dtype=(request.form.get('document_type') or '').strip()
"""
        new_allowed="""    allowed={
        'modulo_unico_tesseramento','certificato_medico','documento_identita',
        'trasporto_minori','documenti_gara','documenti_saggio','ricevuta_pagamento','altro'
    }
    dtype=_r13_canonical_type((request.form.get('document_type') or '').strip())
"""
        if old_allowed not in s:
            raise RuntimeError('R13 A202 allowed anchor missing')
        s=s.replace(old_allowed,new_allowed,1)

        # Correcting a type is not the same as verifying the document.
        s=s.replace(
"status='associato' if tid>0 and dtype!='altro' else ('associato_tipo_da_verificare' if tid>0 else 'needs_manual_match')",
"status='richiede_conferma' if tid>0 and dtype!='altro' else ('associato_tipo_da_verificare' if tid>0 else 'needs_manual_match')",1)
        s=s.replace(
"status='associato' if dtype not in ('','altro') and int(row['document_confidence'] or 0)>=75 else 'associato_tipo_da_verificare'",
"status='richiede_conferma' if _r13_canonical_type(dtype) not in ('','altro') and int(row['document_confidence'] or 0)>=75 else 'associato_tipo_da_verificare'",1)

        ok_anchor="""        dtype=str(row['document_type'] or '')
        if tid<=0:
"""
        ok_new="""        dtype=_r13_canonical_type(row['document_type'] or '')
        if dtype != str(row['document_type'] or ''):
            conn.execute("UPDATE inbound_documents SET document_type=?,document_label=? WHERE id=?",(dtype,_r11_doc_label(dtype),doc_id))
        if tid<=0:
"""
        if ok_anchor not in s:
            raise RuntimeError('R13 OK dtype anchor missing')
        s=s.replace(ok_anchor,ok_new,1)

        sync_anchor="""        _r11_sync_documento(conn,row)
        conn.commit()
"""
        sync_new="""        _r11_sync_documento(conn,row)
        _r13_accept_unified(conn,row)
        conn.commit()
"""
        # Only the first occurrence after r11_documento_ok.
        okpos=s.find("def r11_documento_ok")
        synpos=s.find(sync_anchor,okpos)
        if synpos<0:
            raise RuntimeError('R13 OK sync anchor missing')
        s=s[:synpos]+s[synpos:].replace(sync_anchor,sync_new,1)

        s=s.replace(
"<div><span class='r11-kicker'>Documenti · coda operativa</span><h1>Da verificare</h1><p>Qui compaiono soltanto i documenti che richiedono una scelta umana. Apri, correggi se serve e premi OK.</p></div>",
"<div><span class='r11-kicker'>Documenti · coda operativa</span><h1>Da verificare</h1><p>Il Modulo Unico MU-2026.1 comprende iscrizione, privacy, immagini, tutela e consensi genitoriali. Non vanno classificati come documenti separati. Apri, correggi il tipo se serve e premi OK solo dopo il controllo.</p></div>",1)
        return s

    patch_file('asd_app/routes_a202_operational_integrity.py',patch_a202)

    def patch_inbound(s):
        if 'BODYMIND_R13_LEGACY_SELECTOR' in s:
            return s
        s=s.replace(
"""    labels = {
        'certificato_medico': 'Certificato medico',
        'iscrizione': 'Domanda iscrizione',
        'manleva': 'Manleva',
        'liberatoria_immagini': 'Liberatoria immagini',
        'documento_identita': 'Documento identità',
        'consenso_minore': 'Consenso minore',
        'autorizzazione_genitore': 'Autorizzazione genitore',
        'trasporto_minori': 'Trasporto minori',
        'documenti_gara': 'Documenti gara',
        'documenti_saggio': 'Documenti saggio',
        'ricevuta_pagamento': 'Ricevuta / prova pagamento',
    }
""",
"""    labels = {  # BODYMIND_R13_LEGACY_SELECTOR
        'modulo_unico_tesseramento': 'Modulo iscrizione / Modulo Unico MU-2026.1',
        'certificato_medico': 'Certificato medico',
        'documento_identita': 'Documento identità',
        'trasporto_minori': 'Delega / trasporto minori',
        'documenti_gara': 'Documenti gara',
        'documenti_saggio': 'Documenti saggio',
        'ricevuta_pagamento': 'Ricevuta / prova pagamento',
    }
""",1)
        s=s.replace(
"""    categories = {
        'certificato_medico': 'Certificato medico',
        'iscrizione': 'Domanda iscrizione',
        'manleva': 'Manleva',
        'liberatoria_immagini': 'Liberatoria immagini',
        'documento_identita': 'Documento identità',
        'consenso_minore': 'Consenso minore',
        'autorizzazione_genitore': 'Autorizzazione genitore',
        'trasporto_minori': 'Documenti gara',
        'documenti_gara': 'Documenti gara',
        'documenti_saggio': 'Documenti saggio',
        'ricevuta_pagamento': 'Pagamenti da verificare',
    }
""",
"""    categories = {
        'modulo_unico_tesseramento': 'Modulo iscrizione BodyMind',
        'certificato_medico': 'Certificato medico',
        'documento_identita': 'Documento identità',
        'trasporto_minori': 'Delega / trasporto minori',
        'documenti_gara': 'Documenti gara',
        'documenti_saggio': 'Documenti saggio',
        'ricevuta_pagamento': 'Pagamenti da verificare',
    }
""",1)
        old_choices="""    choices = [
        ('certificato_medico','Certificato medico'),('iscrizione','Domanda iscrizione'),
        ('manleva','Manleva'),('liberatoria_immagini','Liberatoria immagini'),
        ('documento_identita','Documento identità'),('consenso_minore','Consenso minore'),
        ('autorizzazione_genitore','Autorizzazione genitore'),('trasporto_minori','Trasporto minori'),
        ('documenti_gara','Documenti gara'),('documenti_saggio','Documenti saggio'),
        ('ricevuta_pagamento','Ricevuta / prova pagamento')
    ]
"""
        new_choices="""    choices = [
        ('modulo_unico_tesseramento','Modulo iscrizione / Modulo Unico MU-2026.1'),
        ('certificato_medico','Certificato medico'),
        ('documento_identita','Documento identità'),
        ('trasporto_minori','Delega / trasporto minori'),
        ('documenti_gara','Documenti gara'),
        ('documenti_saggio','Documenti saggio'),
        ('ricevuta_pagamento','Ricevuta / prova pagamento')
    ]
"""
        if old_choices in s:
            s=s.replace(old_choices,new_choices,1)
        return s

    patch_file('asd_app/routes_inbound_documents.py',patch_inbound)

    if not compileall.compile_dir(str(APP/'asd_app'),quiet=1):
        raise RuntimeError('R13 compile failed')

    a202=(APP/'asd_app/routes_a202_operational_integrity.py').read_text(encoding='utf-8')
    inbound=(APP/'asd_app/routes_inbound_documents.py').read_text(encoding='utf-8')
    checks={
        'unified-type':"modulo_unico_tesseramento" in a202,
        'no-old-choice':"('manleva','Manleva')" not in a202 and "('liberatoria_immagini','Liberatoria immagini')" not in a202,
        'final-ok':'_r13_accept_unified(conn,row)' in a202,
        'type-keeps-review':"status='richiede_conferma' if tid>0 and dtype!='altro'" in a202,
        'legacy-selector':'BODYMIND_R13_LEGACY_SELECTOR' in inbound,
    }
    failed=[k for k,v in checks.items() if not v]
    if failed:
        raise RuntimeError('R13 selftest failed: '+repr(failed))
    MARKER.write_text('BodyMind unified registration document R13 applied\n',encoding='utf-8')
    print('[unified-r13] applied',flush=True)
    print('[unified-r13-selftest] PASS single-module selector final-OK onboarding-sync minor-consent legacy-selector',flush=True)
else:
    print('[unified-r13] already applied',flush=True)
