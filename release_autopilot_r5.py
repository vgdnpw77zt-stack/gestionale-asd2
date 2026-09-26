from __future__ import annotations
from pathlib import Path
import ast, hashlib, re

APP = Path('/data/top2_app')
FILES = [
    'asd_app/athlete_matcher.py',
    'asd_app/document_classifier.py',
    'asd_app/routes_email_documents.py',
    'asd_app/medical_certificate_dates.py',
    'asd_app/routes_bodymind_fix49.py',
]
TOKENS = (
    '45', 'confidence', 'match_result', 'auto_save', 'confirm',
    'PdfReader', 'pytesseract', 'ocr', 'max_pages', 'extract_text',
    'document_text', 'filename_stem', 'file_words',
)

print('[autopilot-r5-probe] begin', flush=True)
for rel in FILES:
    p = APP / rel
    if not p.exists():
        print(f'[autopilot-r5-probe] missing {rel}', flush=True)
        continue
    src = p.read_text(encoding='utf-8', errors='replace')
    digest = hashlib.sha256(src.encode('utf-8')).hexdigest()[:16]
    print(f'[autopilot-r5-probe] file={rel} sha256={digest} lines={len(src.splitlines())}', flush=True)
    try:
        tree = ast.parse(src)
        defs=[]
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args=[a.arg for a in node.args.args]
                defs.append(f"{node.name}({','.join(args)})@{node.lineno}")
        print(f"[autopilot-r5-probe] defs {rel}: " + ' | '.join(defs[:80]), flush=True)
    except Exception as exc:
        print(f'[autopilot-r5-probe] ast-error {rel}: {type(exc).__name__}: {exc}', flush=True)

    hits=[]
    for no,line in enumerate(src.splitlines(),1):
        if any(tok.lower() in line.lower() for tok in TOKENS):
            cleaned=re.sub(r'\s+',' ',line.strip())
            if len(cleaned)>260:
                cleaned=cleaned[:257]+'...'
            hits.append(f'{no}:{cleaned}')
    print(f"[autopilot-r5-probe] hits {rel}: " + ' || '.join(hits[:140]), flush=True)
print('[autopilot-r5-probe] end', flush=True)


RANGES = {
    'asd_app/athlete_matcher.py': [(136, 207)],
    'asd_app/routes_email_documents.py': [(167, 235), (381, 473)],
    'asd_app/medical_certificate_dates.py': [(291, 323)],
    'asd_app/document_classifier.py': [(88, 151)],
    'asd_app/routes_inbound_documents.py': [(1, 260)],
}
for rel, ranges in RANGES.items():
    p = APP / rel
    if not p.exists():
        print(f'[autopilot-r5-probe2] missing {rel}', flush=True)
        continue
    lines = p.read_text(encoding='utf-8', errors='replace').splitlines()
    for start,end in ranges:
        chunk=[]
        for no in range(start, min(end, len(lines))+1):
            cleaned=re.sub(r'\s+',' ',lines[no-1].strip())
            if len(cleaned)>300: cleaned=cleaned[:297]+'...'
            chunk.append(f'{no}:{cleaned}')
        print(f"[autopilot-r5-probe2] range {rel} {start}-{end}: " + ' || '.join(chunk), flush=True)
print('[autopilot-r5-probe2] end', flush=True)
