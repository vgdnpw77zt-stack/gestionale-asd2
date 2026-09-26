from __future__ import annotations
from pathlib import Path
import compileall, shutil, sqlite3

APP=Path('/data/top2_app')
DB=Path('/data/tenants/default/asd.db')
MARKER=APP/'.BODYMIND_AUTOPILOT_R9'
BACKUPS=Path('/data/release_backups/20260926_autopilot_r9')

def backup(rel):
    src=APP/rel; dst=BACKUPS/rel
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dst)

def indent_block(text, prefix):
    return '\n'.join((prefix+line if line else '') for line in text.splitlines())+'\n'

def patch_file(rel, transform):
    p=APP/rel
    if not p.exists():
        raise RuntimeError('R9 target missing: '+rel)
    old=p.read_text(encoding='utf-8')
    new=transform(old)
    if new!=old:
        backup(rel)
        p.write_text(new,encoding='utf-8')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

if not MARKER.exists():
    # Recover safely from any partial R9 attempt. Backups were made before the
    # first R9 write and contain the last known-good runtime source.
    for rel in ('asd_app/routes_inbound_documents.py','asd_app/routes_tesserati.py'):
        p=APP/rel; b=BACKUPS/rel
        if p.exists() and b.exists():
            cur=p.read_text(encoding='utf-8',errors='replace')
            if 'BODYMIND_R9_' in cur:
                shutil.copy2(b,p)
                print('[autopilot-r9] restored partial '+rel,flush=True)

    def patch_inbound(s):
        if 'BODYMIND_R9_MANUAL_TYPE' in s:
            return s

        old_import='from .core import app, layout, admin_required, db, e, euro, now_iso_dt, csrf_input, DATA_DIR'
        new_import='from .core import app, layout, admin_required, db, e, euro, now_iso_dt, csrf_input, DATA_DIR, get_workspace_media_dir'
        if new_import not in s:
            if old_import not in s:
                raise RuntimeError('R9 core import anchor missing')
            s=s.replace(old_import,new_import,1)

        file_anchor="@app.route('/documenti-automatici/file/<int:doc_id>')"
        file_route="""# BODYMIND_R9_DOCUMENT_FILE
@app.route('/documenti/file/<int:doc_id>')
@admin_required
def tesserato_document_file(doc_id: int):
    conn = db()
    try:
        row = conn.execute("SELECT id,filename,original_filename FROM documenti WHERE id=? AND COALESCE(visibile,1)=1", (doc_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        abort(404)
    media_root = get_workspace_media_dir().resolve()
    raw = Path(str(row['filename'] or ''))
    fp = raw.resolve() if raw.is_absolute() else (media_root / raw).resolve()
    if fp != media_root and media_root not in fp.parents:
        abort(403)
    if not fp.exists() or not fp.is_file():
        abort(404)
    return send_file(fp, as_attachment=(request.args.get('download') == '1'), download_name=(row['original_filename'] or fp.name))


"""
        if '# BODYMIND_R9_DOCUMENT_FILE' not in s:
            if file_anchor not in s:
                raise RuntimeError('R9 file route anchor missing')
            s=s.replace(file_anchor,file_route+file_anchor,1)

        old_actions="if action in {'mark_review', 'mark_ok', 'delete_doc'} and doc_id:"
        new_actions="if action in {'mark_review', 'mark_ok', 'set_document_type', 'delete_doc'} and doc_id:"
        if new_actions not in s:
            if old_actions not in s:
                raise RuntimeError('R9 POST action anchor missing')
            s=s.replace(old_actions,new_actions,1)

        lines=s.splitlines(True)
        mark_idx=next((i for i,line in enumerate(lines) if "elif action == 'mark_ok':" in line),None)
        if mark_idx is None:
            raise RuntimeError('R9 mark_ok anchor missing')
        mark_line=lines[mark_idx]
        prefix=mark_line[:len(mark_line)-len(mark_line.lstrip())]
        manual_raw="""elif action == 'set_document_type':
    # BODYMIND_R9_MANUAL_TYPE
    new_type = (request.form.get('document_type') or '').strip()
    labels = {
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
    categories = {
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
    if new_type in labels:
        new_status = row['status'] or 'da_verificare'
        if row['tesserato_id']:
            new_status = 'pagamento_da_verificare' if new_type == 'ricevuta_pagamento' else 'associato'
        conn.execute("UPDATE inbound_documents SET document_type=?,document_label=?,document_confidence=100,status=? WHERE id=?", (new_type, labels[new_type], new_status, doc_id))
        try:
            dcols = {str(x[1]) for x in conn.execute("PRAGMA table_info(documenti)").fetchall()}
            updates = {'categoria': categories[new_type]}
            if 'doc_type' in dcols: updates['doc_type'] = new_type
            if 'confidence' in dcols: updates['confidence'] = 100
            if 'match_score' in dcols: updates['match_score'] = int(row['match_score'] or 0)
            if 'source' in dcols: updates['source'] = 'autopilot'
            if 'status' in dcols: updates['status'] = 'salvato'
            if 'inbound_id' in dcols: updates['inbound_id'] = doc_id
            if row['tesserato_id'] and row['saved_path']:
                pairs = ','.join(k+'=?' for k in updates)
                vals = list(updates.values()) + [int(row['tesserato_id']), str(row['saved_path'])]
                conn.execute("UPDATE documenti SET "+pairs+" WHERE tesserato_id=? AND filename=?", vals)
        except Exception as exc:
            log_inbound_event(conn,event_type='manual_type_metadata_warning',message=f'Documento #{doc_id}: tipo assegnato, metadati dossier non completi: {exc}',level='warn',inbound_document_id=doc_id,tesserato_id=row['tesserato_id'])
        if new_type == 'certificato_medico' and row['tesserato_id']:
            try:
                fp = _safe_inbound_file_path(row['saved_path'] or '')
                payload = fp.read_bytes() if fp and fp.exists() else b''
                if payload:
                    dates = infer_medical_certificate_dates(filename=(row['original_filename'] or 'certificato.pdf'), payload=payload)
                    expiry = str((dates or {}).get('expiry_date') or '')
                    issue = str((dates or {}).get('issue_date') or '')
                    if expiry:
                        sync_medical_certificate_state(conn,tesserato_id=int(row['tesserato_id']),expiry_date=expiry,issue_date=issue,source='documenti-automatici tipo manuale',recompute=True)
            except Exception as exc:
                log_inbound_event(conn,event_type='manual_type_medical_warning',message=f'Documento #{doc_id}: certificato classificato, data da verificare: {exc}',level='warn',inbound_document_id=doc_id,tesserato_id=row['tesserato_id'])
        log_inbound_event(conn,event_type='manual_document_type',message=f'Documento #{doc_id}: tipo impostato manualmente su {labels[new_type]}',level='info',inbound_document_id=doc_id,tesserato_id=row['tesserato_id'])
    else:
        log_inbound_event(conn,event_type='manual_document_type_invalid',message=f'Documento #{doc_id}: tipo manuale non valido',level='warn',inbound_document_id=doc_id,tesserato_id=row['tesserato_id'])
"""
        lines.insert(mark_idx,indent_block(manual_raw,prefix))
        s=''.join(lines)

        helper_line="def _post_button(label: str, action: str, doc_id: int, cls: str = 'pro-cta slim', confirm: str = '') -> str:"
        lines=s.splitlines(True)
        helper_idx=next((i for i,line in enumerate(lines) if helper_line in line),None)
        if helper_idx is None:
            raise RuntimeError('R9 selector helper anchor missing')
        hp=lines[helper_idx][:len(lines[helper_idx])-len(lines[helper_idx].lstrip())]
        selector_raw="""def _type_selector(row) -> str:
    current = str(rv(row, 'document_type') or '')
    choices = [
        ('certificato_medico','Certificato medico'),('iscrizione','Domanda iscrizione'),
        ('manleva','Manleva'),('liberatoria_immagini','Liberatoria immagini'),
        ('documento_identita','Documento identità'),('consenso_minore','Consenso minore'),
        ('autorizzazione_genitore','Autorizzazione genitore'),('trasporto_minori','Trasporto minori'),
        ('documenti_gara','Documenti gara'),('documenti_saggio','Documenti saggio'),
        ('ricevuta_pagamento','Ricevuta / prova pagamento')
    ]
    options = ["<option value=''>— scegli tipo —</option>"]
    for value,label in choices:
        selected = ' selected' if value == current else ''
        options.append(f"<option value='{e(value)}'{selected}>{e(label)}</option>")
    button = 'Assegna tipo' if current in ('','altro') else 'Correggi tipo'
    return f"<form method='post' class='doc-type-form'>{csrf_input()}<input type='hidden' name='action' value='set_document_type'><input type='hidden' name='id' value='{int(rv(row,'id',0) or 0)}'><select name='document_type' required>{''.join(options)}</select><button class='pro-cta slim' type='submit'>{button}</button></form>"

"""
        lines.insert(helper_idx,indent_block(selector_raw,hp))
        s=''.join(lines)

        old_cell="<td>{e(rv(r, 'document_label') or rv(r, 'document_type') or 'Documento')}<div class='small-muted'>{e(document_state(r))}</div></td>"
        new_cell="<td>{e(rv(r, 'document_label') or rv(r, 'document_type') or 'Documento')}<div class='small-muted'>{e(document_state(r))}</div>{_type_selector(r)}</td>"
        if old_cell not in s:
            raise RuntimeError('R9 type cell anchor missing')
        s=s.replace(old_cell,new_cell,1)

        style_anchor="<style id='bodymind-fix39-inbound-actions'>"
        style_new="<style id='bodymind-fix39-inbound-actions'>.doc-type-form{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}.doc-type-form select{min-width:180px;max-width:240px;padding:7px 9px;border-radius:9px}"
        if style_anchor not in s:
            raise RuntimeError('R9 style anchor missing')
        s=s.replace(style_anchor,style_new,1)
        return s

    patch_file('asd_app/routes_inbound_documents.py',patch_inbound)

    def patch_tesserati(s):
        if 'BODYMIND_R9_SHEET_DOCUMENTS' in s:
            return s
        lines=s.splitlines(True)
        pay_idx=next((i for i,line in enumerate(lines) if 'pays = c.execute("SELECT COUNT(*) AS n FROM pagamenti WHERE tesserato_id=?"' in line),None)
        if pay_idx is None:
            raise RuntimeError('R9 athlete documents query anchor missing')
        pp=lines[pay_idx][:len(lines[pay_idx])-len(lines[pay_idx].lstrip())]
        docs_raw="""# BODYMIND_R9_SHEET_DOCUMENTS
document_rows = [dict(x) for x in c.execute("""
    SELECT id,titolo,categoria,original_filename,data_caricamento,data_scadenza
    FROM documenti
    WHERE tesserato_id=? AND COALESCE(visibile,1)=1
    ORDER BY COALESCE(data_caricamento,'') DESC,id DESC
    LIMIT 12
