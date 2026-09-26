from __future__ import annotations
from pathlib import Path
import shutil, compileall

APP = Path('/data/top2_app')
MARKER = APP / '.BODYMIND_AUTOPILOT_R4'
BACKUPS = Path('/data/release_backups/20260926_autopilot_r4')

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

    def patch_classifier(s: str) -> str:
        old = 'cm_filename_hint = bool(re.match(r"^\\s*cm(?:\\s|$)", filename_stem))'
        new = '''# AUTOPILOT R4: i file salvati dal gestionale possono avere timestamp davanti.
    # CM va riconosciuto come token autonomo ovunque nel nome file.
    cm_filename_hint = bool(re.search(r"(?:^|\\s)cm(?:\\s|$)", filename_stem))'''
        if old in s:
            s = s.replace(old, new, 1)
        elif 'AUTOPILOT R4' not in s:
            raise RuntimeError('R4 classifier anchor not found')
        return s
    mutate('asd_app/document_classifier.py', patch_classifier)

    def patch_matcher(s: str) -> str:
        old = '''        for idx, item in enumerate(scored):
            cognome = _norm(_val(item.get("row"), "cognome"))
            if cognome and len(cognome) >= 4 and cognome in file_words:
                surname_to_indexes.setdefault(cognome, []).append(idx)
'''
        new = '''        # AUTOPILOT R4: confronta anche la forma compatta del cognome.
        # D'Angelo / De-Angelis / Di Nicola devono combaciare con DAngelo / DeAngelis / DiNicola.
        file_compact_words = {_compact(w) for w in file_words if w}
        for idx, item in enumerate(scored):
            raw_cognome = _val(item.get("row"), "cognome")
            cognome = _norm(raw_cognome)
            cognome_compact = _compact(raw_cognome)
            matched = (
                (cognome and len(cognome) >= 4 and cognome in file_words) or
                (cognome_compact and len(cognome_compact) >= 5 and cognome_compact in file_compact_words)
            )
            if matched:
                surname_to_indexes.setdefault(cognome_compact or cognome, []).append(idx)
'''
        if old in s:
            s = s.replace(old, new, 1)
        elif 'AUTOPILOT R4' not in s:
            raise RuntimeError('R4 matcher anchor not found')
        return s
    mutate('asd_app/athlete_matcher.py', patch_matcher)

    ok = compileall.compile_dir(str(APP / 'asd_app'), quiet=1)
    if not ok:
        raise RuntimeError('Autopilot R4 compile failed')
    MARKER.write_text('BodyMind Autopilot R4 applied\n', encoding='utf-8')
    print('[autopilot-r4] applied', flush=True)
else:
    print('[autopilot-r4] already applied', flush=True)
