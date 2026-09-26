from __future__ import annotations
from pathlib import Path
from collections import defaultdict
from io import BytesIO
import compileall, importlib.util, inspect, shutil, sys

APP = Path('/data/top2_app')
MARKER = APP / '.BODYMIND_AUTOPILOT_R5'
BACKUPS = Path('/data/release_backups/20260926_autopilot_r5')

def backup(rel: str):
    src = APP / rel
    dst = BACKUPS / rel
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

def mutate(rel: str, fn):
    p = APP / rel
    if not p.exists():
        raise RuntimeError(f'missing R5 target: {rel}')
    old = p.read_text(encoding='utf-8')
    new = fn(old)
    if new != old:
        backup(rel)
        p.write_text(new, encoding='utf-8')

def replace_once(s: str, old: str, new: str, label: str) -> str:
    if new in s:
        return s
    if old not in s:
        raise RuntimeError(f'R5 anchor missing: {label}')
    return s.replace(old, new, 1)

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

if not MARKER.exists():
    BACKUPS.mkdir(parents=True, exist_ok=True)

    def patch_matcher(s: str) -> str:
        old = '''    if len(exact_indexes) == 1:
        item = scored[exact_indexes[0]]
        if int(item.get("score") or 0) < 92:
            item["score"] = 92
            item.setdefault("reasons", []).append("nome e cognome esatti e univoci nel documento")
'''
        new = '''    if len(exact_indexes) == 1:
        item = scored[exact_indexes[0]]
        if int(item.get("score") or 0) < 92:
            item["score"] = 92
        if "nome e cognome esatti e univoci nel documento" not in item.setdefault("reasons", []):
            item["reasons"].append("nome e cognome esatti e univoci nel documento")
'''
        s = replace_once(s, old, new, 'exact identity reason')

        old2 = '''        if n and c and n.issubset(words) and c.issubset(words) and int(item.get("score") or 0) < 78:
            item["score"] = 78
            item.setdefault("reasons", []).append("nome e cognome presenti nel testo")
'''
        new2 = '''        if n and c and n.issubset(words) and c.issubset(words):
            if int(item.get("score") or 0) < 78:
                item["score"] = 78
            if "nome e cognome presenti nel testo" not in item.setdefault("reasons", []):
                item["reasons"].append("nome e cognome presenti nel testo")
'''
        s = replace_once(s, old2, new2, 'separate identity reason')

        old3 = '''    # evita auto-match se due persone sono troppo vicine
    if score >= 90 and score - second >= 12:
        action = "auto_save"
    elif score >= 60:
        action = "confirm"
    else:
        action = "review"
'''
        new3 = '''    # AUTOPILOT R5: il nome+cognome completi, presenti nel testo e univoci
    # nell'anagrafica sono una prova identitaria autonoma dal TIPO documento.
    reasons = set(best.get("reasons") or [])
    exact_unique_identity = (
        score >= 92 and
        "nome e cognome esatti e univoci nel documento" in reasons
    )
    # La regola del margine resta per tutti gli altri segnali.
    if exact_unique_identity:
        action = "auto_save"
    elif score >= 90 and score - second >= 12:
        action = "auto_save"
    elif score >= 60:
        action = "confirm"
    else:
        action = "review"
'''
        return replace_once(s, old3, new3, 'identity decision')
    mutate('asd_app/athlete_matcher.py', patch_matcher)

    def patch_classifier(s: str) -> str:
        old = '''    if cm_filename_hint:
        scores["certificato_medico"] = max(scores.get("certificato_medico", 0), 50)
        hits.setdefault("certificato_medico", []).append("CM (certificato medico)")

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
'''
        new = '''    if cm_filename_hint:
        scores["certificato_medico"] = max(scores.get("certificato_medico", 0), 50)
        hits.setdefault("certificato_medico", []).append("CM (certificato medico)")

    # AUTOPILOT R5: una intestazione medica esplicita nel testo estratto/OCR
    # non deve ricadere nel fallback 45%. Manteniamo una soglia prudente:
    # vale come segnale forte, ma una reale ambiguita con un altro tipo resta da verificare.
    extracted_clean = _clean(extracted_text or "")
    medical_text_hint = bool(
        re.search(r"\bcertificat\w*\s+medic\w*\b", extracted_clean)
        or (
            re.search(r"\bcertificat\w*\s+(?:di\s+)?idoneit\w*", extracted_clean)
            and ("sportiv" in extracted_clean or "attivit" in extracted_clean)
        )
    )
    if medical_text_hint:
        scores["certificato_medico"] = max(scores.get("certificato_medico", 0), 40)
        hits.setdefault("certificato_medico", []).append("intestazione medica esplicita nel documento")

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
'''
        return replace_once(s, old, new, 'digital medical classifier')
    mutate('asd_app/document_classifier.py', patch_classifier)

    def patch_processing(s: str) -> str:
        old = '''            identity_certain = (match_result.get('action') == 'auto_save' and row is not None)
            type_certain = (doc_conf >= 60 and doc_area != 'unknown')
            tesserato_id = int(row['id']) if identity_certain else None
            if identity_certain and not type_certain:
                classification = dict(classification)
                classification['type_needs_review'] = True
                classification['identity_confirmed'] = True
                classification['identity_score'] = int(best.get('score') or 0)
'''
        new = '''            match_score = int(best.get('score') or 0)
            identity_reasons = set(best.get('reasons') or [])
            exact_unique_identity = (
                row is not None and
                match_score >= 92 and
                'nome e cognome esatti e univoci nel documento' in identity_reasons
            )
            identity_certain = (
                row is not None and
                (match_result.get('action') == 'auto_save' or exact_unique_identity)
            )
            identity_confirmable = (
                row is not None and
                (match_result.get('action') == 'confirm' or match_score >= 78)
            )
            type_certain = (doc_conf >= 60 and doc_area != 'unknown')
            tesserato_id = int(row['id']) if identity_certain else None
            classification = dict(classification)
            classification['document_state'] = 'recognized' if type_certain else 'confirm'
            classification['identity_state'] = (
                'recognized' if identity_certain
                else ('confirm' if identity_confirmable else 'review')
            )
            classification['identity_score'] = match_score
            if identity_certain and not type_certain:
                classification['type_needs_review'] = True
                classification['identity_confirmed'] = True
'''
        s = replace_once(s, old, new, 'separate type and identity state')
        s = s.replace(
            "status = 'richiede_conferma' if match_result.get('action') == 'confirm' else 'needs_manual_match'",
            "status = 'richiede_conferma' if identity_confirmable else 'needs_manual_match'",
            1
        )
        oldout = """                'document_confidence_label': classification.get('confidence_label') or '',
                'document_type_needs_review': bool(classification.get('type_needs_review')),
                'match_score': int(match.get('score') or 0),
"""
        newout = """                'document_confidence_label': classification.get('confidence_label') or '',
                'document_state_label': 'Documento riconosciuto' if classification.get('document_state') == 'recognized' else 'Documento da confermare',
                'document_type_needs_review': bool(classification.get('type_needs_review')),
                'identity_state_label': (
                    'Identità atleta riconosciuta' if classification.get('identity_state') == 'recognized'
                    else ('Identità atleta da confermare' if classification.get('identity_state') == 'confirm' else 'Identità atleta non riconosciuta')
                ),
                'match_score': int(match.get('score') or 0),
"""
        return replace_once(s, oldout, newout, 'autopilot response states')
    mutate('asd_app/routes_email_documents.py', patch_processing)

    def patch_mobile(s: str) -> str:
        old = """   if(d.document_label||d.document_type) html+=badge('Tipo documento: '+(d.document_label||d.document_type)+(d.document_confidence?' · '+d.document_confidence+'%':'')+(d.document_confidence_label?' · '+d.document_confidence_label:''), d.document_confidence>=60?'':'warn');
"""
        new = """   if(d.document_label||d.document_type){ const ds=d.document_state_label||(d.document_confidence>=60?'Documento riconosciuto':'Documento da confermare'); html+=badge(ds+': '+(d.document_label||d.document_type)+(d.document_confidence?' · '+d.document_confidence+'%':'')+(d.document_confidence_label?' · '+d.document_confidence_label:''), d.document_confidence>=60?'':'warn'); }
"""
        s = replace_once(s, old, new, 'mobile document state')
        old2 = """   html+='<div class="kv"><span>Identità atleta</span><b>'+esc(d.match_score?d.match_score+'%':'—')+'</b></div>';
"""
        new2 = """   { const ids=d.identity_state_label||(d.status==='richiede_conferma'?'Identità atleta da confermare':(d.match_score>=92?'Identità atleta riconosciuta':'Identità atleta non riconosciuta')); html+='<div class="kv"><span>Identità atleta</span><b>'+esc(ids)+(d.match_score?' · '+esc(d.match_score)+'%':'')+'</b></div>'; }
"""
        return replace_once(s, old2, new2, 'mobile identity state')
    mutate('asd_app/routes_bodymind_fix49.py', patch_mobile)

    def patch_desktop(s: str) -> str:
        s = s.replace("'associato': 'Associato automatico',", "'associato': 'Documento riconosciuto · identità atleta riconosciuta',", 1)
        s = s.replace("'associato_tipo_da_verificare': 'Associato atleta · tipo da verificare',", "'associato_tipo_da_verificare': 'Identità atleta riconosciuta · documento da confermare',", 1)
        s = s.replace("'richiede_conferma': 'Richiede conferma',", "'richiede_conferma': 'Identità atleta da confermare',", 1)
        s = s.replace("'needs_manual_match': 'Match manuale necessario',", "'needs_manual_match': 'Identità atleta non riconosciuta · verifica manuale',", 1)
        return s
    mutate('asd_app/routes_inbound_documents.py', patch_desktop)

    if not compileall.compile_dir(str(APP / 'asd_app'), quiet=1):
        raise RuntimeError('Autopilot R5 compile failed')

    # Functional self-tests. Synthetic only: no production DB reads or writes.
    def load_module(name: str, path: Path):
        spec = importlib.util.spec_from_file_location(name, str(path))
        if spec is None or spec.loader is None:
            raise RuntimeError(f'cannot load {name}')
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod

    matcher = load_module('bodymind_r5_matcher_test', APP / 'asd_app/athlete_matcher.py')
    classifier = load_module('bodymind_r5_classifier_test', APP / 'asd_app/document_classifier.py')
    med = load_module('bodymind_r5_medical_test', APP / 'asd_app/medical_certificate_dates.py')

    def row(**kw):
        d = defaultdict(str)
        d.update(kw)
        return d

    rows = [
        row(id=900001, nome='Anna', cognome='Rossi'),
        row(id=900002, nome='Beatrice', cognome='Verdi'),
    ]
    exact = matcher.match_athlete(rows, 'CERTIFICATO MEDICO Anna Rossi idoneita sportiva', '', filename='documento.pdf')
    if exact.get('action') != 'auto_save' or int((exact.get('best') or {}).get('score') or 0) < 92:
        raise RuntimeError(f"R5 selftest exact identity failed: {exact.get('action')} / {(exact.get('best') or {}).get('score')}")

    separate = matcher.match_athlete(rows, 'NOME Anna sezione anagrafica COGNOME Rossi', '', filename='documento.pdf')
    if int((separate.get('best') or {}).get('score') or 0) < 78 or separate.get('action') == 'review':
        raise RuntimeError(f"R5 selftest separate identity failed: {separate.get('action')} / {(separate.get('best') or {}).get('score')}")

    compact_rows = [
        row(id=900003, nome='Lia', cognome='Di Nicola'),
        row(id=900004, nome='Marta', cognome='Bianchi'),
    ]
    compact = matcher.match_athlete(compact_rows, '', '', filename='20260926_CM_DiNicola.pdf')
    if compact.get('action') != 'auto_save' or int((compact.get('best') or {}).get('score') or 0) < 92:
        raise RuntimeError(f"R5 selftest compact surname failed: {compact.get('action')} / {(compact.get('best') or {}).get('score')}")

    ambiguous_rows = [
        row(id=900005, nome='Anna', cognome='Rossi'),
        row(id=900006, nome='Clara', cognome='Rossi'),
    ]
    ambiguous = matcher.match_athlete(ambiguous_rows, '', '', filename='CM_Rossi.pdf')
    if ambiguous.get('action') == 'auto_save':
        raise RuntimeError('R5 selftest ambiguous surname auto-saved unexpectedly')

    # Real digital-PDF path: embedded text must be used before OCR.
    from reportlab.pdfgen import canvas
    pdfbuf = BytesIO()
    c = canvas.Canvas(pdfbuf)
    c.drawString(72, 760, 'CERTIFICATO MEDICO')
    c.drawString(72, 735, 'Anna Rossi - idoneita alla pratica sportiva')
    c.save()
    original_ocr = med._ocr_pdf
    def _ocr_must_not_run(*args, **kwargs):
        raise RuntimeError('OCR called for digital PDF')
    med._ocr_pdf = _ocr_must_not_run
    try:
        digital_text = med.extract_attachment_text('documento.pdf', pdfbuf.getvalue())
    finally:
        med._ocr_pdf = original_ocr
    if 'CERTIFICATO MEDICO' not in digital_text.upper():
        raise RuntimeError('R5 selftest digital PDF extraction failed')

    default_pages = inspect.signature(med._ocr_pdf).parameters['max_pages'].default
    if int(default_pages) < 3:
        raise RuntimeError(f'R5 selftest OCR pages failed: {default_pages}')

    doc = classifier.classify_document(filename='documento.pdf', extracted_text=digital_text)
    if doc.get('type') != 'certificato_medico' or int(doc.get('confidence') or 0) < 80:
        raise RuntimeError(f"R5 selftest digital classifier failed: {doc.get('type')} / {doc.get('confidence')}")

    mobile_src = (APP / 'asd_app/routes_bodymind_fix49.py').read_text(encoding='utf-8')
    desktop_src = (APP / 'asd_app/routes_inbound_documents.py').read_text(encoding='utf-8')
    for label in ('Documento riconosciuto', 'Documento da confermare', 'Identità atleta riconosciuta', 'Identità atleta da confermare'):
        if label not in mobile_src and label not in desktop_src:
            raise RuntimeError(f'R5 selftest UI label missing: {label}')

    print(
        '[autopilot-r5] selftest ok '
        f"exact={exact.get('action')}/{int((exact.get('best') or {}).get('score') or 0)} "
        f"separate={separate.get('action')}/{int((separate.get('best') or {}).get('score') or 0)} "
        f"compact={compact.get('action')}/{int((compact.get('best') or {}).get('score') or 0)} "
        f"ambiguous={ambiguous.get('action')}/{int((ambiguous.get('best') or {}).get('score') or 0)} "
        f"digital_pdf=no_ocr type={doc.get('type')}/{int(doc.get('confidence') or 0)} ocr_pages={default_pages}",
        flush=True,
    )

    MARKER.write_text('BodyMind Autopilot R5 applied and self-tested\n', encoding='utf-8')
    print('[autopilot-r5] applied', flush=True)
else:
    print('[autopilot-r5] already applied', flush=True)
