from __future__ import annotations
from pathlib import Path
import shutil, compileall

APP = Path('/data/top2_app')
MARKER = APP / '.BODYMIND_AUTOPILOT_R3'
BACKUPS = Path('/data/release_backups/20260926_autopilot_r3')

def backup(rel: str):
    src = APP / rel
    dst = BACKUPS / rel
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

def mutate(rel: str, fn):
    p = APP / rel
    if not p.exists():
        raise RuntimeError(f'missing target: {rel}')
    old = p.read_text(encoding='utf-8')
    new = fn(old)
    if new != old:
        backup(rel)
        p.write_text(new, encoding='utf-8')

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

if not MARKER.exists():
    BACKUPS.mkdir(parents=True, exist_ok=True)

    def patch_matcher(s: str) -> str:
        if "nome e cognome esatti e univoci nel documento" in s or "AUTOPILOT R3 exact full-name identity" in s:
            return s
        anchor = """    scored.sort(key=lambda x: x["score"], reverse=True)
    best = scored[0] if scored else {"row": None, "score": 0, "reasons": []}
"""
        block = '''    # AUTOPILOT R3 exact full-name identity: extracted/OCR text is authoritative
    # for association only when the full name identifies one athlete uniquely.
    hay_norm = _norm(text or "")
    exact_full = []
    for idx, item in enumerate(scored):
        r = item.get("row")
        nome = _val(r, "nome")
        cognome = _val(r, "cognome")
        full = _norm(f"{nome} {cognome}")
        rev = _norm(f"{cognome} {nome}")
        if nome and cognome and ((full and full in hay_norm) or (rev and rev in hay_norm)):
            exact_full.append(idx)
    if len(exact_full) == 1:
        item = scored[exact_full[0]]
        if int(item.get("score") or 0) < 92:
            item["score"] = 92
            item.setdefault("reasons", []).append("nome e cognome esatti e univoci nel documento")

    scored.sort(key=lambda x: x["score"], reverse=True)
    best = scored[0] if scored else {"row": None, "score": 0, "reasons": []}
'''
        if anchor not in s:
            raise RuntimeError("R3 anchor athlete matcher not found")
        return s.replace(anchor, block, 1)

    mutate('asd_app/athlete_matcher.py', patch_matcher)

    def patch_email(s: str) -> str:
        if "identity_certain = (match_result.get('action') == 'auto_save'" not in s:
            old = '''            # Sicurezza: serve match tesserato forte E tipo documento abbastanza chiaro.
            # Se il tesserato è certo ma il documento è ambiguo, non lo infiliamo nella scheda: va confermato.
            can_auto_save = (match_result.get('action') == 'auto_save' and doc_conf >= 60 and doc_area != 'unknown')
            tesserato_id = int(row['id']) if row is not None and can_auto_save else None
        if tesserato_id:
            status = 'pagamento_da_verificare' if doc_area == 'pagamenti' else 'associato'
        else:
            status = 'richiede_conferma' if match_result.get('action') in ('auto_save', 'confirm') else 'needs_manual_match'
'''
            new = '''            # AUTOPILOT R3: identita atleta e tipo documento sono due certezze distinte.
            identity_certain = (match_result.get('action') == 'auto_save' and row is not None)
            type_certain = (doc_conf >= 60 and doc_area != 'unknown')
            tesserato_id = int(row['id']) if identity_certain else None
            if identity_certain and not type_certain:
                classification = dict(classification)
                classification['type_needs_review'] = True
                classification['identity_confirmed'] = True
                classification['identity_score'] = int(best.get('score') or 0)
        if tesserato_id:
            if doc_area == 'pagamenti':
                status = 'pagamento_da_verificare'
            elif classification.get('type_needs_review'):
                status = 'associato_tipo_da_verificare'
            else:
                status = 'associato'
        else:
            status = 'richiede_conferma' if match_result.get('action') == 'confirm' else 'needs_manual_match'
'''
            if old not in s:
                raise RuntimeError('R3 anchor process_inbound_attachment not found')
            s = s.replace(old, new, 1)

        oldret = "return {'status': status, 'tesserato_id': tesserato_id, 'saved': str(saved), 'classification': classification, 'match': {'action': match_result.get('action'), 'score': int(best.get('score') or 0), 'reasons': best.get('reasons') or []}, 'medical_dates': medical_dates, 'medical_sync': medical_sync, 'payment': payment}"
        newret = "return {'status': status, 'inbound_id': inbound_id, 'tesserato_id': tesserato_id, 'saved': str(saved), 'classification': classification, 'match': {'action': match_result.get('action'), 'score': int(best.get('score') or 0), 'reasons': best.get('reasons') or []}, 'medical_dates': medical_dates, 'medical_sync': medical_sync, 'payment': payment}"
        if oldret in s:
            s = s.replace(oldret, newret, 1)

        s = s.replace("'pagamento_da_verificare': 'Associato · pagamento da verificare',", "'pagamento_da_verificare': 'Associato · pagamento da verificare',\n                'associato_tipo_da_verificare': 'Atleta associata · tipo documento da verificare',")
        if "'inbound_id': processed.get('inbound_id')," not in s:
            s = s.replace("'filename': filename,\n                'status': status,", "'filename': filename,\n                'inbound_id': processed.get('inbound_id'),\n                'status': status,", 1)
        if "'document_confidence_label': classification.get('confidence_label') or ''," not in s:
            s = s.replace("'document_confidence': int(classification.get('confidence') or 0),", "'document_confidence': int(classification.get('confidence') or 0),\n                'document_confidence_label': classification.get('confidence_label') or '',", 1)
        if "'document_type_needs_review': bool(classification.get('type_needs_review'))," not in s:
            s = s.replace("'match_score': int(match.get('score') or 0),", "'document_type_needs_review': bool(classification.get('type_needs_review')),\n                'match_score': int(match.get('score') or 0),", 1)
        s = s.replace("if status == 'associato' or status == 'pagamento_da_verificare':", "if status in ('associato', 'associato_tipo_da_verificare', 'pagamento_da_verificare'):")
        return s

    mutate('asd_app/routes_email_documents.py', patch_email)

    def patch_mobile(s: str) -> str:
        if '.confirm-link{' not in s:
            s = s.replace('.tip{font-size:12px;color:#64748b;margin-top:10px}', '.tip{font-size:12px;color:#64748b;margin-top:10px}.confirm-link{display:inline-flex;margin-top:10px;padding:10px 12px;border-radius:12px;background:#0b5bd3;color:#fff;text-decoration:none;font-size:12px;font-weight:850}')

        s = s.replace("html+=badge((d.document_label||d.document_type)+(d.document_confidence?' · '+d.document_confidence+'%':''));", "html+=badge('Tipo documento: '+(d.document_label||d.document_type)+(d.document_confidence?' · '+d.document_confidence+'%':'')+(d.document_confidence_label?' · '+d.document_confidence_label:''), d.document_confidence>=60?'':'warn');")
        s = s.replace("html+='<div class=\"kv\"><span>Match</span><b>'+esc(d.match_score?d.match_score+'%':'—')+'</b></div>';", "html+='<div class=\"kv\"><span>Identità atleta</span><b>'+esc(d.match_score?d.match_score+'%':'—')+'</b></div>';")

        old = "   html+='</div></article>'; return html;"
        new = """   html+='</div>';
   if(d.status==='associato_tipo_da_verificare') html+='<div class="tip"><b>Atleta associata automaticamente.</b> Il '+esc(d.document_confidence||'—')+'% riguarda solo il tipo di documento, che puoi classificare in seguito.</div>';
   if(d.status==='richiede_conferma' && d.inbound_id) html+='<a class="confirm-link" href="/documenti-automatici#doc-'+encodeURIComponent(d.inbound_id)+'">Conferma associazione</a>';
   if(d.status==='needs_manual_match') html+='<a class="confirm-link" href="/documenti-automatici#docs">Apri Documenti automatici</a>';
   html+='</article>'; return html;"""
        if old in s:
            s = s.replace(old, new, 1)
        elif 'Atleta associata automaticamente.' not in s:
            raise RuntimeError('R3 anchor mobile detailCard not found')
        return s

    mutate('asd_app/routes_bodymind_fix49.py', patch_mobile)

    def patch_inbound(s: str) -> str:
        if "'associato_tipo_da_verificare': 'Associato atleta · tipo da verificare'," not in s:
            s = s.replace("'associato': 'Associato automatico',", "'associato': 'Associato automatico',\n    'associato_tipo_da_verificare': 'Associato atleta · tipo da verificare',", 1)
        s = s.replace("tone = tone or ('ok' if text in ('associato','paid','pagamento_completato')", "tone = tone or ('ok' if text in ('associato','associato_tipo_da_verificare','paid','pagamento_completato')")
        s = s.replace("SUM(CASE WHEN status='associato' THEN 1 ELSE 0 END) AS associati,", "SUM(CASE WHEN status IN ('associato','associato_tipo_da_verificare') THEN 1 ELSE 0 END) AS associati,")
        if "<tr id='doc-{int(rv(r, 'id', 0) or 0)}'>" not in s:
            s = s.replace("    doc_rows = ''.join(f\"\"\"\n        <tr>", "    doc_rows = ''.join(f\"\"\"\n        <tr id='doc-{int(rv(r, 'id', 0) or 0)}'>", 1)
        return s

    mutate('asd_app/routes_inbound_documents.py', patch_inbound)

    ok = compileall.compile_dir(str(APP / 'asd_app'), quiet=1)
    if not ok:
        raise RuntimeError('Autopilot R3 compile failed')
    MARKER.write_text('BodyMind Autopilot R3 applied\n', encoding='utf-8')
    print('[autopilot-r3] applied', flush=True)
else:
    print('[autopilot-r3] already applied', flush=True)
