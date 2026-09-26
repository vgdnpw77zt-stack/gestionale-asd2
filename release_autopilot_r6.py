from __future__ import annotations
from pathlib import Path
import shutil, compileall, importlib.util, inspect, io

APP = Path('/data/top2_app')
MARKER = APP / '.BODYMIND_AUTOPILOT_R6'
BACKUPS = Path('/data/release_backups/20260926_autopilot_r6')

def backup(rel: str):
    src = APP / rel
    dst = BACKUPS / rel
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

def mutate(rel: str, fn):
    p = APP / rel
    if not p.exists():
        raise RuntimeError(f'missing R6 target: {rel}')
    old = p.read_text(encoding='utf-8')
    new = fn(old)
    if new != old:
        backup(rel)
        p.write_text(new, encoding='utf-8')

def req_replace(s: str, old: str, new: str, label: str) -> str:
    if new in s:
        return s
    if old not in s:
        raise RuntimeError(f'R6 anchor missing: {label}')
    return s.replace(old, new, 1)

if not APP.joinpath('.TOP2_OFFICIAL').exists():
    raise SystemExit('TOP2_OFFICIAL marker missing')

if not MARKER.exists():
    BACKUPS.mkdir(parents=True, exist_ok=True)

    def patch_matcher(s: str) -> str:
        s = req_replace(
            s,
            '    file_hay, _file_compact = _filename_identity_hay(filename)\n    file_words = set(file_hay.split())\n',
            '    file_hay, _file_compact = _filename_identity_hay(filename)\n    file_tokens = file_hay.split()\n    file_words = set(file_tokens)\n',
            'ordered filename tokens',
        )
        old = '        file_compact_words = {_compact(w) for w in file_words if w}\n'
        new = '''        # AUTOPILOT R6: ricostruisci anche n-grammi compatti mantenendo l'ordine.
        # "Di Nicola" -> "dinicola", "D Angelo" -> "dangelo".
        file_compact_words = {_compact(w) for w in file_words if w}
        for i in range(len(file_tokens)):
            for j in range(i + 2, min(len(file_tokens), i + 6) + 1):
                phrase = _compact(" ".join(file_tokens[i:j]))
                if phrase:
                    file_compact_words.add(phrase)
'''
        s = req_replace(s, old, new, 'compound filename surname')

        old2 = '    hay_norm = _norm(text or "")\n    exact_indexes: list[int] = []\n'
        new2 = '''    hay_norm = _norm(text or "")
    hay_tokens = hay_norm.split()
    # R6: n-grammi compatti del testo per OCR/sanitizzazioni (D'Angelo -> DANGELO).
    hay_compact_phrases: set[str] = set()
    for i in range(len(hay_tokens)):
        for j in range(i + 1, min(len(hay_tokens), i + 6) + 1):
            phrase = _compact(" ".join(hay_tokens[i:j]))
            if phrase:
                hay_compact_phrases.add(phrase)
    exact_indexes: list[int] = []
'''
        s = req_replace(s, old2, new2, 'compact text phrases')

        old3 = '''        full = _norm(f"{nome} {cognome}")
        rev = _norm(f"{cognome} {nome}")
        if nome and cognome and ((full and full in hay_norm) or (rev and rev in hay_norm)):
            exact_indexes.append(idx)
'''
        new3 = '''        full = _norm(f"{nome} {cognome}")
        rev = _norm(f"{cognome} {nome}")
        full_compact = _compact(f"{nome} {cognome}")
        rev_compact = _compact(f"{cognome} {nome}")
        exact_phrase = (full and full in hay_norm) or (rev and rev in hay_norm)
        compact_phrase = (
            (full_compact and full_compact in hay_compact_phrases) or
            (rev_compact and rev_compact in hay_compact_phrases)
        )
        if nome and cognome and (exact_phrase or compact_phrase):
            exact_indexes.append(idx)
'''
        s = req_replace(s, old3, new3, 'compact exact full name')
        return s

    mutate('asd_app/athlete_matcher.py', patch_matcher)

    def patch_mobile(s: str) -> str:
        old_doc = "if(d.document_label||d.document_type) html+=badge('Tipo documento: '+(d.document_label||d.document_type)+(d.document_confidence?' · '+d.document_confidence+'%':'')+(d.document_confidence_label?' · '+d.document_confidence_label:''), d.document_confidence>=60?'':'warn');"
        new_doc = "if(d.document_label||d.document_type){const docState=(d.document_type_needs_review||Number(d.document_confidence||0)<60)?'Tipo documento da confermare':'Documento riconosciuto';html+=badge(docState+': '+(d.document_label||d.document_type)+(d.document_confidence?' · '+d.document_confidence+'%':''),Number(d.document_confidence||0)>=60&&!d.document_type_needs_review?'':'warn');}"
        s = req_replace(s, old_doc, new_doc, 'mobile document state')
        old_id = "html+='<div class=\"kv\"><span>Identità atleta</span><b>'+esc(d.match_score?d.match_score+'%':'—')+'</b></div>';"
        new_id = "const identityState=d.match_action==='auto_save'?'Identità atleta riconosciuta':(d.match_action==='confirm'?'Da confermare':'Identità atleta da verificare');html+='<div class=\"kv\"><span>'+esc(identityState)+'</span><b>'+esc(d.match_score?d.match_score+'%':'—')+'</b></div>';"
        s = req_replace(s, old_id, new_id, 'mobile identity state')
        return s

    mutate('asd_app/routes_bodymind_fix49.py', patch_mobile)

    def patch_desktop(s: str) -> str:
        old_helpers = '''    def person_name(row) -> str:
        return (((rv(row, 'nome') or '') + ' ' + (rv(row, 'cognome') or '')).strip() or '-')

    def _post_button(label: str, action: str, doc_id: int, cls: str = 'pro-cta slim', confirm: str = '') -> str:
'''
        new_helpers = '''    def person_name(row) -> str:
        return (((rv(row, 'nome') or '') + ' ' + (rv(row, 'cognome') or '')).strip() or '-')

    def document_state(row) -> str:
        confidence = int(rv(row, 'document_confidence', 0) or 0)
        doc_type = str(rv(row, 'document_type') or '')
        if confidence >= 60 and doc_type not in ('', 'altro'):
            return f'Documento riconosciuto · {confidence}%'
        if confidence in (20, 25):
            return f'Tipo documento non riconosciuto · {confidence}%'
        return f'Tipo documento da confermare · {confidence}%'

    def identity_state(row) -> str:
        score = int(rv(row, 'match_score', 0) or 0)
        action = str(rv(row, 'match_action') or '')
        if action == 'auto_save':
            return f'Identità atleta riconosciuta · {score}%'
        if action == 'confirm':
            return f'Da confermare · {score}%'
        return f'Identità atleta da verificare · {score}%'

    def _post_button(label: str, action: str, doc_id: int, cls: str = 'pro-cta slim', confirm: str = '') -> str:
'''
        s = req_replace(s, old_helpers, new_helpers, 'desktop helper states')
        s = req_replace(
            s,
            "<td>{e(rv(r, 'document_label') or rv(r, 'document_type') or 'Documento')}<div class='small-muted'>Confidenza tipo: {int(rv(r, 'document_confidence', 0) or 0)}%</div></td>",
            "<td>{e(rv(r, 'document_label') or rv(r, 'document_type') or 'Documento')}<div class='small-muted'>{e(document_state(r))}</div></td>",
            'desktop document row',
        )
        s = req_replace(
            s,
            "<td><div class='a34-score'><span style='width:{max(3,min(100,int(rv(r, 'match_score', 0) or 0)))}%'></span></div><b>{int(rv(r, 'match_score', 0) or 0)}%</b><div class='small-muted'>{e(rv(r, 'match_action') or '')}</div></td>",
            "<td><div class='a34-score'><span style='width:{max(3,min(100,int(rv(r, 'match_score', 0) or 0)))}%'></span></div><b>{int(rv(r, 'match_score', 0) or 0)}%</b><div class='small-muted'>{e(identity_state(r))}</div></td>",
            'desktop identity row',
        )
        s = s.replace("<th>Tipo</th><th>Tesserato</th><th>Match</th>", "<th>Tipo documento</th><th>Tesserato</th><th>Identità atleta</th>", 1)
        s = s.replace("<b>Riconoscimento</b><span>Il sistema legge tipo documento e confidenza.</span>", "<b>Tipo documento</b><span>Il sistema riconosce il tipo documento con una confidenza separata dall'identità.</span>", 1)
        s = s.replace("<b>Matching</b><span>ASDRET, CF, nome, email, nascita e genitore guidano l'abbinamento.</span>", "<b>Identità atleta</b><span>ASDRET, CF, nome, email, nascita e genitore guidano l'abbinamento.</span>", 1)
        s = s.replace("<span>Associati automatici</span><small>Match ≥ 90%</small>", "<span>Identità riconosciuta</span><small>Identità ≥ 90%</small>", 1)
        s = s.replace("<span>Da confermare</span><small>Match 60–89%</small>", "<span>Identità da confermare</span><small>Identità 60–89%</small>", 1)
        s = s.replace("<span>Da verificare</span><small>Match &lt; 60%</small>", "<span>Identità da verificare</span><small>Identità &lt; 60%</small>", 1)
        s = s.replace("<li><b>2. Classificazione</b><span>Manleva, certificato medico, liberatoria immagini, documento identità o iscrizione.</span></li>", "<li><b>2. Tipo documento</b><span>Manleva, certificato medico, liberatoria immagini, documento identità o iscrizione.</span></li>", 1)
        s = s.replace("<li><b>3. Matching</b><span>CF, nome+cognome, email, data nascita e genitore/tutore.</span></li>", "<li><b>3. Identità atleta</b><span>CF, nome+cognome, email, data nascita e genitore/tutore.</span></li>", 1)
        s = s.replace("Qui vedi tutto il flusso: documento ricevuto, riconoscimento tipo, matching tesserato, salvataggio, pagamento iscrizione e log tecnico. Non devi più andare a tentativi.", "Qui vedi tutto il flusso. Tipo documento e identità atleta sono valutazioni separate: un 45% sul tipo non significa che il nome non sia stato letto.", 1)
        return s

    mutate('asd_app/routes_inbound_documents.py', patch_desktop)

    if not compileall.compile_dir(str(APP / 'asd_app'), quiet=1):
        raise RuntimeError('Autopilot R6 compile failed')

    def load_module(rel: str, name: str):
        spec = importlib.util.spec_from_file_location(name, APP / rel)
        if spec is None or spec.loader is None:
            raise RuntimeError(f'cannot load {rel}')
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    matcher = load_module('asd_app/athlete_matcher.py', '_bodymind_r6_matcher')
    classifier = load_module('asd_app/document_classifier.py', '_bodymind_r6_classifier')

    base = [
        {'id': 1, 'nome': 'Mario', 'cognome': 'Rossi'},
        {'id': 2, 'nome': 'Giulia', 'cognome': 'Verdi'},
    ]
    r = matcher.match_athlete(base, 'CERTIFICATO MEDICO SPORTIVO Mario Rossi idoneita', filename='certificato.pdf')
    assert r['action'] == 'auto_save' and int(r['best']['score']) >= 92, r
    r = matcher.match_athlete(base, 'Nome: Mario -- sezione -- Cognome: Rossi', filename='documento.pdf')
    assert r['action'] == 'confirm' and int(r['best']['score']) >= 78, r

    compound = [
        {'id': 3, 'nome': 'Elena', 'cognome': 'Di Nicola'},
        {'id': 4, 'nome': 'Paola', 'cognome': 'Bianchi'},
    ]
    r = matcher.match_athlete(compound, 'certificato medico sportivo', filename='20260926 CM Di Nicola.pdf')
    assert r['action'] == 'auto_save' and int(r['best']['score']) >= 92, r
    r = matcher.match_athlete(compound, 'certificato medico sportivo', filename='20260926_CM_DiNicola.pdf')
    assert r['action'] == 'auto_save' and int(r['best']['score']) >= 92, r

    apostrophe = [
        {'id': 5, 'nome': 'Anna', 'cognome': "D'Angelo"},
        {'id': 6, 'nome': 'Laura', 'cognome': 'Neri'},
    ]
    r = matcher.match_athlete(apostrophe, 'CERTIFICATO MEDICO ANNA DANGELO IDONEITA SPORTIVA', filename='scan.pdf')
    assert r['action'] == 'auto_save' and int(r['best']['score']) >= 92, r

    ambiguous = [
        {'id': 7, 'nome': 'Anna', 'cognome': 'Di Nicola'},
        {'id': 8, 'nome': 'Sara', 'cognome': 'Di Nicola'},
    ]
    r = matcher.match_athlete(ambiguous, 'certificato medico', filename='CM Di Nicola.pdf')
    assert r['action'] != 'auto_save', r

    c = classifier.classify_document(filename='scan.pdf', extracted_text='CERTIFICATO MEDICO SPORTIVO NON AGONISTICO IDONEITA SPORTIVA')
    assert c.get('type') == 'certificato_medico' and int(c.get('confidence') or 0) >= 60, c

    med = load_module('asd_app/medical_certificate_dates.py', '_bodymind_r6_med')
    assert inspect.signature(med._ocr_pdf).parameters['max_pages'].default >= 3
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    cv = canvas.Canvas(buf)
    cv.drawString(72, 760, 'CERTIFICATO MEDICO SPORTIVO MARIO ROSSI TESTO DIGITALE LEGGIBILE')
    cv.drawString(72, 740, 'IDONEITA SPORTIVA NON AGONISTICA - DOCUMENTO DIGITALE')
    cv.save()
    med._ocr_pdf = lambda *a, **k: (_ for _ in ()).throw(AssertionError('OCR called for readable digital PDF'))
    extracted = med.extract_attachment_text('digital.pdf', buf.getvalue())
    assert 'MARIO ROSSI' in extracted.upper(), extracted[:200]

    desktop = (APP / 'asd_app/routes_inbound_documents.py').read_text(encoding='utf-8')
    mobile = (APP / 'asd_app/routes_bodymind_fix49.py').read_text(encoding='utf-8')
    for token in ('Documento riconosciuto', 'Identità atleta riconosciuta', 'Da confermare'):
        assert token in desktop or token in mobile, token

    MARKER.write_text('BodyMind Autopilot R6 applied; synthetic selftests PASS\n', encoding='utf-8')
    print('[autopilot-r6] applied', flush=True)
    print('[autopilot-r6-selftest] PASS exact=92 separate=78 compound=92 compact-ocr=92 ambiguous=safe pdf-digital-first=PASS ocr-pages>=3 ui-separation=PASS', flush=True)
else:
    print('[autopilot-r6] already applied', flush=True)