""", (tesserato_id,)).fetchall()]
if document_rows:
    parts=[]
    for dr in document_rows:
        title = dr.get('titolo') or dr.get('original_filename') or 'Documento'
        meta = ' · '.join(x for x in [str(dr.get('categoria') or ''), str(dr.get('data_caricamento') or '')[:10]] if x)
        expiry = str(dr.get('data_scadenza') or '')
        if expiry:
            meta += (' · ' if meta else '') + 'scadenza ' + expiry
        parts.append(f"<div class='bm30-doc-row'><div><b>{e(title)}</b><div class='small-muted'>{e(meta)}</div></div><a class='pro-cta slim ghost' href='/documenti/file/{int(dr.get('id') or 0)}' target='_blank'>Apri</a></div>")
    document_html = ''.join(parts)
else:
    document_html = "<div class='small-muted'>Nessun documento associato.</div>"
"""
        lines.insert(pay_idx,indent_block(docs_raw,pp))
        s=''.join(lines)

        css_anchor=".bm30-formgrid input,.bm30-formgrid textarea,.bm30-formgrid select{{width:100%;min-height:44px}}"
        css_new=css_anchor+".bm30-doc-row{{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 0;border-bottom:1px solid rgba(120,170,220,.14)}}.bm30-doc-row:last-child{{border-bottom:0}}"
        if css_anchor not in s:
            raise RuntimeError('R9 athlete css anchor missing')
        s=s.replace(css_anchor,css_new,1)

        card_anchor="<div class='card bm30-card'><div class='kicker'>Quota mese corrente</div>"
        card="<div class='card bm30-card'><div class='kicker'>Documenti associati</div>{document_html}<div style='margin-top:10px'><a class='action-pill action-docs' href='/documenti?tesserato_id={tesserato_id}'>Apri dossier completo</a></div></div>\n"
        if card_anchor not in s:
            raise RuntimeError('R9 athlete card anchor missing')
        s=s.replace(card_anchor,card+card_anchor,1)
        return s

    patch_file('asd_app/routes_tesserati.py',patch_tesserati)

    if not compileall.compile_dir(str(APP/'asd_app'),quiet=1):
        raise RuntimeError('R9 compile failed')

    if DB.exists():
        conn=sqlite3.connect(str(DB),timeout=20)
        try:
            dcols={r[1] for r in conn.execute('PRAGMA table_info(documenti)').fetchall()}
            if 'inbound_id' in dcols:
                conn.execute("""UPDATE documenti
                    SET inbound_id=COALESCE(inbound_id,(SELECT i.id FROM inbound_documents i WHERE i.tesserato_id=documenti.tesserato_id AND i.saved_path=documenti.filename ORDER BY i.id DESC LIMIT 1))
                    WHERE EXISTS(SELECT 1 FROM inbound_documents i WHERE i.tesserato_id=documenti.tesserato_id AND i.saved_path=documenti.filename)""")
            if 'doc_type' in dcols:
                conn.execute("""UPDATE documenti
                    SET doc_type=COALESCE(NULLIF(doc_type,''),(SELECT i.document_type FROM inbound_documents i WHERE i.tesserato_id=documenti.tesserato_id AND i.saved_path=documenti.filename ORDER BY i.id DESC LIMIT 1))
                    WHERE EXISTS(SELECT 1 FROM inbound_documents i WHERE i.tesserato_id=documenti.tesserato_id AND i.saved_path=documenti.filename)""")
            if 'confidence' in dcols:
                conn.execute("""UPDATE documenti
                    SET confidence=COALESCE(confidence,(SELECT i.document_confidence FROM inbound_documents i WHERE i.tesserato_id=documenti.tesserato_id AND i.saved_path=documenti.filename ORDER BY i.id DESC LIMIT 1))
                    WHERE EXISTS(SELECT 1 FROM inbound_documents i WHERE i.tesserato_id=documenti.tesserato_id AND i.saved_path=documenti.filename)""")
            if 'match_score' in dcols:
                conn.execute("""UPDATE documenti
                    SET match_score=CASE WHEN COALESCE(match_score,0)=0 THEN COALESCE((SELECT i.match_score FROM inbound_documents i WHERE i.tesserato_id=documenti.tesserato_id AND i.saved_path=documenti.filename ORDER BY i.id DESC LIMIT 1),match_score) ELSE match_score END
                    WHERE EXISTS(SELECT 1 FROM inbound_documents i WHERE i.tesserato_id=documenti.tesserato_id AND i.saved_path=documenti.filename)""")
            conn.commit()
            linked=conn.execute("SELECT COUNT(*) FROM documenti WHERE inbound_id IS NOT NULL").fetchone()[0] if 'inbound_id' in dcols else 0
            print('[autopilot-r9-backfill] linked_documenti='+str(linked),flush=True)
        finally:
            conn.close()

    inbound=(APP/'asd_app/routes_inbound_documents.py').read_text(encoding='utf-8')
    tess=(APP/'asd_app/routes_tesserati.py').read_text(encoding='utf-8')
    checks={
        'manual-type':'BODYMIND_R9_MANUAL_TYPE' in inbound,
        'type-selector':'Assegna tipo' in inbound and 'Correggi tipo' in inbound,
        'document-file-route':"/documenti/file/<int:doc_id>" in inbound,
        'sheet-documents':'BODYMIND_R9_SHEET_DOCUMENTS' in tess and 'Documenti associati' in tess,
    }
    failed=[k for k,v in checks.items() if not v]
    if failed:
        raise RuntimeError('R9 selftest failed: '+repr(failed))
    MARKER.write_text('BodyMind Autopilot R9 manual type + athlete document visibility applied\n',encoding='utf-8')
    print('[autopilot-r9] applied',flush=True)
    print('[autopilot-r9-selftest] PASS manual-type selector document-file-route athlete-sheet-documents metadata-backfill',flush=True)
else:
    print('[autopilot-r9] already applied',flush=True)
