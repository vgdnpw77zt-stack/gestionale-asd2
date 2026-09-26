from pathlib import Path
import ast, hashlib, re
APP=Path('/data/top2_app')
FILES=[
 'asd_app/document_classifier.py',
 'asd_app/athlete_matcher.py',
 'asd_app/routes_email_documents.py',
 'asd_app/routes_inbound_documents.py',
 'asd_app/routes_bodymind_fix49.py',
 'asd_app/medical_certificate_dates.py',
]
def redacted_excerpt(s, pattern, radius=420):
    m=re.search(pattern,s,re.I|re.S)
    if not m:return None
    a=max(0,m.start()-radius); b=min(len(s),m.end()+radius)
    out=s[a:b].replace('\n','\\n')
    return out[:1800]
print('[autopilot-diag] begin', flush=True)
for rel in FILES:
    p=APP/rel
    if not p.exists():
        print(f'[autopilot-diag] missing {rel}', flush=True); continue
    raw=p.read_bytes(); s=raw.decode('utf-8','replace')
    print(f'[autopilot-diag] file={rel} sha256={hashlib.sha256(raw).hexdigest()} bytes={len(raw)}', flush=True)
    try:
        tree=ast.parse(s)
        funcs=[]
        for n in tree.body:
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
                args=[a.arg for a in n.args.args]
                funcs.append(f"{n.name}({','.join(args)})")
        print(f'[autopilot-diag] funcs {rel}: '+', '.join(funcs[:80]), flush=True)
    except Exception as e:
        print(f'[autopilot-diag] ast_error {rel}: {type(e).__name__}', flush=True)
    for label,pat in [
      ('confidence45',r'confidence.{0,50}45|45.{0,50}confidence'),
      ('identity92',r'92'),
      ('identity78',r'78'),
      ('decision',r'auto_save|requires?_confirmation|confirm'),
      ('pdftext',r'pypdf|PdfReader|extract_text|ocr_pdf|pdftoppm'),
      ('separation',r'identity_certain|type_certain|associato_tipo_da_verificare'),
    ]:
        ex=redacted_excerpt(s,pat)
        if ex:
            print(f'[autopilot-diag] {rel} {label}: {ex}', flush=True)
print('[autopilot-diag] end', flush=True)
